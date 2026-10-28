package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	pb "core/proto"
	"google.golang.org/grpc"
)

type sessionAgent struct {
	pb.PredictorClient
	turns int
}

func planFixture(id string, amount int) map[string]any {
	return map[string]any{"id": id, "total": map[string]any{"amount_minor": amount, "currency": "RUB"}}
}
func (a *sessionAgent) RunTurn(_ context.Context, req *pb.TurnRequest, _ ...grpc.CallOption) (*pb.TurnReply, error) {
	a.turns++
	if req.Message == "fail" {
		return nil, errors.New("model offline")
	}
	var state map[string]any
	_ = json.Unmarshal([]byte(req.StateJson), &state)
	budget := 12000000
	if req.Message == "100" {
		budget = 10000000
	}
	if req.Message == "30" {
		budget = 3000000
	}
	spec := map[string]any{"origin": "Москва", "destination": "Сочи", "budget": map[string]any{"amount_minor": budget, "currency": "RUB"}, "budget_scope": "booking"}
	turn := map[string]any{"status": "choosing", "trip_spec": spec, "assistant_message": "Fixture tool result", "options": []any{planFixture("A", 10900000), planFixture("B", 9700000)}, "questions": []any{}, "destination_options": []any{}, "change_preview": nil, "checkout_allowed": false, "data_mode": "synthetic"}
	if state["selected_plan"] != nil && budget == 10000000 {
		turn["change_preview"] = map[string]any{"baseline_plan_id": "A", "proposed_plan": planFixture("B", 9700000), "based_on_revision": state["revision"]}
	}
	if budget == 3000000 {
		turn["status"] = "no_solution"
		turn["options"] = []any{}
	}
	data, _ := json.Marshal(turn)
	return &pb.TurnReply{Caller: req.Caller, TurnJson: string(data)}, nil
}
func (a *sessionAgent) Evaluate(_ context.Context, req *pb.EvaluateRequest, _ ...grpc.CallOption) (*pb.TurnReply, error) {
	var state map[string]any
	_ = json.Unmarshal([]byte(req.StateJson), &state)
	budget := asMap(asMap(state["trip_spec"])["budget"])["amount_minor"].(float64)
	amount := 10900000
	if req.PlanId == "B" {
		amount = 9700000
	}
	options := []any{}
	if float64(amount) <= budget {
		options = append(options, planFixture(req.PlanId, amount))
	}
	data, _ := json.Marshal(map[string]any{"options": options})
	return &pb.TurnReply{Caller: req.Caller, TurnJson: string(data)}, nil
}
func TestLocalTripLifecycleAndPersistence(t *testing.T) {
	agent := &sessionAgent{}
	api := NewAPI(agent)
	dir := t.TempDir()
	api.trips = &TripStore{dir: dir}
	handler := api.Handler()
	var cookie *http.Cookie
	call := func(method, path string, body any, expected int) map[string]any {
		t.Helper()
		data, _ := json.Marshal(body)
		req := httptest.NewRequest(method, path, strings.NewReader(string(data)))
		if cookie != nil {
			req.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != expected {
			t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
		}
		if len(w.Result().Cookies()) > 0 {
			cookie = w.Result().Cookies()[0]
		}
		var result map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		return result
	}
	snap := call("POST", "/api/sessions/", map[string]any{}, 200)
	path := "/api/sessions/" + snap["session_id"].(string)
	operation := func(kind, message string, rev int, key string, expected int) map[string]any {
		t.Helper()
		body := map[string]any{"expected_revision": rev, "idempotency_key": key}
		suffix := "/actions"
		if kind == "turn" {
			suffix = "/turns"
			body["message"] = message
		} else {
			body["type"] = kind
			if kind == "select_plan" {
				body["plan_id"] = message
			}
		}
		return call("POST", path+suffix, body, expected)
	}
	operation("turn", "full", 0, "initial-turn", 200)
	selected := operation("select_plan", "A", 1, "select-plan-a", 200)
	replay := operation("select_plan", "A", 1, "select-plan-a", 200)
	if selected["revision"] != replay["revision"] || selected["request_id"] != replay["request_id"] {
		t.Fatal("idempotency changed response")
	}
	operation("select_plan", "B", 1, "select-plan-a", 409)
	changed := operation("turn", "100", 2, "budget-first", 200)
	if changed["checkout_allowed"] != false || asMap(changed["selected_plan"])["id"] != "A" {
		t.Fatal("baseline lost or checkout allowed")
	}
	operation("confirm_booking_demo", "", 3, "blocked-booking", 409)
	operation("accept_change", "", 2, "stale-preview", 409)
	noSolution := operation("turn", "30", 3, "budget-second", 200)
	if noSolution["change_preview"] != nil {
		t.Fatal("stale preview survived new turn")
	}
	operation("accept_change", "", 4, "reject-preview", 409)
	operation("turn", "100", 4, "budget-third", 200)
	failed := operation("turn", "fail", 5, "offline-model", 200)
	if failed["change_preview"] != nil || asMap(failed["selected_plan"])["id"] != "A" || asMap(asMap(failed["trip_spec"])["budget"])["amount_minor"] != float64(10000000) {
		t.Fatal("model error corrupted state")
	}
	operation("accept_change", "", 6, "old-after-error", 409)
	operation("turn", "100", 6, "budget-final", 200)
	accepted := operation("accept_change", "", 7, "accept-preview", 200)
	if asMap(accepted["selected_plan"])["id"] != "B" || accepted["checkout_allowed"] != true {
		t.Fatal("failed acceptance")
	}
	booked := operation("confirm_booking_demo", "", 8, "booking-once", 200)
	again := operation("confirm_booking_demo", "", 8, "booking-once", 200)
	if asMap(booked["booking"])["demo_booking_id"] != asMap(again["booking"])["demo_booking_id"] {
		t.Fatal("duplicate booking")
	}
	// Restart Core's store and load the same saved trip.
	api.trips = &TripStore{dir: dir}
	handler = api.Handler()
	restored := call("GET", path, nil, 200)
	if restored["status"] != "booked_demo" {
		t.Fatal("state did not persist")
	}
	cookie = &http.Cookie{Name: "odin_local_owner", Value: randomID()}
	call("GET", path, nil, 404)
}
func TestLocalTripRejectsForeignOrigin(t *testing.T) {
	api := NewAPI(&sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	req := httptest.NewRequest("POST", "/api/sessions/", strings.NewReader("{}"))
	req.Header.Set("Origin", "https://unrelated.example")
	w := httptest.NewRecorder()
	api.Handler().ServeHTTP(w, req)
	if w.Code != 403 {
		t.Fatal(w.Code)
	}
}

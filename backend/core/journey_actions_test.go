package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	pb "core/proto"
	"google.golang.org/grpc"
)

type journeyAgent struct {
	sessionAgent
	fixtures map[string]any
	conflict bool
}

func (a *journeyAgent) Evaluate(_ context.Context, req *pb.EvaluateRequest, _ ...grpc.CallOption) (*pb.TurnReply, error) {
	var state map[string]any
	_ = json.Unmarshal([]byte(req.StateJson), &state)
	key := "original"
	if asMap(asMap(state["trip_spec"])["dates"])["end"] == "2026-11-17" {
		key = "changed"
	}
	h := cloneTrip(asMap(asMap(a.fixtures[key])["hotel"]))
	if req.PlanId == "sample-sochi-2" {
		h["id"], h["name"] = req.PlanId, "Другой отель"
		q := asMap(h["quote"])
		extra := float64(100000)
		q["nightly_minor"] = q["nightly_minor"].(float64) + extra
		delta := extra * q["nights"].(float64)
		q["total_minor"] = q["total_minor"].(float64) + delta
		j := asMap(h["journey"])
		breakdown := asMap(j["breakdown"])
		breakdown["hotel"] = breakdown["hotel"].(float64) + delta
		j["total_minor"] = j["total_minor"].(float64) + delta
	}
	if a.conflict {
		asMap(h["journey"])["checks"] = []any{map[string]any{"code": "checkin", "blocking": true, "status": "fail", "message": "Позднее прибытие: стойка закрыта."}}
	}
	data, _ := json.Marshal(map[string]any{"hotel_options": []any{h}})
	return &pb.TurnReply{Caller: req.Caller, TurnJson: string(data)}, nil
}

func TestWholeJourneyPreviewConflictAndPersistence(t *testing.T) {
	raw, err := os.ReadFile("testdata/journey-quotes.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	agent := &journeyAgent{fixtures: fixtures}
	api := NewAPI("", &http.Client{}, agent)
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	var cookie *http.Cookie
	call := func(method, path string, body any, code int) map[string]any {
		t.Helper()
		raw, _ := json.Marshal(body)
		req := httptest.NewRequest(method, path, strings.NewReader(string(raw)))
		if cookie != nil {
			req.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != code {
			t.Fatalf("%s %d: %s", path, w.Code, w.Body.String())
		}
		if len(w.Result().Cookies()) > 0 {
			cookie = w.Result().Cookies()[0]
		}
		var out map[string]any
		_ = json.Unmarshal(w.Body.Bytes(), &out)
		return out
	}
	initial := call("POST", "/api/sessions/", map[string]any{"search_mode": "hotels"}, 200)
	id := initial["session_id"].(string)
	path := "/api/sessions/" + id
	file, _ := api.trips.read(id, hashText(cookie.Value))
	a := asMap(fixtures["original"])
	file.Snapshot["trip_spec"], file.Snapshot["hotel_options"], file.Snapshot["status"] = a["spec"], []any{a["hotel"]}, "choosing"
	_ = api.trips.save(id, file)
	action := func(kind string, revision int, key string, extra map[string]any, code int) map[string]any {
		t.Helper()
		body := map[string]any{"type": kind, "expected_revision": revision, "idempotency_key": key}
		for k, v := range extra {
			body[k] = v
		}
		return call("POST", path+"/actions", body, code)
	}
	action("select_hotel", 0, "invented-id", map[string]any{"hotel_id": "invented"}, 409)
	selected := action("select_hotel", 0, "select-journey", map[string]any{"hotel_id": "sample-sochi-1"}, 200)
	old := journeyTotal(asMap(selected["selected_hotel"]))
	preview := action("update_hotel_stay", 1, "edit-journey", map[string]any{"stay": map[string]any{"check_in": "2026-11-10", "check_out": "2026-11-17", "adults": 2, "children": []int{}}}, 200)
	p := asMap(preview["journey_preview"])
	if p == nil || journeyTotal(asMap(p["previous_hotel"])) != old || journeyTotal(asMap(p["proposed_hotel"])) <= old {
		t.Fatal("missing full-trip preview", preview)
	}
	fields := map[string]any{"guest_name": "Тестовый Гость", "check_in": "2026-11-10", "confirm_prototype": true, "accept_budget_overrun": true}
	action("confirm_hotel_booking", 2, "cannot-book-preview", fields, 409)
	accepted := action("accept_journey_change", 2, "accept-preview", nil, 200)
	if asMap(asMap(accepted["trip_spec"])["dates"])["end"] != "2026-11-17" {
		t.Fatal("dates lost")
	}
	agent.conflict = true
	action("confirm_hotel_booking", 3, "conflict-not-budget", fields, 409)
	agent.conflict = false
	booked := action("confirm_hotel_booking", 3, "book-journey-once", fields, 200)
	replay := action("confirm_hotel_booking", 3, "book-journey-once", fields, 200)
	booking := asMap(booked["hotel_booking"])
	if booking["id"] != asMap(replay["hotel_booking"])["id"] {
		t.Fatal("duplicate booking")
	}
	saved := asMap(booking["hotel"])
	if journeyTotal(saved) <= old || len(asList(asMap(saved["journey"])["segments"])) != 4 {
		t.Fatal("incomplete booking")
	}
	restored := call("GET", path, nil, 200)
	if asMap(restored["hotel_booking"])["id"] != booking["id"] {
		t.Fatal("lost booking")
	}
}

func TestJourneyHotelSwitchRetainsRepricedShortlist(t *testing.T) {
	raw, err := os.ReadFile("testdata/journey-quotes.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	agent := &journeyAgent{fixtures: fixtures}
	api := NewAPI("", &http.Client{}, agent)
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	var cookie *http.Cookie
	var current map[string]any
	call := func(method, path string, body any) map[string]any {
		t.Helper()
		data, _ := json.Marshal(body)
		req := httptest.NewRequest(method, path, strings.NewReader(string(data)))
		if cookie != nil {
			req.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != 200 {
			t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
		}
		if len(w.Result().Cookies()) > 0 {
			cookie = w.Result().Cookies()[0]
		}
		var result map[string]any
		_ = json.Unmarshal(w.Body.Bytes(), &result)
		return result
	}
	current = call("POST", "/api/sessions/", map[string]any{"search_mode": "hotels"})
	id := current["session_id"].(string)
	path := "/api/sessions/" + id
	file, _ := api.trips.read(id, hashText(cookie.Value))
	original := asMap(fixtures["original"])
	seed, _ := json.Marshal(map[string]any{"trip_spec": original["spec"]})
	reply, _ := agent.Evaluate(context.Background(), &pb.EvaluateRequest{StateJson: string(seed), PlanId: "sample-sochi-2"})
	var secondResult map[string]any
	_ = json.Unmarshal([]byte(reply.TurnJson), &secondResult)
	second := asList(secondResult["hotel_options"])[0]
	file.Snapshot["trip_spec"], file.Snapshot["hotel_options"], file.Snapshot["status"] = original["spec"], []any{original["hotel"], second}, "choosing"
	_ = api.trips.save(id, file)
	serial := 0
	action := func(kind string, extra map[string]any) {
		t.Helper()
		serial++
		body := map[string]any{"type": kind, "expected_revision": current["revision"], "idempotency_key": fmt.Sprintf("switch-%d", serial)}
		for k, v := range extra {
			body[k] = v
		}
		current = call("POST", path+"/actions", body)
	}
	checkOptions := func(nights float64) {
		t.Helper()
		options := asList(current["hotel_options"])
		if len(options) != 2 {
			t.Fatalf("lost shortlist: %v", options)
		}
		fixture := "original"
		if nights == 7 {
			fixture = "changed"
		}
		for _, item := range options {
			h := asMap(item)
			if asMap(h["quote"])["nights"] != nights {
				t.Fatalf("stale alternative: %v", item)
			}
			expected := journeyTotal(asMap(asMap(fixtures[fixture])["hotel"]))
			if h["id"] == "sample-sochi-2" {
				expected += 100000 * nights
			}
			if journeyTotal(h) != expected {
				t.Fatalf("stale shortlist total: got %v want %v", journeyTotal(h), expected)
			}
		}
	}
	action("select_hotel", map[string]any{"hotel_id": "sample-sochi-1"})
	checkOptions(5)
	oldTotal := journeyTotal(asMap(current["selected_hotel"]))
	stay := map[string]any{"stay": map[string]any{"check_in": "2026-11-10", "check_out": "2026-11-17", "adults": 2, "children": []int{}}}
	action("update_hotel_stay", stay)
	action("discard_journey_change", nil)
	checkOptions(5)
	if journeyTotal(asMap(current["selected_hotel"])) != oldTotal {
		t.Fatal("discard lost original price")
	}
	action("update_hotel_stay", stay)
	action("accept_journey_change", nil)
	checkOptions(7)
	firstTotal := journeyTotal(asMap(current["selected_hotel"]))
	spec := cloneTrip(asMap(current["trip_spec"]))
	action("clear_hotel_selection", nil)
	checkOptions(7)
	action("select_hotel", map[string]any{"hotel_id": "sample-sochi-2"})
	checkOptions(7)
	chosen := asMap(current["selected_hotel"])
	if chosen["id"] != "sample-sochi-2" || journeyTotal(chosen) <= firstTotal {
		t.Fatal("wrong hotel price", chosen)
	}
	if !sameJourneySpec(spec, asMap(current["trip_spec"])) {
		t.Fatal("switch reset dates or guests")
	}
	current = call("GET", path, nil)
	checkOptions(7)
	action("clear_hotel_selection", nil)
	action("select_hotel", map[string]any{"hotel_id": "sample-sochi-1"})
	if journeyTotal(asMap(current["selected_hotel"])) != firstTotal {
		t.Fatal("return used other hotel's price")
	}
	action("clear_hotel_selection", nil)
	action("select_hotel", map[string]any{"hotel_id": "sample-sochi-2"})
	action("confirm_hotel_booking", map[string]any{"guest_name": "Тестовый Гость", "check_in": "2026-11-10", "confirm_prototype": true, "accept_budget_overrun": true})
	current = call("GET", path, nil)
	booking := asMap(current["hotel_booking"])
	if asMap(booking["hotel"])["id"] != chosen["id"] || journeyTotal(asMap(booking["hotel"])) != journeyTotal(chosen) {
		t.Fatal("booking persisted previous hotel", booking)
	}
	if !sameJourneySpec(asMap(booking["travellers"]), asMap(spec["travellers"])) {
		t.Fatal("booking lost guests")
	}
}

func TestDiscardTransportAdditionRestoresHotelOnly(t *testing.T) {
	raw, err := os.ReadFile("testdata/journey-quotes.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	api := NewAPI("", &http.Client{}, &journeyAgent{fixtures: fixtures})
	original := asMap(fixtures["original"])
	hotel := cloneTrip(asMap(original["hotel"]))
	delete(hotel, "journey")
	spec := cloneTrip(asMap(original["spec"]))
	spec["include_transport"], spec["budget_scope"] = false, "hotel"
	snap := map[string]any{"trip_spec": spec, "hotel_options": []any{hotel}, "selected_hotel": hotel, "status": "hotel_checkout"}
	before := cloneTrip(snap)
	if message := api.changeTransport(context.Background(), snap, "sample-sochi-1", &TransportEdit{Mode: "train"}, "owner"); message != "" {
		t.Fatal(message)
	}
	preview := asMap(snap["journey_preview"])
	if asMap(preview["previous_hotel"])["journey"] != nil {
		t.Fatal("hotel-only baseline acquired a fake route")
	}
	expected := journeyTotal(asMap(preview["proposed_hotel"])) - hotelPlanTotal(hotel)
	if preview["price_delta"] != expected {
		t.Fatalf("wrong extra cost: %v want %v", preview["price_delta"], expected)
	}
	if message := applyJourneyPreview(snap, false); message != "" {
		t.Fatal(message)
	}
	if !sameJourneySpec(asMap(snap["selected_hotel"]), asMap(before["selected_hotel"])) || !sameJourneySpec(asMap(snap["trip_spec"]), spec) {
		t.Fatal("discard changed hotel or conditions")
	}
	if !sameJourneySpec(asMap(asList(snap["hotel_options"])[0]), hotel) {
		t.Fatal("discard changed shortlist")
	}
	if message := hotelAction(snap, "confirm_hotel_booking", "", "2026-11-10", "Тестовый Гость", true); message != "" {
		t.Fatal(message)
	}
	if asMap(asMap(snap["hotel_booking"])["hotel"])["journey"] != nil {
		t.Fatal("booking saved cancelled route")
	}
}

func TestDemoJourneySupplierConfirmation(t *testing.T) {
	for _, code := range []string{"children", "pets", "cancellation", "other", "no_connections", "no_night_travel", "owned_price", "dates", "budget"} {
		for _, status := range []string{"unknown", "fail"} {
			t.Run(code+"/"+status, func(t *testing.T) {
				h := map[string]any{"journey": map[string]any{"checks": []any{map[string]any{"code": code, "status": status, "blocking": true, "message": "Needs attention"}}}}
				allowed := status == "unknown" && code != "owned_price" && code != "dates" && code != "budget"
				if got := journeyBlock(h, false); (got == "") != allowed {
					t.Fatalf("allowed=%v, got %q", allowed, got)
				}
			})
		}
	}
}

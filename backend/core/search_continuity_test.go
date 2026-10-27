package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	pb "core/proto"
	"google.golang.org/grpc"
)

type continuityAgent struct {
	journeyAgent
	hotelOnly bool
}

func (a *continuityAgent) RunTurn(_ context.Context, req *pb.TurnRequest, _ ...grpc.CallOption) (*pb.TurnReply, error) {
	if req.Message == "error" {
		return nil, errors.New("temporary outage")
	}
	var state map[string]any
	_ = json.Unmarshal([]byte(req.StateJson), &state)
	spec := cloneTrip(asMap(state["trip_spec"]))
	travellers := asMap(spec["travellers"])
	travellers["children"] = []any{nil}
	result := map[string]any{"status": req.Message, "trip_spec": spec, "hotel_options": []any{}, "questions": []any{"Сколько лет ребёнку?"}, "assistant_message": "Уточните возраст ребёнка.", "selection": map[string]any{}}
	if req.Message == "age" {
		if asMap(state["selected_hotel"]) == nil {
			return nil, errors.New("selected hotel was lost before follow-up")
		}
		travellers["children"] = []any{float64(5)}
		h := cloneTrip(asMap(asMap(a.fixtures["changed"])["hotel"]))
		if a.hotelOnly {
			delete(h, "journey")
		}
		result["hotel_options"], result["status"] = []any{h}, "choosing"
	}
	data, _ := json.Marshal(result)
	return &pb.TurnReply{Caller: req.Caller, TurnJson: string(data)}, nil
}

func TestHotelSearchSurvivesClarificationFailureAndReload(t *testing.T) {
	raw, err := os.ReadFile("testdata/journey-quotes.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	for _, hotelOnly := range []bool{false, true} {
		for _, selected := range []bool{false, true} {
			for _, outcome := range []string{"needs_input", "no_solution", "error"} {
				t.Run(fmt.Sprintf("hotelOnly=%v/selected=%v/%s", hotelOnly, selected, outcome), func(t *testing.T) {
					agent := &continuityAgent{journeyAgent: journeyAgent{fixtures: fixtures}, hotelOnly: hotelOnly}
					api := NewAPI("", &http.Client{}, agent)
					api.trips = &TripStore{dir: t.TempDir()}
					handler := api.Handler()
					var cookie *http.Cookie
					call := func(method, path string, body any, code int) map[string]any {
						t.Helper()
						data, _ := json.Marshal(body)
						r := httptest.NewRequest(method, path, strings.NewReader(string(data)))
						if cookie != nil {
							r.AddCookie(cookie)
						}
						w := httptest.NewRecorder()
						handler.ServeHTTP(w, r)
						if w.Code != code {
							t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
						}
						if len(w.Result().Cookies()) > 0 {
							cookie = w.Result().Cookies()[0]
						}
						var out map[string]any
						_ = json.Unmarshal(w.Body.Bytes(), &out)
						return out
					}
					initial := call("POST", "/api/sessions/", map[string]any{"search_mode": "hotels"}, 200)
					id := stringValue(initial["session_id"])
					path := "/api/sessions/" + id
					file, _ := api.trips.read(id, hashText(cookie.Value))
					fixture := cloneTrip(asMap(fixtures["original"]))
					h := asMap(fixture["hotel"])
					spec := asMap(fixture["spec"])
					if hotelOnly {
						delete(h, "journey")
						spec["include_transport"] = false
						spec["budget_scope"] = "hotel"
					}
					file.Snapshot["trip_spec"], file.Snapshot["hotel_options"], file.Snapshot["status"] = spec, []any{h}, "choosing"
					if selected {
						file.Snapshot["selected_hotel"], file.Snapshot["status"] = h, "hotel_checkout"
					}
					if err := api.trips.save(id, file); err != nil {
						t.Fatal(err)
					}
					turn := func(message string, rev int) map[string]any {
						return call("POST", path+"/turns", map[string]any{"message": message, "expected_revision": rev, "idempotency_key": fmt.Sprintf("turn-key-%d", rev)}, 200)
					}
					snap := turn(outcome, 0)
					if snap["status"] != outcome || asMap(snap["journey_recovery"]) == nil || len(asList(snap["hotel_options"])) != 1 {
						t.Fatalf("lost recovery: %v", snap)
					}
					if selected && asMap(snap["selected_hotel"])["id"] != h["id"] {
						t.Fatal("selected hotel lost")
					}
					if !sameJourneySpec(asMap(asMap(snap["journey_recovery"])["spec"]), spec) {
						t.Fatal("baseline criteria overwritten")
					}
					reloaded := call("GET", path, nil, 200)
					if asMap(reloaded["journey_recovery"]) == nil {
						t.Fatal("recovery not persisted")
					}
					call("POST", path+"/actions", map[string]any{"type": "select_hotel", "hotel_id": h["id"], "expected_revision": 1, "idempotency_key": "reject-stale-price"}, 409)
					call("POST", path+"/actions", map[string]any{"type": "confirm_hotel_booking", "expected_revision": 1, "idempotency_key": "reject-stale-booking"}, 409)
					if selected && outcome == "needs_input" {
						snap = turn("error", 1)
						if !sameJourneySpec(asMap(asMap(snap["journey_recovery"])["spec"]), spec) {
							t.Fatal("retry replaced recovery baseline")
						}
						snap = turn("age", 2)
						preview := asMap(snap["journey_preview"])
						if preview == nil || asMap(preview["proposed_hotel"])["id"] != h["id"] {
							t.Fatal("follow-up lost chosen hotel")
						}
						snap = call("POST", path+"/actions", map[string]any{"type": "accept_journey_change", "expected_revision": 3, "idempotency_key": "accept-new-family"}, 200)
						if snap["status"] != "hotel_checkout" || asMap(snap["selected_hotel"])["id"] != h["id"] || snap["journey_recovery"] != nil {
							t.Fatal("updated choice not restored")
						}
						if len(asList(asMap(asMap(snap["trip_spec"])["travellers"])["children"])) != 1 {
							t.Fatal("new family lost")
						}
					} else {
						snap = call("POST", path+"/actions", map[string]any{"type": "restore_journey", "expected_revision": 1, "idempotency_key": "restore-old-search"}, 200)
						wanted := "choosing"
						if selected {
							wanted = "hotel_checkout"
						}
						if snap["status"] != wanted || !sameJourneySpec(asMap(snap["trip_spec"]), spec) || snap["journey_recovery"] != nil {
							t.Fatal("restore lost previous conditions")
						}
					}
				})
			}
		}
	}
}

type unavailableAlternativeAgent struct{ journeyAgent }

func (a *unavailableAlternativeAgent) Evaluate(ctx context.Context, req *pb.EvaluateRequest, opts ...grpc.CallOption) (*pb.TurnReply, error) {
	if req.PlanId == "unavailable-alternative" {
		return nil, errors.New("provider unavailable")
	}
	return a.journeyAgent.Evaluate(ctx, req, opts...)
}
func TestUnavailableAlternativeCannotCancelSelectedHotelEdit(t *testing.T) {
	raw, err := os.ReadFile("testdata/journey-quotes.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	selected := asMap(asMap(fixtures["changed"])["hotel"])
	agent := &unavailableAlternativeAgent{journeyAgent{fixtures: fixtures}}
	api := NewAPI("", &http.Client{}, agent)
	snap := map[string]any{"trip_spec": asMap(fixtures["changed"])["spec"], "hotel_options": []any{selected, map[string]any{"id": "unavailable-alternative"}}}
	if err := api.refreshJourneyOptions(context.Background(), snap, selected, "test-owner"); err != nil {
		t.Fatal(err)
	}
	if len(asList(snap["hotel_options"])) != 1 || asMap(asList(snap["hotel_options"])[0])["id"] != selected["id"] {
		t.Fatal("selected hotel lost or stale alternative retained")
	}
}

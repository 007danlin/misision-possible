package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestOwnedTicketsCompleteRecoveryAndPreserveRollback(t *testing.T) {
	raw, err := os.ReadFile("testdata/journey-quotes.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixtures map[string]any
	if err := json.Unmarshal(raw, &fixtures); err != nil {
		t.Fatal(err)
	}
	agent := &transportAgent{journeyAgent: journeyAgent{fixtures: fixtures}}
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
		if err := json.Unmarshal(w.Body.Bytes(), &out); err != nil {
			t.Fatal(err)
		}
		return out
	}
	initial := call("POST", "/api/sessions/", map[string]any{"search_mode": "hotels"}, 200)
	id := stringValue(initial["session_id"])
	path := "/api/sessions/" + id
	file, err := api.trips.read(id, hashText(cookie.Value))
	if err != nil {
		t.Fatal(err)
	}
	original := cloneTrip(asMap(fixtures["original"]))
	hotel := asMap(original["hotel"])
	spec := asMap(original["spec"])
	pending := cloneTrip(spec)
	pending["transport_owned"] = true
	file.Snapshot["trip_spec"], file.Snapshot["selected_hotel"], file.Snapshot["hotel_options"] = pending, hotel, []any{hotel}
	file.Snapshot["status"] = "needs_input"
	file.Snapshot["journey_recovery"] = map[string]any{"hotel": hotel, "spec": spec, "previous_options": []any{hotel}}
	if err := api.trips.save(id, file); err != nil {
		t.Fatal(err)
	}
	call("POST", path+"/actions", map[string]any{"type": "change_transport", "transport": map[string]any{"mode": "train"}, "expected_revision": 0, "idempotency_key": "blocked-mode"}, 409)
	call("POST", path+"/actions", map[string]any{"type": "confirm_hotel_booking", "expected_revision": 0, "idempotency_key": "blocked-booking"}, 409)
	paid := int64(2200000)
	tickets := &OwnedTickets{Arrival: "2026-11-10T12:00:00+03:00", Departure: "2026-11-15T18:00:00+03:00", Terminal: "airport", PaidTotalMinor: &paid}
	snap := call("POST", path+"/actions", map[string]any{"type": "change_transport", "transport": &TransportEdit{Tickets: tickets}, "expected_revision": 0, "idempotency_key": "complete-tickets"}, 200)
	preview := asMap(snap["journey_preview"])
	if preview == nil || snap["journey_recovery"] != nil {
		t.Fatal("ticket form did not resolve recovery")
	}
	if !sameJourneySpec(spec, asMap(preview["previous_spec"])) {
		t.Fatal("rollback baseline replaced by pending request")
	}
	if asMap(preview["proposed_spec"])["transport_owned"] != true || asMap(preview["proposed_hotel"])["id"] != hotel["id"] {
		t.Fatal("tickets or selected hotel lost")
	}
	if journeyTotal(asMap(preview["proposed_hotel"])) == journeyTotal(hotel) {
		t.Fatal("price not recomputed")
	}
	snap = call("POST", path+"/actions", map[string]any{"type": "discard_journey_change", "expected_revision": 1, "idempotency_key": "discard-tickets"}, 200)
	if !sameJourneySpec(spec, asMap(snap["trip_spec"])) {
		t.Fatal("discard did not restore previous conditions")
	}
}

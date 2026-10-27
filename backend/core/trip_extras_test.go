package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestExtrasAfterBookingSharePrivacyAndRevocation(t *testing.T) {
	raw, _ := os.ReadFile("testdata/journey-quotes.json")
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	a := &journeyAgent{fixtures: fixtures}
	api := NewAPI("", &http.Client{}, a)
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	var cookie *http.Cookie
	call := func(method, path string, body any, code int, owner bool) map[string]any {
		t.Helper()
		raw, _ := json.Marshal(body)
		r := httptest.NewRequest(method, path, strings.NewReader(string(raw)))
		if owner && cookie != nil {
			r.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != code {
			t.Fatalf("%s %d: %s", path, w.Code, w.Body.String())
		}
		if owner && len(w.Result().Cookies()) > 0 {
			cookie = w.Result().Cookies()[0]
		}
		var out map[string]any
		_ = json.Unmarshal(w.Body.Bytes(), &out)
		return out
	}
	initial := call("POST", "/api/sessions/", map[string]any{"search_mode": "hotels"}, 200, true)
	id := stringValue(initial["session_id"])
	path := "/api/sessions/" + id
	f, _ := api.trips.read(id, hashText(cookie.Value))
	original := asMap(fixtures["original"])
	hotel := cloneTrip(asMap(original["hotel"]))
	delete(hotel, "journey")
	f.Snapshot["trip_spec"] = cloneTrip(asMap(original["spec"]))
	asMap(f.Snapshot["trip_spec"])["include_transport"] = false
	asMap(f.Snapshot["trip_spec"])["budget_scope"] = "hotel"
	f.Snapshot["hotel_booking"] = map[string]any{"id": "booking", "hotel": hotel, "guest_name": "PRIVATE_GUEST", "dates": asMap(original["spec"])["dates"], "travellers": asMap(original["spec"])["travellers"]}
	f.Snapshot["messages"] = []any{map[string]any{"text": "PRIVATE_CHAT"}}
	f.Snapshot["status"] = "hotel_booked"
	_ = api.trips.save(id, f)
	revision := 0
	action := func(kind, key string, extra map[string]any, code int) map[string]any {
		t.Helper()
		body := map[string]any{"type": kind, "expected_revision": revision, "idempotency_key": key}
		for k, v := range extra {
			body[k] = v
		}
		out := call("POST", path+"/actions", body, code, true)
		if code == 200 {
			revision++
		}
		return out
	}
	action("save_early_request", "bad-time-key", map[string]any{"request_time": "25:00"}, 409)
	early := action("save_early_request", "good-time-key", map[string]any{"request_time": "10:30"}, 200)
	if asMap(asMap(early["hotel_booking"])["early_checkin_request"])["status"] != "draft" {
		t.Fatal("request must remain a draft")
	}
	proposal := action("quote_transfer_addon", "addon-preview", nil, 200)
	if proposal["transfer_addon_preview"] == nil || asMap(asMap(proposal["hotel_booking"])["hotel"])["transfer_addon"] != nil {
		t.Fatal("preview must not change saved price")
	}
	accepted := action("accept_transfer_addon", "addon-accept", nil, 200)
	if asMap(asMap(accepted["hotel_booking"])["hotel"])["transfer_addon"] == nil {
		t.Fatal("addon missing")
	}
	action("quote_transfer_addon", "addon-double", nil, 409)
	share := action("create_share", "share-create", nil, 200)
	token := id + "-" + stringValue(asMap(share["share"])["token"])
	public := call("GET", "/api/shared/"+token, nil, 200, false)
	encoded, _ := json.Marshal(public)
	if strings.Contains(string(encoded), "PRIVATE_") {
		t.Fatal("private information leaked")
	}
	call("POST", "/api/shared/"+token, map[string]any{"hotel_id": "invented"}, 400, false)
	voted := call("POST", "/api/shared/"+token, map[string]any{"hotel_id": hotel["id"]}, 200, false)
	if asMap(voted["votes"])[stringValue(hotel["id"])] != float64(1) {
		t.Fatal("vote not recorded")
	}
	action("revoke_share", "share-revoke", nil, 200)
	call("GET", "/api/shared/"+token, nil, 404, false)
	call("GET", path, nil, 404, false)
}
func TestTransferConflictBlocksAddon(t *testing.T) {
	raw, _ := os.ReadFile("testdata/journey-quotes.json")
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	a := &journeyAgent{fixtures: fixtures, conflict: true}
	api := NewAPI("", &http.Client{}, a)
	v := asMap(fixtures["original"])
	h := cloneTrip(asMap(v["hotel"]))
	delete(h, "journey")
	s := map[string]any{"search_mode": "hotels", "revision": float64(1), "trip_spec": v["spec"], "hotel_booking": map[string]any{"hotel": h, "dates": asMap(v["spec"])["dates"], "travellers": asMap(v["spec"])["travellers"]}}
	if api.tripExtra(context.Background(), s, "quote_transfer_addon", "", "owner") == "" {
		t.Fatal("invalid connection accepted")
	}
	if s["transfer_addon_preview"] != nil {
		t.Fatal("conflicting addon exposed")
	}
}

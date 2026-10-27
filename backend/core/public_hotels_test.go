package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPublicHotelsCannotUseDemoBookingActions(t *testing.T) {
	api := NewAPI("", &http.Client{}, &sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	create := httptest.NewRequest("POST", "/api/sessions/", strings.NewReader(`{"search_mode":"hotels"}`))
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, create)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	var snap map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &snap); err != nil {
		t.Fatal(err)
	}
	if snap["search_mode"] != "hotels" || snap["data_mode"] != "public_catalogue" {
		t.Fatal("public mode lost", snap)
	}
	var state map[string]any
	if err := json.Unmarshal([]byte(stateFor(snap)), &state); err != nil {
		t.Fatal(err)
	}
	if state["search_mode"] != "hotels" {
		t.Fatal("agent did not receive hotel mode")
	}
	for _, action := range []string{"select_plan", "select_destination", "accept_change", "confirm_booking_demo"} {
		req := httptest.NewRequest("POST", "/api/sessions/"+snap["session_id"].(string)+"/actions", strings.NewReader(`{"type":"`+action+`","expected_revision":0,"idempotency_key":"public-mode-test"}`))
		req.AddCookie(w.Result().Cookies()[0])
		reply := httptest.NewRecorder()
		handler.ServeHTTP(reply, req)
		if reply.Code != 409 {
			t.Fatalf("%s must be unavailable: %d %s", action, reply.Code, reply.Body.String())
		}
	}
}

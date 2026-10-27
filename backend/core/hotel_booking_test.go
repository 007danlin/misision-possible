package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHotelCheckoutPersistenceAndIdempotency(t *testing.T) {
	api := NewAPI("", &http.Client{}, &sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	var cookie *http.Cookie
	call := func(method, path string, body any, status int) map[string]any {
		t.Helper()
		raw, _ := json.Marshal(body)
		req := httptest.NewRequest(method, path, strings.NewReader(string(raw)))
		if cookie != nil {
			req.AddCookie(cookie)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != status {
			t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
		}
		if len(w.Result().Cookies()) > 0 {
			cookie = w.Result().Cookies()[0]
		}
		var result map[string]any
		_ = json.Unmarshal(w.Body.Bytes(), &result)
		return result
	}
	snap := call("POST", "/api/sessions/", map[string]any{"search_mode": "hotels"}, 200)
	id := snap["session_id"].(string)
	path := "/api/sessions/" + id
	file, _ := api.trips.read(id, hashText(cookie.Value))
	file.Snapshot["status"] = "choosing"
	file.Snapshot["trip_spec"] = map[string]any{"travellers": map[string]any{"adults": 2}}
	file.Snapshot["hotel_options"] = []any{map[string]any{"id": "hotel-a", "name": "Hotel A", "quote": map[string]any{"source_kind": "demo", "currency": "RUB", "nightly_minor": 500000, "nights": 3, "total_minor": 1500000, "rooms": 1}}}
	if err := api.trips.save(id, file); err != nil {
		t.Fatal(err)
	}
	action := func(kind string, rev int, key string, extra map[string]any, code int) map[string]any {
		body := map[string]any{"type": kind, "expected_revision": rev, "idempotency_key": key}
		for k, v := range extra {
			body[k] = v
		}
		return call("POST", path+"/actions", body, code)
	}
	action("select_hotel", 0, "bad-hotel-id", map[string]any{"hotel_id": "invented"}, 409)
	selected := action("select_hotel", 0, "select-hotel", map[string]any{"hotel_id": "hotel-a"}, 200)
	if selected["status"] != "hotel_checkout" {
		t.Fatal(selected)
	}
	date := time.Now().AddDate(0, 0, 5).Format("2006-01-02")
	fields := map[string]any{"guest_name": "Гость Тестовый", "check_in": date, "confirm_prototype": false}
	action("confirm_hotel_booking", 1, "no-confirmation", fields, 409)
	fields["confirm_prototype"] = true
	fields["check_in"] = "2020-01-01"
	action("confirm_hotel_booking", 1, "past-date-invalid", fields, 409)
	fields["check_in"] = date
	action("confirm_hotel_booking", 0, "stale-confirmation", fields, 409)
	booked := action("confirm_hotel_booking", 1, "book-hotel-once", fields, 200)
	replay := action("confirm_hotel_booking", 1, "book-hotel-once", fields, 200)
	b := asMap(booked["hotel_booking"])
	if b["id"] != asMap(replay["hotel_booking"])["id"] || booked["revision"] != replay["revision"] {
		t.Fatal("duplicate booking")
	}
	if asMap(b["quote"])["total_minor"] != float64(1500000) || b["is_demo"] != true {
		t.Fatal("quote changed", b)
	}
	restored := call("GET", path, nil, 200)
	if asMap(restored["hotel_booking"])["id"] != b["id"] {
		t.Fatal("not persisted")
	}
	call("POST", path+"/turns", map[string]any{"message": "new", "expected_revision": 2, "idempotency_key": "after-booking"}, 409)
	cookie = nil
	call("GET", path, nil, 404)
	call("GET", path+"/progress?key=select-hotel", nil, 404)
}

func TestHotelSelectionRetainedButCheckoutInvalidatedOnFailedTurn(t *testing.T) {
	api := NewAPI("", &http.Client{}, &sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	owner := strings.Repeat("a", 32)
	id := randomID()
	file := &tripFile{Owner: hashText(owner), Operations: map[string]savedOperation{}, Snapshot: map[string]any{"revision": 0, "search_mode": "hotels", "trip_spec": map[string]any{}, "selected_hotel": map[string]any{"id": "old"}, "status": "hotel_checkout"}}
	_ = api.trips.save(id, file)
	req := httptest.NewRequest("POST", "/api/sessions/"+id+"/turns", strings.NewReader(`{"message":"fail","expected_revision":0,"idempotency_key":"invalidate-on-failure"}`))
	req.AddCookie(&http.Cookie{Name: "odin_local_owner", Value: owner})
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)
	file, _ = api.trips.read(id, hashText(owner))
	if asMap(file.Snapshot["selected_hotel"])["id"] != "old" || asMap(file.Snapshot["journey_recovery"]) == nil {
		t.Fatal("previous choice was lost")
	}
	if file.Snapshot["status"] != "error" || file.Snapshot["checkout_allowed"] == true {
		t.Fatal("stale quote is still eligible for checkout")
	}
}

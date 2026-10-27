package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestStayEditCountsAllChildrenAndBothDates(t *testing.T) {
	var snap map[string]any
	json.Unmarshal([]byte(`{"status":"hotel_checkout","trip_spec":{"budget":{"amount_minor":2000000}},"selected_hotel":{"id":"h","quote":{"source_kind":"demo","currency":"RUB","base_room_nightly_minor":200000,"nightly_minor":200000,"total_minor":1000000,"nights":5,"rooms":1}},"hotel_options":[{"id":"h","reasons":["В вашем бюджете","Бассейн"],"quote":{"source_kind":"demo","currency":"RUB","base_room_nightly_minor":200000,"nightly_minor":200000,"total_minor":1000000,"nights":5,"rooms":1}}]}`), &snap)
	ages := []*int{}
	for i := 3; i < 8; i++ {
		n := i
		ages = append(ages, &n)
	}
	start := time.Now().AddDate(0, 0, 5)
	end := start.AddDate(0, 0, 6)
	edit := &HotelStayEdit{CheckIn: start.Format("2006-01-02"), CheckOut: end.Format("2006-01-02"), Adults: 2, Children: ages}
	if e := updateHotelStay(snap, edit); e != "" {
		t.Fatal(e)
	}
	q := asMap(asMap(snap["selected_hotel"])["quote"])
	if q["rooms"] != float64(4) || q["total_minor"] != float64(4800000) || q["nights"] != float64(6) {
		t.Fatal(q)
	}
	if len(asList(asMap(asMap(snap["trip_spec"])["travellers"])["children"])) != 5 {
		t.Fatal(snap)
	}
	if asMap(asMap(snap["trip_spec"])["dates"])["end"] != edit.CheckOut || !hotelBudgetExceeded(snap) {
		t.Fatal(snap)
	}
	edit.CheckOut = edit.CheckIn
	if updateHotelStay(snap, edit) == "" {
		t.Fatal("accepted zero nights")
	}
	edit.CheckOut = end.Format("2006-01-02")
	edit.Children[0] = nil
	if updateHotelStay(snap, edit) == "" {
		t.Fatal("accepted unknown age")
	}
}
func TestHistoryIsOwnerScoped(t *testing.T) {
	s := &TripStore{dir: t.TempDir()}
	owner := strings.Repeat("a", 32)
	own := randomID()
	other := randomID()
	for _, id := range []string{own, other} {
		o := hashText(owner)
		if id == other {
			o = hashText("different")
		}
		s.save(id, &tripFile{Owner: o, Snapshot: map[string]any{"session_id": id, "revision": 1, "search_mode": "hotels", "search_title": "Хочу в лес", "status": "choosing"}})
	}
	for _, withCookie := range []bool{false, true} {
		r := httptest.NewRequest("GET", "/api/sessions/?mode=hotels", nil)
		if withCookie {
			r.AddCookie(&http.Cookie{Name: "odin_local_owner", Value: owner})
		}
		w := httptest.NewRecorder()
		s.history(w, r)
		var items []map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &items); err != nil {
			t.Fatal(err)
		}
		if !withCookie && len(items) != 0 {
			t.Fatal("anonymous history leak")
		}
		if withCookie && (len(items) != 1 || items[0]["session_id"] != own) {
			t.Fatal(items)
		}
	}
}

func TestDateOnlyEditPreservesRoomCapacityAndNightlyPrice(t *testing.T) {
	var snap map[string]any
	if err := json.Unmarshal([]byte(`{"status":"hotel_checkout","trip_spec":{},"selected_hotel":{"id":"family","content":{"room_capacity":4},"quote":{"source_kind":"demo","currency":"RUB","base_room_nightly_minor":500000,"nightly_minor":500000,"total_minor":2500000,"nights":5,"rooms":1}},"hotel_options":[{"id":"family","content":{"room_capacity":4},"quote":{"source_kind":"demo","currency":"RUB","base_room_nightly_minor":500000,"nightly_minor":500000,"total_minor":2500000,"nights":5,"rooms":1}}]}`), &snap); err != nil {
		t.Fatal(err)
	}
	start := time.Now().AddDate(0, 0, 5)
	edit := &HotelStayEdit{CheckIn: start.Format("2006-01-02"), CheckOut: start.AddDate(0, 0, 7).Format("2006-01-02"), Adults: 4}
	if err := updateHotelStay(snap, edit); err != "" {
		t.Fatal(err)
	}
	q := asMap(asMap(snap["selected_hotel"])["quote"])
	if q["rooms"] != float64(1) || q["nightly_minor"] != float64(500000) || q["total_minor"] != float64(3500000) {
		t.Fatalf("date-only edit changed room count or nightly price: %v", q)
	}
	if err := hotelAction(snap, "confirm_hotel_booking", "", edit.CheckIn, "Тестовый Гость", true); err != "" {
		t.Fatal(err)
	}
	booking := asMap(snap["hotel_booking"])
	if asMap(booking["quote"])["total_minor"] != float64(3500000) || asMap(booking["dates"])["end"] != edit.CheckOut {
		t.Fatalf("confirmation changed the recalculated dates or price: %v", booking)
	}
}

func TestStaySearchURLTracksEditAndPreviewRollback(t *testing.T) {
	var snap map[string]any
	if err := json.Unmarshal([]byte(`{"search_url":"https://ostrovok.ru/hotel/russia/sochi/?dates=10.11.2026-15.11.2026&guests=2&language=ru","trip_spec":{"dates":{"start":"2026-11-10","end":"2026-11-17"},"travellers":{"adults":4,"children":[]}}}`), &snap); err != nil {
		t.Fatal(err)
	}
	syncHotelSearchURL(snap)
	u, _ := url.Parse(stringValue(snap["search_url"]))
	if u.Query().Get("dates") != "10.11.2026-17.11.2026" || u.Query().Get("guests") != "4" || u.Query().Get("language") != "ru" {
		t.Fatal(u)
	}
	previousSpec := map[string]any{"dates": map[string]any{"start": "2026-11-10", "end": "2026-11-15"}, "travellers": map[string]any{"adults": float64(2), "children": []any{}}}
	snap["journey_preview"] = map[string]any{"previous_hotel": map[string]any{"id": "h"}, "previous_spec": previousSpec}
	if err := applyJourneyPreview(snap, false); err != "" {
		t.Fatal(err)
	}
	u, _ = url.Parse(stringValue(snap["search_url"]))
	if u.Query().Get("dates") != "10.11.2026-15.11.2026" || u.Query().Get("guests") != "2" {
		t.Fatal("rollback left changed URL", u)
	}
	asMap(previousSpec["travellers"])["children"] = []any{float64(5)}
	syncHotelSearchURL(snap)
	u, _ = url.Parse(stringValue(snap["search_url"]))
	if u.Query().Has("guests") {
		t.Fatal("URL silently omitted children", u)
	}
}

func TestStayEditAndConfirmationPersistDatesPriceAndSearchURL(t *testing.T) {
	api := NewAPI("", &http.Client{}, &sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	owner := strings.Repeat("b", 32)
	id := randomID()
	start := time.Now().AddDate(0, 0, 5)
	end := start.AddDate(0, 0, 7)
	var snap map[string]any
	if err := json.Unmarshal([]byte(`{"schema_version":"0.2","revision":0,"search_mode":"hotels","status":"hotel_checkout","search_url":"https://ostrovok.ru/hotel/russia/sochi/?guests=2&language=ru","trip_spec":{},"selected_hotel":{"id":"family","content":{"room_capacity":4},"quote":{"source_kind":"demo","currency":"RUB","base_room_nightly_minor":500000,"nightly_minor":500000,"total_minor":2500000,"nights":5,"rooms":1}},"hotel_options":[{"id":"family","content":{"room_capacity":4},"quote":{"source_kind":"demo","currency":"RUB","base_room_nightly_minor":500000,"nightly_minor":500000,"total_minor":2500000,"nights":5,"rooms":1}}]}`), &snap); err != nil {
		t.Fatal(err)
	}
	snap["session_id"] = id
	if err := api.trips.save(id, &tripFile{Owner: hashText(owner), Snapshot: snap, Operations: map[string]savedOperation{}}); err != nil {
		t.Fatal(err)
	}
	handler := api.Handler()
	call := func(method string, body any) map[string]any {
		t.Helper()
		raw, _ := json.Marshal(body)
		path := "/api/sessions/" + id
		if method == "POST" {
			path += "/actions"
		}
		req := httptest.NewRequest(method, path, strings.NewReader(string(raw)))
		req.AddCookie(&http.Cookie{Name: "odin_local_owner", Value: owner})
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, req)
		if w.Code != 200 {
			t.Fatalf("%s: %d %s", path, w.Code, w.Body.String())
		}
		var result map[string]any
		if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil {
			t.Fatal(err)
		}
		return result
	}
	changed := call("POST", map[string]any{"type": "update_hotel_stay", "expected_revision": 0, "idempotency_key": "family-edit-dates", "stay": HotelStayEdit{CheckIn: start.Format("2006-01-02"), CheckOut: end.Format("2006-01-02"), Adults: 4, Children: []*int{}}})
	restored := call("GET", nil)
	u, _ := url.Parse(stringValue(restored["search_url"]))
	if u.Query().Get("dates") != start.Format("02.01.2006")+"-"+end.Format("02.01.2006") || u.Query().Get("guests") != "4" {
		t.Fatal("stale saved search URL", u)
	}
	if asMap(asMap(restored["selected_hotel"])["quote"])["total_minor"] != float64(3500000) {
		t.Fatal("saved wrong price", restored)
	}
	booked := call("POST", map[string]any{"type": "confirm_hotel_booking", "expected_revision": changed["revision"], "idempotency_key": "family-confirm-once", "check_in": start.Format("2006-01-02"), "guest_name": "Тестовый Гость", "confirm_prototype": true})
	persisted := call("GET", nil)
	b := asMap(persisted["hotel_booking"])
	if asMap(b["quote"])["total_minor"] != float64(3500000) || asMap(b["dates"])["end"] != end.Format("2006-01-02") || b["id"] != asMap(booked["hotel_booking"])["id"] {
		t.Fatal("confirmation lost recalculated values", b)
	}
}

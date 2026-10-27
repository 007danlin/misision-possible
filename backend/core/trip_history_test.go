package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHistoryUsesConfirmedHotelDatesGuestsAndTotal(t *testing.T) {
	for _, kind := range []string{"hotel", "addon", "owned", "car"} {
		t.Run(kind, func(t *testing.T) {
			store := &TripStore{dir: t.TempDir()}
			owner := strings.Repeat("a", 32)
			id := randomID()
			hotel := map[string]any{"id": "confirmed", "name": "Оформленный отель", "quote": map[string]any{"currency": "RUB", "total_minor": float64(2100000)}}
			expected := float64(2100000)
			switch kind {
			case "addon":
				hotel["transfer_addon"] = map[string]any{"total_minor": float64(480000)}
				expected += 480000
			case "owned", "car":
				expected += 2700000
				transfers := float64(480000)
				label := "Ваши билеты"
				if kind == "car" {
					transfers = 0
					label = "Автомобиль"
				}
				expected += transfers
				hotel["journey"] = map[string]any{"total_minor": expected, "breakdown": map[string]any{"hotel": float64(2100000), "transport": float64(2700000), "transfers": transfers}, "transport": map[string]any{"kind": kind, "label": label}, "transfer_choice": map[string]any{"provider": "hotel", "label": "Трансфер отеля по запросу"}}
			}
			dates := map[string]any{"start": "2026-11-10", "end": "2026-11-17"}
			guests := map[string]any{"adults": float64(3), "children": []any{float64(0), float64(7)}}
			booking := map[string]any{"hotel": hotel, "dates": dates, "travellers": guests}
			snap := map[string]any{"session_id": id, "revision": float64(3), "search_mode": "hotels", "status": "hotel_booked", "trip_spec": map[string]any{"dates": map[string]any{"start": "2026-11-01", "end": "2026-11-05"}, "travellers": map[string]any{"adults": float64(1)}, "destination": "Сочи"}, "selected_hotel": map[string]any{"name": "Прежний отель"}, "hotel_booking": booking}
			if err := store.save(id, &tripFile{Owner: hashText(owner), Snapshot: snap}); err != nil {
				t.Fatal(err)
			}
			req := httptest.NewRequest("GET", "/api/sessions/?mode=hotels", nil)
			req.AddCookie(&http.Cookie{Name: "odin_local_owner", Value: owner})
			w := httptest.NewRecorder()
			store.history(w, req)
			var items []map[string]any
			if err := json.Unmarshal(w.Body.Bytes(), &items); err != nil || len(items) != 1 {
				t.Fatalf("invalid history: %s", w.Body.String())
			}
			item := items[0]
			spec := asMap(item["trip_spec"])
			if item["hotel_name"] != hotel["name"] || item["total_minor"] != expected || item["currency"] != "RUB" {
				t.Fatal("history differs from booking", item)
			}
			if !sameJourneySpec(asMap(spec["dates"]), dates) || !sameJourneySpec(asMap(spec["travellers"]), guests) {
				t.Fatal("history uses search conditions instead of confirmed stay", spec)
			}
			if kind == "owned" && (item["transport_label"] != "Ваши билеты" || item["transfer_label"] != "Трансфер отеля по запросу") {
				t.Fatal(item)
			}
			if kind == "car" && item["transfer_label"] != "Без отдельных трансферов" {
				t.Fatal(item)
			}
			if kind == "addon" && item["transfer_label"] != "Добавлены оба трансфера" {
				t.Fatal(item)
			}
			saved, err := store.read(id, hashText(owner))
			if err != nil {
				t.Fatal(err)
			}
			if !sameJourneySpec(asMap(saved.Snapshot["hotel_booking"]), booking) || !sameJourneySpec(asMap(saved.Snapshot["trip_spec"]), asMap(snap["trip_spec"])) {
				t.Fatal("reading history changed the saved trip")
			}
		})
	}
}

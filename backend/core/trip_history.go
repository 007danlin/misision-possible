package main

import (
	"net/http"
	"os"
	"sort"
	"strings"
	"time"
)

func (s *TripStore) history(w http.ResponseWriter, r *http.Request) {
	owner := ownerCookie(w, r, false)
	items := []map[string]any{}
	if owner == "" {
		writeSnapshot(w, items)
		return
	}
	files, err := os.ReadDir(s.dir)
	if err != nil {
		tripError(w, 500, "storage", "Не удалось открыть историю.", nil)
		return
	}
	for _, entry := range files {
		id := strings.TrimSuffix(entry.Name(), ".json")
		if !validID.MatchString(id) {
			continue
		}
		file, err := s.read(id, owner)
		if err != nil {
			continue
		}
		snap := file.Snapshot
		if rev, ok := snap["revision"].(float64); !ok || rev < 1 {
			continue
		}
		if mode := r.URL.Query().Get("mode"); mode != "" && snap["search_mode"] != mode {
			continue
		}
		info, err := entry.Info()
		if err != nil {
			continue
		}
		title := stringValue(snap["search_title"])
		if title == "" {
			for _, h := range asList(snap["history"]) {
				t := stringValue(h)
				if len([]rune(t)) > 25 {
					title = t
					break
				}
			}
		}
		if title == "" {
			title = "Поиск поездки"
		}
		if chars := []rune(title); len(chars) > 120 {
			title = string(chars[:120]) + "…"
		}
		item := map[string]any{"session_id": id, "title": title, "trip_spec": snap["trip_spec"], "status": snap["status"], "updated_at": info.ModTime().UTC(), "hotel_name": asMap(snap["selected_hotel"])["name"]}
		if booking := asMap(snap["hotel_booking"]); booking != nil {
			// Confirmed data, including later transfer additions, is authoritative.
			hotel := asMap(booking["hotel"])
			spec := cloneTrip(asMap(snap["trip_spec"]))
			if spec == nil {
				spec = map[string]any{}
			}
			spec["dates"], spec["travellers"] = booking["dates"], booking["travellers"]
			item["trip_spec"], item["hotel_name"] = spec, hotel["name"]
			total := hotelPlanTotal(hotel)
			if addon := asMap(hotel["transfer_addon"]); addon != nil {
				extra, _ := addon["total_minor"].(float64)
				total += extra
				item["transfer_label"] = "Добавлены оба трансфера"
			}
			if journey := asMap(hotel["journey"]); journey != nil {
				transport := asMap(journey["transport"])
				item["transport_label"] = transport["label"]
				item["transfer_label"] = "Оба трансфера"
				if label := asMap(journey["transfer_choice"])["label"]; label != nil {
					item["transfer_label"] = label
				}
				if transport["kind"] == "car" {
					item["transfer_label"] = "Без отдельных трансферов"
				}
			}
			item["total_minor"], item["currency"] = total, asMap(hotel["quote"])["currency"]
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["updated_at"].(time.Time).UnixNano() > items[j]["updated_at"].(time.Time).UnixNano()
	})
	if len(items) > 100 {
		items = items[:100]
	}
	writeSnapshot(w, items)
}

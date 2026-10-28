package main

import (
	"context"
	"github.com/go-chi/chi/v5"
	"net/http"
	"strings"
	"time"
)

type OwnedTickets struct {
	Arrival        string `json:"arrival"`
	Departure      string `json:"departure"`
	Terminal       string `json:"terminal"`
	PaidTotalMinor *int64 `json:"paid_total_minor"`
}
type TransportEdit struct {
	TransferProvider string        `json:"transfer_provider"`
	Mode             string        `json:"mode"`
	Origin           string        `json:"origin"`
	Tickets          *OwnedTickets `json:"tickets"`
}

func (s *API) changeTransport(ctx context.Context, snap map[string]any, hotelID string, edit *TransportEdit, owner string) string {
	if edit == nil {
		return "Выберите способ добраться."
	}
	if edit.Mode != "" && edit.Mode != "auto" && edit.Mode != "train" && edit.Mode != "flight" && edit.Mode != "car" {
		return "Неизвестный способ добраться."
	}
	if edit.TransferProvider != "" && edit.TransferProvider != "hotel" && edit.TransferProvider != "estimate" {
		return "Неизвестный вариант трансфера."
	}
	candidate := cloneTrip(snap)
	spec := asMap(candidate["trip_spec"])
	if edit.Origin != "" {
		if len([]rune(strings.TrimSpace(edit.Origin))) > 100 {
			return "Слишком длинное название города."
		}
		spec["origin"] = strings.TrimSpace(edit.Origin)
	}
	spec["include_transport"] = true
	if edit.TransferProvider != "" {
		spec["transfer_provider"] = edit.TransferProvider
	}
	if edit.Mode != "" {
		spec["transport_mode"] = edit.Mode
		spec["transport_owned"] = false
		spec["owned_transport"] = nil
	}
	if edit.Tickets != nil {
		t := edit.Tickets
		a, e1 := time.Parse(time.RFC3339, t.Arrival)
		b, e2 := time.Parse(time.RFC3339, t.Departure)
		if e1 != nil || e2 != nil || !b.After(a) || (t.Terminal != "airport" && t.Terminal != "station") || (t.PaidTotalMinor != nil && (*t.PaidTotalMinor < 0 || *t.PaidTotalMinor > 1e12)) {
			return "Проверьте даты, время, терминал и сумму билетов."
		}
		spec["transport_owned"] = true
		spec["owned_transport"] = map[string]any{"arrival": t.Arrival, "departure": t.Departure, "terminal": t.Terminal, "paid_total_minor": t.PaidTotalMinor}
	}
	if strings.TrimSpace(stringValue(spec["origin"])) == "" {
		return "Сначала укажите город отправления."
	}
	previous := asMap(snap["selected_hotel"])
	previousSpec := cloneTrip(asMap(snap["trip_spec"]))
	if recovery := asMap(snap["journey_recovery"]); recovery != nil {
		previous = asMap(recovery["hotel"])
		previousSpec = cloneTrip(asMap(recovery["spec"]))
	}
	if previous == nil {
		for _, v := range asList(snap["hotel_options"]) {
			h := asMap(v)
			if h["id"] == hotelID {
				previous = h
				break
			}
		}
	}
	if previous == nil {
		// Tickets can be supplied before a hotel has been selected. The next normal
		// search applies these facts; no prices are accepted from the browser.
		if edit.Tickets == nil {
			return "Сначала выберите отель из подборки."
		}
		snap["trip_spec"] = spec
		snap["status"] = "needs_input"
		snap["assistant_message"] = "Данные билетов сохранены. Нажмите «Подобрать поездку», чтобы связать их с отелем и трансферами."
		return ""
	}
	fresh, err := s.refreshJourney(ctx, candidate, previous, owner)
	if err != nil {
		return "Для этой дороги пока нет расчёта. Прежний план сохранён; попробуйте другой способ или город."
	}
	if err := s.refreshJourneyOptions(ctx, candidate, fresh, owner); err != nil {
		return err.Error()
	}
	candidate["journey_recovery"] = nil
	setJourneyPreview(candidate, cloneTrip(previous), previousSpec, fresh, asList(cloneTrip(snap)["hotel_options"]))
	for k, v := range candidate {
		snap[k] = v
	}
	return ""
}

func (s *API) hotelContext(store *TripStore, w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	hotelID := chi.URLParam(r, "hotelID")
	owner := ownerCookie(w, r, false)
	unlock := store.lock(id)
	file, err := store.read(id, owner)
	if err != nil {
		unlock()
		tripError(w, 404, "not_found", "Поездка не найдена.", nil)
		return
	}
	snap := cloneTrip(file.Snapshot)
	unlock()
	found := false
	for _, v := range asList(snap["hotel_options"]) {
		if asMap(v)["id"] == hotelID {
			found = true
		}
	}
	if h := asMap(asMap(snap["hotel_booking"])["hotel"]); h != nil && h["id"] == hotelID {
		found = true
	}
	if !found {
		tripError(w, 404, "not_found", "Отель не найден в этой поездке.", nil)
		return
	}
	result, err := s.evaluateTrip(r.Context(), snap, "content:"+hotelID, owner)
	if err != nil || len(asList(result["hotel_options"])) != 1 {
		tripError(w, 503, "context_unavailable", "Сведения временно недоступны.", nil)
		return
	}
	h := asMap(asList(result["hotel_options"])[0])
	writeSnapshot(w, map[string]any{"weather": h["weather"], "nearby_places": h["nearby_places"]})
}

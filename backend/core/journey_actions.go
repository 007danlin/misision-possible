package main

import (
	"context"
	"encoding/json"
	"errors"
)

func cloneTrip(value map[string]any) map[string]any {
	data, _ := json.Marshal(value)
	var copy map[string]any
	_ = json.Unmarshal(data, &copy)
	return copy
}

func sameJourneySpec(left, right map[string]any) bool {
	a, _ := json.Marshal(left)
	b, _ := json.Marshal(right)
	return string(a) == string(b)
}

func journeyEnabled(spec map[string]any) bool {
	return spec["include_transport"] == true || spec["budget_scope"] == "booking" || spec["budget_scope"] == "whole_trip"
}

func journeyTotal(h map[string]any) float64 {
	n, _ := asMap(h["journey"])["total_minor"].(float64)
	return n
}

func hotelPlanTotal(h map[string]any) float64 {
	if asMap(h["journey"]) != nil {
		return journeyTotal(h)
	}
	total, _ := asMap(h["quote"])["total_minor"].(float64)
	return total
}

func (s *API) refreshJourney(ctx context.Context, snap, hotel map[string]any, owner string) (map[string]any, error) {
	result, err := s.evaluateTrip(ctx, snap, stringValue(hotel["id"]), owner)
	if err != nil || len(asList(result["hotel_options"])) != 1 {
		return nil, errors.New("Не удалось пересчитать поездку. Проверьте направление и условия.")
	}
	h := asMap(asList(result["hotel_options"])[0])
	j := asMap(h["journey"])
	if h["id"] != hotel["id"] || !validHotelQuote(h) || j == nil {
		return nil, errors.New("Нужен новый расчёт поездки.")
	}
	sum := float64(0)
	for _, value := range asMap(j["breakdown"]) {
		n, ok := value.(float64)
		if !ok || n < 0 {
			return nil, errors.New("Некорректный состав стоимости.")
		}
		sum += n
	}
	if sum <= 0 || sum != journeyTotal(h) || len(asList(j["checks"])) == 0 {
		return nil, errors.New("Не удалось проверить итог поездки.")
	}
	return h, nil
}

// Keep the complete shortlist while replacing the selected hotel's canonical quote.
func replaceJourneyOption(options []any, hotel map[string]any) []any {
	result := make([]any, 0, len(options)+1)
	found := false
	for _, item := range options {
		if asMap(item)["id"] == hotel["id"] {
			result = append(result, hotel)
			found = true
		} else {
			result = append(result, item)
		}
	}
	if !found {
		result = append(result, hotel)
	}
	return result
}

// A changed trip specification applies to every option shown on returning to results.
func (s *API) refreshJourneyOptions(ctx context.Context, snap, selected map[string]any, owner string) error {
	options := replaceJourneyOption(asList(snap["hotel_options"]), selected)
	refreshed := make([]any, 0, len(options))
	for _, item := range options {
		h := asMap(item)
		if h["id"] == selected["id"] {
			refreshed = append(refreshed, selected)
			continue
		}
		fresh, err := s.refreshJourney(ctx, snap, h, owner)
		if err != nil {
			// An unavailable alternative cannot cancel a valid edit of the chosen hotel.
			continue
		}
		refreshed = append(refreshed, fresh)
	}
	snap["hotel_options"] = refreshed
	return nil
}

func previewOptions(preview map[string]any, key string, hotel any) []any {
	if options := asList(preview[key+"_options"]); len(options) > 0 {
		return options
	}
	return []any{hotel} // Persisted previews from older sessions.
}

func journeyBlock(h map[string]any, acceptBudget bool) string {
	j := asMap(h["journey"])
	if j == nil {
		return "Сначала соберите дорогу и трансферы."
	}
	for _, item := range asList(j["checks"]) {
		c := asMap(item)
		if c["blocking"] == false || c["status"] == "pass" {
			continue
		}
		// Saving a demo plan does not require supplier confirmation. Actual
		// conflicts and missing ticket prices still prevent confirmation.
		if c["status"] == "unknown" {
			switch c["code"] {
			case "children", "pets", "cancellation", "other", "no_connections", "no_night_travel":
				continue
			}
		}
		if acceptBudget && (c["code"] == "budget" || c["code"] == "hotel_budget") {
			continue
		}
		return stringValue(c["message"])
	}
	return ""
}

func setJourneyPreview(snap, previousHotel, previousSpec, proposedHotel map[string]any, previousOptions []any) {
	snap["journey_preview"] = map[string]any{
		"previous_hotel": previousHotel, "previous_spec": previousSpec,
		"proposed_hotel": proposedHotel, "proposed_spec": cloneTrip(asMap(snap["trip_spec"])),
		"price_delta": hotelPlanTotal(proposedHotel) - hotelPlanTotal(previousHotel),
	}
	p := asMap(snap["journey_preview"])
	p["proposed_options"] = cloneTrip(snap)["hotel_options"]
	p["previous_options"] = previousOptions
	snap["selected_hotel"] = nil
	snap["status"] = "choosing"
	snap["assistant_message"] = "Пересчитал всю поездку. Сравните изменения и подтвердите новый план — прежний выбор сохранён."
}

func applyJourneyPreview(snap map[string]any, accept bool) string {
	preview := asMap(snap["journey_preview"])
	if preview == nil {
		return "Нет изменения для подтверждения."
	}
	key := "previous"
	if accept {
		key = "proposed"
	}
	h := asMap(preview[key+"_hotel"])
	snap["selected_hotel"], snap["trip_spec"] = h, preview[key+"_spec"]
	snap["hotel_options"] = previewOptions(preview, key, h)
	syncHotelSearchURL(snap)
	snap["journey_preview"], snap["selection"] = nil, map[string]any{}
	snap["status"] = "hotel_checkout"
	snap["assistant_message"] = "План сохранён. Проверьте состав перед оформлением."
	return ""
}

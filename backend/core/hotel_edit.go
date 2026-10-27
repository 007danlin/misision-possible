package main

import (
	"fmt"
	"math"
	"net/url"
	"strconv"
	"time"
)

type HotelStayEdit struct {
	CheckIn  string `json:"check_in"`
	CheckOut string `json:"check_out"`
	Adults   int    `json:"adults"`
	Children []*int `json:"children"`
}

func hotelBudgetExceeded(snap map[string]any) bool {
	q := asMap(asMap(snap["selected_hotel"])["quote"])
	spec := asMap(snap["trip_spec"])
	limit, ok := asMap(spec["budget"])["amount_minor"].(float64)
	if !ok {
		return false
	}
	price, _ := q["total_minor"].(float64)
	if spec["budget_period"] == "night" {
		price, _ = q["nightly_minor"].(float64)
	}
	return price > limit
}

func updateHotelStay(snap map[string]any, edit *HotelStayEdit) string {
	if edit == nil || snap["status"] != "hotel_checkout" {
		return "Сначала выберите отель."
	}
	selected := asMap(snap["selected_hotel"])
	if selected == nil || !validHotelQuote(selected) {
		return "Выберите отель с актуальным расчётом."
	}
	if edit.Adults < 1 || edit.Adults > 20 || len(edit.Children) > 10 {
		return "Укажите от 1 до 20 взрослых и не более 10 детей."
	}
	children := []any{}
	for _, age := range edit.Children {
		if age == nil || *age < 0 || *age > 17 {
			return "Укажите возраст каждого ребёнка от 0 до 17 лет."
		}
		children = append(children, float64(*age))
	}
	start, e1 := time.Parse("2006-01-02", edit.CheckIn)
	end, e2 := time.Parse("2006-01-02", edit.CheckOut)
	today, _ := time.Parse("2006-01-02", time.Now().In(time.FixedZone("Moscow", 3*3600)).Format("2006-01-02"))
	nights := int(end.Sub(start).Hours() / 24)
	if e1 != nil || e2 != nil || start.Before(today) || start.After(today.AddDate(3, 0, 0)) || nights < 1 || nights > 60 {
		return "Проверьте даты: от 1 до 60 ночей, заезд не в прошлом."
	}
	oldQ := asMap(selected["quote"])
	base, ok := oldQ["base_room_nightly_minor"].(float64)
	if !ok || base <= 0 {
		return "Для этого сохранённого поиска нужен новый расчёт. Обновите подборку."
	}
	spec := asMap(snap["trip_spec"])
	spec["dates"] = map[string]any{"start": edit.CheckIn, "end": edit.CheckOut}
	spec["stay_nights"] = nights
	spec["travellers"] = map[string]any{"adults": edit.Adults, "children": children}
	// Recalculate every displayed tariff so returning to the options is consistent.
	for _, item := range asList(snap["hotel_options"]) {
		h := asMap(item)
		q := asMap(h["quote"])
		b, ok := q["base_room_nightly_minor"].(float64)
		if !ok {
			continue
		}
		capacity, ok := asMap(h["content"])["room_capacity"].(float64)
		if !ok || capacity < 1 || math.IsNaN(capacity) || math.IsInf(capacity, 0) || capacity != math.Trunc(capacity) {
			capacity = 2
		}
		rooms := math.Ceil(float64(edit.Adults+len(children)) / capacity)
		nightly := b * rooms
		if q["breakfast"] == true {
			nightly += 65000 * float64(edit.Adults+len(children))
		}
		if q["free_cancellation"] == true {
			nightly = math.Ceil(nightly*1.12/10000) * 10000
		}
		q["nightly_minor"], q["total_minor"], q["nights"], q["rooms"] = nightly, nightly*float64(nights), float64(nights), rooms
		h["url"] = hotelStayURL(stringValue(h["url"]), start, end, edit.Adults, len(children) > 0)
		// Reasons from the old budget are invalid after direct edits.
		reasons := []any{}
		for _, v := range asList(h["reasons"]) {
			if v != "В вашем бюджете" {
				reasons = append(reasons, v)
			}
		}
		h["reasons"] = reasons
		if h["id"] == selected["id"] {
			snap["selected_hotel"] = h
		}
	}
	snap["assistant_message"] = fmt.Sprintf("Обновил даты и гостей: %d ночей, %d взрослых, %d детей. Стоимость пересчитана.", nights, edit.Adults, len(children))
	if hotelBudgetExceeded(snap) {
		snap["assistant_message"] = snap["assistant_message"].(string) + " Новая стоимость выше бюджета — проверьте сумму перед подтверждением."
	}
	syncHotelSearchURL(snap)
	snap["selection"] = map[string]any{}
	return ""
}

func hotelStayURL(raw string, start, end time.Time, adults int, hasChildren bool) string {
	u, err := url.Parse(raw)
	if err != nil || u.Hostname() != "ostrovok.ru" {
		return raw
	}
	query := u.Query()
	query.Set("dates", start.Format("02.01.2006")+"-"+end.Format("02.01.2006"))
	query.Del("guests")
	if !hasChildren {
		query.Set("guests", strconv.Itoa(adults))
	}
	u.RawQuery = query.Encode()
	return u.String()
}

func syncHotelSearchURL(snap map[string]any) {
	raw, ok := snap["search_url"].(string)
	if !ok {
		return
	}
	spec := asMap(snap["trip_spec"])
	dates := asMap(spec["dates"])
	start, err1 := time.Parse("2006-01-02", stringValue(dates["start"]))
	end, err2 := time.Parse("2006-01-02", stringValue(dates["end"]))
	if err1 != nil || err2 != nil {
		return
	}
	travellers := asMap(spec["travellers"])
	adults, _ := travellers["adults"].(float64)
	// Direct edits construct an int; restored JSON snapshots contain float64.
	if n, ok := travellers["adults"].(int); ok {
		adults = float64(n)
	}
	snap["search_url"] = hotelStayURL(raw, start, end, int(adults), len(asList(travellers["children"])) > 0)
}

package main

import (
	"context"
	"encoding/json"
	"io"
	"math"
	"net/http"
	"os"
	"strings"
	"time"
	"unicode"

	"github.com/go-chi/chi/v5"
)

// Progress is ephemeral and read without the operation lock: snapshots are atomic
// files, and the opaque token binds the event to its owner, session and operation.
func (s *API) hotelProgress(store *TripStore, w http.ResponseWriter, r *http.Request) {
	owner, id := ownerCookie(w, r, false), chi.URLParam(r, "id")
	if _, err := store.read(id, owner); err != nil {
		tripError(w, 404, "not_found", "Поиск не найден.", nil)
		return
	}
	key := r.URL.Query().Get("key")
	if len(key) < 8 || len(key) > 128 {
		tripError(w, 400, "invalid_request", "Нужен ключ запроса.", nil)
		return
	}
	addr := os.Getenv("AGENT_PROGRESS_URL")
	if addr == "" {
		addr = "http://127.0.0.1:15052"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", strings.TrimRight(addr, "/")+"/"+hashText(owner+":"+id+":"+key), nil)
	if err != nil {
		writeSnapshot(w, map[string]any{"stage": "waiting"})
		return
	}
	response, err := http.DefaultClient.Do(req)
	if err != nil {
		writeSnapshot(w, map[string]any{"stage": "waiting"})
		return
	}
	defer response.Body.Close()
	var event map[string]any
	if response.StatusCode != 200 || json.NewDecoder(io.LimitReader(response.Body, 32768)).Decode(&event) != nil {
		event = map[string]any{"stage": "waiting"}
	}
	writeSnapshot(w, event)
}

func validHotelQuote(h map[string]any) bool {
	q := asMap(h["quote"])
	n, nOK := q["nights"].(float64)
	price, pOK := q["nightly_minor"].(float64)
	total, tOK := q["total_minor"].(float64)
	return nOK && pOK && tOK && q["source_kind"] == "demo" && q["currency"] == "RUB" && n >= 1 && n <= 60 && n == math.Trunc(n) && price > 0 && total == price*n
}

// All prices and hotel attributes come from the stored search, never the browser.
func hotelAction(snap map[string]any, action, hotelID, checkIn, guestName string, confirmed bool) string {
	switch action {
	case "select_hotel":
		if snap["status"] != "choosing" && snap["status"] != "hotel_checkout" {
			return "Сначала получите актуальную подборку."
		}
		for _, item := range asList(snap["hotel_options"]) {
			h := asMap(item)
			if h["id"] == hotelID && validHotelQuote(h) {
				snap["selected_hotel"] = h
				snap["status"] = "hotel_checkout"
				snap["assistant_message"] = "Выбрали «" + stringValue(h["name"]) + "». Проверьте даты и условия, затем заполните имя гостя."
				return ""
			}
		}
		return "Выберите отель из актуальной подборки с рассчитанной стоимостью."
	case "clear_hotel_selection":
		if snap["status"] != "hotel_checkout" {
			return "Нет выбранного отеля."
		}
		snap["selected_hotel"] = nil
		snap["status"] = "choosing"
		snap["assistant_message"] = "Вернулись к подборке. Можно выбрать другой отель."
		return ""
	case "confirm_hotel_booking":
		h := asMap(snap["selected_hotel"])
		if snap["status"] != "hotel_checkout" || h == nil || !validHotelQuote(h) {
			return "Сначала выберите отель по текущим условиям."
		}
		if !confirmed {
			return "Подтвердите оформление в демонстрационном режиме — без оплаты и реального бронирования."
		}
		guestName = strings.Join(strings.Fields(guestName), " ")
		if len([]rune(guestName)) < 2 || len([]rune(guestName)) > 100 || strings.IndexFunc(guestName, unicode.IsControl) >= 0 {
			return "Укажите имя гостя: от 2 до 100 символов."
		}
		start, err := time.Parse("2006-01-02", checkIn)
		now := time.Now().In(time.FixedZone("Moscow", 3*3600))
		today, _ := time.Parse("2006-01-02", now.Format("2006-01-02"))
		if err != nil || start.Before(today) || start.After(today.AddDate(3, 0, 0)) {
			return "Выберите дату заезда от сегодняшнего дня до трёх лет вперёд."
		}
		spec := asMap(snap["trip_spec"])
		q := asMap(h["quote"])
		end := start.AddDate(0, 0, int(q["nights"].(float64))).Format("2006-01-02")
		if dates := asMap(spec["dates"]); dates != nil && (dates["start"] != checkIn || dates["end"] != end) {
			return "Даты изменились. Обновите подборку в чате."
		}
		snap["hotel_booking"] = map[string]any{"id": "OP-" + strings.ToUpper(randomID()[:8]), "is_demo": true, "hotel": h, "quote": q, "dates": map[string]any{"start": checkIn, "end": end}, "travellers": spec["travellers"], "guest_name": guestName, "created_at": time.Now().UTC().Format(time.RFC3339)}
		snap["status"] = "hotel_booked"
		snap["assistant_message"] = "Готово! Поездка сохранена. В плане — отель, даты и детали дороги."
		return ""
	default:
		return "Это действие недоступно для поиска отелей."
	}
}

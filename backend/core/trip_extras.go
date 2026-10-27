package main

import (
	"context"
	"encoding/json"
	"github.com/go-chi/chi/v5"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

func extraAction(kind string) bool {
	switch kind {
	case "save_early_request", "clear_early_request", "quote_transfer_addon", "accept_transfer_addon", "discard_transfer_addon", "create_share", "revoke_share":
		return true
	}
	return false
}
func (s *API) tripExtra(ctx context.Context, snap map[string]any, kind, requestedTime, owner string, origins ...string) string {
	b := asMap(snap["hotel_booking"])
	switch kind {
	case "create_share":
		options := asList(snap["hotel_options"])
		if b != nil {
			options = []any{b["hotel"]}
		}
		if len(options) == 0 {
			return "Сначала подберите варианты."
		}
		// Explicit publication freezes only decision data; never guest names/messages.
		public := []any{}
		for _, item := range options {
			h := asMap(item)
			q := asMap(h["quote"])
			total := q["total_minor"]
			if asMap(h["journey"]) != nil {
				total = journeyTotal(h)
			}
			if addon := asMap(h["transfer_addon"]); addon != nil {
				base, _ := total.(float64)
				extra, _ := addon["total_minor"].(float64)
				total = base + extra
			}
			public = append(public, map[string]any{"id": h["id"], "name": h["name"], "address": h["address"], "rating": h["rating"], "total_minor": total, "reasons": h["reasons"]})
		}
		spec := asMap(snap["trip_spec"])
		snap["share"] = map[string]any{"token": randomID(), "expires_at": time.Now().Add(7 * 24 * time.Hour).UTC().Format(time.RFC3339), "options": public, "destination": spec["destination"], "dates": spec["dates"], "votes": map[string]any{}}
		snap["assistant_message"] = "Ссылка для совместного выбора готова на 7 дней. Имя гостя и переписка в неё не входят."
	case "revoke_share":
		snap["share"] = nil
		snap["assistant_message"] = "Доступ по прежней ссылке закрыт."
	case "save_early_request":
		if b == nil {
			return "Сначала сохраните поездку."
		}
		t, err := time.Parse("15:04", requestedTime)
		if err != nil || t.Format("15:04") != requestedTime {
			return "Укажите время в формате ЧЧ:ММ."
		}
		b["early_checkin_request"] = map[string]any{"time": requestedTime, "status": "draft", "created_at": time.Now().UTC().Format(time.RFC3339)}
		snap["assistant_message"] = "Пожелание раннего заезда сохранено. Оно не отправлено в отель и не подтверждено."
	case "clear_early_request":
		if b == nil {
			return "Нет сохранённой поездки."
		}
		delete(b, "early_checkin_request")
		snap["assistant_message"] = "Пожелание удалено."
	case "quote_transfer_addon", "accept_transfer_addon":
		if b == nil {
			return "Сначала сохраните отель."
		}
		h := asMap(b["hotel"])
		if asMap(h["journey"]) != nil || asMap(h["transfer_addon"]) != nil {
			return "Трансферы уже включены."
		}
		temp := cloneTrip(snap)
		spec := asMap(temp["trip_spec"])
		spec["include_transport"] = true
		spec["budget_scope"] = "hotel"
		spec["dates"] = b["dates"]
		spec["travellers"] = b["travellers"]
		if stringValue(spec["origin"]) == "" {
			origin := stringValue(asMap(snap["transfer_addon_preview"])["origin"])
			if len(origins) > 0 && strings.TrimSpace(origins[0]) != "" {
				origin = strings.TrimSpace(origins[0])
			}
			if origin == "" || len([]rune(origin)) > 100 {
				return "Укажите город отправления для расчёта трансферов."
			}
			spec["origin"] = origin
		}
		fresh, err := s.refreshJourney(ctx, temp, h, owner)
		if err != nil {
			return err.Error()
		}
		j := asMap(fresh["journey"])
		segments := []any{}
		for _, item := range asList(j["segments"]) {
			if asMap(item)["kind"] == "transfer" {
				segments = append(segments, item)
			}
		}
		checks := []any{}
		for _, item := range asList(j["checks"]) {
			c := asMap(item)
			if c["code"] == "budget" || c["code"] == "hotel_budget" || c["code"] == "no_night_flights" {
				continue
			}
			if c["blocking"] == true && c["status"] != "pass" {
				return stringValue(c["message"])
			}
			checks = append(checks, item)
		}
		if len(segments) != 2 {
			return "Для выбранной дороги отдельные трансферы не рассчитаны."
		}
		proposal := map[string]any{"origin": spec["origin"], "segments": segments, "total_minor": asMap(j["breakdown"])["transfers"], "checks": checks, "notice": "Оценка двух трансферов от терминала и обратно по расчётному расписанию. Услуга не заказана; время подачи, вместимость и багаж требуют подтверждения.", "source_kind": "estimate"}
		if kind == "accept_transfer_addon" {
			previous := asMap(snap["transfer_addon_preview"])
			if previous == nil {
				return "Сначала посмотрите расчёт трансфера."
			}
			if previous["total_minor"] != proposal["total_minor"] {
				snap["transfer_addon_preview"] = proposal
				snap["assistant_message"] = "Цена изменилась. Проверьте новый расчёт."
				return ""
			}
			h["transfer_addon"] = proposal
			snap["transfer_addon_preview"] = nil
			snap["assistant_message"] = "Трансферы добавлены в сохранённый план. Итог обновлён; оплата не выполнялась."
		} else {
			snap["transfer_addon_preview"] = proposal
			snap["assistant_message"] = "Проверьте маршрут и доплату за оба трансфера."
		}
	case "discard_transfer_addon":
		snap["transfer_addon_preview"] = nil
		snap["assistant_message"] = "Состав поездки оставлен прежним."
	}
	return ""
}

func (store *TripStore) shared(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Robots-Tag", "noindex, nofollow")
	parts := strings.Split(chi.URLParam(r, "token"), "-")
	if len(parts) != 2 || !validID.MatchString(parts[0]) || !validID.MatchString(parts[1]) {
		tripError(w, 404, "not_found", "Ссылка недоступна.", nil)
		return
	}
	id := parts[0]
	unlock := store.lock(id)
	defer unlock()
	raw, err := os.ReadFile(filepath.Join(store.dir, id+".json"))
	var f tripFile
	if err != nil || json.Unmarshal(raw, &f) != nil {
		tripError(w, 404, "not_found", "Ссылка недоступна.", nil)
		return
	}
	share := asMap(f.Snapshot["share"])
	expiry, _ := time.Parse(time.RFC3339, stringValue(share["expires_at"]))
	if share["token"] != parts[1] || time.Now().After(expiry) {
		tripError(w, 404, "not_found", "Ссылка закрыта или срок истёк.", nil)
		return
	}
	votes := asMap(share["votes"])
	if votes == nil {
		votes = map[string]any{}
	}
	if r.Method == "POST" {
		var input struct {
			HotelID string `json:"hotel_id"`
		}
		d := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1024))
		d.DisallowUnknownFields()
		if d.Decode(&input) != nil {
			tripError(w, 400, "invalid", "Выберите вариант.", nil)
			return
		}
		valid := false
		for _, h := range asList(share["options"]) {
			if asMap(h)["id"] == input.HotelID {
				valid = true
			}
		}
		if !valid {
			tripError(w, 400, "invalid", "Вариант отсутствует в подборке.", nil)
			return
		}
		voter := hashText(ownerCookie(w, r, true))
		if len(votes) >= 100 && votes[voter] == nil {
			tripError(w, 409, "limit", "Достигнут предел голосов.", nil)
			return
		}
		votes[voter] = input.HotelID
		share["votes"] = votes
		if err := store.save(id, &f); err != nil {
			tripError(w, 500, "storage", "Не удалось сохранить выбор.", nil)
			return
		}
	}
	counts := map[string]int{}
	for _, h := range votes {
		counts[stringValue(h)]++
	}
	writeSnapshot(w, map[string]any{"destination": share["destination"], "dates": share["dates"], "options": share["options"], "votes": counts, "expires_at": share["expires_at"]})
}

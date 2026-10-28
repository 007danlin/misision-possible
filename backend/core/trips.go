package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	pb "core/proto"
	"github.com/go-chi/chi/v5"
	"google.golang.org/grpc/metadata"
)

//go:embed web/*
var tripWeb embed.FS

// The local demo uses the SAME Core and agent. Durable snapshots belong to Core,
// stored as atomic files under the project's private data directory (one writer).
// This local adapter can later be replaced with Luka's production persistence.
type TripStore struct {
	dir   string
	locks sync.Map
}
type savedOperation struct {
	Hash  string          `json:"hash"`
	Reply json.RawMessage `json:"reply"`
}
type tripFile struct {
	Owner      string                    `json:"owner"`
	Snapshot   map[string]any            `json:"snapshot"`
	Operations map[string]savedOperation `json:"operations"`
}

var validID = regexp.MustCompile(`^[a-f0-9]{32}$`)

func randomID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
func hashText(s string) string { v := sha256.Sum256([]byte(s)); return hex.EncodeToString(v[:]) }
func (s *TripStore) lock(id string) func() {
	v, _ := s.locks.LoadOrStore(id, &sync.Mutex{})
	m := v.(*sync.Mutex)
	m.Lock()
	return m.Unlock
}
func (s *TripStore) read(id, owner string) (*tripFile, error) {
	if !validID.MatchString(id) {
		return nil, os.ErrNotExist
	}
	data, err := os.ReadFile(filepath.Join(s.dir, id+".json"))
	if err != nil {
		return nil, err
	}
	var file tripFile
	if err = json.Unmarshal(data, &file); err != nil {
		return nil, err
	}
	if file.Owner != owner {
		return nil, os.ErrNotExist
	}
	return &file, nil
}
func (s *TripStore) save(id string, file *tripFile) error {
	data, err := json.Marshal(file)
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(s.dir, ".trip-")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if _, err = tmp.Write(data); err == nil {
		err = tmp.Sync()
	}
	closeErr := tmp.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err = os.Rename(name, filepath.Join(s.dir, id+".json")); err != nil {
		return err
	}
	dir, err := os.Open(s.dir)
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}
func ownerCookie(w http.ResponseWriter, r *http.Request, create bool) string {
	if cookie, err := r.Cookie("odin_local_owner"); err == nil && validID.MatchString(cookie.Value) {
		return hashText(cookie.Value)
	}
	if !create {
		return ""
	}
	id := randomID()
	http.SetCookie(w, &http.Cookie{Name: "odin_local_owner", Value: id, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: 86400 * 30})
	return hashText(id)
}
func tripError(w http.ResponseWriter, code int, kind, message string, revision any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]any{"request_id": randomID(), "error": map[string]any{"code": kind, "message": message, "retryable": code >= 500, "current_revision": revision}})
}
func writeSnapshot(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(value)
}
func asMap(v any) map[string]any { m, _ := v.(map[string]any); return m }
func asList(v any) []any         { m, _ := v.([]any); return m }
func stringValue(v any) string   { s, _ := v.(string); return s }
func stateFor(snapshot map[string]any) string {
	value := map[string]any{"schema_version": "0.2", "revision": snapshot["revision"], "trip_spec": snapshot["trip_spec"], "selected_plan": snapshot["selected_plan"]}
	if mode, ok := snapshot["search_mode"]; ok {
		value["search_mode"] = mode
	}
	if snapshot["search_mode"] == "hotels" {
		for _, key := range []string{"hotel_options", "selected_hotel", "assistant_message", "questions", "search_url", "selection"} {
			if v, ok := snapshot[key]; ok && v != nil {
				value[key] = v
			}
		}
	}
	if history, ok := snapshot["history"]; ok {
		value["history"] = history
	}
	data, _ := json.Marshal(value)
	return string(data)
}
func (s *API) evaluateTrip(ctx context.Context, snapshot map[string]any, planID, owner string) (map[string]any, error) {
	timeout := 5 * time.Second
	if strings.HasPrefix(planID, "content:") {
		timeout = 12 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	reply, err := s.agent.Evaluate(ctx, &pb.EvaluateRequest{StateJson: stateFor(snapshot), PlanId: planID, Caller: owner})
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if reply.Caller != owner || json.Unmarshal([]byte(reply.TurnJson), &result) != nil {
		return nil, errors.New("invalid catalogue response")
	}
	return result, nil
}
func copyTurn(snapshot, turn map[string]any) {
	for _, key := range []string{"status", "trip_spec", "assistant_message", "questions", "destination_options", "options", "change_preview", "data_mode", "telemetry", "error_code", "hotel_options", "search_url", "selection"} {
		snapshot[key] = turn[key]
	}
	snapshot["checkout_allowed"] = false
}
func (s *API) mountLocalTrips(r chi.Router, store *TripStore) {
	// Enabled on the local demo (native loopback or loopback-published Docker).
	r.Route("/api/sessions", func(r chi.Router) {
		r.Use(func(next http.Handler) http.Handler {
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != "GET" && r.Header.Get("Origin") != "" && r.Header.Get("Origin") != "http://"+r.Host {
					tripError(w, 403, "origin", "Запрос с другого сайта отклонён.", nil)
					return
				}
				next.ServeHTTP(w, r)
			})
		})
		r.Get("/", func(w http.ResponseWriter, r *http.Request) { store.history(w, r) })
		r.Post("/", func(w http.ResponseWriter, r *http.Request) {
			var input struct {
				SearchMode string `json:"search_mode"`
			}
			dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1024))
			dec.DisallowUnknownFields()
			if err := dec.Decode(&input); err != nil && err != io.EOF {
				tripError(w, 400, "invalid_request", "Некорректный режим поиска.", nil)
				return
			}
			if input.SearchMode != "" && input.SearchMode != "trip" && input.SearchMode != "hotels" {
				tripError(w, 400, "invalid_request", "Неизвестный режим поиска.", nil)
				return
			}
			owner := ownerCookie(w, r, true)
			id := randomID()
			snapshot := map[string]any{"schema_version": "0.2", "session_id": id, "revision": 0, "request_id": randomID(), "status": "needs_input", "trip_spec": map[string]any{}, "selected_plan": nil, "change_preview": nil, "booking": nil, "checkout_allowed": false, "options": []any{}, "destination_options": []any{}, "questions": []any{}, "data_mode": "synthetic", "assistant_message": "Расскажите, куда и когда хотите поехать. Можно начать с идеи отдыха."}
			if input.SearchMode == "hotels" {
				snapshot["search_mode"] = "hotels"
				snapshot["trip_spec"] = map[string]any{"include_transport": true}
				snapshot["data_mode"] = "public_catalogue"
				snapshot["assistant_message"] = "Расскажите о поездке: откуда, куда, даты и бюджет. Соберу отель, дорогу и трансферы — или подберу только отель."
			}
			file := &tripFile{Owner: owner, Snapshot: snapshot, Operations: map[string]savedOperation{}}
			if err := store.save(id, file); err != nil {
				tripError(w, 500, "storage", "Не удалось сохранить поездку.", nil)
				return
			}
			writeSnapshot(w, snapshot)
		})
		r.Get("/{id}", func(w http.ResponseWriter, r *http.Request) {
			id := chi.URLParam(r, "id")
			unlock := store.lock(id)
			defer unlock()
			file, err := store.read(id, ownerCookie(w, r, false))
			if err != nil {
				tripError(w, 404, "not_found", "Поездка не найдена.", nil)
				return
			}
			writeSnapshot(w, file.Snapshot)
		})
		r.Get("/{id}/context/{hotelID}", func(w http.ResponseWriter, r *http.Request) { s.hotelContext(store, w, r) })
		r.Get("/{id}/progress", func(w http.ResponseWriter, r *http.Request) { s.hotelProgress(store, w, r) })
		r.Post("/{id}/turns", func(w http.ResponseWriter, r *http.Request) { s.tripOperation(store, w, r, false) })
		r.Post("/{id}/actions", func(w http.ResponseWriter, r *http.Request) { s.tripOperation(store, w, r, true) })
	})
	r.Get("/api/shared/{token}", store.shared)
	r.Post("/api/shared/{token}", store.shared)
	r.Get("/api/map-config", func(w http.ResponseWriter, r *http.Request) {
		writeSnapshot(w, map[string]any{"tile_url": envOrDefault("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")})
	})
	r.Get("/api/local/status", func(w http.ResponseWriter, r *http.Request) {
		writeSnapshot(w, map[string]any{"mode": "local_demo", "data_mode": "synthetic", "real_booking": false})
	})
	web, _ := fs.Sub(tripWeb, "web")
	// Native local development serves edits immediately; packaged builds keep
	// using the embedded assets when no directory is configured.
	if directory := os.Getenv("LOCAL_WEB_DIR"); directory != "" {
		web = os.DirFS(directory)
	}
	staticFiles := http.FileServer(http.FS(web))
	r.Handle("/*", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-cache")
		staticFiles.ServeHTTP(w, r)
	}))
}
func (s *API) tripOperation(store *TripStore, w http.ResponseWriter, r *http.Request, action bool) {
	var input struct {
		Message             string         `json:"message"`
		Transport           *TransportEdit `json:"transport"`
		RequestTime         string         `json:"request_time"`
		RequestOrigin       string         `json:"request_origin"`
		HotelID             string         `json:"hotel_id"`
		CheckIn             string         `json:"check_in"`
		GuestName           string         `json:"guest_name"`
		Stay                *HotelStayEdit `json:"stay"`
		AcceptBudgetOverrun bool           `json:"accept_budget_overrun"`
		ConfirmPrototype    bool           `json:"confirm_prototype"`
		Type                string         `json:"type"`
		PlanID              string         `json:"plan_id"`
		DestinationID       string         `json:"destination_id"`
		ExpectedRevision    *int           `json:"expected_revision"`
		Key                 string         `json:"idempotency_key"`
	}
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 32<<10))
	dec.DisallowUnknownFields()
	if dec.Decode(&input) != nil || dec.Decode(new(any)) != io.EOF || input.ExpectedRevision == nil || *input.ExpectedRevision < 0 || len(input.Key) < 8 || len(input.Key) > 128 || (!action && (strings.TrimSpace(input.Message) == "" || len([]rune(input.Message)) > 12000)) {
		tripError(w, 400, "invalid_request", "Нужны корректные параметры, revision и idempotency_key.", nil)
		return
	}
	id, owner := chi.URLParam(r, "id"), ownerCookie(w, r, false)
	unlock := store.lock(id)
	defer unlock()
	file, err := store.read(id, owner)
	if err != nil {
		tripError(w, 404, "not_found", "Поездка не найдена.", nil)
		return
	}
	payload, _ := json.Marshal(input)
	digest := hashText(r.URL.Path + string(payload))
	if previous, ok := file.Operations[input.Key]; ok {
		if previous.Hash != digest {
			tripError(w, 409, "idempotency_conflict", "Этот ключ уже использован для другого действия.", file.Snapshot["revision"])
			return
		}
		writeSnapshot(w, previous.Reply)
		return
	}
	snap := file.Snapshot
	revision := int(snap["revision"].(float64))
	if *input.ExpectedRevision != revision {
		tripError(w, 409, "stale_revision", "Поездка уже изменена. Обновите состояние.", revision)
		return
	}
	if len(file.Operations) >= 500 {
		tripError(w, 409, "session_limit", "Создайте новую поездку: достигнут предел действий.", revision)
		return
	}
	if snap["hotel_booking"] != nil && (!action || !extraAction(input.Type)) {
		tripError(w, 409, "already_booked", "Оформление уже завершено. Начните новый поиск.", revision)
		return
	}
	if snap["booking"] != nil {
		if !action || input.Type != "confirm_booking_demo" {
			tripError(w, 409, "already_booked", "Учебная поездка уже оформлена. Начните новую.", revision)
			return
		}
		writeSnapshot(w, snap)
		return
	}
	if !action {
		previousOptions := asList(cloneTrip(snap)["hotel_options"])
		previousHotel, previousSpec := cloneTrip(asMap(snap["selected_hotel"])), cloneTrip(asMap(snap["trip_spec"]))
		if p := asMap(snap["journey_recovery"]); p != nil {
			previousHotel, previousSpec = asMap(p["hotel"]), asMap(p["spec"])
			previousOptions = previewOptions(p, "previous", p["hotel"])
		}
		if p := asMap(snap["journey_preview"]); p != nil {
			previousHotel, previousSpec = asMap(p["previous_hotel"]), asMap(p["previous_spec"])
			previousOptions = previewOptions(p, "previous", p["previous_hotel"])
		}
		previousSearchURL := snap["search_url"]
		if recovery := asMap(snap["journey_recovery"]); recovery != nil {
			previousSearchURL = recovery["search_url"]
		}
		// Supply the saved choice for a follow-up age/guest clarification.
		if previousSpec["destination"] == asMap(snap["trip_spec"])["destination"] {
			snap["selected_hotel"] = previousHotel
		} else {
			snap["selected_hotel"] = nil
		}
		snap["journey_preview"] = nil
		snap["journey_recovery"] = nil
		ctx, cancel := context.WithTimeout(r.Context(), agentTimeout())
		defer cancel()
		ctx = metadata.AppendToOutgoingContext(ctx, "x-progress-token", hashText(owner+":"+id+":"+input.Key))
		reply, callErr := s.agent.RunTurn(ctx, &pb.TurnRequest{Message: input.Message, StateJson: stateFor(snap), Caller: owner})
		snap["selected_hotel"] = nil
		var turn map[string]any
		// Any new message invalidates an outstanding preview, including model failure.
		snap["change_preview"], snap["checkout_allowed"] = nil, false
		if callErr != nil || reply == nil || reply.Caller != owner || json.Unmarshal([]byte(reply.TurnJson), &turn) != nil {
			snap["status"], snap["assistant_message"] = "error", "Модель не ответила вовремя. Поездка сохранена, прежнее предложение изменения отменено."
			snap["error_code"] = "model_unavailable"
		} else if turn["status"] == "error" {
			snap["status"], snap["assistant_message"], snap["error_code"] = "error", turn["assistant_message"], turn["error_code"]
		} else {
			copyTurn(snap, turn)
			if previousHotel != nil && snap["status"] == "choosing" && len(asList(snap["hotel_options"])) > 0 {
				proposed := asMap(asList(snap["hotel_options"])[0])
				for _, item := range asList(snap["hotel_options"]) {
					h := asMap(item)
					if h["id"] == previousHotel["id"] {
						proposed = h
						break
					}
				}
				if validHotelQuote(proposed) {
					if proposed["id"] == previousHotel["id"] && hotelPlanTotal(proposed) == hotelPlanTotal(previousHotel) && (sameJourneySpec(previousSpec, asMap(snap["trip_spec"])) || asMap(snap["selection"])["open_panel"] == "transport") {
						snap["selected_hotel"], snap["status"] = proposed, "hotel_checkout"
					} else {
						setJourneyPreview(snap, previousHotel, previousSpec, proposed, previousOptions)
					}
				}
			}
			if preview := asMap(snap["change_preview"]); preview != nil {
				preview["based_on_revision"] = revision + 1
			}
		}
		if snap["search_mode"] == "hotels" && (snap["status"] == "needs_input" || snap["status"] == "no_solution" || snap["status"] == "error") && (previousHotel != nil || len(previousOptions) > 0) {
			// Previous quotes remain visible, but are never valid for the pending criteria.
			snap["journey_recovery"] = map[string]any{"hotel": previousHotel, "spec": previousSpec, "previous_options": previousOptions, "search_url": previousSearchURL}
			snap["selected_hotel"], snap["hotel_options"] = previousHotel, previousOptions
		}
	} else {
		if snap["search_mode"] == "hotels" {
			var message string
			completingTickets := input.Type == "change_transport" && input.Transport != nil && input.Transport.Tickets != nil && asMap(snap["trip_spec"])["transport_owned"] == true && snap["status"] == "needs_input"
			if snap["journey_recovery"] != nil && input.Type != "restore_journey" && !completingTickets {
				message = "Сначала уточните новые условия в чате или вернитесь к сохранённому плану."
			} else if extraAction(input.Type) {
				message = s.tripExtra(r.Context(), snap, input.Type, input.RequestTime, owner, input.RequestOrigin)
			} else if input.Type == "restore_journey" {
				p := asMap(snap["journey_recovery"])
				if p == nil {
					message = "Прежний план не найден."
				} else {
					snap["selected_hotel"], snap["trip_spec"], snap["hotel_options"] = p["hotel"], p["spec"], previewOptions(p, "previous", p["hotel"])
					snap["search_url"] = p["search_url"]
					syncHotelSearchURL(snap)
					snap["journey_recovery"], snap["status"], snap["assistant_message"] = nil, "choosing", "Вернули прежнюю подборку и условия."
					if asMap(p["hotel"]) != nil {
						snap["status"] = "hotel_checkout"
					}
					snap["questions"], snap["selection"], snap["error_code"] = []any{}, map[string]any{}, nil
				}
			} else if input.Type == "accept_journey_change" || input.Type == "discard_journey_change" {
				message = applyJourneyPreview(snap, input.Type == "accept_journey_change")
			} else if snap["journey_preview"] != nil {
				message = "Сначала примите изменение или вернитесь к прежнему плану."
			} else if input.Type == "change_transport" {
				message = s.changeTransport(r.Context(), snap, input.HotelID, input.Transport, owner)
			} else if journeyEnabled(asMap(snap["trip_spec"])) && (input.Type == "select_hotel" || input.Type == "confirm_hotel_booking" || input.Type == "update_hotel_stay") {
				candidate := cloneTrip(snap)
				previous := cloneTrip(asMap(snap["selected_hotel"]))
				if input.Type == "update_hotel_stay" {
					message = updateHotelStay(candidate, input.Stay)
				}
				h := asMap(candidate["selected_hotel"])
				if input.Type == "select_hotel" {
					h = nil
					for _, item := range asList(candidate["hotel_options"]) {
						option := asMap(item)
						if option["id"] == input.HotelID {
							h = option
							break
						}
					}
				}
				if message == "" && h == nil {
					message = "Выберите поездку из текущей подборки."
				}
				if message == "" {
					fresh, err := s.refreshJourney(r.Context(), candidate, h, owner)
					if err != nil {
						message = err.Error()
					} else {
						candidate["hotel_options"], candidate["selected_hotel"] = replaceJourneyOption(asList(candidate["hotel_options"]), fresh), fresh
						if input.Type == "update_hotel_stay" {
							if err := s.refreshJourneyOptions(r.Context(), candidate, fresh, owner); err != nil {
								message = err.Error()
							} else {
								setJourneyPreview(candidate, previous, cloneTrip(asMap(snap["trip_spec"])), fresh, asList(cloneTrip(snap)["hotel_options"]))
							}
						} else if input.Type == "confirm_hotel_booking" {
							message = journeyBlock(fresh, input.AcceptBudgetOverrun)
							if message == "" && journeyTotal(h) != journeyTotal(fresh) {
								message = "Стоимость изменилась. Обновите расчёт перед подтверждением."
							}
							if message == "" {
								if input.AcceptBudgetOverrun {
									asMap(fresh["journey"])["budget_override_accepted"] = true
								}
								message = hotelAction(candidate, input.Type, input.HotelID, input.CheckIn, input.GuestName, input.ConfirmPrototype)
							}
						} else {
							message = hotelAction(candidate, input.Type, input.HotelID, input.CheckIn, input.GuestName, input.ConfirmPrototype)
						}
						if message == "" {
							for k, v := range candidate {
								snap[k] = v
							}
						}
					}
				}
			} else if input.Type == "update_hotel_stay" {
				message = updateHotelStay(snap, input.Stay)
			} else if input.Type == "confirm_hotel_booking" && hotelBudgetExceeded(snap) && !input.AcceptBudgetOverrun {
				message = "Новая стоимость выше бюджета. Подтвердите новую сумму перед оформлением."
			} else {
				message = hotelAction(snap, input.Type, input.HotelID, input.CheckIn, input.GuestName, input.ConfirmPrototype)
			}
			if message != "" {
				tripError(w, 409, "action_unavailable", message, revision)
				return
			}
		} else {
			fail := func(message string) { tripError(w, 409, "action_unavailable", message, revision) }
			switch input.Type {
			case "select_destination":
				found := ""
				for _, v := range asList(snap["destination_options"]) {
					d := asMap(v)
					if d["id"] == input.DestinationID {
						found = stringValue(d["name"])
						break
					}
				}
				if found == "" {
					fail("Выберите направление из текущего списка.")
					return
				}
				spec := asMap(snap["trip_spec"])
				spec["destination"] = found
				turn, err := s.evaluateTrip(r.Context(), snap, "", owner)
				if err != nil {
					tripError(w, 503, "tools_unavailable", "Каталог недоступен.", revision)
					return
				}
				copyTurn(snap, turn)
				snap["selected_plan"] = nil
			case "select_plan", "accept_change":
				var plan map[string]any
				if input.Type == "accept_change" {
					preview := asMap(snap["change_preview"])
					if preview == nil || int(preview["based_on_revision"].(float64)) != revision {
						fail("Предложение устарело. Пересчитайте поездку.")
						return
					}
					plan = asMap(preview["proposed_plan"])
				} else {
					if snap["change_preview"] != nil {
						fail("Сначала примите предложенное изменение.")
						return
					}
					for _, v := range asList(snap["options"]) {
						p := asMap(v)
						if p["id"] == input.PlanID {
							plan = p
							break
						}
					}
				}
				if plan == nil {
					fail("Вариант отсутствует в текущем предложении.")
					return
				}
				checked, err := s.evaluateTrip(r.Context(), snap, stringValue(plan["id"]), owner)
				if err != nil || len(asList(checked["options"])) != 1 {
					fail("План не прошёл повторную проверку текущих условий.")
					return
				}
				snap["selected_plan"] = asList(checked["options"])[0]
				snap["change_preview"] = nil
				snap["status"], snap["checkout_allowed"], snap["assistant_message"] = "ready", true, "Поездка выбрана. Можно изменить условия или подтвердить учебное оформление."
			case "confirm_booking_demo":
				selected := asMap(snap["selected_plan"])
				if selected == nil || snap["change_preview"] != nil || snap["checkout_allowed"] != true {
					fail("Сначала выберите и подтвердите актуальную поездку.")
					return
				}
				checked, err := s.evaluateTrip(r.Context(), snap, stringValue(selected["id"]), owner)
				if err != nil || len(asList(checked["options"])) != 1 {
					fail("План больше не проходит проверку.")
					return
				}
				plan := asMap(asList(checked["options"])[0])
				snap["selected_plan"] = plan
				snap["booking"] = map[string]any{"demo_booking_id": "DEMO-" + randomID()[:10], "plan_id": plan["id"], "total": plan["total"], "is_demo": true}
				snap["status"], snap["checkout_allowed"], snap["assistant_message"] = "booked_demo", false, "Учебное оформление завершено. Реальные услуги не забронированы, деньги не списаны."
			default:
				tripError(w, 400, "unknown_action", "Неизвестное действие.", revision)
				return
			}
		}
	}
	messages := asList(snap["messages"])
	if !action {
		if snap["search_title"] == nil {
			title := []rune(input.Message)
			if len(title) > 120 {
				title = title[:120]
			}
			snap["search_title"] = string(title)
		}
		messages = append(messages, map[string]any{"role": "user", "text": input.Message})
	}
	messages = append(messages, map[string]any{"role": "assistant", "text": snap["assistant_message"]})
	if len(messages) > 100 {
		messages = messages[len(messages)-100:]
	}
	snap["messages"] = messages
	history := asList(snap["history"])
	event := input.Type
	if !action {
		event = input.Message
	}
	chars := []rune(event)
	if len(chars) > 480 {
		chars = chars[:480]
	}
	history = append(history, string(chars))
	if len(history) > 10 {
		history = history[len(history)-10:]
	}
	snap["history"] = history
	snap["revision"], snap["request_id"] = revision+1, randomID()
	data, _ := json.Marshal(snap)
	file.Operations[input.Key] = savedOperation{Hash: digest, Reply: data}
	if err = store.save(id, file); err != nil {
		tripError(w, 500, "storage", "Не удалось сохранить результат. Повторите действие с тем же ключом.", revision)
		return
	}
	writeSnapshot(w, snap)
}

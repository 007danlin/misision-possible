package main

import (
	"context"
	pb "core/proto"
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type startupStatus struct {
	Phase          string  `json:"phase"`
	Message        string  `json:"message"`
	Ready          bool    `json:"ready"`
	Downloaded     int64   `json:"downloaded_bytes,omitempty"`
	Total          int64   `json:"total_bytes,omitempty"`
	Percent        float64 `json:"percent,omitempty"`
	BytesPerSecond float64 `json:"bytes_per_second,omitempty"`
	Elapsed        float64 `json:"elapsed_seconds,omitempty"`
	Attempt        int     `json:"attempt,omitempty"`
}

// Readiness is separate from process health: the web server starts while weights
// are downloading, but no trip operation is sent to an unprepared agent.
func (s *API) startupHandler(next http.Handler) http.Handler {
	file := os.Getenv("MODEL_STATUS_FILE")
	if file == "" {
		return next
	}
	var mu sync.Mutex
	var last time.Time
	current := startupStatus{Phase: "starting", Message: "Подготавливаем сервисы"}
	client := &http.Client{Timeout: time.Second}
	probe := func(ctx context.Context) startupStatus {
		mu.Lock()
		defer mu.Unlock()
		if time.Since(last) < 2*time.Second {
			return current
		}
		last = time.Now()
		current = startupStatus{Phase: "starting", Message: "Подготавливаем сервисы"}
		if data, err := os.ReadFile(file); err == nil {
			_ = json.Unmarshal(data, &current)
		}
		// Do not trust a stale progress file for readiness after a container restart.
		current.Ready = false
		// The process health RPC alone stays alive if a model container dies.
		// Require the inference server as well, including on warm restarts.
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, envOrDefault("MODEL_HEALTH_URL", "http://model:8082/health"), nil)
		modelReady := false
		if err == nil {
			if resp, e := client.Do(req); e == nil {
				resp.Body.Close()
				modelReady = resp.StatusCode == http.StatusOK
			}
		}
		if !modelReady {
			return current
		}
		current.Phase = "warmup"
		current.Message = "Прогреваем модель перед первым запросом"
		current.Percent = 0
		current.BytesPerSecond = 0
		check, cancel := context.WithTimeout(ctx, time.Second)
		defer cancel()
		reply, err := s.agent.Predict(check, &pb.PredictRequest{Name: "health", Caller: "startup"})
		if err == nil && reply.Caller == "startup" {
			current = startupStatus{Phase: "ready", Message: "Всё готово", Ready: true}
		}
		return current
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			next.ServeHTTP(w, r)
			return
		}
		state := probe(r.Context())
		w.Header().Set("Cache-Control", "no-store")
		if r.URL.Path == "/api/runtime/status" || r.URL.Path == "/ready" {
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			if r.URL.Path == "/ready" && !state.Ready {
				w.WriteHeader(http.StatusServiceUnavailable)
			}
			_ = json.NewEncoder(w).Encode(state)
			return
		}
		if !state.Ready {
			if strings.HasPrefix(r.URL.Path, "/api/") {
				w.Header().Set("Retry-After", "3")
				writeError(w, http.StatusServiceUnavailable, "Подготовка модели ещё идёт. Дождитесь завершения на главной странице.")
				return
			}
			if r.Method == http.MethodGet || r.Method == http.MethodHead {
				page, err := tripWeb.ReadFile("web/startup.html")
				if err == nil {
					w.Header().Set("Content-Type", "text/html; charset=utf-8")
					if r.Method != http.MethodHead {
						_, _ = w.Write(page)
					}
					return
				}
			}
		}
		next.ServeHTTP(w, r)
	})
}

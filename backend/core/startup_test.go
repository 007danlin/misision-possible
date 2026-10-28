package main

import (
	"context"
	pb "core/proto"
	"encoding/json"
	"errors"
	"google.golang.org/grpc"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type startupAgent struct {
	pb.PredictorClient
	ready bool
}

func (a *startupAgent) Predict(_ context.Context, req *pb.PredictRequest, _ ...grpc.CallOption) (*pb.PredictReply, error) {
	if !a.ready {
		return nil, errors.New("warming up")
	}
	return &pb.PredictReply{Caller: req.Caller}, nil
}
func TestColdStartupServesProgressBeforeAgentAndBlocksTripMutations(t *testing.T) {
	file := filepath.Join(t.TempDir(), "model.json")
	if err := os.WriteFile(file, []byte(`{"phase":"downloading","message":"Скачиваем модель","downloaded_bytes":500,"total_bytes":1000,"percent":50}`), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("MODEL_STATUS_FILE", file)
	model := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(503) }))
	defer model.Close()
	t.Setenv("MODEL_HEALTH_URL", model.URL)
	api := NewAPI(&startupAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	for _, test := range []struct {
		method, path string
		code         int
		contains     string
	}{
		{"GET", "/plan.html", 200, "Готовим помощника"},
		{"GET", "/api/runtime/status", 200, `"percent":50`},
		{"GET", "/ready", 503, `"ready":false`},
		{"GET", "/health", 200, `"status":"ok"`},
		{"POST", "/api/sessions/", 503, "Подготовка модели"},
	} {
		r := httptest.NewRecorder()
		handler.ServeHTTP(r, httptest.NewRequest(test.method, test.path, nil))
		if r.Code != test.code || !strings.Contains(r.Body.String(), test.contains) {
			t.Fatalf("%s %s: %d %s", test.method, test.path, r.Code, r.Body.String())
		}
	}
}
func TestStaleReadyFileDoesNotBypassAgentReadiness(t *testing.T) {
	file := filepath.Join(t.TempDir(), "model.json")
	_ = os.WriteFile(file, []byte(`{"phase":"ready","ready":true}`), 0600)
	t.Setenv("MODEL_STATUS_FILE", file)
	model := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	defer model.Close()
	t.Setenv("MODEL_HEALTH_URL", model.URL)
	api := NewAPI(&startupAgent{})
	r := httptest.NewRecorder()
	api.Handler().ServeHTTP(r, httptest.NewRequest("GET", "/ready", nil))
	if r.Code != 503 || !strings.Contains(r.Body.String(), `"phase":"warmup"`) {
		t.Fatalf("stale readiness accepted: %d %s", r.Code, r.Body.String())
	}
}
func TestReadyAgentOpensOriginalApplication(t *testing.T) {
	model := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	defer model.Close()
	t.Setenv("MODEL_HEALTH_URL", model.URL)
	t.Setenv("MODEL_STATUS_FILE", filepath.Join(t.TempDir(), "missing.json"))
	api := NewAPI(&startupAgent{ready: true})
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	for _, path := range []string{"/ready", "/plan.html"} {
		r := httptest.NewRecorder()
		handler.ServeHTTP(r, httptest.NewRequest("GET", path, nil))
		if r.Code != 200 {
			t.Fatalf("%s: %d", path, r.Code)
		}
		if path == "/ready" && !strings.Contains(r.Body.String(), `"ready":true`) {
			t.Fatal(r.Body.String())
		}
		if path == "/plan.html" && !strings.Contains(r.Body.String(), "/app.js") {
			t.Fatal("application did not open")
		}
	}
}

func TestHealthyAgentDoesNotHideUnavailableModel(t *testing.T) {
	t.Setenv("MODEL_STATUS_FILE", filepath.Join(t.TempDir(), "missing.json"))
	model := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(503) }))
	defer model.Close()
	t.Setenv("MODEL_HEALTH_URL", model.URL)
	api := NewAPI(&startupAgent{ready: true})
	r := httptest.NewRecorder()
	api.Handler().ServeHTTP(r, httptest.NewRequest("GET", "/ready", nil))
	if r.Code != 503 || !strings.Contains(r.Body.String(), `"ready":false`) {
		t.Fatalf("unavailable model accepted: %d %s", r.Code, r.Body.String())
	}
}

func TestWarmupPreservesDownloadedBytesWithoutClaimingReadiness(t *testing.T) {
	file := filepath.Join(t.TempDir(), "model.json")
	if err := os.WriteFile(file, []byte(`{"phase":"loading","downloaded_bytes":2500000000,"total_bytes":2500000000,"percent":100}`), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("MODEL_STATUS_FILE", file)
	model := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(200) }))
	defer model.Close()
	t.Setenv("MODEL_HEALTH_URL", model.URL)
	api := NewAPI(&startupAgent{})
	r := httptest.NewRecorder()
	api.Handler().ServeHTTP(r, httptest.NewRequest("GET", "/api/runtime/status", nil))
	var status startupStatus
	if err := json.Unmarshal(r.Body.Bytes(), &status); err != nil {
		t.Fatal(err)
	}
	if status.Ready || status.Phase != "warmup" || status.Downloaded != 2500000000 || status.Total != 2500000000 || status.Percent != 100 {
		t.Fatalf("lost download progress or premature readiness: %+v", status)
	}
}

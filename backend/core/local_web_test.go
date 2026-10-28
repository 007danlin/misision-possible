package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLocalStatusDistinguishesPublicContentFromEstimatedPrices(t *testing.T) {
	for _, test := range []struct {
		source, expectedSource, expectedMode string
	}{{"", "public", "public_catalogue"}, {"public", "public", "public_catalogue"}, {"synthetic", "synthetic", "synthetic"}} {
		t.Run(test.source, func(t *testing.T) {
			t.Setenv("JOURNEY_DATA_SOURCE", test.source)
			api := NewAPI(&sessionAgent{})
			api.trips = &TripStore{dir: t.TempDir()}
			response := httptest.NewRecorder()
			api.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/api/local/status", nil))
			var status map[string]any
			if err := json.Unmarshal(response.Body.Bytes(), &status); err != nil {
				t.Fatal(err)
			}
			if response.Code != http.StatusOK || status["hotel_data_source"] != test.expectedSource || status["data_mode"] != test.expectedMode || status["pricing_mode"] != "estimated" || status["real_booking"] != false {
				t.Fatalf("incorrect runtime provenance: %d %v", response.Code, status)
			}
		})
	}
}

func TestLocalWebDirectoryServesEditsWithoutRestart(t *testing.T) {
	directory := t.TempDir()
	t.Setenv("LOCAL_WEB_DIR", directory)
	api := NewAPI(&sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	for _, content := range []string{"initial frontend", "updated frontend"} {
		if err := os.WriteFile(filepath.Join(directory, "app.js"), []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
		request := httptest.NewRequest(http.MethodGet, "/app.js?v=unchanged", nil)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK || response.Body.String() != content {
			t.Fatalf("response = %d %q", response.Code, response.Body.String())
		}
		if response.Header().Get("Cache-Control") != "no-cache" {
			t.Fatal("local frontend must be revalidated")
		}
	}
}

func TestLocalWebDefaultsToEmbeddedAssets(t *testing.T) {
	t.Setenv("LOCAL_WEB_DIR", "")
	api := NewAPI(&sessionAgent{})
	api.trips = &TripStore{dir: t.TempDir()}
	response := httptest.NewRecorder()
	api.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/plan.html", nil))
	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), "/app.js") {
		t.Fatalf("embedded frontend unavailable: %d", response.Code)
	}
}

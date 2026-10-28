package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

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

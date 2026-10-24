package handlers

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/rs/zerolog"

	"auth/internal/crypto"
)

func TestServerMetricsAreIsolated(t *testing.T) {
	crypt, err := crypto.New("test", "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer crypt.Close()
	first := New(nil, nil, crypt, nil, zerolog.New(io.Discard), "PROD").Handler()
	second := New(nil, nil, crypt, nil, zerolog.New(io.Discard), "PROD").Handler()
	first.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("GET", "/health", nil))
	response := httptest.NewRecorder()
	first.ServeHTTP(response, httptest.NewRequest("GET", "/metrics", nil))
	if !strings.Contains(response.Body.String(), "http_requests_total 1\n") {
		t.Fatal(response.Body.String())
	}
	response = httptest.NewRecorder()
	second.ServeHTTP(response, httptest.NewRequest("GET", "/metrics", nil))
	if !strings.Contains(response.Body.String(), "http_requests_total 0\n") {
		t.Fatal("server metrics shared across instances")
	}
}

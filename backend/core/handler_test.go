package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestParseCaller(t *testing.T) {
	for _, tc := range []struct {
		name, body string
		status     int
		valid      bool
	}{
		{"active", `{"user_id":42,"status":"active"}`, 200, true},
		{"banned", `{"user_id":42,"status":"banned"}`, 200, false},
		{"revoked", `{}`, 401, false},
		{"expired", `{}`, 403, false},
		{"unavailable", `{}`, 500, false},
		{"bad response", `invalid`, 200, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			auth := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path != "/api/auth/users/me" || r.Header.Get("Authorization") != "Bearer test-token" {
					t.Error("incorrect auth request")
				}
				w.WriteHeader(tc.status)
				w.Write([]byte(tc.body))
			}))
			defer auth.Close()
			api := NewAPI(auth.URL, auth.Client(), nil)
			req := httptest.NewRequest("POST", "/api/core/handle", strings.NewReader(`{"name":"Alice"}`))
			req.Header.Set("Authorization", "Bearer test-token")
			caller, err := api.ParseCaller(req)
			if (err == nil) != tc.valid {
				t.Fatalf("caller=%q error=%v", caller, err)
			}
			if tc.valid && caller != "42" {
				t.Fatal(caller)
			}
		})
	}
}
func TestParseCallerMissingToken(t *testing.T) {
	for _, token := range []string{"", "demo-admin", "Bearer "} {
		req := httptest.NewRequest("POST", "/", nil)
		req.Header.Set("Authorization", token)
		if _, err := NewAPI("", &http.Client{}, nil).ParseCaller(req); err == nil {
			t.Fatal("accepted invalid token")
		}
	}
}

package handlers

import (
	"crypto/ed25519"
	"crypto/rand"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"auth/internal/types"
)

func TestJWTRejectsInvalidTokens(t *testing.T) {
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	_, other, _ := ed25519.GenerateKey(rand.Reader)
	for _, tc := range []struct {
		name    string
		expires *jwt.NumericDate
		key     ed25519.PrivateKey
	}{
		{"expired", jwt.NewNumericDate(time.Now().Add(-time.Minute)), priv},
		{"no expiry", nil, priv},
		{"forged", jwt.NewNumericDate(time.Now().Add(time.Minute)), other},
	} {
		t.Run(tc.name, func(t *testing.T) {
			claims := types.Claims{UserID: "1", SessionID: "session", RegisteredClaims: jwt.RegisteredClaims{ExpiresAt: tc.expires}}
			token, _ := jwt.NewWithClaims(jwt.SigningMethodEdDSA, claims).SignedString(tc.key)
			req := httptest.NewRequest("GET", "/", nil)
			req.Header.Set("Authorization", "Bearer "+token)
			w := httptest.NewRecorder()
			JWTAuth(pub, nil)(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { t.Fatal("invalid token accepted") })).ServeHTTP(w, req)
			if w.Code != http.StatusUnauthorized {
				t.Fatalf("status %d", w.Code)
			}
		})
	}
}

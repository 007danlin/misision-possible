package handlers

import (
	"context"
	"crypto/ed25519"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/bytedance/sonic"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/golang-jwt/jwt/v5"

	"auth/internal/ports"
	"auth/internal/types"
)

type contextKey string

const (
	ctxUserID    contextKey = "user_id"
	ctxSessionID contextKey = "session_id"
	ctxRole      contextKey = "role"
)

func WriteJson(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = sonic.ConfigDefault.NewEncoder(w).Encode(v)
}

func (s *Server) LoggerMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		ww := middleware.NewWrapResponseWriter(w, r.ProtoMajor)

		next.ServeHTTP(ww, r)

		duration := time.Since(start)
		status := ww.Status()

		if s.style == "PROD" {
			s.logger.Info().
				Str("method", r.Method).
				Int("status", status).
				Str("path", r.URL.Path).
				Dur("duration", duration).
				Send()
			return
		}

		var statusColor string
		switch {
		case status >= 200 && status < 300:
			statusColor = fmt.Sprintf("\033[97;42m %d \033[0m", status)
		case status >= 300 && status < 400:
			statusColor = fmt.Sprintf("\033[97;44m %d \033[0m", status)
		case status >= 400 && status < 500:
			statusColor = fmt.Sprintf("\033[90;43m %d \033[0m", status)
		default:
			statusColor = fmt.Sprintf("\033[97;41m %d \033[0m", status)
		}

		var methodColor string
		switch r.Method {
		case "GET":
			methodColor = "\033[97;44m GET \033[0m"
		case "POST":
			methodColor = "\033[97;46m POST \033[0m"
		case "PUT":
			methodColor = "\033[97;43m PUT \033[0m"
		case "DELETE":
			methodColor = "\033[97;41m DELETE \033[0m"
		default:
			methodColor = fmt.Sprintf("\033[97;45m %s \033[0m", r.Method)
		}

		logLine := fmt.Sprintf("%s  %s  %s %s", methodColor, statusColor, r.URL.Path, duration.String())
		s.logger.Info().Msg(logLine)
	})
}

func JWTAuth(pubKey ed25519.PublicKey, cacheClient ports.Sessions) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			tokenStr, ok := strings.CutPrefix(authHeader, "Bearer ")
			if !ok || tokenStr == "" {
				WriteErr(w, http.StatusUnauthorized, "ERR_UNAUTHORIZED", "нет токена")
				return
			}

			claims := &types.Claims{}
			token, err := jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (interface{}, error) {
				if _, ok := t.Method.(*jwt.SigningMethodEd25519); !ok {
					return nil, errors.New("unexpected signing method")
				}
				return pubKey, nil
			}, jwt.WithExpirationRequired())
			if err != nil || !token.Valid || claims.UserID == "" || claims.SessionID == "" {
				WriteErr(w, http.StatusUnauthorized, "ERR_TOKEN_EXPIRED", "токен невалиден или истёк")
				return
			}

			blacklisted, err := cacheClient.Exists(r.Context(), "blacklist:"+claims.SessionID)
			if err != nil {
				WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка проверки сессии")
				return
			}
			if blacklisted {
				WriteErr(w, http.StatusUnauthorized, "ERR_TOKEN_EXPIRED", "сессия отозвана")
				return
			}

			ctx := context.WithValue(r.Context(), ctxUserID, claims.UserID)
			ctx = context.WithValue(ctx, ctxSessionID, claims.SessionID)
			ctx = context.WithValue(ctx, ctxRole, claims.Role)

			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func RequireRole(role string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			userRole, ok := r.Context().Value(ctxRole).(string)
			if !ok || userRole != role {
				WriteErr(w, http.StatusForbidden, "ERR_FORBIDDEN", "недостаточно прав")
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func WriteErr(w http.ResponseWriter, status int, code, message string) {
	WriteJson(w, status, types.ErrorResponse{
		Error: types.ErrorBody{Code: code, Message: message},
	})
}

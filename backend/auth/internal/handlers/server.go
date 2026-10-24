package handlers

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog"

	"auth/internal/crypto"
	"auth/internal/ports"
	"auth/internal/service"
	"auth/internal/types"
)

type Server struct {
	users    ports.Users
	cache    ports.Sessions
	mailer   ports.Mailer
	crypto   *crypto.Service
	sessions *service.Sessions
	logger   zerolog.Logger
	style    string
	metrics  metrics
}

func New(users ports.Users, cache ports.Sessions, crypt *crypto.Service, mailer ports.Mailer, log zerolog.Logger, style string) *Server {
	return &Server{users: users, cache: cache, crypto: crypt, mailer: mailer, logger: log, style: style, sessions: service.NewSessions(cache, crypt)}
}

func (s *Server) Handler() http.Handler {
	r := chi.NewRouter()
	r.Use(s.metrics.middleware)
	r.Use(s.LoggerMiddleware)
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
			next.ServeHTTP(w, r)
		})
	})
	s.registerRoutes(r)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		WriteJson(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	r.NotFound(func(w http.ResponseWriter, r *http.Request) {
		WriteJson(w, 404, types.Response{Status: "error", Message: "not found"})
	})
	return r
}

func (s *Server) registerRoutes(r chi.Router) {
	// --- Регистрация и верификация email ---
	r.Group(func(r chi.Router) {
		r.Post("/api/auth/auth/register", s.handleRegistration)         // создать юзера, статус unverified
		r.Post("/api/auth/auth/verify-email", s.handleVerifyEmail)      // подтвердить email кодом -> active + токены
		r.Post("/api/auth/auth/resend-verification", s.handleResendVer) // повторно прислать код, rate-limit 60s
	})

	// --- Логин ---
	r.Group(func(r chi.Router) {
		r.Post("/api/auth/auth/login", s.handleLogin)       // email+пароль -> токены или requires_2fa
		r.Post("/api/auth/auth/2fa/verify", s.handle2faVer) // pending_token + код -> токены
		r.Post("/api/auth/auth/refresh", s.handleRefresh)   // refresh_token -> новая пара (ротация)
	})

	// --- Сессии: нужен access_token, чтобы знать какую сессию отзывать ---
	r.Group(func(r chi.Router) {
		r.Use(JWTAuth(s.crypto.PublicKey(), s.cache))

		r.Post("/api/auth/auth/logout", s.handleLogout)        // выйти с текущей сессии
		r.Post("/api/auth/auth/logout-all", s.handleLogoutAll) // выйти со всех сессий
	})

	// --- Восстановление пароля ---
	r.Group(func(r chi.Router) {
		r.Post("/api/auth/auth/forgot-password", s.handleForgotPassword) // запросить код сброса
		r.Post("/api/auth/auth/reset-password", s.handleResetPassword)   // сбросить пароль по коду, отзыв всех сессий
	})

	// --- Профиль пользователя ---
	// требует Authorization: Bearer <access_token>
	r.Group(func(r chi.Router) {
		r.Use(JWTAuth(s.crypto.PublicKey(), s.cache))

		r.Get("/api/auth/users/me", s.handleUsMe)                        // свой профиль
		r.Patch("/api/auth/users/me", s.handleUpdMe)                     // изменить nickname/avatar
		r.Post("/api/auth/users/me/change-password", s.handleChangePass) // сменить пароль, отзыв др. сессий

		r.Post("/api/auth/users/me/change-email", s.handleChangeEmail)                // шаг 1: new_email -> код на новый ящик
		r.Post("/api/auth/users/me/change-email/confirm", s.handleChangeEmailConfirm) // шаг 2: code -> email меняется

		r.Post("/api/auth/users/me/2fa/enable", s.handle2faEnable)   // сгенерить TOTP-секрет + QR
		r.Post("/api/auth/users/me/2fa/confirm", s.handle2faConfirm) // подтвердить первым кодом -> включить
		r.Post("/api/auth/users/me/2fa/disable", s.handle2faDisable) // пароль + код -> выключить
	})

	// --- Admin ---
	// требует Authorization + role: admin
	r.Group(func(r chi.Router) {
		r.Use(JWTAuth(s.crypto.PublicKey(), s.cache))
		r.Use(RequireRole("admin"))

		r.Get("/api/auth/admin/users", s.handleUsers)               // список юзеров, пагинация
		r.Get("/api/auth/admin/users/{id}", s.handleGetUsers)       // юзер по id
		r.Patch("/api/auth/admin/users/{id}/ban", s.handleBan)      // забанить, мгновенный отзыв сессий
		r.Patch("/api/auth/admin/users/{id}/unban", s.handleUnban)  // разбанить
		r.Patch("/api/auth/admin/users/{id}/role", s.handleUpdRole) // сменить роль user<->admin
	})
}

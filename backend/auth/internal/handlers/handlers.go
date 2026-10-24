package handlers

import (
	"context"
	"io"
	"net/http"
	"strconv"
	"time"

	"github.com/bytedance/sonic"
	"github.com/go-chi/chi/v5"

	"auth/internal/crypto"
	"auth/internal/types"
)

func decodeJSON(r *http.Request, v interface{}) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	defer r.Body.Close()
	return sonic.Unmarshal(body, v)
}

func (s *Server) handleRegistration(w http.ResponseWriter, r *http.Request) {
	var req types.UserReq
	if err := decodeJSON(r, &req); err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный JSON")
		return
	}

	if req.Username == "" || req.Email == "" || req.Password == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "username, email и password обязательны")
		return
	}

	passwordHash, salt, err := s.crypto.GenerationPassword(req.Password)
	if err != nil {
		s.logger.Err(err).Msg("password hashing failed")
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка обработки пароля")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	dbUser := &types.User{
		Username: req.Username,
		Email:    req.Email,
		Password: passwordHash,
		Salt:     salt,
	}

	if err := s.users.InsertUser(ctx, dbUser); err != nil {
		s.logger.Err(err).Str("email", req.Email).Msg("failed to insert user")
		WriteErr(w, http.StatusConflict, "ERR_EMAIL_TAKEN", "email или username уже заняты")
		return
	}

	userIDStr := strconv.Itoa(dbUser.ID)

	code, err := crypto.GenerateNumericCode()
	if err != nil {
		s.logger.Err(err).Msg("failed to generate verification code")
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка генерации кода")
		return
	}

	if err := s.cache.Set(ctx, "verify:"+userIDStr, code, 15*time.Minute); err != nil {
		s.logger.Err(err).Msg("failed to store verification code")
	}

	if err := s.mailer.SendVerificationEmail(userIDStr, req.Email, code); err != nil {
		s.logger.Err(err).Msg("failed to publish verification email event")
	}

	WriteJson(w, http.StatusCreated, map[string]string{
		"user_id": userIDStr,
		"status":  "verification_sent",
	})
}

func (s *Server) handleVerifyEmail(w http.ResponseWriter, r *http.Request) {
	var req types.VerifyEmailReq
	if err := decodeJSON(r, &req); err != nil || req.UserID == "" || req.Code == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "user_id и code обязательны")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	storedCode, err := s.cache.Get(ctx, "verify:"+req.UserID)
	if err != nil || storedCode != req.Code {
		WriteErr(w, http.StatusBadRequest, "ERR_INVALID_VERIFICATION_CODE", "код неверный или устарел")
		return
	}

	userID, err := strconv.Atoi(req.UserID)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный user_id")
		return
	}

	userBefore, err := s.users.GetUserByID(ctx, userID)
	if err != nil || userBefore.Status != "unverified" {
		WriteErr(w, http.StatusForbidden, "ERR_FORBIDDEN", "аккаунт не ожидает подтверждения")
		return
	}
	consumed, err := s.cache.Consume(ctx, "verify:"+req.UserID, req.Code)
	if err != nil || !consumed {
		WriteErr(w, http.StatusBadRequest, "ERR_INVALID_VERIFICATION_CODE", "код уже использован")
		return
	}

	if err := s.users.SetUserStatus(ctx, userID, "active"); err != nil {
		s.logger.Err(err).Msg("failed to activate user")
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка активации")
		return
	}
	_ = s.cache.Delete(ctx, "verify:"+req.UserID)

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	pair, err := s.sessions.Issue(ctx, user)
	if err != nil {
		s.logger.Err(err).Msg("failed to issue token pair")
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка выпуска токенов")
		return
	}

	WriteJson(w, http.StatusOK, pair)
}

func (s *Server) handleResendVer(w http.ResponseWriter, r *http.Request) {
	var req types.ResendVerificationReq
	if err := decodeJSON(r, &req); err != nil || req.UserID == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "user_id обязателен")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	rlKey := "verify_rl:" + req.UserID
	if exists, _ := s.cache.Exists(ctx, rlKey); exists {
		WriteErr(w, http.StatusTooManyRequests, "ERR_RATE_LIMITED", "подожди перед повторной отправкой")
		return
	}

	userID, err := strconv.Atoi(req.UserID)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный user_id")
		return
	}

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusNotFound, "ERR_NOT_FOUND", "пользователь не найден")
		return
	}

	code, err := crypto.GenerateNumericCode()
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка генерации кода")
		return
	}

	_ = s.cache.Set(ctx, "verify:"+req.UserID, code, 15*time.Minute)
	_ = s.cache.Set(ctx, rlKey, "1", 60*time.Second)

	if err := s.mailer.SendVerificationEmail(req.UserID, user.Email, code); err != nil {
		s.logger.Err(err).Msg("failed to publish verification email event")
	}

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "verification_sent"})
}

func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	var req types.LoginReq
	if err := decodeJSON(r, &req); err != nil || req.Email == "" || req.Password == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "email и password обязательны")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByEmail(ctx, req.Email)
	if err != nil {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_CREDENTIALS", "неверный email или пароль")
		return
	}

	if err := s.crypto.CheckPassword(req.Password, user.Salt, user.Password); err != nil {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_CREDENTIALS", "неверный email или пароль")
		return
	}

	if user.Status == "banned" {
		WriteErr(w, http.StatusForbidden, "ERR_ACCOUNT_BANNED", "аккаунт заблокирован")
		return
	}

	if user.Status == "unverified" {
		WriteErr(w, http.StatusForbidden, "ERR_EMAIL_NOT_VERIFIED", "подтверди email перед входом")
		return
	}

	if user.TOTPEnabled {
		pendingToken, err := crypto.GenerateOpaqueToken("pt_")
		if err != nil {
			WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка генерации токена")
			return
		}
		_ = s.cache.Set(ctx, "pending2fa:"+pendingToken, strconv.Itoa(user.ID), 5*time.Minute)

		WriteJson(w, http.StatusOK, types.Requires2FAResponse{
			Requires2FA:  true,
			PendingToken: pendingToken,
		})
		return
	}

	pair, err := s.sessions.Issue(ctx, user)
	if err != nil {
		s.logger.Err(err).Msg("failed to issue token pair")
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка выпуска токенов")
		return
	}

	WriteJson(w, http.StatusOK, pair)
}

func (s *Server) handle2faVer(w http.ResponseWriter, r *http.Request) {
	var req types.TwoFAVerifyReq
	if err := decodeJSON(r, &req); err != nil || req.PendingToken == "" || req.Code == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "pending_token и code обязательны")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	userIDStr, err := s.cache.Get(ctx, "pending2fa:"+req.PendingToken)
	if err != nil {
		WriteErr(w, http.StatusUnauthorized, "ERR_UNAUTHORIZED", "pending_token невалиден или истёк")
		return
	}

	userID, _ := strconv.Atoi(userIDStr)
	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	if !crypto.ValidateTOTPCode(user.TOTPSecret, req.Code) {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_2FA_CODE", "неверный код")
		return
	}

	_ = s.cache.Delete(ctx, "pending2fa:"+req.PendingToken)

	if user.Status != "active" {
		WriteErr(w, http.StatusForbidden, "ERR_FORBIDDEN", "аккаунт неактивен")
		return
	}

	pair, err := s.sessions.Issue(ctx, user)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка выпуска токенов")
		return
	}

	WriteJson(w, http.StatusOK, pair)
}

func (s *Server) handleRefresh(w http.ResponseWriter, r *http.Request) {
	var req types.RefreshReq
	if err := decodeJSON(r, &req); err != nil || req.RefreshToken == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "refresh_token обязателен")
		return
	}

	sessionID, ok := crypto.ParseRefreshToken(req.RefreshToken)
	if !ok {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_REFRESH_TOKEN", "невалидный refresh_token")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	raw, err := s.cache.GetDel(ctx, "refresh:"+sessionID)
	if err != nil {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_REFRESH_TOKEN", "сессия не найдена или истекла")
		return
	}

	var session types.RefreshSession
	if err := sonic.Unmarshal([]byte(raw), &session); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка чтения сессии")
		return
	}

	if !crypto.EqualTokenHashes(session.TokenHash, crypto.HashToken(req.RefreshToken)) {
		_ = s.cache.Delete(ctx, "refresh:"+sessionID)
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_REFRESH_TOKEN", "невалидный refresh_token")
		return
	}

	user, err := s.users.GetUserByID(ctx, session.UserID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	_ = s.cache.Delete(ctx, "refresh:"+sessionID)

	if user.Status != "active" {
		WriteErr(w, http.StatusForbidden, "ERR_FORBIDDEN", "аккаунт неактивен")
		return
	}

	pair, err := s.sessions.Issue(ctx, user)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка выпуска токенов")
		return
	}

	WriteJson(w, http.StatusOK, pair)
}

func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	sessionID, ok := r.Context().Value(ctxSessionID).(string)
	if !ok {
		WriteErr(w, http.StatusUnauthorized, "ERR_UNAUTHORIZED", "нет сессии")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	_ = s.cache.Delete(ctx, "refresh:"+sessionID)
	_ = s.cache.Set(ctx, "blacklist:"+sessionID, "1", crypto.AccessTokenTTL)

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "logged_out"})
}

func (s *Server) handleLogoutAll(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(ctxUserID).(string)
	if !ok {
		WriteErr(w, http.StatusUnauthorized, "ERR_UNAUTHORIZED", "нет сессии")
		return
	}
	userID, _ := strconv.Atoi(userIDStr)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	revoked, err := s.sessions.RevokeAll(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка отзыва сессий")
		return
	}

	WriteJson(w, http.StatusOK, map[string]interface{}{
		"status":           "logged_out_all",
		"sessions_revoked": revoked,
	})
}

func (s *Server) handleForgotPassword(w http.ResponseWriter, r *http.Request) {
	var req types.ForgotPasswordReq
	if err := decodeJSON(r, &req); err != nil || req.Email == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "email обязателен")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	if user, err := s.users.GetUserByEmail(ctx, req.Email); err == nil {
		if code, genErr := crypto.GenerateNumericCode(); genErr == nil {
			_ = s.cache.Set(ctx, "reset:"+code, strconv.Itoa(user.ID), 15*time.Minute)
			if err := s.mailer.SendPasswordResetEmail(strconv.Itoa(user.ID), user.Email, code); err != nil {
				s.logger.Err(err).Msg("failed to publish password reset event")
			}
		}
	}

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "reset_email_sent"})
}

func (s *Server) handleResetPassword(w http.ResponseWriter, r *http.Request) {
	var req types.ResetPasswordReq
	if err := decodeJSON(r, &req); err != nil || req.Code == "" || req.NewPassword == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "code и new_password обязательны")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	userIDStr, err := s.cache.Get(ctx, "reset:"+req.Code)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_INVALID_VERIFICATION_CODE", "код неверный или устарел")
		return
	}
	_ = s.cache.Delete(ctx, "reset:"+req.Code)

	userID, _ := strconv.Atoi(userIDStr)

	passwordHash, salt, err := s.crypto.GenerationPassword(req.NewPassword)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка обработки пароля")
		return
	}

	if err := s.users.SetUserPassword(ctx, userID, passwordHash, salt); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка смены пароля")
		return
	}

	_, _ = s.sessions.RevokeAll(ctx, userID)

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "password_reset"})
}

func (s *Server) handleUsMe(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusNotFound, "ERR_NOT_FOUND", "пользователь не найден")
		return
	}

	WriteJson(w, http.StatusOK, user.ToPublic())
}

func (s *Server) handleUpdMe(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)

	var req types.UpdateProfileReq
	if err := decodeJSON(r, &req); err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный JSON")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	if err := s.users.UpdateProfile(ctx, userID, req.Username, req.AvatarURL); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка обновления профиля")
		return
	}

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	WriteJson(w, http.StatusOK, user.ToPublic())
}

func (s *Server) handleChangePass(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)
	currentSessionID, _ := r.Context().Value(ctxSessionID).(string)

	var req types.ChangePasswordReq
	if err := decodeJSON(r, &req); err != nil || req.CurrentPassword == "" || req.NewPassword == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "current_password и new_password обязательны")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	if err := s.crypto.CheckPassword(req.CurrentPassword, user.Salt, user.Password); err != nil {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_CREDENTIALS", "неверный текущий пароль")
		return
	}

	hash, salt, err := s.crypto.GenerationPassword(req.NewPassword)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка обработки пароля")
		return
	}

	if err := s.users.SetUserPassword(ctx, userID, hash, salt); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка смены пароля")
		return
	}

	sessions, _ := s.cache.SMembers(ctx, "user_sessions:"+userIDStr)
	for _, sid := range sessions {
		if sid == currentSessionID {
			continue
		}
		_ = s.cache.Delete(ctx, "refresh:"+sid)
		_ = s.cache.Set(ctx, "blacklist:"+sid, "1", crypto.AccessTokenTTL)
	}

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "password_changed"})
}

func (s *Server) handleChangeEmail(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)

	var req types.ChangeEmailReq
	if err := decodeJSON(r, &req); err != nil || req.NewEmail == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "new_email обязателен")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	code, err := crypto.GenerateNumericCode()
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка генерации кода")
		return
	}

	payload, err := sonic.Marshal(types.ChangeEmailPending{NewEmail: req.NewEmail, Code: code})
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка сериализации")
		return
	}
	_ = s.cache.Set(ctx, "changeemail:"+userIDStr, string(payload), 15*time.Minute)

	if err := s.mailer.SendEmailChangeConfirmation(userIDStr, req.NewEmail, code); err != nil {
		s.logger.Err(err).Msg("failed to publish email change event")
	}

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "verification_sent_to_new_email"})
}

func (s *Server) handleChangeEmailConfirm(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)

	var req types.ChangeEmailConfirmReq
	if err := decodeJSON(r, &req); err != nil || req.Code == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "code обязателен")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	raw, err := s.cache.Get(ctx, "changeemail:"+userIDStr)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_INVALID_VERIFICATION_CODE", "код неверный или устарел")
		return
	}

	var pending types.ChangeEmailPending
	if err := sonic.Unmarshal([]byte(raw), &pending); err != nil || pending.Code != req.Code {
		WriteErr(w, http.StatusBadRequest, "ERR_INVALID_VERIFICATION_CODE", "код неверный или устарел")
		return
	}

	if err := s.users.SetUserEmail(ctx, userID, pending.NewEmail); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка смены email")
		return
	}
	_ = s.cache.Delete(ctx, "changeemail:"+userIDStr)

	WriteJson(w, http.StatusOK, map[string]string{
		"status": "email_changed",
		"email":  pending.NewEmail,
	})
}

func (s *Server) handle2faEnable(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	key, err := crypto.GenerateTOTPSecret(user.Email)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка генерации 2FA-секрета")
		return
	}

	if err := s.users.SetTOTPSecret(ctx, userID, key.Secret()); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка сохранения секрета")
		return
	}

	WriteJson(w, http.StatusOK, map[string]string{
		"secret":      key.Secret(),
		"otpauth_url": key.URL(),
	})
}

func (s *Server) handle2faConfirm(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)

	var req types.TwoFAConfirmReq
	if err := decodeJSON(r, &req); err != nil || req.Code == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "code обязателен")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	if !crypto.ValidateTOTPCode(user.TOTPSecret, req.Code) {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_2FA_CODE", "неверный код")
		return
	}

	if err := s.users.EnableTOTP(ctx, userID); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка включения 2FA")
		return
	}

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "2fa_enabled"})
}

func (s *Server) handle2faDisable(w http.ResponseWriter, r *http.Request) {
	userIDStr, _ := r.Context().Value(ctxUserID).(string)
	userID, _ := strconv.Atoi(userIDStr)

	var req types.TwoFADisableReq
	if err := decodeJSON(r, &req); err != nil || req.Password == "" || req.Code == "" {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "password и code обязательны")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByID(ctx, userID)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения юзера")
		return
	}

	if err := s.crypto.CheckPassword(req.Password, user.Salt, user.Password); err != nil {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_CREDENTIALS", "неверный пароль")
		return
	}

	if !crypto.ValidateTOTPCode(user.TOTPSecret, req.Code) {
		WriteErr(w, http.StatusUnauthorized, "ERR_INVALID_2FA_CODE", "неверный код")
		return
	}

	if err := s.users.DisableTOTP(ctx, userID); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка отключения 2FA")
		return
	}

	WriteJson(w, http.StatusOK, types.Response{Status: "success", Message: "2fa_disabled"})
}

func (s *Server) handleUsers(w http.ResponseWriter, r *http.Request) {
	page := 1
	limit := 20
	if p := r.URL.Query().Get("page"); p != "" {
		if v, err := strconv.Atoi(p); err == nil && v > 0 {
			page = v
		}
	}
	if l := r.URL.Query().Get("limit"); l != "" {
		if v, err := strconv.Atoi(l); err == nil && v > 0 {
			limit = v
		}
	}
	search := r.URL.Query().Get("search")

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	users, total, err := s.users.ListUsers(ctx, limit, (page-1)*limit, search)
	if err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка получения списка")
		return
	}

	public := make([]types.UserPublic, 0, len(users))
	for i := range users {
		public = append(public, users[i].ToPublic())
	}

	WriteJson(w, http.StatusOK, map[string]interface{}{
		"users": public,
		"page":  page,
		"limit": limit,
		"total": total,
	})
}

func (s *Server) handleGetUsers(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный id")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	user, err := s.users.GetUserByID(ctx, id)
	if err != nil {
		WriteErr(w, http.StatusNotFound, "ERR_NOT_FOUND", "пользователь не найден")
		return
	}

	WriteJson(w, http.StatusOK, user.ToPublic())
}

func (s *Server) handleBan(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный id")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	if err := s.users.SetUserStatus(ctx, id, "banned"); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка бана")
		return
	}
	_, _ = s.sessions.RevokeAll(ctx, id)

	WriteJson(w, http.StatusOK, map[string]string{"status": "banned", "user_id": idStr})
}

func (s *Server) handleUnban(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный id")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	if err := s.users.SetUserStatus(ctx, id, "active"); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка разбана")
		return
	}

	WriteJson(w, http.StatusOK, map[string]string{"status": "unbanned", "user_id": idStr})
}

func (s *Server) handleUpdRole(w http.ResponseWriter, r *http.Request) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.Atoi(idStr)
	if err != nil {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "невалидный id")
		return
	}

	var req types.UpdateRoleReq
	if err := decodeJSON(r, &req); err != nil || (req.Role != "user" && req.Role != "admin") {
		WriteErr(w, http.StatusBadRequest, "ERR_VALIDATION", "role должен быть user или admin")
		return
	}

	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()

	if err := s.users.SetUserRole(ctx, id, req.Role); err != nil {
		WriteErr(w, http.StatusInternalServerError, "ERR_INTERNAL", "ошибка смены роли")
		return
	}

	WriteJson(w, http.StatusOK, map[string]string{"status": "role_updated", "user_id": idStr, "role": req.Role})
}

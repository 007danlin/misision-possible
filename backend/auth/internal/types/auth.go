package types

import "github.com/golang-jwt/jwt/v5"

type Claims struct {
	UserID    string `json:"user_id"`
	SessionID string `json:"session_id"`
	Role      string `json:"role"`
	jwt.RegisteredClaims
}

type RefreshSession struct {
	UserID    int    `json:"user_id"`
	TokenHash string `json:"token_hash"`
}

type ChangeEmailPending struct {
	NewEmail string `json:"new_email"`
	Code     string `json:"code"`
}

type TokenPair struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"`
}

type Requires2FAResponse struct {
	Requires2FA  bool   `json:"requires_2fa"`
	PendingToken string `json:"pending_token"`
}

type LoginReq struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type VerifyEmailReq struct {
	UserID string `json:"user_id"`
	Code   string `json:"code"`
}

type ResendVerificationReq struct {
	UserID string `json:"user_id"`
}

type RefreshReq struct {
	RefreshToken string `json:"refresh_token"`
}

type ForgotPasswordReq struct {
	Email string `json:"email"`
}

type ResetPasswordReq struct {
	Code        string `json:"code"`
	NewPassword string `json:"new_password"`
}

type ChangePasswordReq struct {
	CurrentPassword string `json:"current_password"`
	NewPassword     string `json:"new_password"`
}

type ChangeEmailReq struct {
	NewEmail string `json:"new_email"`
}

type ChangeEmailConfirmReq struct {
	Code string `json:"code"`
}

type TwoFAVerifyReq struct {
	PendingToken string `json:"pending_token"`
	Code         string `json:"code"`
}

type TwoFAConfirmReq struct {
	Code string `json:"code"`
}

type TwoFADisableReq struct {
	Password string `json:"password"`
	Code     string `json:"code"`
}

type UpdateProfileReq struct {
	Username  *string `json:"nickname,omitempty"`
	AvatarURL *string `json:"avatar_url,omitempty"`
}

type UpdateRoleReq struct {
	Role string `json:"role"`
}

type BanReq struct {
	Reason string `json:"reason"`
}

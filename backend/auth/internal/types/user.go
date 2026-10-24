package types

import (
	"time"
)

type UserReq struct {
	Username string `json:"username"`
	Email    string `json:"email"`
	Password string `json:"password"`
}

type Response struct {
	Status  string `json:"status"`
	Message string `json:"message"`
}

type User struct {
	ID          int       `db:"id"`           // BIGSERIAL
	Username    string    `db:"username"`     // VARCHAR(50)
	Email       string    `db:"email"`        // VARCHAR(150)
	Password    string    `db:"password"`     // VARCHAR(255)
	Salt        string    `db:"salt"`         // VARCHAR(64)
	AvatarURL   string    `db:"avatar_url"`   // VARCHAR(255)
	Status      string    `db:"status"`       // unverified / active / banned
	Role        string    `db:"role"`         // user / admin
	TOTPSecret  string    `db:"totp_secret"`  // пусто, пока 2FA не включена
	TOTPEnabled bool      `db:"totp_enabled"` // включена ли 2FA
	CreatedAt   time.Time `db:"created_at"`   // TIMESTAMPTZ
}

type UserPublic struct {
	UserID      int       `json:"user_id"`
	Email       string    `json:"email"`
	Nickname    string    `json:"nickname"`
	AvatarURL   string    `json:"avatar_url,omitempty"`
	Role        string    `json:"role"`
	Status      string    `json:"status"`
	TOTPEnabled bool      `json:"totp_enabled"`
	CreatedAt   time.Time `json:"created_at"`
}

func (u *User) ToPublic() UserPublic {
	return UserPublic{
		UserID:      u.ID,
		Email:       u.Email,
		Nickname:    u.Username,
		AvatarURL:   u.AvatarURL,
		Role:        u.Role,
		Status:      u.Status,
		TOTPEnabled: u.TOTPEnabled,
		CreatedAt:   u.CreatedAt,
	}
}

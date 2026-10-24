package ports

import (
	"context"
	"time"

	"auth/internal/types"
)

type Users interface {
	InsertUser(context.Context, *types.User) error
	GetUserByEmail(context.Context, string) (*types.User, error)
	GetUserByID(context.Context, int) (*types.User, error)
	SetUserStatus(context.Context, int, string) error
	SetUserPassword(context.Context, int, string, string) error
	SetUserEmail(context.Context, int, string) error
	SetUserRole(context.Context, int, string) error
	UpdateProfile(context.Context, int, *string, *string) error
	SetTOTPSecret(context.Context, int, string) error
	EnableTOTP(context.Context, int) error
	DisableTOTP(context.Context, int) error
	ListUsers(context.Context, int, int, string) ([]types.User, int, error)
}

type Sessions interface {
	GetDel(context.Context, string) (string, error)
	Consume(context.Context, string, string) (bool, error)
	Exists(context.Context, string) (bool, error)
	Set(context.Context, string, string, time.Duration) error
	Get(context.Context, string) (string, error)
	Delete(context.Context, string) error
	SAdd(context.Context, string, string) error
	SMembers(context.Context, string) ([]string, error)
	SRem(context.Context, string, string) error
}

type Mailer interface {
	SendVerificationEmail(string, string, string) error
	SendPasswordResetEmail(string, string, string) error
	SendEmailChangeConfirmation(string, string, string) error
}

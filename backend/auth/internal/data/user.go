package data

import (
	"context"
	"errors"
	"fmt"

	"github.com/lib/pq"

	"auth/internal/types"
)

func (r *Repository) InsertUser(ctx context.Context, user *types.User) error {
	query := `
		INSERT INTO users (username, email, password, salt)
		VALUES (:username, :email, :password, :salt)
		RETURNING id, status, role, totp_enabled, created_at;`

	stmt, err := r.db.PrepareNamedContext(ctx, query)
	if err != nil {
		return fmt.Errorf("failed to prepare statement: %w", err)
	}
	defer stmt.Close()

	err = stmt.Get(user, user)
	if err != nil {
		var pqErr *pq.Error
		if errors.As(err, &pqErr) && pqErr.Code == "23505" {
			return fmt.Errorf("user with username '%s' or this email already exists", user.Username)
		}
		return fmt.Errorf("failed to insert user: %w", err)
	}

	return nil
}

func (r *Repository) GetUserByEmail(ctx context.Context, email string) (*types.User, error) {
	var user types.User
	query := `SELECT * FROM users WHERE email = $1`
	if err := r.db.GetContext(ctx, &user, query, email); err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *Repository) GetUserByID(ctx context.Context, id int) (*types.User, error) {
	var user types.User
	query := `SELECT * FROM users WHERE id = $1`
	if err := r.db.GetContext(ctx, &user, query, id); err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *Repository) SetUserStatus(ctx context.Context, id int, status string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET status = $1 WHERE id = $2`, status, id)
	return err
}

func (r *Repository) SetUserPassword(ctx context.Context, id int, hash, salt string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET password = $1, salt = $2 WHERE id = $3`, hash, salt, id)
	return err
}

func (r *Repository) SetUserEmail(ctx context.Context, id int, email string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET email = $1 WHERE id = $2`, email, id)
	return err
}

func (r *Repository) SetUserRole(ctx context.Context, id int, role string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET role = $1 WHERE id = $2`, role, id)
	return err
}

func (r *Repository) UpdateProfile(ctx context.Context, id int, username, avatarURL *string) error {
	if username != nil {
		if _, err := r.db.ExecContext(ctx, `UPDATE users SET username = $1 WHERE id = $2`, *username, id); err != nil {
			return err
		}
	}
	if avatarURL != nil {
		if _, err := r.db.ExecContext(ctx, `UPDATE users SET avatar_url = $1 WHERE id = $2`, *avatarURL, id); err != nil {
			return err
		}
	}
	return nil
}

func (r *Repository) SetTOTPSecret(ctx context.Context, id int, secret string) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET totp_secret = $1 WHERE id = $2`, secret, id)
	return err
}

func (r *Repository) EnableTOTP(ctx context.Context, id int) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET totp_enabled = TRUE WHERE id = $1`, id)
	return err
}

func (r *Repository) DisableTOTP(ctx context.Context, id int) error {
	_, err := r.db.ExecContext(ctx, `UPDATE users SET totp_enabled = FALSE, totp_secret = '' WHERE id = $1`, id)
	return err
}

func (r *Repository) ListUsers(ctx context.Context, limit, offset int, search string) ([]types.User, int, error) {
	var users []types.User
	var total int

	pattern := "%" + search + "%"

	countQuery := `SELECT COUNT(*) FROM users WHERE username ILIKE $1 OR email ILIKE $1`
	if err := r.db.GetContext(ctx, &total, countQuery, pattern); err != nil {
		return nil, 0, err
	}

	query := `SELECT * FROM users WHERE username ILIKE $1 OR email ILIKE $1 ORDER BY id LIMIT $2 OFFSET $3`
	if err := r.db.SelectContext(ctx, &users, query, pattern, limit, offset); err != nil {
		return nil, 0, err
	}

	return users, total, nil
}

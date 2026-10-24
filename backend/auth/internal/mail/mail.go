package mail

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/nats-io/nats.go"
)

type Publisher struct{ conn *nats.Conn }

func New(url string) (*Publisher, error) {
	if url == "" {
		return nil, fmt.Errorf("NATS URL is required")
	}
	conn, err := nats.Connect(url, nats.Timeout(5*time.Second))
	if err != nil {
		return nil, fmt.Errorf("connect NATS: %w", err)
	}
	return &Publisher{conn: conn}, nil
}

func (p *Publisher) Close() { p.conn.Close() }

func (p *Publisher) publish(subject string, payload any) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	if err := p.conn.Publish(subject, data); err != nil {
		return err
	}
	return p.conn.FlushTimeout(3 * time.Second)
}

type VerificationEmailPayload struct {
	UserID string `json:"user_id"`
	Email  string `json:"email"`
	Code   string `json:"code"`
}

func (p *Publisher) SendVerificationEmail(userID, email, code string) error {
	return p.publish("auth.user.registered", VerificationEmailPayload{
		UserID: userID,
		Email:  email,
		Code:   code,
	})
}

type PasswordResetPayload struct {
	UserID string `json:"user_id"`
	Email  string `json:"email"`
	Code   string `json:"code"`
}

func (p *Publisher) SendPasswordResetEmail(userID, email, code string) error {
	return p.publish("auth.user.password_reset_requested", PasswordResetPayload{
		UserID: userID,
		Email:  email,
		Code:   code,
	})
}

type EmailChangePayload struct {
	UserID   string `json:"user_id"`
	NewEmail string `json:"new_email"`
	Code     string `json:"code"`
}

func (p *Publisher) SendEmailChangeConfirmation(userID, newEmail, code string) error {
	return p.publish("auth.user.email_change_requested", EmailChangePayload{
		UserID:   userID,
		NewEmail: newEmail,
		Code:     code,
	})
}

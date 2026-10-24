package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/smtp"
	"os"
	"strings"

	"github.com/nats-io/nats.go"
)

var Handlers = map[string]func(map[string]any) string{
	"auth.user.email_change_requested": func(payload map[string]any) string {
		email, _ := payload["new_email"].(string)
		code, _ := payload["code"].(string)
		if err := SendEmailByProvider(email, "Смена email", "Ваш код подтверждения: "+code); err != nil {
			return fmt.Sprintf("SMTP send failed: %v", err)
		}
		return fmt.Sprintf("send email change confirmation to %s", email)
	},
	"auth.user.registered": func(payload map[string]any) string {
		userID, _ := payload["user_id"].(string)
		email, _ := payload["email"].(string)
		code, _ := payload["code"].(string)
		if err := SendEmailByProvider(email, "Подтверждение email", fmt.Sprintf("Ваш код подтверждения: %s\nuser_id=%s", code, userID)); err != nil {
			return fmt.Sprintf("SMTP send failed to %s: %v", email, err)
		}
		return fmt.Sprintf("send verification email to %s (%s)", email, userID)
	},
	"auth.user.password_reset_requested": func(payload map[string]any) string {
		userID, _ := payload["user_id"].(string)
		email, _ := payload["email"].(string)
		code, _ := payload["code"].(string)
		if err := SendEmailByProvider(email, "Восстановление пароля", fmt.Sprintf("Ваш код сброса пароля: %s\nuser_id=%s", code, userID)); err != nil {
			return fmt.Sprintf("SMTP send failed to %s: %v", email, err)
		}
		return fmt.Sprintf("send password reset email to %s (%s)", email, userID)
	},
	"chat.message.sent": func(payload map[string]any) string {
		userID, _ := payload["user_id"].(string)
		msg, _ := payload["message"].(string)
		return fmt.Sprintf("notify user %s about message: %s", userID, msg)
	},
}

func SMTPProviderForEmail(email string) (string, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	if email == "" {
		return "", errors.New("empty email")
	}

	switch {
	case strings.HasSuffix(email, "@gmail.com"):
		return "gmail", nil
	case strings.HasSuffix(email, "@yandex.ru"), strings.HasSuffix(email, "@yandex.com"):
		return "yandex", nil
	default:
		return "", fmt.Errorf("unsupported email domain for smtp: %s", email)
	}
}

func SendEmailByProvider(email, subject, body string) error {
	provider, err := SMTPProviderForEmail(email)
	if err != nil {
		return err
	}

	host := ""
	port := ""
	authUser := os.Getenv("SMTP_USER")
	authPass := os.Getenv("SMTP_PASSWORD")

	switch provider {
	case "gmail":
		host = "smtp.gmail.com"
		port = "587"
	case "yandex":
		host = "smtp.yandex.ru"
		port = "587"
	default:
		return errors.New("unsupported smtp provider")
	}

	if authUser == "" || authPass == "" {
		fmt.Printf("smtp stub: %s [%s] -> %s\n", provider, email, subject)
		fmt.Printf("body: %s\n", body)
		return nil
	}

	address := host + ":" + port
	auth := smtp.PlainAuth("", authUser, authPass, host)
	msg := []byte("To: " + email + "\r\n" +
		"From: " + authUser + "\r\n" +
		"Subject: " + subject + "\r\n" +
		"MIME-Version: 1.0\r\n" +
		"Content-Type: text/plain; charset=UTF-8\r\n\r\n" +
		body + "\r\n")

	if err := smtp.SendMail(address, auth, authUser, []string{email}, msg); err != nil {
		return err
	}

	return nil
}

func RenderMessage(subject string, payload map[string]any) string {
	if handler, ok := Handlers[subject]; ok {
		return handler(payload)
	}
	return fmt.Sprintf("process event %s: %v", subject, payload)
}

func StartNATS(url string) (*nats.Conn, error) {
	nc, err := nats.Connect(url)
	if err != nil {
		return nil, err
	}

	for subject := range Handlers {
		if _, err := nc.Subscribe(subject, func(msg *nats.Msg) {
			var payload map[string]any
			if err := json.Unmarshal(msg.Data, &payload); err != nil {
				fmt.Printf("notif: invalid payload for %s: %v\n", msg.Subject, err)
				return
			}

			fmt.Printf("notif: %s -> %s\n", msg.Subject, RenderMessage(msg.Subject, payload))
		}); err != nil {
			nc.Close()
			return nil, err
		}
	}

	if err := nc.Flush(); err != nil {
		nc.Close()
		return nil, err
	}

	return nc, nil
}

func envOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

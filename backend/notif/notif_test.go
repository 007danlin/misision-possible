package main

import (
	"github.com/nats-io/nats.go"
	"os"
	"testing"
	"time"
)

func TestKnownSubjects(t *testing.T) {
	if _, ok := Handlers["auth.user.email_change_requested"]; !ok {
		t.Fatal("missing email change handler")
	}
	if _, ok := Handlers["auth.user.registered"]; !ok {
		t.Fatal("missing auth.user.registered handler")
	}
	if _, ok := Handlers["auth.user.password_reset_requested"]; !ok {
		t.Fatal("missing auth.user.password_reset_requested handler")
	}
}

func TestRenderMessage(t *testing.T) {
	msg := RenderMessage("auth.user.registered", map[string]any{"user_id": "u1", "email": "test@example.com"})
	if msg == "" {
		t.Fatal("expected rendered message")
	}
}

func TestSMTPProviderFromEmail(t *testing.T) {
	provider, err := SMTPProviderForEmail("user@gmail.com")
	if err != nil {
		t.Fatalf("gmail should resolve: %v", err)
	}
	if provider != "gmail" {
		t.Fatalf("expected gmail, got %q", provider)
	}

	provider, err = SMTPProviderForEmail("user@yandex.ru")
	if err != nil {
		t.Fatalf("yandex should resolve: %v", err)
	}
	if provider != "yandex" {
		t.Fatalf("expected yandex, got %q", provider)
	}

	if _, err = SMTPProviderForEmail("user@example.com"); err == nil {
		t.Fatal("expected unsupported domain error")
	}
}

// Exercise the actual subscription lifecycle when NATS is available.
func TestNATSSubscriptionShutdown(t *testing.T) {
	url := os.Getenv("NATS_TEST_URL")
	if url == "" {
		t.Skip("set NATS_TEST_URL to check the NATS lifecycle")
	}
	nc, err := StartNATS(url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(nc.Close)
	closed := make(chan struct{})
	nc.SetClosedHandler(func(*nats.Conn) { close(closed) })
	if err := nc.Publish("chat.message.sent", []byte(`{"user_id":"smoke","message":"lifecycle check"}`)); err != nil {
		t.Fatal(err)
	}
	if err := nc.FlushTimeout(2 * time.Second); err != nil {
		t.Fatal(err)
	}
	if err := nc.Drain(); err != nil {
		t.Fatal(err)
	}
	select {
	case <-closed:
	case <-time.After(5 * time.Second):
		t.Fatal("NATS connection did not stop")
	}
}

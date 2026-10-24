package crypto

import (
	"errors"
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"

	"auth/internal/types"
)

func TestPasswordCompatibility(t *testing.T) {
	service, err := New("test-pepper", "", "")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	hash, salt, err := service.GenerationPassword("correct-password")
	if err != nil {
		t.Fatal(err)
	}
	// Existing stored hashes must remain valid after secret.Do is introduced.
	if err := bcrypt.CompareHashAndPassword([]byte(hash), []byte("correct-password"+salt+service.pepper)); err != nil {
		t.Fatal(err)
	}
	if err := service.CheckPassword("correct-password", salt, hash); err != nil {
		t.Fatal(err)
	}
	if !errors.Is(service.CheckPassword("wrong-password", salt, hash), types.NotEqualPassword) {
		t.Fatal("wrong password accepted")
	}
}

func TestPasswordHashFailure(t *testing.T) {
	service, err := New("test-pepper", "", "")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(service.Close)
	hash, salt, err := service.GenerationPassword(strings.Repeat("a", 73))
	if !errors.Is(err, bcrypt.ErrPasswordTooLong) || hash != "" || salt != "" {
		t.Fatalf("hash error not propagated: %v", err)
	}
}

func TestServiceSecretsAreIsolated(t *testing.T) {
	first, err := New("first-pepper", "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer first.Close()
	second, err := New("second-pepper", "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer second.Close()
	hash, salt, err := first.GenerationPassword("password")
	if err != nil {
		t.Fatal(err)
	}
	if second.CheckPassword("password", salt, hash) == nil {
		t.Fatal("different service accepted password with another pepper")
	}
	if first.CheckPassword("password", salt, hash) != nil {
		t.Fatal("constructing another service replaced the first pepper")
	}
	if string(first.PublicKey()) == string(second.PublicKey()) {
		t.Fatal("service keys shared")
	}
}

package crypto

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"fmt"
)

type Service struct {
	publicKey  ed25519.PublicKey
	privateKey ed25519.PrivateKey
	pepper     string
}

func New(pepper, pubB64, privB64 string) (*Service, error) {
	s := &Service{pepper: pepper}
	if err := s.loadKeys(pubB64, privB64); err != nil {
		return nil, err
	}
	return s, nil
}

func (s *Service) PublicKey() ed25519.PublicKey {
	return append(ed25519.PublicKey(nil), s.publicKey...)
}

func (s *Service) Close() { clear(s.privateKey); s.pepper = "" }

func (s *Service) loadKeys(pubB64, privB64 string) error {
	if (pubB64 == "") != (privB64 == "") {
		return fmt.Errorf("both JWT keys must be configured")
	}
	if pubB64 == "" && privB64 == "" {
		pub, priv, err := ed25519.GenerateKey(rand.Reader)
		if err != nil {
			return fmt.Errorf("generate ephemeral ed25519 keypair: %w", err)
		}
		s.publicKey = pub
		s.privateKey = priv
		return nil
	}

	pubBytes, err := base64.StdEncoding.DecodeString(pubB64)
	if err != nil {
		return fmt.Errorf("decode JWT_PUBLIC_KEY: %w", err)
	}
	privBytes, err := base64.StdEncoding.DecodeString(privB64)
	if err != nil {
		return fmt.Errorf("decode JWT_PRIVATE_KEY: %w", err)
	}

	if len(pubBytes) != ed25519.PublicKeySize || len(privBytes) != ed25519.PrivateKeySize {
		return fmt.Errorf("invalid ed25519 key length")
	}
	if !bytes.Equal(ed25519.PrivateKey(privBytes).Public().(ed25519.PublicKey), pubBytes) {
		return fmt.Errorf("JWT keys do not match")
	}
	s.publicKey = ed25519.PublicKey(pubBytes)
	s.privateKey = ed25519.PrivateKey(privBytes)
	return nil
}

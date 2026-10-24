package crypto

import (
	"crypto/rand"
	"encoding/base64"
	"runtime/secret"

	"golang.org/x/crypto/bcrypt"

	"auth/internal/types"
)

func generateSalt() string {
	var salt [16]byte
	_, _ = rand.Read(salt[:])
	return base64.StdEncoding.EncodeToString(salt[:])
}

func (s *Service) passwordMaterial(password, salt string) []byte {
	material := make([]byte, 0, len(password)+len(salt)+len(s.pepper))
	material = append(material, password...)
	material = append(material, salt...)
	return append(material, s.pepper...)
}

func (s *Service) GenerationPassword(password string) (string, string, error) {
	salt := generateSalt()
	var hash string
	var hashErr error
	secret.Do(func() {
		material := s.passwordMaterial(password, salt)
		defer clear(material)
		hashed, err := bcrypt.GenerateFromPassword(material, bcrypt.DefaultCost)
		if err != nil {
			hashErr = err
			return
		}
		hash = string(hashed)
		clear(hashed)
	})
	if hashErr != nil {
		return "", "", hashErr
	}
	return hash, salt, nil
}

func (s *Service) CheckPassword(password, salt, hash string) error {
	var compareErr error
	secret.Do(func() {
		material := s.passwordMaterial(password, salt)
		defer clear(material)
		compareErr = bcrypt.CompareHashAndPassword([]byte(hash), material)
	})
	if compareErr != nil {
		return types.NotEqualPassword
	}
	return nil
}

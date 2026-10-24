package crypto

import (
	"runtime/secret"
	"time"

	"github.com/golang-jwt/jwt/v5"

	"auth/internal/types"
)

const AccessTokenTTL = 15 * time.Minute

func (s *Service) IssueAccessToken(userID, sessionID, role string) (string, error) {
	claims := types.Claims{
		UserID:    userID,
		SessionID: sessionID,
		Role:      role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(AccessTokenTTL)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodEdDSA, claims)
	var signed string
	var err error
	secret.Do(func() { signed, err = token.SignedString(s.privateKey) })
	return signed, err
}

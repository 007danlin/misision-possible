package crypto

import (
	"github.com/pquerna/otp"
	"github.com/pquerna/otp/totp"
)

const totpIssuer = "misison-possible"

func GenerateTOTPSecret(email string) (*otp.Key, error) {
	return totp.Generate(totp.GenerateOpts{
		Issuer:      totpIssuer,
		AccountName: email,
	})
}

func ValidateTOTPCode(secret, code string) bool {
	return totp.Validate(code, secret)
}

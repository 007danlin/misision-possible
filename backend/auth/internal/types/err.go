package types

import "errors"

// Errs of check password
var NotEqualPassword = errors.New("Wrong password or username")

type ErrorResponse struct {
	Error ErrorBody `json:"error"`
}

type ErrorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

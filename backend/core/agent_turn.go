package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	pb "core/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// AgentTurn is a stateless integration endpoint, not a persisted trip session.
// Client-supplied state only produces a proposal; it never authorizes checkout.
func (s *API) AgentTurn(w http.ResponseWriter, r *http.Request) {
	caller, err := s.ParseCaller(r)
	if err != nil {
		code := http.StatusUnauthorized
		if errors.Is(err, errAuthUnavailable) {
			code = http.StatusServiceUnavailable
		}
		writeError(w, code, err.Error())
		return
	}
	var payload struct {
		Message string          `json:"message"`
		State   json.RawMessage `json:"state"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 128<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, "invalid turn JSON")
		return
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		writeError(w, http.StatusBadRequest, "expected one JSON object")
		return
	}
	if strings.TrimSpace(payload.Message) == "" || len([]rune(payload.Message)) > 12000 {
		writeError(w, http.StatusBadRequest, "message must contain 1-12000 characters")
		return
	}
	if len(payload.State) == 0 {
		payload.State = json.RawMessage(`{}`)
	}
	ctx, cancel := context.WithTimeout(r.Context(), agentTimeout())
	defer cancel()
	reply, err := s.agent.RunTurn(ctx, &pb.TurnRequest{
		Message: payload.Message, StateJson: string(payload.State), Caller: caller,
	})
	if err != nil {
		code := http.StatusBadGateway
		if status.Code(err) == codes.InvalidArgument {
			code = http.StatusBadRequest
		}
		if status.Code(err) == codes.DeadlineExceeded {
			code = http.StatusGatewayTimeout
		}
		writeError(w, code, "agent turn unavailable or invalid")
		return
	}
	// Defend the integration boundary even if a future agent implementation drifts.
	var turn struct {
		Status          string          `json:"status"`
		CheckoutAllowed bool            `json:"checkout_allowed"`
		Booking         json.RawMessage `json:"booking"`
	}
	if reply.Caller != caller || json.Unmarshal([]byte(reply.TurnJson), &turn) != nil ||
		turn.Status == "" || turn.CheckoutAllowed ||
		(len(turn.Booking) != 0 && string(turn.Booking) != "null") {
		writeError(w, http.StatusBadGateway, "invalid agent proposal")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(reply.TurnJson))
}

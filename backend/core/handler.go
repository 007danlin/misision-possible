package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	pb "core/proto"
)

type HandleRequestBody struct {
	Name string `json:"name"`
}

type HandleResponse struct {
	Status       string `json:"status"`
	Caller       string `json:"caller"`
	AgentMessage string `json:"agent_message"`
}

var errAuthUnavailable = errors.New("auth unavailable")

type API struct {
	authURL    string
	authClient *http.Client
	agent      pb.PredictorClient
	metrics    metrics
}

func NewAPI(authURL string, client *http.Client, agent pb.PredictorClient) *API {
	return &API{authURL: strings.TrimRight(authURL, "/"), authClient: client, agent: agent}
}

// Auth owns JWT validation and session revocation; fail closed when unavailable.
func (s *API) ParseCaller(r *http.Request) (string, error) {
	token, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
	if !ok || strings.TrimSpace(token) == "" {
		return "", errors.New("missing bearer token")
	}
	req, err := http.NewRequestWithContext(r.Context(), http.MethodGet,
		s.authURL+"/api/auth/users/me", nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := s.authClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("%w: %v", errAuthUnavailable, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return "", errors.New("invalid or revoked token")
	}
	if resp.StatusCode != http.StatusOK {
		return "", errAuthUnavailable
	}
	var user struct {
		ID     int    `json:"user_id"`
		Status string `json:"status"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
		return "", err
	}
	if user.ID <= 0 || user.Status != "active" {
		return "", errors.New("inactive user")
	}
	return strconv.Itoa(user.ID), nil
}

func (s *API) callAgent(parent context.Context, caller, name string) (string, error) {
	ctx, cancel := context.WithTimeout(parent, 2*time.Second)
	defer cancel()
	resp, err := s.agent.Predict(ctx, &pb.PredictRequest{Name: name, Caller: caller})
	if err != nil {
		return "", fmt.Errorf("predict: %w", err)
	}
	return resp.Message, nil
}

func (s *API) HandleRequest(w http.ResponseWriter, r *http.Request) {
	caller, err := s.ParseCaller(r)
	if err != nil {
		status := http.StatusUnauthorized
		if errors.Is(err, errAuthUnavailable) {
			status = http.StatusServiceUnavailable
		}
		writeError(w, status, err.Error())
		return
	}

	var payload HandleRequestBody
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	payload.Name = strings.TrimSpace(payload.Name)
	if payload.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}

	message, err := s.callAgent(r.Context(), caller, payload.Name)
	if err != nil {
		log.Printf("agent request failed: %v", err)
		writeError(w, http.StatusBadGateway, "agent unavailable")
		return
	}

	resp := HandleResponse{
		Status:       "ok",
		Caller:       caller,
		AgentMessage: message,
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(resp)
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": message})
}

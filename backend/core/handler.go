package main

import (
	"encoding/json"
	"net/http"

	pb "core/proto"
)

type API struct {
	agent   pb.PredictorClient
	metrics metrics
	trips   *TripStore
}

func NewAPI(agent pb.PredictorClient) *API {
	return &API{agent: agent}
}

func writeError(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": message})
}

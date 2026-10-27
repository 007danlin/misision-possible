package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	pb "core/proto"
	"google.golang.org/grpc"
)

type turnClient struct {
	pb.PredictorClient
	called bool
	unsafe bool
}

func (c *turnClient) RunTurn(ctx context.Context, req *pb.TurnRequest, _ ...grpc.CallOption) (*pb.TurnReply, error) {
	c.called = true
	if req.Caller != "7" {
		panic("unverified caller")
	}
	deadline, ok := ctx.Deadline()
	if !ok || time.Until(deadline) > 45*time.Second || time.Until(deadline) < 40*time.Second {
		panic("wrong model timeout")
	}
	if c.unsafe {
		return &pb.TurnReply{Caller: "7", TurnJson: `{"status":"choosing","checkout_allowed":true}`}, nil
	}
	return &pb.TurnReply{Caller: "7", TurnJson: `{"status":"needs_input","checkout_allowed":false,"booking":null}`}, nil
}

func TestAgentTurnHTTPBoundary(t *testing.T) {
	auth := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer valid" {
			w.WriteHeader(401)
			return
		}
		_, _ = w.Write([]byte(`{"user_id":7,"status":"active"}`))
	}))
	defer auth.Close()
	for _, tc := range []struct {
		body, token    string
		code           int
		called, unsafe bool
	}{
		{`{"message":"Хочу в Казань"}`, "valid", 200, true, false},
		{`{"message":"Хочу в Казань","state":{"revision":2}}`, "valid", 200, true, false},
		{`{"message":"test","caller":"admin"}`, "valid", 400, false, false},
		{`{"message":"test"} {}`, "valid", 400, false, false},
		{`{"message":" "}`, "valid", 400, false, false},
		{`{"message":"test"}`, "forged", 401, false, false},
		{`{"message":"test"}`, "valid", 502, true, true},
	} {
		client := &turnClient{unsafe: tc.unsafe}
		api := NewAPI(auth.URL, auth.Client(), client)
		req := httptest.NewRequest("POST", "/api/core/agent/turn", strings.NewReader(tc.body))
		req.Header.Set("Authorization", "Bearer "+tc.token)
		recorder := httptest.NewRecorder()
		api.Handler().ServeHTTP(recorder, req)
		if recorder.Code != tc.code || client.called != tc.called {
			t.Fatalf("%s: code=%d body=%s called=%v", tc.body, recorder.Code, recorder.Body.String(), client.called)
		}
		if !json.Valid(recorder.Body.Bytes()) {
			t.Fatal("invalid JSON response")
		}
	}
}

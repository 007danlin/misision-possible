package main

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"strings"
	"testing"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "core/proto"
)

type testPredictor struct {
	pb.UnimplementedPredictorServer
}

func (testPredictor) Predict(_ context.Context, req *pb.PredictRequest) (*pb.PredictReply, error) {
	return &pb.PredictReply{Message: "hello " + req.Name + " for " + req.Caller}, nil
}
func TestHandleWithAuthAndGRPC(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	pb.RegisterPredictorServer(server, testPredictor{})
	go server.Serve(listener)
	defer server.Stop()
	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	auth := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer valid" {
			w.WriteHeader(401)
			return
		}
		w.Write([]byte(`{"user_id":7,"status":"active"}`))
	}))
	defer auth.Close()
	api := NewAPI(auth.URL, auth.Client(), pb.NewPredictorClient(conn))
	for _, tc := range []struct {
		token, body string
		status      int
	}{
		{"valid", `{"name":"Alice"}`, 200},
		{"forged", `{"name":"Alice"}`, 401},
		{"valid", `{"name":" "}`, 400},
		{"valid", `invalid`, 400},
	} {
		req := httptest.NewRequest("POST", "/api/core/handle", strings.NewReader(tc.body))
		req.Header.Set("Authorization", "Bearer "+tc.token)
		w := httptest.NewRecorder()
		api.HandleRequest(w, req)
		if w.Code != tc.status {
			t.Fatalf("status=%d body=%s", w.Code, w.Body.String())
		}
		if tc.status == 200 {
			var resp HandleResponse
			if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
				t.Fatal(err)
			}
			if resp.Caller != "7" || resp.AgentMessage != "hello Alice for 7" {
				t.Fatalf("unexpected response: %+v", resp)
			}
		}
	}
}

// The Python server has a separately generated binding; compare its actual
// service namespace so an in-process Go test cannot hide contract drift.
func TestPythonAgentServiceContract(t *testing.T) {
	source, err := os.ReadFile("../../agent/proto/predict.proto")
	if err != nil {
		t.Fatal(err)
	}
	goSource, err := os.ReadFile("proto/predict.proto")
	if err != nil {
		t.Fatal(err)
	}
	// The Go import option is the only intentional difference between contracts.
	goSource = regexp.MustCompile(`(?m)^option go_package[^\n]*\n`).ReplaceAll(goSource, nil)
	if strings.Join(strings.Fields(string(source)), " ") != strings.Join(strings.Fields(string(goSource)), " ") {
		t.Fatal("Go and Python proto contracts differ")
	}
	matches := regexp.MustCompile(`(?m)^package\s+(\w+)\s*;`).FindSubmatch(source)
	if len(matches) != 2 {
		t.Fatal("Python proto package not found")
	}
	expected := "/" + string(matches[1]) + ".Predictor/Predict"
	if pb.Predictor_Predict_FullMethodName != expected {
		t.Fatalf("Go gRPC method %s differs from Python %s", pb.Predictor_Predict_FullMethodName, expected)
	}
}

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

	pb "core/proto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type testPredictor struct {
	pb.UnimplementedPredictorServer
	session sessionAgent
}

func (s *testPredictor) RunTurn(ctx context.Context, req *pb.TurnRequest) (*pb.TurnReply, error) {
	return s.session.RunTurn(ctx, req)
}

func TestSessionWithGRPC(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	pb.RegisterPredictorServer(server, &testPredictor{})
	go server.Serve(listener)
	defer server.Stop()
	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	api := NewAPI(pb.NewPredictorClient(conn))
	api.trips = &TripStore{dir: t.TempDir()}
	handler := api.Handler()
	create := httptest.NewRecorder()
	handler.ServeHTTP(create, httptest.NewRequest("POST", "/api/sessions/", strings.NewReader("{}")))
	if create.Code != http.StatusOK {
		t.Fatalf("create: %d %s", create.Code, create.Body.String())
	}
	var initial map[string]any
	if err := json.Unmarshal(create.Body.Bytes(), &initial); err != nil {
		t.Fatal(err)
	}
	cookie := create.Result().Cookies()[0]
	path := "/api/sessions/" + initial["session_id"].(string)
	req := httptest.NewRequest("POST", path+"/turns", strings.NewReader(`{"message":"Хочу в Сочи","expected_revision":0,"idempotency_key":"grpc-turn-1"}`))
	req.AddCookie(cookie)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, req)
	if response.Code != http.StatusOK {
		t.Fatalf("turn: %d %s", response.Code, response.Body.String())
	}
	var snap map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &snap); err != nil {
		t.Fatal(err)
	}
	if snap["revision"] != float64(1) || snap["status"] != "choosing" || snap["assistant_message"] != "Fixture tool result" {
		t.Fatalf("unexpected snapshot: %v", snap)
	}
	read := httptest.NewRequest("GET", path, nil)
	read.AddCookie(cookie)
	saved := httptest.NewRecorder()
	handler.ServeHTTP(saved, read)
	if saved.Code != http.StatusOK || saved.Body.String() != response.Body.String() {
		t.Fatalf("persisted snapshot differs: %d %s", saved.Code, saved.Body.String())
	}
	unauthorized := httptest.NewRecorder()
	handler.ServeHTTP(unauthorized, httptest.NewRequest("GET", path, nil))
	if unauthorized.Code != http.StatusNotFound {
		t.Fatalf("ownerless read: %d", unauthorized.Code)
	}
	for _, legacy := range []string{"/api/core/handle", "/api/core/agent/turn"} {
		retired := httptest.NewRecorder()
		handler.ServeHTTP(retired, httptest.NewRequest("POST", legacy, strings.NewReader("{}")))
		if retired.Code != http.StatusNotFound {
			t.Fatalf("retired %s: %d", legacy, retired.Code)
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

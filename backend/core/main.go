package main

import (
	"context"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "core/proto"
)

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func agentTimeout() time.Duration {
	seconds, err := strconv.Atoi(os.Getenv("AGENT_TURN_TIMEOUT_SECONDS"))
	if err != nil || seconds < 1 || seconds > 300 {
		seconds = 45
	}
	return time.Duration(seconds) * time.Second
}

func (s *API) Handler() http.Handler {
	r := chi.NewRouter()
	r.Use(s.metrics.middleware)
	r.Post("/api/core/handle", s.HandleRequest)
	r.Post("/api/core/agent/turn", s.AgentTurn)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	if s.trips != nil {
		s.mountLocalTrips(r, s.trips)
	}
	return s.startupHandler(r)
}

func run() error {
	port := envOrDefault("PORT", "8081")
	conn, err := grpc.NewClient(net.JoinHostPort(envOrDefault("AGENT_HOST", "localhost"), envOrDefault("AGENT_PORT", "50051")), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return err
	}
	defer conn.Close()
	transport := http.DefaultTransport.(*http.Transport).Clone()
	defer transport.CloseIdleConnections()
	api := NewAPI(envOrDefault("AUTH_URL", "http://localhost:8080"), &http.Client{Timeout: 3 * time.Second, Transport: transport}, pb.NewPredictorClient(conn))

	if os.Getenv("LOCAL_DEMO_MODE") == "true" {
		dir := envOrDefault("TRIP_DATA_DIR", "./data/trips")
		if err := os.MkdirAll(dir, 0700); err != nil {
			return err
		}
		api.trips = &TripStore{dir: dir}
	}
	host := ""
	if api.trips != nil {
		host = "127.0.0.1"
	}
	// Container demo binds internally to all interfaces; Compose publishes only
	// on the host loopback. The native launcher keeps its loopback default.
	host = envOrDefault("BIND_HOST", host)
	server := &http.Server{
		Addr:              net.JoinHostPort(host, port),
		Handler:           api.Handler(),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second,
		WriteTimeout: agentTimeout() + 5*time.Second,
		IdleTimeout:  30 * time.Second,
	}

	stop, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- server.ListenAndServe() }()
	log.Printf("core listening on :%s", port)
	if os.Getenv("MODEL_STATUS_FILE") != "" {
		log.Printf("О!План: откройте http://localhost:%s — здесь виден прогресс подготовки модели", port)
	}
	select {
	case err := <-done:
		if err != nil && err != http.ErrServerClosed {
			return err
		}
	case <-stop.Done():
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(ctx); err != nil {
			_ = server.Close()
			<-done
			return err
		}
		<-done
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		log.Print(err)
		os.Exit(1)
	}
}

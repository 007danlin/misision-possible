package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
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

func (s *API) Handler() http.Handler {
	r := chi.NewRouter()
	r.Use(s.metrics.middleware)
	r.Post("/api/core/handle", s.HandleRequest)
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})
	return r
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

	server := &http.Server{
		Addr:              fmt.Sprintf(":%s", port),
		Handler:           api.Handler(),
		ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  30 * time.Second,
	}

	stop, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- server.ListenAndServe() }()
	log.Printf("core listening on :%s", port)
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

package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"auth/internal/cache"
	"auth/internal/config"
	"auth/internal/crypto"
	"auth/internal/data"
	"auth/internal/handlers"
	"auth/internal/logger"
	"auth/internal/mail"
)

func run() error {
	cfg, err := config.Load()
	if err != nil {
		return err
	}
	logger := logger.New(cfg.Style)
	crypt, err := crypto.New(cfg.Pepper, cfg.JWTPublicKey, cfg.JWTPrivateKey)
	if err != nil {
		return err
	}
	defer crypt.Close()
	if cfg.JWTPublicKey == "" {
		logger.Warn().Msg("ephemeral JWT keys; configure persistent keys to keep sessions across restarts")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	users, err := data.New(ctx, cfg.PostgresURL)
	if err != nil {
		return err
	}
	defer users.Close()
	sessions, err := cache.New(cfg.RedisURL)
	if err != nil {
		return err
	}
	defer sessions.Close()
	mailer, err := mail.New(cfg.NATSURL)
	if err != nil {
		return err
	}
	defer mailer.Close()
	handler := handlers.New(users, sessions, crypt, mailer, logger, cfg.Style).Handler()
	server := &http.Server{Addr: ":" + cfg.Port, Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second}
	stop, cancelSignal := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancelSignal()
	errorsCh := make(chan error, 1)
	go func() { errorsCh <- server.ListenAndServe() }()
	logger.Info().Str("port", cfg.Port).Msg("Auth started")
	select {
	case err := <-errorsCh:
		if !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	case <-stop.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			_ = server.Close()
			return fmt.Errorf("shutdown: %w", err)
		}
		<-errorsCh
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		log.Print(err)
		os.Exit(1)
	}
}

package config

import "os"

type Config struct {
	Port          string
	Pepper        string
	Style         string
	RedisURL      string
	PostgresURL   string
	NATSURL       string
	JWTPublicKey  string
	JWTPrivateKey string
}

func Load() (Config, error) {
	dir, err := os.Getwd()
	if err != nil {
		return Config{}, err
	}
	values, err := loadDotEnv(dir)
	if err != nil {
		return Config{}, err
	}
	get := func(key, fallback string) string { return getFromEnv(values, key, fallback) }
	return Config{
		Port: get("PORT", "8080"), Pepper: get("PEPPER", "local-development-pepper"),
		Style: get("STYLE", "PROD"), RedisURL: get("REDISURL", "redis://localhost:6379/0"),
		PostgresURL: get("POSTGRES", "host=localhost port=5432 user=app password=local-development-password dbname=users sslmode=disable"),
		NATSURL:     get("NATS", "nats://localhost:4222"), JWTPublicKey: get("JWT_PUBLIC_KEY", ""), JWTPrivateKey: get("JWT_PRIVATE_KEY", ""),
	}, nil
}

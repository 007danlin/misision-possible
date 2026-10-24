package data

import (
	"context"
	_ "embed"
	"fmt"

	"github.com/jmoiron/sqlx"
	_ "github.com/lib/pq"
)

//go:embed schema.sql
var schema string

type Repository struct{ db *sqlx.DB }

func New(ctx context.Context, dsn string) (*Repository, error) {
	db, err := sqlx.ConnectContext(ctx, "postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("connect postgres: %w", err)
	}
	if _, err := db.ExecContext(ctx, schema); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("initialize schema: %w", err)
	}
	return &Repository{db: db}, nil
}

func (r *Repository) Close() error { return r.db.Close() }

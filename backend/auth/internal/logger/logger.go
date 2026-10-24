package logger

import (
	"io"
	"os"

	"github.com/rs/zerolog"
)

func New(style string) zerolog.Logger {
	var output io.Writer = os.Stdout
	if style == "DEV" {
		output = zerolog.ConsoleWriter{Out: os.Stdout}
	}
	return zerolog.New(output).With().Timestamp().Logger()
}

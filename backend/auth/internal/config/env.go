package config

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/joho/godotenv"
)

func getFromEnv(fileEnv map[string]string, key string, def string) string {

	if value, ok := os.LookupEnv(key); ok {
		return value
	}

	value, ok := fileEnv[key]
	if ok {
		return value
	}
	return def
}

func loadDotEnv(startDir string) (map[string]string, error) {
	currentDir := startDir

	for {
		candidate := filepath.Join(currentDir, ".env")
		info, err := os.Stat(candidate)
		if err == nil && !info.IsDir() {
			values, readErr := godotenv.Read(candidate)
			if readErr != nil {
				return nil, fmt.Errorf("read %s: %w", candidate, readErr)
			}

			return values, nil
		}

		if err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("stat %s: %w", candidate, err)
		}

		parentDir := filepath.Dir(currentDir)
		if parentDir == currentDir {
			return map[string]string{}, nil
		}

		currentDir = parentDir
	}
}

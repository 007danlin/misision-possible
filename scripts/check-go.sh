#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
# The exact toolchain is shared by Docker, CI and local checks.
export GOTOOLCHAIN=${GOTOOLCHAIN:-go1.27.1}
export GOEXPERIMENT=runtimesecret
mode=${1:-all}

selected=${2:-all}
case "$selected" in
  all) services="backend/auth backend/core backend/notif backend/chat" ;;
  auth|core|notif|chat) services="backend/$selected" ;;
  *) echo "Unknown service: $selected" >&2; exit 2 ;;
esac

for service in $services; do
  (
    cd "$service"
    echo "Checking $service ($mode)"
    case "$mode" in
      format)
        unformatted=$(gofmt -l .)
        if [ -n "$unformatted" ]; then
          echo "$unformatted"
          exit 1
        fi
        ;;
      vet) go vet ./... ;;
      test) go test -race -count=1 -timeout=2m ./... ;;
      stress) go test -race -count=20 -timeout=5m ./... ;;
      build) go build -o /dev/null ./... ;;
      all)
        unformatted=$(gofmt -l .)
        if [ -n "$unformatted" ]; then echo "$unformatted"; exit 1; fi
        go vet ./...
        go test -race -count=1 -timeout=2m ./...
        go build -o /dev/null ./...
        ;;
      *) echo "Unknown check: $mode" >&2; exit 2 ;;
    esac
  )
done

package cache

import (
	"net"
	"testing"
)

func TestNewClosesClientOnConnectionFailure(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	if err := listener.Close(); err != nil {
		t.Fatal(err)
	}
	client, err := New("redis://" + address + "?dial_timeout=50ms&read_timeout=50ms&write_timeout=50ms&max_retries=-1")
	if err == nil {
		client.Close()
		t.Fatal("expected connection failure")
	}
	// TestMain verifies the failed client leaves no pool or retry goroutines.
}

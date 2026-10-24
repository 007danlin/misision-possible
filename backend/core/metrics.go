package main

import (
	"fmt"
	"net/http"
	"sync/atomic"
	"time"
)

type metrics struct {
	requestCount atomic.Uint64
	requestNanos atomic.Uint64
}

func (m *metrics) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/metrics" {
			w.Header().Set("Content-Type", "text/plain; version=0.0.4")
			fmt.Fprintf(w, "# TYPE http_requests_total counter\nhttp_requests_total %d\n# TYPE http_request_duration_seconds summary\nhttp_request_duration_seconds_sum %g\nhttp_request_duration_seconds_count %d\n", m.requestCount.Load(), float64(m.requestNanos.Load())/1e9, m.requestCount.Load())
			return
		}
		start := time.Now()
		defer func() { m.requestCount.Add(1); m.requestNanos.Add(uint64(time.Since(start))) }()
		next.ServeHTTP(w, r)
	})
}

package main

import (
	"testing"
	"time"
)

func TestAgentTimeoutConfiguration(t *testing.T) {
	for _, test := range []struct {
		value   string
		seconds int
	}{{"", 45}, {"180", 180}, {"0", 45}, {"301", 45}, {"invalid", 45}} {
		t.Run(test.value, func(t *testing.T) {
			t.Setenv("AGENT_TURN_TIMEOUT_SECONDS", test.value)
			if got := agentTimeout(); got != time.Duration(test.seconds)*time.Second {
				t.Fatalf("got %v", got)
			}
		})
	}
}

package main

import "testing"

func TestMissingRouteCannotBeConfirmedWithBudgetOverride(t *testing.T) {
	h := map[string]any{"journey": map[string]any{
		"route_missing":    true,
		"total_incomplete": true,
		"checks": []any{
			map[string]any{"code": "route_missing", "status": "unknown", "blocking": true, "message": "Дорога не рассчитана"},
			map[string]any{"code": "budget", "status": "unknown", "blocking": true, "message": "Полный бюджет неизвестен"},
		},
	}}
	for _, override := range []bool{false, true} {
		if got := journeyBlock(h, override); got != "Дорога не рассчитана" {
			t.Fatalf("override=%v: missing route was not blocked: %q", override, got)
		}
	}
}

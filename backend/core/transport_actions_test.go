package main

import (
	"context"
	pb "core/proto"
	"encoding/json"
	"google.golang.org/grpc"
	"net/http"
	"os"
	"testing"
)

type transportAgent struct {
	journeyAgent
	seen map[string]any
}

func (a *transportAgent) Evaluate(ctx context.Context, req *pb.EvaluateRequest, opts ...grpc.CallOption) (*pb.TurnReply, error) {
	_ = json.Unmarshal([]byte(req.StateJson), &a.seen)
	r, e := a.journeyAgent.Evaluate(ctx, req, opts...)
	if e != nil {
		return r, e
	}
	var result map[string]any
	_ = json.Unmarshal([]byte(r.TurnJson), &result)
	h := asMap(asList(result["hotel_options"])[0])
	j := asMap(h["journey"])
	cost := asMap(j["breakdown"])
	cost["transport"] = float64(1234500)
	total := float64(0)
	for _, v := range cost {
		total += v.(float64)
	}
	j["total_minor"] = total
	raw, _ := json.Marshal(result)
	r.TurnJson = string(raw)
	return r, nil
}
func TestTransportPreviewAtomicityAndOwnedTickets(t *testing.T) {
	raw, _ := os.ReadFile("testdata/journey-quotes.json")
	var fixtures map[string]any
	_ = json.Unmarshal(raw, &fixtures)
	v := asMap(fixtures["original"])
	h := cloneTrip(asMap(v["hotel"]))
	spec := cloneTrip(asMap(v["spec"]))
	snap := map[string]any{"trip_spec": spec, "selected_hotel": h, "hotel_options": []any{h}, "search_mode": "hotels", "status": "hotel_checkout"}
	agent := &transportAgent{journeyAgent: journeyAgent{fixtures: fixtures}}
	api := NewAPI("", &http.Client{}, agent)
	before := cloneTrip(snap)
	for _, edit := range []*TransportEdit{{Mode: "rocket"}, {Origin: " "}, {Tickets: &OwnedTickets{Arrival: "bad", Departure: "bad", Terminal: "airport"}}} {
		if api.changeTransport(context.Background(), snap, "", edit, "owner") == "" {
			t.Fatal("invalid edit accepted")
		}
		if !sameJourneySpec(before, snap) {
			t.Fatal("failed edit changed prior trip")
		}
	}
	if msg := api.changeTransport(context.Background(), snap, "", &TransportEdit{Mode: "train", Origin: "Владимир"}, "owner"); msg != "" {
		t.Fatal(msg)
	}
	preview := asMap(snap["journey_preview"])
	if preview == nil || asMap(preview["previous_hotel"])["id"] != h["id"] || asMap(preview["proposed_hotel"])["id"] != h["id"] {
		t.Fatal("hotel lost")
	}
	if asMap(preview["previous_spec"])["origin"] != spec["origin"] || asMap(preview["proposed_spec"])["origin"] != "Владимир" {
		t.Fatal("origin diff lost")
	}
	if journeyTotal(asMap(preview["proposed_hotel"])) == journeyTotal(h) {
		t.Fatal("price not recomputed")
	}
	if asMap(agent.seen["trip_spec"])["transport_mode"] != "train" {
		t.Fatal("agent didn't see mode")
	}
	if msg := applyJourneyPreview(snap, false); msg != "" {
		t.Fatal(msg)
	}
	if !sameJourneySpec(spec, asMap(snap["trip_spec"])) {
		t.Fatal("rollback failed")
	}
	paid := int64(2400000)
	tickets := &OwnedTickets{Arrival: "2026-11-10T12:00:00+03:00", Departure: "2026-11-15T18:00:00+03:00", Terminal: "airport", PaidTotalMinor: &paid}
	if msg := api.changeTransport(context.Background(), snap, "", &TransportEdit{Tickets: tickets}, "owner"); msg != "" {
		t.Fatal(msg)
	}
	if asMap(agent.seen["trip_spec"])["transport_owned"] != true {
		t.Fatal("owned facts lost")
	}
	applyJourneyPreview(snap, true)
	if asMap(snap["trip_spec"])["transport_owned"] != true {
		t.Fatal("accept didn't preserve tickets")
	}
}
func TestAddonNeverInventsOrigin(t *testing.T) {
	api := NewAPI("", &http.Client{}, nil)
	snap := map[string]any{"trip_spec": map[string]any{}, "hotel_booking": map[string]any{"hotel": map[string]any{}}}
	before := cloneTrip(snap)
	if api.tripExtra(context.Background(), snap, "quote_transfer_addon", "", "owner") == "" {
		t.Fatal("missing origin accepted")
	}
	if !sameJourneySpec(before, snap) {
		t.Fatal("invented origin")
	}
}

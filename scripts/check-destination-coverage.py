"""Opt-in live provider smoke test; no booking or model calls."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from travel_agent.destinations import resolve_destination, destination_question
from travel_agent.domain import State, TripSpec
from travel_agent.demo_tools import DemoTools
from travel_agent.model import Settings
from travel_agent.ostrovok import search_hotels
from travel_agent.runner import run_turn


class SearchAgain:
    settings = Settings(model="provider-smoke", timeout=90)

    async def extract(self, context, repair, timeout):
        return "{}", {}


async def main():
    report = []
    for name in ["Ялта", "Карелия", "Крым", "Париж", "Улан-Удэ", "Несуществующийгород12345"]:
        resolved = await resolve_destination(name)
        item = dict(query=name, status=resolved["status"], region=resolved["region"])
        if resolved["status"] == "available":
            hotels, url = await search_hotels(TripSpec(destination=name, travellers={"adults": 2}, stay_nights=4))
            item.update(hotels=len(hotels), url=url, provider_region=hotels[0].get("destination_region") if hotels else None)
            assert hotels, item
        else:
            item["answer"] = (await destination_question(name, resolved))[0]
        report.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
    state = State(search_mode="hotels", trip_spec=dict(
        origin="Москва", destination="Ялта", dates={"start": "2026-11-11", "end": "2026-11-15"},
        travellers={"adults": 2}, budget={"amount_minor": 50000000}, budget_scope="whole_trip",
        expense_reserve={"amount_minor": 1000000}, include_transport=True, hotel_preferences={"pool": True},
    ))
    turn = await run_turn(state, "Подобрать поездку", DemoTools(), SearchAgain())
    assert turn.status == "choosing", turn.assistant_message
    assert turn.hotel_options and all("has_pool" in h["amenity_codes"] for h in turn.hotel_options)
    assert all(h["journey"]["route_missing"] and not h["journey"]["can_book"] for h in turn.hotel_options)
    output = ROOT / ".runtime/destination-coverage"
    output.mkdir(exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    snapshot = dict(state.model_dump(mode="json"), **turn.model_dump(mode="json"))
    snapshot.update(session_id="c" * 32, revision=1, search_mode="hotels")
    (output / "live-turn.json").write_text(json.dumps(snapshot, ensure_ascii=False))
    print("PASS: provider cities, regions, unknown destination and Yalta hotel shortlist", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

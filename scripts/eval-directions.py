"""Opt-in real-model regression: semantic selection, not exact ranked answers.
Run from agent/: PYTHONPATH=. .venv/bin/python ../scripts/eval-directions.py
"""

import asyncio
import json
import time
from pathlib import Path
from travel_agent.domain import State, TripSpec
from travel_agent.demo_tools import DemoTools
from travel_agent.model import QwenModel, Settings
from travel_agent.runner import run_turn

CASES = [
    (
        "forest",
        "Хочется сбежать от зданий: сосны, тропинки, озеро. Никаких экскурсий по центру.",
        {},
        {"karelia", "seliger", "altai", "sochi_nature"},
    ),
    (
        "culture",
        "Хочу музеи и дворцы, леса и походы не нужны.",
        {},
        {
            "petersburg",
            "moscow",
            "kazan",
            "vladimir",
            "yaroslavl",
            "nizhny",
            "kaliningrad",
            "minsk",
            "istanbul",
            "paris",
            "rome",
            "venice",
        },
    ),
    (
        "nearby",
        "Из Москвы на два дня к озеру, без самолётов и дальней дороги.",
        {},
        {"seliger"},
    ),
    (
        "sea",
        "Хочу море и прогулки по набережной, без музеев.",
        {},
        {"sochi", "gelendzhik", "anapa"},
    ),
    (
        "change",
        "Передумал: теперь хочу музеи и дворцы, лес не нужен. Предложи другие места.",
        {"destination": "Сортавала", "travel_setting": "forest"},
        {
            "petersburg",
            "moscow",
            "kazan",
            "vladimir",
            "yaroslavl",
            "nizhny",
            "kaliningrad",
            "minsk",
            "istanbul",
            "paris",
            "rome",
            "venice",
        },
    ),
    ("unsupported", "Хочу увидеть пингвинов в Антарктиде.", {}, set()),
]


async def main():
    results = []
    for name, message, spec, allowed in CASES:
        start = time.monotonic()
        turn = await run_turn(
            State(search_mode="hotels", trip_spec=TripSpec(**spec)),
            message,
            DemoTools(),
            QwenModel(Settings.from_env()),
            timeout=180,
        )
        ids = {d["id"] for d in turn.destination_options}
        passed = (
            (bool(ids) and ids <= allowed)
            if allowed
            else (not ids and turn.status == "needs_input")
        )
        result = dict(
            case=name,
            request=message,
            passed=passed,
            ids=sorted(ids),
            setting=turn.trip_spec.travel_setting,
            destination=turn.trip_spec.destination,
            status=turn.status,
            answer=turn.assistant_message,
            seconds=round(time.monotonic() - start, 2),
            usage=turn.telemetry.usage,
        )
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    target = Path(__file__).resolve().parents[1] / ".runtime/direction-evaluation.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    if not all(r["passed"] for r in results):
        raise SystemExit(1)


asyncio.run(main())

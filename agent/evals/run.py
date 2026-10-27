"""Run actual Qwen calls separately from deterministic contract tests.

From agent/: python -m evals.run --output evals/results/qwen-local.json
"""
import argparse
import hashlib
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from travel_agent.demo_tools import DemoTools
from travel_agent.domain import State, TripSpec
from travel_agent.model import QwenModel, Settings, SYSTEM_PROMPT
from travel_agent.runner import run_turn

FULL = "Из Москвы в Сочи, 10–15 ноября 2026, двое взрослых, до 120 тысяч рублей на дорогу, отель и трансферы со сборами, без ночных рейсов. Хочу спокойно отдохнуть."
BASE = {"origin": "Москва", "destination": "Сочи", "dates": {"start": "2026-11-10", "end": "2026-11-15"}, "travellers": {"adults": 2}, "budget": {"amount_minor": 12000000}, "budget_scope": "booking", "hard_constraints": {"no_night_flights": True}}

# Predicates are independent expectations, not response strings used by production.
CASES = [
    ("01_full", FULL, "empty", "choosing", {"origin": "Москва", "destination": "Сочи", "budget.amount_minor": 12000000, "budget_scope": "booking", "dates.start": "2026-11-10", "dates.end": "2026-11-15", "travellers.adults": 2, "hard_constraints.no_night_flights": True}),
    ("02_origin", "В Сочи 10–15 ноября 2026. Два взрослых, 120 тысяч рублей на дорогу, отель, трансферы и сборы.", "empty", "needs_input", {"origin": None, "destination": "Сочи"}),
    ("03a_whole", "Теперь 100 тысяч рублей на всё", "selected", "needs_input", {"budget_scope": "whole_trip", "budget.amount_minor": 10000000, "expense_reserve": None}),
    ("03b_hotel", "Теперь 100 тысяч рублей только на отель", "selected", "choosing", {"budget_scope": "hotel", "budget.amount_minor": 10000000}),
    ("04_dates", "Мы с девушкой хотим куда-нибудь на 4 дня в ноябре. До 40 тысяч рублей на двоих, красивые места и недолгая дорога.", "empty", "needs_input", {"dates": None, "travellers.adults": 2, "duration_days": 4}),
    ("05_budget", "Теперь максимум 100 тысяч, остальное оставь", "selected", "choosing", {"budget.amount_minor": 10000000, "dates.start": "2026-11-10", "hard_constraints.no_night_flights": True, "travellers.adults": 2}),
    ("06_two_changes", "Теперь максимум 100 тысяч, остальное оставь", "sequence", "choosing", {"budget.amount_minor": 10000000, "hard_constraints.no_night_flights": True}),
    ("07_impossible", "Теперь бюджет 30 тысяч рублей, остальное оставь", "selected", "no_solution", {"budget.amount_minor": 3000000}),
    ("08_refund", "Теперь максимум 100 тысяч, остальное оставь", "refund", "no_solution", {"hard_constraints.free_cancellation": True}),
    ("09a_inspire", "Мы с девушкой хотим куда-нибудь съездить на выходные. Бюджет до 30 тысяч рублей. Хочется природы и недолгой дороги.", "empty", "needs_input", {"destination": None, "travellers.adults": 2}),
    ("09b_kazan", "Лучше в Казань, остальное сохрани", "selected", "choosing", {"destination": "Казань", "origin": "Москва", "dates.start": "2026-11-10"}),
    ("10a_child", "С нами ещё ребёнок", "selected", "needs_input", {"travellers.children": [None]}),
    ("10b_pet", "Поедем с собакой, размещение с ней обязательно", "selected", "no_solution", {"hard_constraints.pets": True}),
    ("12_paraphrase", "Нужен отдых в Сочи вдвоём: отправляемся из Москвы десятого ноября 2026, возвращаемся пятнадцатого. За билеты туда-обратно, проживание, трансферы и сборы готовы отдать не больше ста двадцати тысяч рублей. Ночью лететь нельзя.", "empty", "choosing", {"origin": "Москва", "destination": "Сочи", "dates.start": "2026-11-10", "dates.end": "2026-11-15", "budget.amount_minor": 12000000, "budget_scope": "booking", "travellers.adults": 2, "hard_constraints.no_night_flights": True}),
    ("13_date_shift_igor", "А если мы поедем на два дня позже?", "selected", "choosing", {"dates.start": "2026-11-12", "dates.end": "2026-11-17", "travellers.adults": 2, "destination": "Сочи"}),
    ("14_fresh_wording", "Двое взрослых летят Москва → Казань с 12 по 17 ноября 2026. Бюджет 36 000 ₽ на билеты туда-обратно, гостиницу, трансферы и сборы. Только дневные рейсы.", "empty", "choosing", {"origin": "Москва", "destination": "Казань", "dates.start": "2026-11-12", "dates.end": "2026-11-17", "travellers.adults": 2, "budget.amount_minor": 3600000, "budget_scope": "booking", "hard_constraints.no_night_flights": True}),
    ("15_cheaper_without_amount", "Найди вариант подешевле, ничего другого не меняй", "selected", "choosing", {"budget.amount_minor": 12000000, "dates.start": "2026-11-10", "destination": "Сочи", "travellers.adults": 2, "hard_constraints.no_night_flights": True}),
]


def nested(data, path):
    for key in path.split("."):
        data = data[key] if isinstance(data, dict) and key in data else None
    return data


async def main(output, limit, only=None, warmup=False, suite="regression"):
    tools = DemoTools()
    model = QwenModel(Settings.from_env())
    results = []
    source_root = Path(__file__).resolve().parents[1] / "travel_agent"
    code_sha256 = {name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
                   for name in ("domain.py", "demo_tools.py", "model.py", "runner.py", "tools.py")}
    warmup_ms = None
    if warmup:
        if model.settings.provider != "ollama":
            raise ValueError("Warmup is supported only for local Ollama")
        import httpx
        import time
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.post(model.settings.base_url.rstrip("/").removesuffix("/v1") + "/api/chat",
                                         json={"model": model.settings.model, "messages": [], "stream": False,
                                               "think": False, "keep_alive": "10m", "options": {"num_ctx": 8192}})
            response.raise_for_status()
        warmup_ms = round((time.monotonic() - started) * 1000)
        print(f"Local model warmup: {warmup_ms}ms (outside request budget)", flush=True)
    cases = CASES
    if suite == "holdout-20261027":
        from .holdout_20261027 import CASES as cases
    selected_cases = [case for case in cases if only is None or case[0] in only.split(",")]
    if not selected_cases:
        raise ValueError("No evaluation cases selected")
    for case_id, message, kind, expected_status, expected in selected_cases[:limit]:
        spec = TripSpec.model_validate(BASE)
        if kind == "refund":
            spec.hard_constraints.free_cancellation = True
        selected = (await tools.search_packages(spec))[0]
        state = State() if kind == "empty" else State(revision=3, trip_spec=spec, selected_plan=selected)
        sequence_errors = []
        if kind == "sequence":
            previous = await run_turn(state, "Снизим до 110 тысяч рублей, остальное оставь", tools, model)
            if previous.trip_spec.budget.amount_minor != 11000000 or previous.status == "error":
                sequence_errors.append("first budget change failed")
            state.trip_spec = previous.trip_spec
            state.revision += 1
        turn = await run_turn(state, message, tools, model)
        observed = turn.trip_spec.model_dump(mode="json")
        errors = sequence_errors + [f"{key}: expected {value!r}, got {nested(observed, key)!r}" for key, value in expected.items() if nested(observed, key) != value]
        if turn.status != expected_status:
            errors.append(f"status: expected {expected_status}, got {turn.status}")
        if case_id in {"05_budget", "15_cheaper_without_amount"} and (not turn.change_preview or turn.change_preview.price_delta != -1200000):
            errors.append("expected A -> B, delta -12000 RUB")
        if case_id == "13_date_shift_igor" and (not turn.change_preview or turn.change_preview.price_delta != 200000 or not turn.change_preview.proposed_plan.id.endswith(":A")):
            errors.append("date shift should retain combination A and add 2000 RUB")
        if case_id == "01_full" and turn.questions:
            errors.append("full request must not ask questions")
        if case_id == "09a_inspire" and len(turn.destination_options) < 3:
            errors.append("expected several destinations")
        if turn.checkout_allowed or turn.booking:
            errors.append("agent must never authorize booking")
        row = {"case_id": case_id, "input_message": message, "expected_outcome": {"status": expected_status, "fields": expected},
               "observed_outcome": turn.model_dump(mode="json"), "pass": not errors, "constraint_errors": errors,
               **turn.telemetry.model_dump(), "evaluation_mode": "live_qwen_synthetic_tools", "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(), "configuration": {"provider": model.settings.provider, "model": model.settings.model, "timeout_seconds": model.settings.timeout, "temperature": 0, "code_sha256": code_sha256}}
        results.append(row)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "suite": suite, "warmup_ms": warmup_ms, "results": results}, ensure_ascii=False, indent=2) + "\n")
        print(f"{case_id}: {'PASS' if not errors else 'FAIL'} {turn.telemetry.total_ms}ms {errors}", flush=True)
    return all(row["pass"] for row in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evals/results/qwen-local.json")
    parser.add_argument("--limit", type=int, default=len(CASES))
    parser.add_argument("--only", help="comma-separated case IDs")
    parser.add_argument("--warmup", action="store_true", help="preload local Ollama before timed turns")
    parser.add_argument("--suite", choices=["regression", "holdout-20261027"], default="regression")
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(main(args.output, args.limit, args.only, args.warmup, args.suite)) else 1)

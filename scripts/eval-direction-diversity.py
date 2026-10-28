"""Opt-in HTTP regression against a running stack and its real model.

python3 scripts/eval-direction-diversity.py --output .runtime/direction-diversity.json
Checks semantic alternatives, never an exact ranked order. No API keys needed.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from travel_agent.verify_running import Verification  # noqa: E402


CASES = [
    ("luka_forest", ["Хочу на природу, в лес. Дикая природа.",
                     "Отправляемся из Москвы"],
     {"karelia", "altai", "seliger", "sochi_nature"}, 2, 3),
    ("forest_lakes", ["Из Казани хочется лесных прогулок и озёр. Предложи места для отдыха."],
     {"karelia", "altai", "seliger", "sochi_nature"}, 2, 3),
    ("mountains", ["Из Москвы хочу горные пейзажи и пешие прогулки. Куда поехать?"],
     {"altai", "sochi_nature", "kislovodsk"}, 2, 3),
    ("sea", ["Из Москвы хочу к морю, гулять по берегу. Куда поехать?"],
     {"sochi", "gelendzhik", "anapa"}, 2, 3),
    ("nature", ["Из Москвы хочется отдохнуть на природе. Предложи направления."],
     {"karelia", "altai", "seliger", "sochi_nature", "kislovodsk", "murmansk"}, 2, 3),
    ("city_walks", ["Из Москвы хочу поехать погулять по красивому городу. Предложи направления."],
     {"petersburg", "kazan", "yaroslavl", "vladimir", "nizhny", "kaliningrad",
      "sochi", "kislovodsk", "murmansk"}, 2, 3),
    ("exclusions", ["Из Москвы хочу в лес, но не на Алтай, не на Селигер и не в Сочи."],
     {"karelia"}, 1, 1),
    ("nearby", ["Из Москвы на два дня к озеру, без самолётов и дальней дороги."],
     {"seliger"}, 1, 1),
    ("specific_culture", ["Из Москвы хочу посмотреть каналы и дворцы. Куда поехать?"],
     {"petersburg"}, 1, 1),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"success": False, "cases": []}
    deadline = time.monotonic() + 900
    probe = Verification(args.base_url, 900)
    while time.monotonic() < deadline:
        try:
            code, data = probe.request("/ready", expected=None, record=False)
            if code == 200 and data.get("ready"):
                break
        except (OSError, ValueError):
            pass
        time.sleep(2)
    else:
        raise SystemExit("Stack readiness timed out")

    for name, messages, allowed, minimum, maximum in CASES:
        started = time.monotonic()
        client = Verification(args.base_url, 900)
        result = {"case": name, "messages": messages, "passed": False,
                  "allowed_ids": sorted(allowed), "expected_count": [minimum, maximum]}
        try:
            _, client.state = client.request("/api/sessions/", {"search_mode": "hotels"})
            client.session_path = "/api/sessions/" + client.state["session_id"]
            for message in messages:
                client.operation(message=message)
            cards = client.state.get("destination_options", [])
            ids = [d["id"] for d in cards]
            result.update(ids=ids, cards=cards, answer=client.state.get("assistant_message"),
                          trip_spec=client.state.get("trip_spec"),
                          telemetry=client.state.get("telemetry"))
            assert minimum <= len(ids) <= maximum, f"Unexpected count: {len(ids)}"
            assert len(set(ids)) == len(ids), "Duplicate destinations"
            assert set(ids) <= allowed, "Unsuitable or excluded destination"
            assert client.state.get("telemetry", {}).get("model_calls", 0) >= 1, "No real model call"
            result["passed"] = True
        except (AssertionError, KeyError, OSError, ValueError) as error:
            result["failure"] = str(error)
        result["seconds"] = round(time.monotonic() - started, 3)
        result["steps"] = client.report["steps"]
        report["cases"].append(result)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k: result[k] for k in ("case", "passed", "seconds")}
                         | {"ids": result.get("ids"), "failure": result.get("failure")},
                         ensure_ascii=False), flush=True)
    report["success"] = all(case["passed"] for case in report["cases"])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

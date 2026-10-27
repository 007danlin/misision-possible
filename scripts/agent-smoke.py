"""Explicit live-model HTTP smoke test; requires an existing Auth token.

AGENT_SMOKE_TOKEN=... python3 scripts/agent-smoke.py
Never prints the token; use a local shell environment, not a checked-in file.
"""
import json
import os
import urllib.error
import urllib.request

base = os.environ.get("SMOKE_BASE_URL", "http://localhost").rstrip("/")
token = os.environ.get("AGENT_SMOKE_TOKEN")
if not token:
    raise SystemExit("Set AGENT_SMOKE_TOKEN to an existing Auth access token")
body = {"message": "Хочу в Казань. Нас двое.", "state": {}}
request = urllib.request.Request(base + "/api/core/agent/turn", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
try:
    with urllib.request.urlopen(request, timeout=50) as response:
        turn = json.load(response)
except urllib.error.HTTPError as error:
    raise SystemExit(f"HTTP {error.code}: agent integration failed") from None
assert turn["status"] == "needs_input", (turn["status"], turn.get("error_code"))
assert turn["trip_spec"]["destination"] == "Казань", turn["trip_spec"]
assert turn["trip_spec"]["travellers"]["adults"] == 2, turn["trip_spec"]
assert not turn["checkout_allowed"] and turn["booking"] is None
assert turn["questions"]
print(json.dumps({"status": "PASS", "path": "HTTP Core -> Auth -> gRPC -> Qwen", "telemetry": turn["telemetry"]}, ensure_ascii=False))

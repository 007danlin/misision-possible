"""Verify the real HTTP/model/search/checkout path of an already running stack.

Run inside the existing agent container; no host Python, browser or API key is
needed. This creates one explicitly simulated booking and leaves it for review.
It never switches sources or changes the service's inference timeouts.
"""

import argparse
from datetime import datetime, timedelta, timezone
import http.cookiejar
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid


def check(condition, message):
    if not condition:
        raise AssertionError(message)


class Verification:
    def __init__(self, base_url, ready_timeout):
        self.base_url = base_url.rstrip("/")
        self.ready_timeout = ready_timeout
        self.client = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )
        self.report = {"success": False, "steps": []}
        self.state = None
        self.session_path = None

    def request(self, route, payload=None, *, expected=200, record=True):
        started = time.monotonic()
        request = urllib.request.Request(
            self.base_url + route,
            data=json.dumps(payload, ensure_ascii=False).encode()
            if payload is not None
            else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = self.client.open(request, timeout=315 if record else 3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.status
            data = json.load(response)
        if record:
            step = {
                "method": request.get_method(),
                "route": route,
                "http_status": status,
                "seconds": round(time.monotonic() - started, 3),
            }
            self.report["steps"].append(step)
            if isinstance(data, dict):
                step["state"] = data.get("status")
                step["error_code"] = data.get("error_code")
                if "telemetry" in data:
                    step["telemetry"] = data["telemetry"]
        check(
            expected is None or status == expected,
            f"{route}: HTTP {status}, {data.get('error', data.get('message'))}",
        )
        return status, data

    def operation(self, action=None, message=None, **extra):
        payload = {
            "expected_revision": self.state["revision"],
            "idempotency_key": str(uuid.uuid4()),
            **extra,
        }
        if action:
            payload["type"] = action
        else:
            payload["message"] = message
        _, self.state = self.request(
            self.session_path + ("/actions" if action else "/turns"), payload
        )
        check(
            not self.state.get("error_code"),
            f"Agent failed: {self.state.get('error_code')}",
        )
        return self.state

    def run(self):
        started = time.monotonic()
        last_phase = None
        while time.monotonic() - started <= self.ready_timeout:
            try:
                code, readiness = self.request("/ready", expected=None, record=False)
                if code == 200 and readiness.get("ready"):
                    break
                phase = readiness.get("phase")
                if phase != last_phase:
                    print(
                        json.dumps({"waiting": phase}, ensure_ascii=False),
                        file=sys.stderr,
                        flush=True,
                    )
                    last_phase = phase
            except (OSError, ValueError):
                pass
            time.sleep(2)
        else:
            raise AssertionError(
                "The stack did not become ready within the verification deadline"
            )
        self.report["readiness_wait_seconds"] = round(time.monotonic() - started, 3)
        _, health = self.request("/health")
        check(health.get("status") == "ok", "Process health failed")
        _, runtime = self.request("/api/local/status")
        check(
            runtime.get("hotel_data_source") == "public",
            "Expected public hotel metadata",
        )
        check(
            runtime.get("pricing_mode") == "estimated"
            and runtime.get("real_booking") is False,
            "The prototype must report estimated prices and simulated booking",
        )
        self.report["runtime"] = runtime

        start = (datetime.now(timezone(timedelta(hours=3))) + timedelta(days=14)).date()
        end = start + timedelta(days=5)
        _, self.state = self.request("/api/sessions/", {"search_mode": "hotels"})
        self.session_path = "/api/sessions/" + self.state["session_id"]
        self.report["session_id"] = self.state["session_id"]
        message = (
            f"Из Москвы в Сочи, {start:%d.%m.%Y}–{end:%d.%m.%Y}, двое взрослых. "
            "120 тысяч рублей на дорогу, отель и оба трансфера. "
            "Без ночных рейсов, нужен бассейн. Резерв на личные расходы 0 рублей."
        )
        self.report["request_message"] = message
        self.operation(message=message)
        model_calls = self.state.get("telemetry", {}).get("model_calls", 0)
        if self.state["status"] == "needs_input":
            self.operation(message="Резерв на личные расходы 0 рублей.")
        check(model_calls >= 1, "The first free-text request must use the real model")
        check(
            self.state["status"] == "choosing",
            f"No usable shortlist: {self.state['status']}",
        )
        spec = self.state["trip_spec"]
        check(
            spec.get("origin") == "Москва" and spec.get("destination") == "Сочи",
            "Route was not preserved",
        )
        check(
            spec.get("dates") == {"start": str(start), "end": str(end)},
            "Dates were not preserved",
        )
        check(
            spec.get("travellers", {}).get("adults") == 2,
            "Traveller count was not preserved",
        )
        check(
            spec.get("hotel_preferences", {}).get("pool") is True,
            "Pool requirement was lost",
        )
        check(
            spec.get("hard_constraints", {}).get("no_night_flights") is True,
            "Night-flight constraint was lost",
        )
        options = self.state.get("hotel_options", [])
        check(
            options and all(h.get("source_kind") == "public" for h in options),
            "No real public hotel metadata",
        )
        bookable = [h for h in options if h.get("journey", {}).get("can_book")]
        check(bookable, "No bookable simulated trip")
        hotel = bookable[0]
        journey = hotel["journey"]
        check(
            sum(journey["breakdown"].values()) == journey["total_minor"],
            "Trip price components do not add up",
        )
        check(
            journey["total_minor"] <= 12000000, "The proposed trip exceeds its budget"
        )
        self.report["public_hotels"] = len(options)
        self.operation("select_hotel", hotel_id=hotel["id"])
        check(self.state["status"] == "hotel_checkout", "Hotel selection failed")

        extended_end = end + timedelta(days=2)
        self.operation(
            "update_hotel_stay",
            stay={
                "check_in": str(start),
                "check_out": str(extended_end),
                "adults": 2,
                "children": [],
            },
        )
        check(
            self.state.get("journey_preview")
            and self.state.get("selected_hotel") is None,
            "A price change must require explicit acceptance",
        )
        self.operation("accept_journey_change")
        check(
            self.state["trip_spec"]["dates"]["end"] == str(extended_end),
            "Date edit was not applied",
        )
        self.operation(
            "confirm_hotel_booking",
            check_in=str(start),
            guest_name="Тестовый Гость",
            confirm_prototype=True,
        )
        check(self.state["status"] == "hotel_booked", "Simulated booking failed")
        booking = self.state["hotel_booking"]
        check(
            booking.get("is_demo") is True, "The test must never create a real booking"
        )
        _, restored = self.request(self.session_path)
        check(
            restored["hotel_booking"] == booking, "The saved booking was not restored"
        )
        self.report["booking_id"] = booking["id"]
        self.report["booking_total_minor"] = booking["hotel"]["journey"]["total_minor"]
        self.report["success"] = True
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://app:8080")
    parser.add_argument("--ready-timeout", type=int, default=600)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verification = Verification(args.base_url, args.ready_timeout)
    started = time.monotonic()
    try:
        verification.run()
    except (AssertionError, KeyError, OSError, ValueError) as error:
        verification.report["failure"] = str(error)
    verification.report["total_seconds"] = round(time.monotonic() - started, 3)
    result = json.dumps(verification.report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
    print(result, flush=True)
    return 0 if verification.report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

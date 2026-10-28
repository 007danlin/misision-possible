"""Documented, keyless Tutu cached timetable. Never a dated availability search."""

import asyncio
import json
import time
import re
import httpx

SOURCE = "https://support.travelpayouts.com/hc/ru/articles/360020147791"
STATIONS = {
    "Москва": "2000000",
    "Сочи": "2064130",
}  # Codes verified in the provider's example.
_cache = {}


def parse(text):
    text = text.strip()
    if text.startswith("n(") and text.endswith(")"):
        text = text[2:-1]
    elif text.startswith("n(") and text.endswith(");"):
        text = text[2:-2]
    data = json.loads(text)
    rows = []
    for row in data.get("trips", []):
        try:
            minutes = int(row["travelTimeInSeconds"]) // 60
            prices = [
                int(x["price"]) * 100
                for x in row.get("categories", [])
                if isinstance(x.get("price"), (int, float)) and x["price"] > 0
            ]
            if not 10 <= minutes <= 10080 or not prices:
                continue
            if not all(
                re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d", row.get(k, ""))
                for k in ["departureTime", "arrivalTime"]
            ):
                continue
            rows.append(
                {
                    "minutes": minutes,
                    "price_minor": min(prices),
                    "departure_time": row["departureTime"][:5],
                    "arrival_time": row["arrivalTime"][:5],
                    "train_number": str(row.get("trainNumber", ""))[:20],
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(rows, key=lambda x: (x["minutes"], x["price_minor"]))


async def prepare(spec):
    if (
        spec.origin not in STATIONS
        or spec.destination not in STATIONS
        or spec.origin == spec.destination
    ):
        return None
    key = spec.origin + "|" + spec.destination
    old = _cache.get(key)
    if old and time.time() - old["retrieved"] < 21600:
        return old

    async def direction(a, b):
        async with httpx.AsyncClient(
            timeout=4, headers={"User-Agent": "OPlan-Hackathon/1.0"}
        ) as client:
            r = await client.get(
                "https://suggest.travelpayouts.com/search",
                params={
                    "service": "tutu_trains",
                    "term": STATIONS[a],
                    "term2": STATIONS[b],
                    "callback": "n",
                },
            )
            r.raise_for_status()
            if len(r.content) > 500000:
                raise ValueError("too large")
            return parse(r.text)

    try:
        out, back = await asyncio.gather(
            direction(spec.origin, spec.destination),
            direction(spec.destination, spec.origin),
        )
        if not out or not back:
            return None
        result = {
            "out": out[0],
            "back": back[0],
            "retrieved": time.time(),
            "source_url": SOURCE,
            "source": "Туту / Travelpayouts · кэш без проверки даты",
            "count_out": len(out),
            "count_back": len(back),
        }
        _cache[key] = result
        return result
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None

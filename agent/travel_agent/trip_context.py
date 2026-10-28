"""Context independent from hotel facts: editorial route estimates and weather."""

from datetime import datetime, timedelta, timezone
import math
import time
import os
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import httpx
from collections import Counter

# Reference terminal points, not a routing service. No road distance claims.
TERMINALS = {
    "Сочи": (43.4499, 39.9566),
    "Казань": (55.7877, 49.1004),
    "Ярославль": (57.6261, 39.8353),
    "Сортавала": (61.6967, 30.6913),
    "Санкт-Петербург": (59.9303, 30.3623),
    "Владимир": (56.1295, 40.4202),
}
SEASONS = {
    "Сочи": "Мягкий приморский климат; поздней осенью отдых лучше планировать вокруг прогулок и крытых пространств, а не купания.",
    "Сортавала": "Северный климат: осенью и зимой короткий световой день; прогулки лучше ставить на первую половину дня.",
    "Казань": "Континентальный климат; в холодный сезон чередуйте прогулки и посещение музеев.",
    "Ярославль": "Умеренно континентальный климат; в холодный сезон пригодятся варианты отдыха в помещении.",
    "Санкт-Петербург": "Влажный морской климат; предусмотрите занятия в помещении на случай осадков.",
    "Владимир": "Умеренно континентальный климат; в холодный сезон закладывайте время на обогрев между прогулками.",
}
_weather = {}
_met_raw = {}


def weather_condition(code):
    """User-facing conditions from WMO codes or MET symbol codes."""
    if isinstance(code, str):
        symbol = code.split("_")[0]
        if "thunder" in symbol:
            return "Возможна гроза"
        if "sleet" in symbol:
            return "Дождь со снегом"
        if "snow" in symbol:
            return "Возможен снег"
        if "rain" in symbol:
            return "Возможен дождь"
        return {
            "clearsky": "Ясно",
            "fair": "Малооблачно",
            "partlycloudy": "Переменная облачность",
            "cloudy": "Облачно",
            "fog": "Туман",
        }.get(symbol)
    if code == 0:
        return "Ясно"
    if code in {1, 2}:
        return "Переменная облачность"
    if code == 3:
        return "Облачно"
    if code in {45, 48}:
        return "Туман"
    if code in {51, 53, 55, 56, 57}:
        return "Морось"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "Возможен дождь"
    if code in {71, 73, 75, 77, 85, 86}:
        return "Возможен снег"
    if code in {95, 96, 99}:
        return "Возможна гроза"
    return None


def forecast_summary(days):
    temperatures = [
        d[k] for d in days for k in ("min", "max") if isinstance(d.get(k), (int, float))
    ]
    if not temperatures:
        return "Прогноз пока недоступен."

    def degrees(t):
        return (("+" if t > 0 else "") + f"{t:g}").replace(".", ",")

    conditions = [d["condition"] for d in days if d.get("condition")]
    condition = Counter(conditions).most_common(1)[0][0] if conditions else ""
    if any(
        "дожд" in c.lower()
        or "снег" in c.lower()
        or "гроз" in c.lower()
        or c == "Морось"
        for c in conditions
    ):
        wet = [
            c
            for c in conditions
            if "дожд" in c.lower()
            or "снег" in c.lower()
            or "гроз" in c.lower()
            or c == "Морось"
        ]
        condition = Counter(wet).most_common(1)[0][0]
    return f"{degrees(min(temperatures))}…{degrees(max(temperatures))} °C" + (
        ". " + condition if condition else ""
    )


def distance(a, b):
    lat1, lat2 = map(math.radians, [a[0], b[0]])
    dl = math.radians(b[0] - a[0])
    dn = math.radians(b[1] - a[1])
    x = math.sin(dl / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dn / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(x)))


def transfer_estimate(hotel, spec):
    point = TERMINALS.get(spec.destination)
    c = hotel.get("coordinates") or {}
    km = (
        distance(point, (c["lat"], c["lng"]))
        if point
        and isinstance(c.get("lat"), (int, float))
        and isinstance(c.get("lng"), (int, float))
        else None
    )
    return {
        "minutes": max(25, math.ceil((km or 20) * 1.5 / 35 * 60 + 15)),
        "oneway_minor": int(math.ceil((800 + (km or 20) * 1.5 * 45) / 100) * 10000),
        "straight_km": round(km, 1) if km is not None else None,
        "terminal": {"lat": point[0], "lng": point[1]} if point else None,
        "assumptions": "Оценка автомобиля: 3 пассажира; путь ≈ расстояние по прямой × 1,5, средняя скорость 35 км/ч + 15 мин. Базовая стоимость 800 ₽ + 45 ₽/км. Пробки и фактическая подача не подтверждены.",
    }


async def weather_context(hotel, spec):
    now = datetime.now(ZoneInfo("Europe/Moscow")).date()
    season = {
        "kind": "seasonal",
        "text": SEASONS.get(spec.destination, "Уточните погоду ближе к поездке."),
        "source_label": "О сезоне",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    c = hotel.get("coordinates") or {}
    if not isinstance(c.get("lat"), (int, float)) or not isinstance(
        c.get("lng"), (int, float)
    ):
        return dict(season, reason="Не удалось определить место для прогноза.")
    requested_dates = spec.dates
    upcoming = (
        not requested_dates
        or requested_dates.start > now + timedelta(days=15)
        or requested_dates.start < now
    )
    if upcoming:
        from .domain import Dates

        spec = spec.model_copy(
            update={"dates": Dates(start=now, end=now + timedelta(days=4))}
        )

    def decorate(result):
        result = dict(result)
        result["summary"] = forecast_summary(result["days"])
        result["scope"] = "upcoming" if upcoming else "trip"
        if upcoming:
            result["text"] = (
                "На даты поездки прогноза ещё нет. Показываем ближайшие дни."
                if requested_dates
                else "Погода на ближайшие дни. Укажите даты, чтобы посмотреть прогноз для поездки."
            )
        else:
            result["text"] = "Погода может меняться — проверьте прогноз перед выездом."
            if result["days"][-1]["date"] < str(requested_dates.end):
                result["text"] = (
                    "Пока доступен прогноз на часть поездки. Остальные дни появятся ближе к выезду."
                )
        return result

    try:
        met = await met_forecast(hotel, spec)
        if met:
            return decorate(met)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
        pass
    end = min(spec.dates.end, now + timedelta(days=15))
    key = (round(c["lat"], 2), round(c["lng"], 2), str(spec.dates.start), str(end))
    cached = _weather.get(key)
    if cached and time.monotonic() - cached[0] < 1800:
        return decorate(cached[1])
    try:
        async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": key[0],
                    "longitude": key[1],
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                    "timezone": "Europe/Moscow",
                    "start_date": key[2],
                    "end_date": key[3],
                },
            )
            r.raise_for_status()
            d = r.json()["daily"]
        days = [
            {
                "date": day,
                "min": d["temperature_2m_min"][i],
                "max": d["temperature_2m_max"][i],
                "rain_probability": d["precipitation_probability_max"][i],
                "condition": weather_condition(
                    d.get("weather_code", [None] * len(d["time"]))[i]
                ),
            }
            for i, day in enumerate(d["time"])
            if isinstance(d["temperature_2m_min"][i], (int, float))
            and isinstance(d["temperature_2m_max"][i], (int, float))
        ]
        if not days:
            raise ValueError("empty forecast")
        result = {
            "kind": "forecast",
            "days": days,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source_url": "https://open-meteo.com/",
            "source_label": "Open-Meteo · CC BY 4.0",
        }
        _weather[key] = (time.monotonic(), result)
        return decorate(result)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
        # MET may have a shorter horizon than the requested trip. Its cached
        # current forecast can still provide useful, explicitly dated weather.
        if not upcoming and (round(c["lat"], 2), round(c["lng"], 2)) in _met_raw:
            from .domain import Dates

            nearby = spec.model_copy(
                update={"dates": Dates(start=now, end=now + timedelta(days=4))}
            )
            try:
                current = await met_forecast(hotel, nearby)
                if current:
                    upcoming = True
                    return decorate(current)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
                pass
        return dict(
            season, reason="Не удалось обновить погоду. Попробуйте ещё раз позже."
        )


async def met_forecast(hotel, spec):
    """MET Norway's hourly values: daily ranges are sampled forecast, not observations."""
    c = hotel.get("coordinates") or {}
    key = (
        "met",
        round(c["lat"], 2),
        round(c["lng"], 2),
        str(spec.dates.start),
        str(spec.dates.end),
    )
    cached = _weather.get(key)
    if cached and time.monotonic() - cached[0] < 1800:
        return cached[1]
    location = key[1:3]
    raw = _met_raw.get(location)
    data = raw["data"] if raw else None
    if not raw or time.time() >= raw["expires"]:
        headers = {
            "User-Agent": os.getenv(
                "PUBLIC_DATA_USER_AGENT",
                "OPlan-Hackathon/1.0 https://github.com/ostrovok-hackathon-2026/misision-possible",
            )
        }
        if raw and raw.get("modified"):
            headers["If-Modified-Since"] = raw["modified"]
        async with httpx.AsyncClient(timeout=3, headers=headers) as client:
            r = await client.get(
                "https://api.met.no/weatherapi/locationforecast/2.0/compact",
                params={"lat": key[1], "lon": key[2]},
            )
            if r.status_code != 304:
                r.raise_for_status()
                data = r.json()["properties"]
        expires = (
            max(
                time.time() + 1800,
                parsedate_to_datetime(r.headers["expires"]).timestamp(),
            )
            if r.headers.get("expires")
            else time.time() + 1800
        )
        _met_raw[location] = {
            "data": data,
            "expires": expires,
            "modified": r.headers.get("last-modified") or (raw or {}).get("modified"),
        }
    days = {}
    conditions = {}
    probabilities = {}
    for item in data["timeseries"]:
        day = (
            datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            .astimezone(ZoneInfo("Europe/Moscow"))
            .date()
        )
        if not spec.dates.start <= day <= spec.dates.end:
            continue
        temp = item["data"]["instant"]["details"].get("air_temperature")
        if not isinstance(temp, (int, float)):
            continue
        day = str(day)
        days.setdefault(day, []).append(temp)
        period = next(
            (
                item["data"][k]
                for k in ("next_1_hours", "next_6_hours", "next_12_hours")
                if k in item["data"]
            ),
            {},
        )
        condition = weather_condition(period.get("summary", {}).get("symbol_code"))
        if condition:
            conditions.setdefault(day, []).append(condition)
        probability = period.get("details", {}).get("probability_of_precipitation")
        if isinstance(probability, (int, float)):
            probabilities.setdefault(day, []).append(probability)
    if not days:
        return None
    forecast = []
    for day, t in sorted(days.items()):
        entry = {"date": day, "min": round(min(t), 1), "max": round(max(t), 1)}
        if conditions.get(day):
            entry["condition"] = Counter(conditions[day]).most_common(1)[0][0]
        if probabilities.get(day):
            entry["rain_probability"] = max(probabilities[day])
        forecast.append(entry)
    result = {
        "kind": "forecast",
        "days": forecast,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "forecast_updated_at": data["meta"]["updated_at"],
        "source_url": "https://api.met.no/",
        "source_label": "MET Norway · CC BY 4.0",
    }
    _weather[key] = (time.monotonic(), result)
    return result

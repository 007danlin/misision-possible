import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx

from travel_agent import trip_context as weather
from travel_agent.domain import Dates, TripSpec


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        weather._weather.clear()
        weather._met_raw.clear()
        self.today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        self.hotel = {"coordinates": {"lat": 43.6, "lng": 39.7}}
        self.spec = TripSpec(
            destination="Сочи",
            dates=Dates(start=self.today, end=self.today + timedelta(days=3)),
        )

    def client(self, handler):
        original = httpx.AsyncClient
        return patch.object(
            weather.httpx,
            "AsyncClient",
            side_effect=lambda **kw: original(
                transport=httpx.MockTransport(handler), **kw
            ),
        )

    async def test_met_supplies_temperature_conditions_precipitation_and_cache(self):
        calls = []
        stamp = datetime.combine(
            self.today, datetime.min.time(), ZoneInfo("Europe/Moscow")
        ).astimezone(timezone.utc)

        def respond(request):
            calls.append(request)
            series = [
                {
                    "time": (stamp + timedelta(hours=i)).isoformat(),
                    "data": {
                        "instant": {"details": {"air_temperature": temp}},
                        "next_1_hours": {
                            "summary": {"symbol_code": "rain_day"},
                            "details": {"probability_of_precipitation": 65},
                        },
                    },
                }
                for i, temp in enumerate((10, 14, 12))
            ]
            return httpx.Response(
                200,
                json={
                    "properties": {
                        "meta": {"updated_at": stamp.isoformat()},
                        "timeseries": series,
                    }
                },
            )

        with self.client(respond):
            result = await weather.weather_context(self.hotel, self.spec)
            cached = await weather.weather_context(self.hotel, self.spec)
        self.assertEqual(result["scope"], "trip")
        self.assertEqual(result["days"][0]["min"], 10)
        self.assertEqual(result["days"][0]["max"], 14)
        self.assertEqual(result["days"][0]["rain_probability"], 65)
        self.assertEqual(result["days"][0]["condition"], "Возможен дождь")
        self.assertIn("+10…+14 °C", result["summary"])
        self.assertIn("дождь", result["summary"])
        self.assertEqual(result, cached)
        self.assertEqual(len(calls), 1)

    async def test_open_meteo_fallback_contains_weather_code_and_preserves_zero(self):
        def respond(request):
            self.assertIn("weather_code", request.url.params["daily"])
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "time": [str(self.today)],
                        "temperature_2m_min": [-2],
                        "temperature_2m_max": [0],
                        "precipitation_probability_max": [0],
                        "weather_code": [3],
                    }
                },
            )

        with (
            patch.object(
                weather,
                "met_forecast",
                AsyncMock(side_effect=httpx.ReadTimeout("timeout")),
            ),
            self.client(respond),
        ):
            result = await weather.weather_context(self.hotel, self.spec)
        self.assertEqual(result["days"][0]["max"], 0)
        self.assertEqual(result["days"][0]["rain_probability"], 0)
        self.assertEqual(result["summary"], "-2…0 °C. Облачно")

    async def test_no_dates_gets_a_labelled_upcoming_forecast(self):
        forecast = {
            "kind": "forecast",
            "days": [
                {"date": str(self.today), "min": 5, "max": 10, "condition": "Ясно"}
            ],
        }
        with patch.object(
            weather, "met_forecast", AsyncMock(return_value=forecast)
        ) as met:
            result = await weather.weather_context(
                self.hotel, TripSpec(destination="Сочи")
            )
        self.assertEqual(result["scope"], "upcoming")
        self.assertIn("Укажите даты", result["text"])
        self.assertEqual(met.call_args.args[1].dates.start, self.today)

    async def test_shorter_provider_horizon_keeps_a_labelled_current_forecast(self):
        self.spec.dates = Dates(
            start=self.today + timedelta(days=14), end=self.today + timedelta(days=18)
        )
        stamp = datetime.combine(
            self.today, datetime.min.time(), ZoneInfo("Europe/Moscow")
        ).isoformat()

        def respond(request):
            if request.url.host == "api.met.no":
                return httpx.Response(
                    200,
                    json={
                        "properties": {
                            "meta": {"updated_at": stamp},
                            "timeseries": [
                                {
                                    "time": stamp,
                                    "data": {
                                        "instant": {"details": {"air_temperature": 15}},
                                        "next_6_hours": {
                                            "summary": {"symbol_code": "cloudy"}
                                        },
                                    },
                                }
                            ],
                        }
                    },
                )
            return httpx.Response(503)

        with self.client(respond):
            result = await weather.weather_context(self.hotel, self.spec)
        self.assertEqual(result["scope"], "upcoming")
        self.assertIn("На даты поездки прогноза", result["text"])
        self.assertIn("+15", result["summary"])
        self.assertEqual(result["days"][0]["date"], str(self.today))

    async def test_empty_and_failed_providers_never_invent_weather(self):
        with (
            patch.object(weather, "met_forecast", AsyncMock(return_value=None)),
            self.client(lambda _: httpx.Response(503)),
        ):
            result = await weather.weather_context(self.hotel, self.spec)
        self.assertEqual(result["kind"], "seasonal")
        self.assertNotIn("days", result)
        self.assertNotIn("summary", result)
        self.assertIn("Не удалось обновить", result["reason"])

    async def test_missing_coordinates_does_not_request_weather(self):
        with patch.object(weather, "met_forecast", AsyncMock()) as met:
            result = await weather.weather_context({}, self.spec)
        met.assert_not_called()
        self.assertNotIn("days", result)

    def test_unknown_condition_is_not_reported_as_clear(self):
        self.assertIsNone(weather.weather_condition(999))
        self.assertIsNone(weather.weather_condition("unknown"))

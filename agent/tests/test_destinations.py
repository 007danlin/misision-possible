import unittest
from unittest.mock import patch

import httpx

from travel_agent import destinations as d
from travel_agent.tools import ToolError


def region(name="Ялта", slug="russia/yalta", **extra):
    return dict(id=180352, type="City", name=name, slug=slug, country="Россия", country_code="RU", is_sales_closed=False, **extra)


class DestinationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        d._cache.clear()

    async def resolve(self, name, regions, country=None, status=200):
        def handle(request):
            self.assertEqual(request.url.host, "ostrovok.ru")
            self.assertEqual(request.url.path, "/api/site/multicomplete.json")
            self.assertEqual(request.url.params["query"], name)
            return httpx.Response(status, json={"regions": regions})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        with patch.object(d.httpx, "AsyncClient", return_value=client):
            return await d.resolve_destination(name, country)

    async def test_yalta_and_arbitrary_city_use_provider_slugs(self):
        for name, slug in [("Ялта", "russia/yalta"), ("Улан-Удэ", "russia/ulan-ude")]:
            result = await self.resolve(name, [region(name, slug)])
            self.assertEqual(result["status"], "available")
            self.assertEqual(result["region"]["slug"], slug)

    async def test_region_not_replaced_by_city(self):
        karelia = region("Республика Карелия", "russia/northwest_russia_karelia_province")
        karelia["type"] = "Province (State)"
        result = await self.resolve("Карелия", [karelia, region("Сортавала, Республика Карелия", "russia/sortavala")])
        self.assertEqual(result["region"]["slug"], karelia["slug"])

    async def test_sales_closed_is_not_available(self):
        closed = region()
        closed["is_sales_closed"] = True
        result = await self.resolve("Ялта", [closed, region("Большая Ялта", "russia/big_yalta")])
        self.assertEqual(result["status"], "closed")
        self.assertEqual([r["name"] for r in result["suggestions"]], ["Большая Ялта"])

    async def test_not_found_and_ambiguity_are_distinct(self):
        self.assertEqual((await self.resolve("Неизвестноград", []))["status"], "not_found")
        choices = [region("Александровск", "russia/aleksandrovsk"), region("Александровск", "russia/other_aleksandrovsk")]
        result = await self.resolve("Александровск", choices)
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["region"])

    async def test_country_resolves_same_name(self):
        choices = [region("Париж", "france/paris"), region("Париж, Витебская область", "belarus/parizh")]
        choices[0].update(country="Франция", country_code="FR")
        choices[1].update(country="Беларусь", country_code="BY")
        result = await self.resolve("Париж", choices, "Беларусь")
        self.assertEqual(result["region"]["slug"], "belarus/parizh")

    async def test_provider_errors_never_become_negative_coverage(self):
        for status, regions in [(503, []), (200, None), (200, [dict(region(), slug="https://example.com/private")])]:
            with self.assertRaisesRegex(ToolError, "временная ошибка"):
                await self.resolve("Ялта", regions, status=status)
            self.assertFalse(d._cache)

    async def test_user_urls_never_become_network_targets(self):
        with patch.object(d.httpx, "AsyncClient") as client:
            for value in ["https://localhost/private", "../private", "127.0.0.1", "file:///tmp/secret"]:
                with self.assertRaises(ToolError):
                    await d.resolve_destination(value)
            client.assert_not_called()

    async def test_positive_cache_is_bounded_and_avoids_duplicate_requests(self):
        first = await self.resolve("Ялта", [region()])
        with patch.object(d.httpx, "AsyncClient") as client:
            self.assertEqual(await d.resolve_destination("ялта"), first)
            client.assert_not_called()

    async def test_fallback_alternatives_are_checked(self):
        async def resolve(name):
            return dict(status="closed" if name == "Казань" else "available", region=region(name, "russia/test"))
        with patch.object(d, "resolve_destination", side_effect=resolve) as lookup:
            text, question, suggestions = await d.destination_question("Неизвестноград", dict(status="not_found", suggestions=[]))
        self.assertEqual(lookup.await_count, 3)
        self.assertIn("Сочи", text)
        self.assertNotIn("Казань", text)
        self.assertEqual(question, "Какое направление выбрать?")

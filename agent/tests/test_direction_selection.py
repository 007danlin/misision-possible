import json
import unittest
from unittest.mock import patch
import httpx

from travel_agent.domain import State, TripSpec
from travel_agent.demo_tools import DemoTools
from travel_agent.inspiration import (
    CATALOGUE,
    direction_options,
    resolve_directions,
    direction_choice,
)
from travel_agent.model import ModelError, QwenModel, Settings
from travel_agent.runner import run_turn
from test_agent import FakeModel


def selection(*ids):
    return {"choices": [{"id": id, "facts": [0]} for id in ids], "question": "none"}


class DirectionValidationTests(unittest.TestCase):
    def test_setting_and_country_are_hard_boundaries_independent_of_transport(self):
        for setting in ("forest", "nature", "mountains", "sea", "city"):
            for include_transport in (False, True):
                options = direction_options(
                    TripSpec(
                        travel_setting=setting,
                        include_transport=include_transport,
                        country="Россия",
                    )
                )
                self.assertTrue(options)
                self.assertTrue(
                    all(
                        setting in d["settings"] and d["country"] == "Россия"
                        for d in options
                    )
                )
        self.assertEqual(direction_options(TripSpec(country="Япония")), [])
        self.assertEqual(
            {d["id"] for d in direction_options(TripSpec(country="Италия"))},
            {"rome", "venice"},
        )

    def test_only_real_supported_places_can_reach_cards(self):
        pool = direction_options(TripSpec(travel_setting="forest"))
        for payload in [
            selection("invented"),
            selection("kazan"),
            selection("karelia", "karelia"),
            {"choices": [{"id": "karelia", "facts": [999]}], "question": "none"},
            {"choices": [{"id": "karelia", "facts": [-1]}], "question": "none"},
            {"choices": [{"id": "karelia", "facts": [True]}], "question": "none"},
            {
                "choices": [{"id": "karelia", "facts": [0], "price": 100}],
                "question": "none",
            },
            {"choices": [], "question": "none"},
            selection("karelia", "altai", "seliger", "sochi_nature"),
        ]:
            with self.subTest(payload=payload), self.assertRaises(ModelError):
                resolve_directions(json.dumps(payload), pool)

    def test_no_padding_and_reasons_are_selected_catalogue_facts(self):
        pool = direction_options(TripSpec())
        cards, question = resolve_directions(json.dumps(selection("rome")), pool)
        self.assertIsNone(question)
        self.assertEqual(len(cards), 1)
        self.assertEqual(
            cards[0]["reason"],
            next(d for d in CATALOGUE if d["id"] == "rome")["facts"][0],
        )
        self.assertNotIn("₽", cards[0]["reason"])

    def test_proximity_uses_grounded_request_and_keeps_only_nearest_match(self):
        spec = TripSpec(origin="Москва", travel_setting="forest")
        pool = direction_options(spec)
        payload = selection("altai", "karelia", "seliger") | {
            "nearby_quote": "недалеко"
        }
        cards, question = resolve_directions(
            json.dumps(payload), pool, message="Хочу недалеко", spec=spec
        )
        self.assertEqual([d["id"] for d in cards], ["seliger"])
        self.assertIn("по прямой", cards[0]["caveat"])
        self.assertIn("времени", question)
        with self.assertRaises(ModelError):
            resolve_directions(
                json.dumps(payload), pool, message="Хочу в горы", spec=spec
            )
        cards, question = resolve_directions(
            json.dumps(payload),
            direction_options(TripSpec()),
            message="Хочу недалеко",
            spec=TripSpec(),
        )
        self.assertEqual(cards, [])
        self.assertIn("города", question)

    def test_distance_is_only_provided_when_origin_is_known(self):
        self.assertTrue(
            all("distance_km" not in d for d in direction_options(TripSpec()))
        )
        pool = {d["id"]: d for d in direction_options(TripSpec(origin="Москва"))}
        self.assertLess(pool["seliger"]["distance_km"], pool["altai"]["distance_km"])
        self.assertNotIn("moscow", pool)


class DirectionDialogueTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_request_and_saved_constraints_reach_selector(self):
        class RecordingModel(FakeModel):
            async def extract(self, context, repair, timeout):
                if context["search_mode"] == "directions":
                    self.context = context
                return await super().extract(context, repair, timeout)

        model = RecordingModel(
            {
                "add_preferences": ["каналы и дворцы"],
                "evidence": {"add_preferences": "каналы и дворцы"},
            },
            selection("petersburg"),
        )
        state = State(
            search_mode="hotels",
            trip_spec=TripSpec(
                origin="Казань",
                budget={"amount_minor": 5000000},
                preferences=["без перелётов"],
            ),
        )
        result = await run_turn(state, "Хочу каналы и дворцы", DemoTools(), model)
        self.assertEqual([d["id"] for d in result.destination_options], ["petersburg"])
        self.assertEqual(model.context["message"], "Хочу каналы и дворцы")
        self.assertEqual(model.context["trip_spec"]["origin"], "Казань")
        self.assertIn("без перелётов", model.context["trip_spec"]["preferences"])
        self.assertEqual(
            result.selection["direction_options"], result.destination_options
        )

    async def test_invalid_selection_never_falls_back_to_fixed_trio(self):
        model = FakeModel({}, selection("atlantis"))
        result = await run_turn(
            State(search_mode="hotels"), "Хочу интересный отдых", DemoTools(), model
        )
        self.assertFalse(result.destination_options)
        self.assertTrue(result.questions)

    async def test_missing_coverage_is_honest_and_needs_no_ranking(self):
        model = FakeModel({})
        result = await run_turn(
            State(search_mode="hotels", trip_spec=TripSpec(origin="Москва", country="Япония")),
            "Покажи идеи",
            DemoTools(),
            model,
        )
        self.assertFalse(result.destination_options)
        self.assertIn("доступных направлениях", result.assistant_message)
        self.assertEqual(model.calls, 1)

    async def test_ordinal_choice_uses_actual_order_and_keeps_wishes(self):
        pool = direction_options(TripSpec())
        cards, _ = resolve_directions(json.dumps(selection("seliger", "altai")), pool)
        state = State(
            search_mode="hotels",
            trip_spec=TripSpec(
                origin="Москва", travel_setting="forest", preferences=["уединение"]
            ),
            selection={"direction_options": cards},
        )
        model = FakeModel()
        result = await run_turn(state, "второй", DemoTools(), model)
        self.assertEqual(result.trip_spec.destination, "Чемал")
        self.assertEqual(result.trip_spec.travel_setting, "forest")
        self.assertEqual(result.trip_spec.preferences, ["уединение"])
        self.assertEqual(model.calls, 0)
        self.assertIsNone(direction_choice(state, "второй, но теперь море"))

    async def test_clarification_has_no_arbitrary_cards(self):
        model = FakeModel({}, {"choices": [], "question": "preferences"})
        result = await run_turn(
            State(search_mode="hotels"), "Пока не знаю", DemoTools(), model
        )
        self.assertFalse(result.destination_options)
        self.assertTrue(result.questions)


class DirectionProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_uses_direction_schema_without_hotel_extraction_grammar(self):
        pool = direction_options(TripSpec(travel_setting="sea"))
        raw = json.dumps(selection("anapa") | {"nearby_quote": ""})
        for provider in ("llama_cpp", "ollama", "openai_compatible", "dashscope"):
            captured = []

            def respond(request):
                captured.append(json.loads(request.content))
                return httpx.Response(
                    200,
                    json=(
                        {"message": {"content": raw}, "done_reason": "stop"}
                        if provider == "ollama"
                        else {
                            "choices": [
                                {"message": {"content": raw}, "finish_reason": "stop"}
                            ]
                        }
                    ),
                )

            original = httpx.AsyncClient

            def client(**kwargs):
                return original(transport=httpx.MockTransport(respond), **kwargs)

            model = QwenModel(Settings(provider=provider, api_key="test-placeholder"))
            with (
                self.subTest(provider=provider),
                patch("travel_agent.model.httpx.AsyncClient", side_effect=client),
            ):
                output, _ = await model.extract(
                    {
                        "search_mode": "directions",
                        "message": "Море",
                        "candidates": pool,
                    },
                    None,
                    2,
                )
            self.assertEqual(output, raw)
            self.assertNotIn("grammar", captured[0])
            schema = (
                captured[0]["format"]
                if provider == "ollama"
                else captured[0]["response_format"]["json_schema"]["schema"]
            )
            variants = schema["properties"]["choices"]["items"]["anyOf"]
            anapa = next(
                v for v in variants if v["properties"]["id"]["enum"] == ["anapa"]
            )
            self.assertEqual(anapa["properties"]["facts"]["items"]["enum"], [0])

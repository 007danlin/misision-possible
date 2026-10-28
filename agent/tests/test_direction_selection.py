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
    proximity_requested,
)
from travel_agent.model import ModelError, QwenModel, Settings
from travel_agent.runner import run_turn
from test_agent import FakeModel


def selection(*ids, scope=None):
    result = {"choices": [{"id": id, "facts": [0]} for id in ids], "question": "none"}
    if scope is not None:
        result["scope"] = scope
    return result


class DirectionValidationTests(unittest.TestCase):
    def test_long_journey_exclusion_requires_distance_context(self):
        self.assertTrue(proximity_requested("На два дня, без самолётов и дальней дороги"))
        self.assertFalse(proximity_requested("Хочу лесные прогулки и озёра"))

    def test_short_journey_is_enforced_when_model_omits_quote(self):
        spec = TripSpec(origin="Москва", travel_setting="forest")
        cards, question = resolve_directions(
            json.dumps(selection("seliger", "karelia") | {"nearby_quote": ""}),
            direction_options(spec), message="К озеру, без дальней дороги", spec=spec,
        )
        self.assertEqual([d["id"] for d in cards], ["seliger"])
        self.assertTrue(question)

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
            selection("karelia", scope="unknown"),
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

    def test_origin_quote_does_not_imply_a_nearby_trip(self):
        spec = TripSpec(origin='Казань', travel_setting='sea')
        pool = direction_options(spec)
        for quote in ('Из Казани', 'Хочу к морю', 'к морю из Казани'):
            cards, question = resolve_directions(
                json.dumps(selection('sochi','anapa') | {'nearby_quote':quote}), pool,
                message='Хочу к морю. Из Казани', spec=spec,
            )
            self.assertEqual(len(cards), 2)
            self.assertIsNone(question)
            self.assertTrue(all('по прямой' not in d['caveat'] for d in cards))


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

    async def test_single_match_searches_remaining_candidates_with_same_wishes(self):
        class RecordingModel(FakeModel):
            async def extract(self, context, repair, timeout):
                if context.get("alternative_search"):
                    self.alternatives = context
                return await super().extract(context, repair, timeout)

        for setting, first, others in [
            ("forest", "karelia", ["seliger", "altai"]),
            ("sea", "anapa", ["gelendzhik", "sochi"]),
            ("city", "kazan", ["yaroslavl", "nizhny"]),
        ]:
            with self.subTest(setting=setting):
                model = RecordingModel({}, selection(first, scope="broad"), selection(*others))
                state = State(search_mode="hotels", history=["Люблю прогулки"],
                              trip_spec=TripSpec(origin="Москва", travel_setting=setting,
                                                 preferences=["без перелётов"]))
                turn = await run_turn(state, "Предложи направления", DemoTools(), model)
                self.assertEqual([d["id"] for d in turn.destination_options], [first, *others])
                self.assertEqual(model.calls, 3)
                self.assertNotIn(first, {d["id"] for d in model.alternatives["candidates"]})
                self.assertEqual(model.alternatives["trip_spec"]["preferences"], ["без перелётов"])
                self.assertEqual(model.alternatives["history"], state.history)
                self.assertIn(first, model.alternatives["previous_choices"])
                self.assertTrue(all(d["country"] == "Россия" for d in model.alternatives["candidates"]))

    async def test_no_padding_or_loss_of_valid_answer_when_alternatives_fail(self):
        for alternative in [
            {"choices": [], "question": "coverage"},
            selection("karelia"),  # Duplicate is outside the remaining pool.
            selection("atlantis"),
            ModelError("model_timeout"),
            TimeoutError(),
        ]:
            with self.subTest(alternative=str(alternative)):
                model = FakeModel({}, selection("karelia", scope="broad"), alternative)
                turn = await run_turn(State(search_mode="hotels", trip_spec=TripSpec(
                    origin="Москва", travel_setting="forest")),
                    "Предложи направления", DemoTools(), model)
                self.assertEqual([d["id"] for d in turn.destination_options], ["karelia"])
                self.assertEqual(model.calls, 3)

    async def test_two_suitable_matches_do_not_trigger_an_extra_call(self):
        model = FakeModel({}, selection("karelia", "seliger", scope="broad"))
        turn = await run_turn(State(search_mode="hotels", trip_spec=TripSpec(
            origin="Москва", travel_setting="forest")),
            "Предложи направления", DemoTools(), model)
        self.assertEqual(len(turn.destination_options), 2)
        self.assertEqual(model.calls, 2)

    async def test_nearly_exhausted_deadline_keeps_the_valid_first_match(self):
        model = FakeModel({}, selection("karelia", scope="broad"))
        turn = await run_turn(State(search_mode="hotels", trip_spec=TripSpec(
            origin="Москва", travel_setting="forest")),
            "Предложи направления", DemoTools(), model, timeout=0.5)
        self.assertEqual([d["id"] for d in turn.destination_options], ["karelia"])
        self.assertEqual(model.calls, 2)

    async def test_constrained_or_nearby_requests_do_not_expand_the_shortlist(self):
        for scope, message in [("constrained", "Хочу каналы и дворцы"),
                               ("broad", "Не хочу дальней дороги")]:
            model = FakeModel({}, selection("petersburg", scope=scope))
            turn = await run_turn(State(search_mode="hotels", trip_spec=TripSpec(
                origin="Москва", travel_setting="city")), message, DemoTools(), model)
            self.assertEqual([d["id"] for d in turn.destination_options], ["petersburg"])
            self.assertEqual(model.calls, 2)

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
    async def test_catalogue_prefix_is_stable_and_eligibility_is_per_request(self):
        captured = []
        def respond(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'choices':[{'message':{'content':'{'}, 'finish_reason':'length'}]})
        original = httpx.AsyncClient
        def client(**kwargs):
            return original(transport=httpx.MockTransport(respond), **kwargs)
        with patch('travel_agent.model.httpx.AsyncClient', side_effect=client), patch.dict('os.environ', {'LLM_DIRECTION_SLOT':'1'}):
            for setting in ('sea', 'forest'):
                await QwenModel(Settings()).extract({
                    'search_mode':'directions', 'message':'Хочу недалеко',
                    'candidates':direction_options(TripSpec(origin='Омск', travel_setting=setting)),
                }, None, 2, prefill=True)
        self.assertEqual(captured[0]['messages'][0], captured[1]['messages'][0])
        self.assertEqual(captured[0]['max_tokens'], 1)
        self.assertEqual(captured[0]['id_slot'], 1)
        self.assertNotIn('Черноморское побережье', captured[0]['messages'][1]['content'])
        for body, expected in zip(captured, ({'sochi','gelendzhik','anapa'}, {'karelia','altai','seliger','sochi_nature'})):
            variants = body['response_format']['json_schema']['schema']['properties']['choices']['items']['anyOf']
            self.assertEqual({v['properties']['id']['enum'][0] for v in variants}, expected)
            self.assertIn('distance_km', body['messages'][1]['content'])

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

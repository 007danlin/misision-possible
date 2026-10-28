import unittest
from unittest.mock import patch

from travel_agent.demo_tools import DemoTools
from travel_agent.domain import State, TripSpec, apply_intent
from travel_agent.fast_intent import fast_intent
from travel_agent.hotel_selection import missing_hotel_questions, response_text, select_hotels
from travel_agent.runner import run_turn
from travel_agent.tools import ToolError
from test_agent import FakeModel
from test_public_content import base


def trip(**updates):
    values = dict(destination="Ялта", dates={"start": "2026-11-10", "end": "2026-11-30"},
                  travellers={"adults": 2}, budget={"amount_minor": 20000000},
                  budget_scope="whole_trip", include_transport=True, hotel_preferences={"pool": True})
    return TripSpec(**(values | updates))


class CoverageConversationTests(unittest.IsolatedAsyncioTestCase):
    @patch("travel_agent.runner.resolve_destination", side_effect=ToolError("Временная ошибка проверки Островка"))
    async def test_provider_failure_preserves_destination_without_claiming_no_coverage(self, resolve):
        state = State(search_mode="hotels", trip_spec=trip())
        turn = await run_turn(state, "Подобрать поездку", DemoTools(), FakeModel({}))
        self.assertEqual(turn.status, "error")
        self.assertEqual(turn.trip_spec, state.trip_spec)
        self.assertNotIn("не нашлось", turn.assistant_message)
        self.assertNotIn("не подключено", turn.assistant_message)

    @patch.dict("os.environ", {"JOURNEY_DATA_SOURCE": "public"})
    @patch("travel_agent.runner.resolve_destination", return_value={"status": "available"})
    async def test_yalta_is_supported_before_asking_departure(self, resolve):
        state = State(search_mode="hotels", trip_spec=trip())
        with patch("travel_agent.ostrovok.search_hotels") as search:
            turn = await run_turn(state, "Подобрать поездку", DemoTools(), FakeModel({}))
        search.assert_not_called()
        resolve.assert_awaited_once_with("Ялта", None)
        self.assertEqual(turn.status, "needs_input")
        self.assertEqual(turn.trip_spec, state.trip_spec)
        self.assertEqual(turn.questions, ["Из какого города отправляетесь?"])

    @patch.dict("os.environ", {"JOURNEY_DATA_SOURCE": "public"})
    async def test_unavailable_destination_offers_provider_alternatives(self):
        for status, phrase in [("closed", "продажи закрыты"), ("not_found", "не нашлось"), ("ambiguous", "похожих направлений")]:
            resolution = dict(status=status, region=None, suggestions=[{"name": "Сочи", "country": "Россия", "slug": "russia/sochi"}])
            state = State(search_mode="hotels", trip_spec=trip())
            with patch("travel_agent.runner.resolve_destination", return_value=resolution), patch("travel_agent.ostrovok.search_hotels") as search:
                turn = await run_turn(state, "Подобрать поездку", DemoTools(), FakeModel({}))
            search.assert_not_called()
            self.assertEqual(turn.trip_spec, state.trip_spec)
            self.assertIn(phrase, turn.assistant_message)
            self.assertIn("Сочи", turn.assistant_message)
            self.assertEqual(turn.questions, ["Какое направление выбрать?"])
            self.assertNotIn("Из какого города", turn.assistant_message)

    @patch.dict("os.environ", {"JOURNEY_DATA_SOURCE": "public"})
    @patch("travel_agent.runner.resolve_destination", return_value={"status": "available"})
    async def test_budget_dates_and_pool_edits_keep_yalta_hotels(self, resolve):
        state = State(search_mode="hotels", trip_spec=trip(origin="Москва", expense_reserve={"amount_minor": 1000000}))
        steps = [
            ("Мой бюджет на всю поездку теперь 500000", {"budget": {"amount_minor": 50000000}}),
            ("Хочу изменить даты на 11-15 ноября", {"dates": {"start": "2026-11-11", "end": "2026-11-15"}}),
            ("Бассейн больше не обязателен", {"hotel_preferences": {"pool": None}}),
        ]
        h = dict(base(), destination="Ялта")
        async def enrich(value):
            return value
        with patch("travel_agent.ostrovok.search_hotels", return_value=([h], "https://ostrovok.ru/hotel/russia/yalta/")), patch("travel_agent.public_content.enrich", side_effect=enrich), patch("travel_agent.trip_context.weather_context", return_value={}), patch("travel_agent.places.nearby_places", return_value=[]):
            for message, changes in steps:
                turn = await run_turn(state, message, DemoTools(), FakeModel({"action": "change", "patch": changes, "evidence": {key: message for key in changes}}))
                self.assertEqual(turn.trip_spec.destination, "Ялта")
                self.assertEqual(turn.trip_spec.origin, "Москва")
                self.assertEqual(turn.status, "choosing", turn.assistant_message)
                self.assertIn("не рассчитаны", turn.assistant_message)
                self.assertTrue(turn.hotel_options[0]["journey"]["route_missing"])
                self.assertFalse(turn.hotel_options[0]["journey"]["can_book"])
                state.trip_spec = turn.trip_spec
        self.assertEqual(state.trip_spec.budget.amount_minor, 50000000)
        self.assertEqual(str(state.trip_spec.dates.start), "2026-11-11")
        self.assertIsNone(state.trip_spec.hotel_preferences.pool)
        self.assertEqual(state.trip_spec.expense_reserve.amount_minor, 1000000)


class MissingRouteTests(unittest.TestCase):
    def test_route_failure_keeps_hotels_but_not_a_complete_trip(self):
        for origin, destination, mode in [("Москва", "Москва", "auto"), ("Владимир", "Сочи", "flight")]:
            spec = trip(origin=origin, destination=destination, transport_mode=mode)
            hotels, info = select_hotels([base()], spec)
            self.assertTrue(hotels)
            j = hotels[0]["journey"]
            self.assertTrue(j["total_incomplete"])
            self.assertFalse(j["can_book"])
            self.assertEqual(j["total_minor"], hotels[0]["quote"]["total_minor"])
            self.assertIsNone(info["min_budget_minor"])
            text = response_text(hotels, info, spec, {})
            self.assertIn("не рассчитаны", text)
            self.assertNotIn("Можно изменить бюджет", text)

    def test_partial_plan_still_enforces_pool_and_hotel_budget(self):
        spec = trip(origin="Москва", hotel_budget={"amount_minor": 100000})
        self.assertFalse(select_hotels([base()], spec)[0])
        spec.hotel_budget = None
        self.assertFalse(select_hotels([dict(base(), amenity_codes=[])], spec)[0])

    def test_suggested_hotel_only_recovery_asks_for_separate_budget(self):
        state = State(search_mode="hotels", trip_spec=trip(origin="Москва", destination="Москва"))
        message = "только отель, без дороги"
        updated = apply_intent(state.trip_spec, fast_intent(state, message), message)
        self.assertFalse(updated.include_transport)
        self.assertEqual(updated.budget_scope, "hotel")
        self.assertIsNone(updated.budget)
        self.assertTrue(updated.hotel_preferences.pool)
        self.assertIn("бюджет на проживание", missing_hotel_questions(updated)[0])

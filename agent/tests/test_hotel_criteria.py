import json
import unittest
from unittest.mock import AsyncMock, patch

from travel_agent.domain import Intent, State, apply_intent
from travel_agent.fast_intent import fast_intent
from travel_agent.model import canonical_intent
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel
from test_hotel_selection import hotel, spec


def extract(message, prefs=None, **extra):
    raw = {"patch": {"hotel_preferences": prefs or {}}, "evidence": message, **extra}
    return Intent.model_validate_json(canonical_intent(json.dumps(raw), message))


class NumericCriteriaTests(unittest.TestCase):
    def test_proximity_never_becomes_zero(self):
        for message in (
            "Около центра",
            "Рядом с центром",
            "Недалеко от центра",
            "Поближе к центру",
            "В самом центре",
            "Хочу отель в центре",
        ):
            with self.subTest(message=message):
                for prefs in ({}, {"max_center_m": 0}, {"max_center_m": None}):
                    intent = extract(message, prefs)
                    self.assertEqual(intent.patch.hotel_preferences.max_center_m, 2000)
                    self.assertFalse(intent.questions)
                self.assertEqual(
                    fast_intent(State(), message).patch.hotel_preferences.max_center_m,
                    2000,
                )

    def test_beach_proximity_and_units(self):
        cases = [
            ("Рядом с морем", "max_beach_m", 1000),
            ("Около пляжа", "max_beach_m", 1000),
            ("От центра не дальше двух километров", "max_center_m", 2000),
            ("До центра максимум 0,5 км", "max_center_m", 500),
            ("До пляжа 0.25 км", "max_beach_m", 250),
            ("Не дальше 500 метров от центра", "max_center_m", 500),
            ("До моря полкилометра", "max_beach_m", 500),
            ("Полтора километра от центра", "max_center_m", 1500),
            ("Не дальше пятисот метров от пляжа", "max_beach_m", 500),
        ]
        for message, key, expected in cases:
            with self.subTest(message=message):
                intent = extract(message, {key: 0})
                self.assertFalse(intent.questions)
                self.assertEqual(getattr(intent.patch.hotel_preferences, key), expected)

    def test_zero_negative_ranges_time_and_conflicts_ask_without_mutation(self):
        previous = spec(
            destination="Сочи", hotel_preferences={"pool": True, "max_center_m": 2000}
        )
        for message in (
            "До центра 0 км",
            "До центра -2 км",
            "Не ближе 2 км от центра",
            "От 2 до 3 км от центра",
            "До центра 10 минут пешком",
            "До центра 2",
            "До центра 200 км",
            "Около центра или у моря",
            "До центра 1 км. До центра 3 км",
            "Рядом с центром. Центр не важен",
            "До центра 2–3 км",
            "Не хочу около центра",
            "Рядом с торговым центром",
            "Не менее 2 км от центра",
            "От 2 км до центра",
        ):
            with self.subTest(message=message):
                intent = extract(message, {"max_center_m": 0})
                self.assertTrue(intent.questions)
                self.assertEqual(apply_intent(previous, intent, message), previous)

    def test_unstated_numbers_nulls_and_removals_cannot_change_saved_filters(self):
        previous = spec(
            hotel_preferences={"pool": True, "max_center_m": 500, "min_rating": 8.5}
        )
        message = "Теперь подешевле, остальное сохрани"
        intent = extract(
            message,
            {"max_center_m": 0, "max_beach_m": 0, "min_rating": None, "min_stars": 5},
            remove_hotel_preferences=["max_center_m", "min_rating"],
        )
        self.assertEqual(apply_intent(previous, intent, message), previous)

    def test_explicit_removal_is_not_a_zero_limit(self):
        previous = spec(
            hotel_preferences={"pool": True, "max_center_m": 500, "max_beach_m": 1000}
        )
        for message, key in [
            ("Центр не важен", "max_center_m"),
            ("Теперь можно далеко от центра", "max_center_m"),
            ("Убери ограничение расстояния до пляжа", "max_beach_m"),
        ]:
            intent = extract(message, {key: 0})
            new = apply_intent(previous, intent, message)
            self.assertIsNone(getattr(new.hotel_preferences, key))
            self.assertTrue(new.hotel_preferences.pool)
            self.assertEqual(new.travellers, previous.travellers)

    def test_separate_targets_and_unrelated_counts(self):
        message = "До центра 2 км и до моря 500 м"
        intent = extract(message)
        self.assertFalse(intent.questions)
        self.assertEqual(intent.patch.hotel_preferences.max_center_m, 2000)
        self.assertEqual(intent.patch.hotel_preferences.max_beach_m, 500)
        self.assertEqual(
            extract(
                "Хочу на 5 ночей около центра"
            ).patch.hotel_preferences.max_center_m,
            2000,
        )

    def test_explicit_distance_overrides_qualitative_proximity(self):
        for message in (
            "Около центра, до 500 метров",
            "До центра 500 м, рядом с центром",
            "Рядом с центром, не дальше 0,5 км от центра",
        ):
            intent = extract(message, {"max_center_m": 0})
            self.assertFalse(intent.questions, message)
            self.assertEqual(intent.patch.hotel_preferences.max_center_m, 500, message)

    def test_ratings_and_stars_use_explicit_numbers(self):
        for message, key, expected in [
            ("Рейтинг от 8,5", "min_rating", 8.5),
            ("Оценка гостей минимум 8.5", "min_rating", 8.5),
            ("Не ниже четырех звезд", "min_stars", 4),
        ]:
            intent = extract(message, {key: 0})
            self.assertFalse(intent.questions)
            self.assertEqual(getattr(intent.patch.hotel_preferences, key), expected)
        for message in ("Рейтинг от 12", "Не ниже 6 звезд", "Не выше трех звезд"):
            self.assertTrue(extract(message).questions)

    def test_hotel_questions_do_not_modify_search(self):
        previous = spec(hotel_preferences={"max_center_m": 500})
        message = "Второй отель в центре?"
        intent = extract(message, {"max_center_m": 0}, action="explain")
        self.assertEqual(apply_intent(previous, intent, message), previous)

    def test_station_is_not_a_city_center(self):
        intent = extract("Рядом с Центральным вокзалом", {"max_center_m": 0})
        self.assertIsNone(intent.patch.hotel_preferences)


class NumericConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_model_zero_still_produces_matching_hotels(self):
        state = State(search_mode="hotels", trip_spec=spec(destination="Сочи"))
        message = "Хочу отель около центра"
        model = FakeModel(
            {"hotel_preferences": {"max_center_m": 0}, "evidence": message}
        )
        with patch(
            "travel_agent.ostrovok.search_hotels",
            AsyncMock(
                return_value=(
                    [hotel("near", center=500), hotel("far", center=8000)],
                    "https://ostrovok.ru/",
                )
            ),
        ):
            result = await run_turn(state, message, DemoTools(), model)
        self.assertEqual(result.status, "choosing")
        self.assertEqual(result.trip_spec.hotel_preferences.max_center_m, 2000)
        self.assertEqual([h["id"] for h in result.hotel_options], ["near"])
        self.assertEqual(model.calls, 1)

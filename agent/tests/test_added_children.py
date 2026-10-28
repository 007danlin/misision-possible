import unittest

from travel_agent.domain import Intent, State, TripSpec, apply_intent
from travel_agent.fast_intent import fast_intent, protect_added_children
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel


class AddedChildrenTests(unittest.TestCase):
    def setUp(self):
        self.previous = TripSpec(
            destination="Казань",
            travellers={"adults": 2, "children": [8]},
            stay_nights=4,
            hotel_preferences={"parking": True},
            budget={"amount_minor": 9000000},
        )

    def test_count_is_a_delta_and_missing_age_is_not_invented(self):
        for message in (
            "Добавь одного ребёнка, возраст уточню позже.",
            "Добавим еще одного ребенка, возраст пока не знаю.",
        ):
            raw = Intent(
                patch={"travellers": {"children": [1]}},
                evidence={"travellers": message},
            )
            fixed = protect_added_children(raw, message, self.previous)
            result = apply_intent(self.previous, fixed, message)
            self.assertEqual(result.travellers.children, [8, None])
            self.assertEqual(result.travellers.adults, 2)
            self.assertEqual(result.hotel_preferences, self.previous.hotel_preferences)
            self.assertEqual(result.budget, self.previous.budget)

    def test_direct_command_can_defer_the_age(self):
        message = "Добавь одного ребёнка, возраст уточню позже."
        intent = fast_intent(
            State(search_mode="hotels", trip_spec=self.previous), message
        )
        self.assertIsNotNone(intent)
        self.assertEqual(
            apply_intent(self.previous, intent, message).travellers.children, [8, None]
        )

    def test_supplied_age_and_previous_children_are_preserved(self):
        for message in (
            "Добавь еще одного ребенка 5 лет",
            "Добавь одного ребенка, ему 5 лет.",
        ):
            result = apply_intent(
                self.previous,
                protect_added_children(Intent(), message, self.previous),
                message,
            )
            self.assertEqual(result.travellers.children, [8, 5])

    def test_ambiguous_plural_and_limits_ask_without_changing_guests(self):
        for message in ("Добавь детей", "Добавь 10 детей"):
            intent = fast_intent(
                State(search_mode="hotels", trip_spec=self.previous), message
            )
            self.assertTrue(intent.questions)
            self.assertEqual(
                apply_intent(self.previous, intent, message), self.previous
            )

    def test_negation_and_conditional_additions_are_not_guessed(self):
        for message in (
            "Не добавь одного ребёнка",
            "Если будут места, добавь одного ребёнка",
        ):
            self.assertEqual(
                protect_added_children(
                    Intent(), message, self.previous
                ).patch.model_dump(exclude_unset=True),
                {},
            )


class AddedChildrenConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_omission_still_saves_count_and_asks_the_age(self):
        message = "Добавь одного ребёнка, возраст уточню позже."
        state = State(
            search_mode="hotels",
            trip_spec={
                "origin": "Москва",
                "destination": "Казань",
                "dates": {"start": "2026-11-12", "end": "2026-11-16"},
                "travellers": {"adults": 2},
                "budget": {"amount_minor": 9000000},
                "budget_scope": "whole_trip",
                "expense_reserve": {"amount_minor": 0},
            },
        )
        for raw in ({}, {"questions": ["Сколько лет ребёнку?"]}):
            result = await run_turn(state, message, DemoTools(), FakeModel(raw))
            self.assertEqual(result.status, "needs_input")
            self.assertEqual(result.trip_spec.travellers.children, [None])
            self.assertEqual(result.trip_spec.travellers.adults, 2)
            self.assertIn("Сколько лет ребёнку?", result.assistant_message)
            self.assertNotIn("1 детей", result.assistant_message)
            self.assertEqual(result.telemetry.tool_calls, [])

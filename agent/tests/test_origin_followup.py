import unittest
from unittest.mock import patch

from travel_agent.demo_tools import DemoTools
from travel_agent.domain import State, apply_intent
from travel_agent.origin_followup import origin_followup
from travel_agent.runner import run_turn
from test_agent import FakeModel


def waiting(**updates):
    values = dict(
        search_mode="hotels",
        assistant_message="Учёл ваши пожелания. Из какого города отправляетесь?",
        trip_spec=dict(
            destination="Сочи", dates={"start": "2026-11-10", "end": "2026-11-15"},
            travellers={"adults": 2, "children": [7]},
            budget={"amount_minor": 12000000}, budget_scope="whole_trip",
            include_transport=True, hotel_preferences={"pool": True},
            preferences=["тихо"],
        ),
    )
    values.update(updates)
    return State(**values)


class OriginFollowupTests(unittest.IsolatedAsyncioTestCase):
    async def test_city_reply_advances_to_reserve_without_calling_model(self):
        for questions in ([], ["Из какого города отправляетесь?"]):
            for message in ("питер", "СПБ", "Санкт-Петербург", "из Питера", "Отправляемся из Санкт-Петербурга"):
                with self.subTest(message=message, questions=questions):
                    state = waiting(questions=questions)
                    before = state.model_dump_json()
                    model = FakeModel()  # Any model call would fail the test.
                    turn = await run_turn(state, message, DemoTools(), model)
                    self.assertEqual(turn.status, "needs_input")
                    self.assertEqual(turn.trip_spec.origin, "Санкт-Петербург")
                    self.assertEqual(turn.trip_spec.model_dump(exclude={"origin"}), state.trip_spec.model_dump(exclude={"origin"}))
                    self.assertEqual(turn.patch, {"origin": "Санкт-Петербург"})
                    self.assertIn("оставить", turn.questions[0])
                    self.assertNotIn("Из какого города", turn.assistant_message)
                    self.assertEqual(turn.telemetry.model_calls, 0)
                    self.assertEqual(state.model_dump_json(), before)

    async def test_missing_city_is_exposed_as_current_question(self):
        turn = await run_turn(waiting(), "Подобрать поездку", DemoTools(), FakeModel({}))
        self.assertEqual(turn.questions, ["Из какого города отправляетесь?"])
        self.assertIn(turn.questions[0], turn.assistant_message)

    @patch("travel_agent.runner.resolve_destination", return_value={"status": "available"})
    async def test_moscow_reply_never_replaces_yalta_destination(self, resolve):
        for message in ("москва", "Отправляемся из Москва", "из Москвы"):
            state = waiting()
            state.trip_spec.destination = "Ялта"
            turn = await run_turn(state, message, DemoTools(), FakeModel())
            self.assertEqual(turn.trip_spec.origin, "Москва")
            self.assertEqual(turn.trip_spec.destination, "Ялта")
            self.assertEqual(turn.patch, {"origin": "Москва"})
            self.assertEqual(turn.telemetry.model_calls, 0)
            self.assertNotIn("Из какого города", turn.assistant_message)
            self.assertIn("резерв", turn.assistant_message)

    def test_other_known_city_and_original_evidence(self):
        for message, city in (("москва", "Москва"), ("Из Москвы", "Москва"), ("Нижний Новгород", "Нижний Новгород"), ("Казань!", "Казань")):
            state = waiting()
            intent = origin_followup(state, message)
            self.assertEqual(intent.evidence, {"origin": message})
            self.assertEqual(apply_intent(state.trip_spec, intent, message).origin, city)

    def test_city_shortcut_requires_the_departure_question(self):
        for state in (
            State(search_mode="hotels"),
            waiting(assistant_message="В каком городе ищем отель?"),
            waiting(questions=["Сколько оставить на личные расходы?"]),
            waiting(trip_spec={"origin": "Москва", "destination": "Сочи"}),
        ):
            self.assertIsNone(origin_followup(state, "питер"))

    def test_complex_or_ambiguous_city_replies_stay_with_model(self):
        for message in ("в Питер", "питер или Москва", "не Питер", "питер, добавь завтрак", "не знаю", "Тула"):
            self.assertIsNone(origin_followup(waiting(), message), message)


if __name__ == "__main__":
    unittest.main()

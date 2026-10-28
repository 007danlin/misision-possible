import unittest
from unittest.mock import patch, AsyncMock
from travel_agent.domain import State, TripSpec
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from travel_agent.hotel_selection import select_hotels
from travel_agent.progress import ProgressStore
from test_agent import FakeModel
from test_hotel_selection import hotel, spec


class InspirationTests(unittest.IsolatedAsyncioTestCase):
    def test_unknown_origin_never_uses_moscow_estimate(self):
        from travel_agent.inspiration import direction_options

        options = direction_options(TripSpec(include_transport=True))
        self.assertEqual(len(options), 3)
        self.assertTrue(all("город отправления" in d["reason"] for d in options))
        self.assertTrue(
            all("Москвы" not in d["reason"] and "₽" not in d["reason"] for d in options)
        )

    async def test_forest_offers_directions_without_city_question(self):
        events = []
        result = await run_turn(
            State(search_mode="hotels"),
            "Хочу в лес",
            DemoTools(),
            FakeModel(
                {
                    "travel_setting": "forest",
                    "evidence": {"travel_setting": "в лес"},
                    "action": "inspire",
                }
            ),
            progress=lambda **e: events.append(e),
        )
        self.assertEqual(result.trip_spec.travel_setting, "forest")
        self.assertEqual(len(result.destination_options), 3)
        self.assertNotIn("В каком городе", result.assistant_message)
        self.assertEqual([e["stage"] for e in events], ["understanding", "understood"])
        self.assertEqual(events[-1]["trip_spec"]["travel_setting"], "forest")

    async def test_followup_preserves_forest_and_real_search_stages(self):
        s = spec(destination="Сортавала", travel_setting="forest")
        state = State(search_mode="hotels", trip_spec=s)
        events = []
        rural = hotel("Коттедж у озера", 200000)
        with patch(
            "travel_agent.ostrovok.search_hotels",
            AsyncMock(
                return_value=(
                    [hotel("Городская квартира", 100000), rural],
                    "https://ostrovok.ru/hotel/russia/sortavala/",
                )
            ),
        ):
            turn = await run_turn(
                state,
                "Теперь 20 тысяч рублей",
                DemoTools(),
                FakeModel(
                    {
                        "budget": {"amount_minor": 2000000},
                        "evidence": {"budget": "20 тысяч рублей"},
                    }
                ),
                progress=lambda **e: events.append(e),
            )
        self.assertEqual(turn.trip_spec.travel_setting, "forest")
        self.assertEqual([h["name"] for h in turn.hotel_options], ["Коттедж у озера"])
        self.assertIn(
            "Лес у дома и степень уединения", turn.hotel_options[0]["unverified"]
        )
        self.assertEqual(
            [e["stage"] for e in events],
            ["understanding", "understood", "searching", "comparing"],
        )

    def test_progress_is_token_scoped(self):
        store = ProgressStore()
        store.put("a" * 64, stage="searching")
        store.put("invalid", stage="complete")
        self.assertEqual(store.get("a" * 64)["stage"], "searching")
        self.assertEqual(store.get("b" * 64)["stage"], "waiting")
        self.assertEqual(len(store.events), 1)


class BudgetPeriodTests(unittest.TestCase):
    def test_stay_length_cannot_become_nightly_budget(self):
        from travel_agent.domain import Intent, apply_intent

        with self.assertRaisesRegex(ValueError, "PER NIGHT"):
            apply_intent(
                TripSpec(),
                Intent(
                    patch={"budget_period": "night"},
                    evidence={"budget_period": "на 5 ночей"},
                ),
                "На 5 ночей, до 40 тысяч рублей",
            )
        result = apply_intent(
            TripSpec(),
            Intent(
                patch={"budget_period": "night"}, evidence={"budget_period": "за ночь"}
            ),
            "До 4000 рублей за ночь",
        )
        self.assertEqual(result.budget_period, "night")


class RuralFitTests(unittest.TestCase):
    def test_explicit_city_centre_house_is_not_wilderness(self):
        s = spec(travel_setting="forest")
        city = hotel("Частный дом недалеко от центра города", 100000)
        country = hotel("Частный Дом Форест", 100000)
        selected, info = select_hotels([city, country], s)
        self.assertEqual([h["id"] for h in selected], [country["id"]])

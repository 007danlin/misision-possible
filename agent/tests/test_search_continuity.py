import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from travel_agent.domain import State, Intent, apply_intent
from travel_agent.fast_intent import (
    fast_intent,
    protect_child_count,
    protect_journey_language,
)
from travel_agent.hotel_selection import select_hotels
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel
from test_public_content import base, spec


class GuestEdits(unittest.TestCase):
    def test_add_child_preserves_family_and_other_conditions(self):
        state = State(
            search_mode="hotels",
            trip_spec=spec(travellers={"adults": 3, "children": [8]}),
        )
        for message, expected in [
            ("Добавь ребёнка", [8, None]),
            ("Добавь еще одного ребенка 5 лет", [8, 5]),
            ("Добавь 2 детей", [8, None, None]),
        ]:
            intent = protect_child_count(
                fast_intent(state, message), message, state.trip_spec
            )
            changed = apply_intent(state.trip_spec, intent, message)
            self.assertEqual(changed.travellers.children, expected)
            self.assertEqual(changed.travellers.adults, 3)
            self.assertEqual(changed.dates, state.trip_spec.dates)
            self.assertEqual(changed.budget, state.trip_spec.budget)
        state.trip_spec.travellers.children = [8, None]
        state.assistant_message = "Сколько лет каждому ребёнку?"
        changed = apply_intent(
            state.trip_spec, fast_intent(state, "Ему 5 лет"), "Ему 5 лет"
        )
        self.assertEqual(changed.travellers.children, [8, 5])

    def test_guest_edit_cannot_drop_transport(self):
        text = "Добавь ребенка 5 лет"
        intent = Intent(
            patch={"include_transport": False, "travellers": {"children": [5]}},
            evidence={"include_transport": text, "travellers": text},
        )
        changed = apply_intent(
            spec(include_transport=True), protect_journey_language(intent, text), text
        )
        self.assertTrue(changed.include_transport)
        text = "Только отель, без дороги"
        intent = Intent(
            patch={"include_transport": False}, evidence={"include_transport": text}
        )
        self.assertFalse(protect_journey_language(intent, text).patch.include_transport)


class SearchContinuity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            patch.dict("os.environ", {"JOURNEY_DATA_SOURCE": "public"})
        )
        for target in [
            "travel_agent.transport.prepare_road",
            "travel_agent.tutu.prepare",
            "travel_agent.travelpayouts.prepare",
            "travel_agent.trip_context.weather_context",
        ]:
            self.stack.enter_context(patch(target, new=AsyncMock(return_value=None)))
        self.stack.enter_context(patch("travel_agent.public_content.remember"))
        self.stack.enter_context(
            patch(
                "travel_agent.public_content.enrich",
                new=AsyncMock(side_effect=lambda h: h),
            )
        )
        self.hotel = base()
        self.stack.enter_context(
            patch(
                "travel_agent.public_content.recall",
                side_effect=lambda ident: self.hotel
                if ident == self.hotel["id"]
                else None,
            )
        )
        self.search = self.stack.enter_context(
            patch(
                "travel_agent.ostrovok.search_hotels",
                new=AsyncMock(return_value=([self.hotel], "https://ostrovok.ru/")),
            )
        )

    async def test_child_age_followup_reprices_chosen_hotel_and_all_services(self):
        s = spec(travellers={"adults": 3}, transport_mode="flight")
        hotels, _ = select_hotels([self.hotel], s)
        state = State(
            search_mode="hotels",
            trip_spec=s,
            hotel_options=hotels,
            selected_hotel=hotels[0],
        )
        original = state.model_dump_json()
        text = "Добавь ребёнка"
        reply = await run_turn(
            state,
            text,
            DemoTools(),
            FakeModel(fast_intent(state, text).model_dump(exclude_unset=True)),
        )
        self.assertEqual(reply.status, "needs_input")
        self.assertEqual(reply.trip_spec.travellers.children, [None])
        self.assertIn("лет", reply.assistant_message)
        self.search.assert_not_awaited()
        state.trip_spec = reply.trip_spec
        state.assistant_message = reply.assistant_message
        text = "Ему 5 лет"
        reply = await run_turn(
            state,
            text,
            DemoTools(),
            FakeModel(fast_intent(state, text).model_dump(exclude_unset=True)),
        )
        self.assertEqual(reply.status, "choosing")
        self.search.assert_not_awaited()
        chosen = reply.hotel_options[0]
        self.assertEqual(chosen["id"], hotels[0]["id"])
        self.assertEqual(reply.trip_spec.travellers.children, [5])
        self.assertEqual(reply.trip_spec.travellers.adults, 3)
        old, new = hotels[0]["journey"], chosen["journey"]
        self.assertGreater(new["breakdown"]["transport"], old["breakdown"]["transport"])
        self.assertEqual(
            new["breakdown"]["transfers"], old["breakdown"]["transfers"] * 2
        )
        self.assertEqual(new["breakdown"]["hotel"], chosen["quote"]["total_minor"])
        self.assertEqual(new["total_minor"], sum(new["breakdown"].values()))
        self.assertEqual(
            len([x for x in new["segments"] if x["kind"] == "transfer"]), 2
        )
        self.assertFalse(new["can_book"])
        self.assertEqual(
            next(c for c in new["checks"] if c["code"] == "children")["status"],
            "unknown",
        )
        self.assertEqual(
            State.model_validate_json(original).trip_spec.travellers.children, []
        )

    async def test_unknown_child_policy_keeps_search_results(self):
        state = State(
            search_mode="hotels",
            trip_spec=spec(travellers={"adults": 2, "children": [5]}),
        )
        reply = await run_turn(
            state, "Подобрать поездку", DemoTools(), FakeModel({"action": "search"})
        )
        self.assertEqual(reply.status, "choosing")
        self.assertTrue(reply.hotel_options)
        self.assertFalse(reply.hotel_options[0]["journey"]["can_book"])

    async def test_over_budget_selected_hotel_stays_visible(self):
        s = spec()
        hotels, _ = select_hotels([self.hotel], s)
        state = State(
            search_mode="hotels",
            trip_spec=s,
            hotel_options=hotels,
            selected_hotel=hotels[0],
        )
        text = "Бюджет 1000 рублей"
        reply = await run_turn(
            state,
            text,
            DemoTools(),
            FakeModel(
                {
                    "patch": {"budget": {"amount_minor": 100000}},
                    "evidence": {"budget": text},
                }
            ),
        )
        self.assertEqual(reply.status, "choosing")
        self.assertEqual(reply.hotel_options[0]["id"], hotels[0]["id"])
        self.assertTrue(
            any(
                c["status"] == "fail" and c["code"] == "budget"
                for c in reply.hotel_options[0]["journey"]["checks"]
            )
        )

    async def test_public_destination_not_limited_to_demo_routes(self):
        self.hotel.update(
            destination="Осташков", coordinates={"lat": 57.14, "lng": 33.1}
        )
        reply = await run_turn(
            State(
                search_mode="hotels",
                trip_spec=spec(
                    destination="Осташков",
                    transport_mode="car",
                    budget={"amount_minor": 100000000},
                ),
            ),
            "Подобрать поездку",
            DemoTools(),
            FakeModel({"action": "search"}),
        )
        self.assertEqual(reply.status, "choosing")
        self.assertEqual(reply.hotel_options[0]["journey"]["transport"]["kind"], "car")

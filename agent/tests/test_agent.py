import asyncio
import json
import unittest

from pydantic import ValidationError

from travel_agent.demo_tools import DemoTools
from travel_agent.domain import Intent, Money, State, TripSpec, apply_intent
from travel_agent.model import ModelError, Settings
from travel_agent.runner import run_turn
from travel_agent.tools import UnavailableTools


def full_spec(**updates):
    data = dict(origin="Москва", destination="Сочи", dates={"start": "2026-11-10", "end": "2026-11-15"},
                travellers={"adults": 2}, budget={"amount_minor": 12000000}, budget_scope="booking",
                hard_constraints={"no_night_flights": True})
    data.update(updates)
    return TripSpec.model_validate(data)


class FakeModel:
    settings = Settings(model="scripted-test-double")

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    async def extract(self, context, repair, timeout):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, str):
            response = json.dumps(response, ensure_ascii=False)
        return response, {"total_tokens": 10}


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tools = DemoTools()
        self.spec = full_spec()
        self.plan = (await self.tools.search_packages(self.spec))[0]
        self.state = State(revision=7, trip_spec=self.spec, selected_plan=self.plan)

    async def turn(self, response, message="запрос", state=None):
        return await run_turn(state or self.state, message, self.tools, FakeModel(response))

    async def test_budget_preserves_conditions_and_selected_state(self):
        before = self.state.model_dump_json()
        turn = await self.turn({"patch": {"budget": {"amount_minor": 10000000}}, "evidence": {"budget": "100 тысяч"}}, "Теперь 100 тысяч")
        self.assertEqual(turn.status, "choosing")
        self.assertEqual(turn.change_preview.price_delta, -1200000)
        self.assertEqual(turn.change_preview.proposed_plan.total.amount_minor, 9700000)
        self.assertEqual(turn.trip_spec.dates, self.spec.dates)
        self.assertEqual(turn.trip_spec.hard_constraints, self.spec.hard_constraints)
        self.assertEqual(turn.trip_spec.travellers, self.spec.travellers)
        self.assertEqual(self.state.model_dump_json(), before)
        self.assertEqual(turn.change_preview.based_on_revision, 7)
        self.assertFalse(turn.checkout_allowed)

    async def test_second_budget_uses_latest_spec(self):
        for amount in (10000000, 3000000):
            turn = await self.turn({"patch": {"budget": {"amount_minor": amount}}, "evidence": {"budget": str(amount)}}, str(amount))
            self.state.trip_spec = turn.trip_spec
            self.state.revision += 1
        self.assertEqual(turn.status, "no_solution")
        self.assertIsNone(turn.change_preview)
        self.assertEqual(turn.based_on_revision, 8)

    async def test_cancellation_does_not_relax_for_budget(self):
        self.state.trip_spec.hard_constraints.free_cancellation = True
        turn = await self.turn({"patch": {"budget": {"amount_minor": 10000000}}, "evidence": {"budget": "100"}}, "100")
        self.assertEqual(turn.status, "no_solution")
        self.assertTrue(turn.trip_spec.hard_constraints.free_cancellation)

    async def test_shift_dates_keeps_duration_and_guests(self):
        turn = await self.turn({"shift_days": 2, "evidence": {"shift_days": "два дня позже"}}, "А если на два дня позже?")
        self.assertEqual(turn.trip_spec.dates.start.isoformat(), "2026-11-12")
        self.assertEqual(turn.trip_spec.dates.end.isoformat(), "2026-11-17")
        self.assertEqual(turn.trip_spec.travellers, self.spec.travellers)
        self.assertTrue(turn.change_preview)
        self.assertEqual(self.state.trip_spec.dates.start.isoformat(), "2026-11-10")

        self.assertTrue(turn.change_preview.proposed_plan.id.endswith(":A"))
        self.assertEqual(turn.change_preview.price_delta, 200000)

    async def test_three_real_fixture_destinations(self):
        for city in ("Сочи", "Казань", "Владимир"):
            state = State(trip_spec=full_spec(destination=city))
            turn = await self.turn({}, state=state)
            self.assertEqual(turn.status, "choosing")
            self.assertEqual(len(turn.options), 3)
            self.assertTrue(all(p.evidence[0].source_kind == "synthetic" for p in turn.options))

    async def test_unknown_destination_not_substituted(self):
        state = State(trip_spec=full_spec(destination="Томск"))
        turn = await self.turn({}, state=state)
        self.assertEqual(turn.status, "no_solution")
        self.assertEqual(turn.trip_spec.destination, "Томск")

    async def test_inspiration_before_details(self):
        turn = await self.turn({}, state=State())
        self.assertEqual(turn.status, "needs_input")
        self.assertGreaterEqual(len(turn.destination_options), 3)
        self.assertFalse(turn.options)

    async def test_missing_origin_only(self):
        turn = await self.turn({}, state=State(trip_spec=full_spec(origin=None)))
        self.assertEqual(turn.questions, ["Из какого города отправляетесь?"])
        self.assertEqual(turn.telemetry.tool_calls, [])

    async def test_hotel_and_whole_trip_differ(self):
        hotel = await self.turn({}, state=State(trip_spec=full_spec(budget_scope="hotel", budget={"amount_minor": 5500000})))
        self.assertEqual(hotel.status, "choosing")
        whole = await self.turn({}, state=State(trip_spec=full_spec(budget_scope="whole_trip")))
        self.assertEqual(whole.status, "needs_input")
        self.assertIn("расходы", whole.questions[0])
        self.assertIsNone(whole.trip_spec.expense_reserve)

    async def test_missing_child_age_and_pet_unknown(self):
        child = await self.turn({}, state=State(trip_spec=full_spec(travellers={"adults": 2, "children": [None]})))
        self.assertEqual(child.status, "needs_input")
        self.assertIn("ребёнку", child.questions[0])
        self.state.trip_spec.hard_constraints.pets = True
        pet = await self.turn({})
        self.assertEqual(pet.status, "no_solution")

    async def test_error_does_not_mutate_plan(self):
        before = self.state.model_dump_json()
        model = FakeModel(ModelError("model_unavailable"))
        turn = await run_turn(self.state, "дешевле", self.tools, model)
        self.assertEqual(turn.error_code, "model_unavailable")
        self.assertIn("сервисом подбора", turn.assistant_message)
        self.assertNotIn("другими словами", turn.assistant_message)
        self.assertEqual(self.state.model_dump_json(), before)
        self.assertEqual(turn.patch, {})
        self.assertEqual(model.calls, 1)

    async def test_exactly_one_json_repair(self):
        for responses, expected in ((('bad', '{}'), 'choosing'), (('bad', 'bad'), 'error')):
            model = FakeModel(*responses)
            turn = await run_turn(self.state, "варианты", self.tools, model)
            self.assertEqual(turn.status, expected)
            self.assertEqual(model.calls, 2)
            self.assertEqual(turn.telemetry.usage["total_tokens"], 20)

    async def test_repair_receives_original_flat_model_output(self):
        class Capture(FakeModel):
            async def extract(self, context, repair, timeout):
                self.last_repair = repair
                return await super().extract(context, repair, timeout)
        first = {"budget": {"amount_minor": 300000}, "evidence": {"budget": "30 тысяч рублей"}}
        corrected = {"budget": {"amount_minor": 3000000}, "evidence": first["evidence"]}
        model = Capture(first, corrected)
        turn = await run_turn(self.state, "Теперь 30 тысяч рублей", self.tools, model)
        self.assertEqual(turn.status, "no_solution")
        self.assertEqual(json.loads(model.last_repair["previous_output"]), first)
        self.assertEqual(model.calls, 2)

    async def test_paraphrased_evidence_is_rejected_then_repaired(self):
        class Capture(FakeModel):
            async def extract(self, context, repair, timeout):
                self.last_repair = repair
                return await super().extract(context, repair, timeout)
        first = {"add_preferences": ["красивые места"], "evidence": {"add_preferences": "красиво"}}
        corrected = {"add_preferences": ["красивые места"], "evidence": {"add_preferences": "красивые места"}}
        model = Capture(first, corrected)
        turn = await run_turn(self.state, "Хочется красивые места", self.tools, model)
        self.assertNotEqual(turn.status, "error")
        self.assertIn("красивые места", turn.trip_spec.preferences)
        self.assertIn("'красиво'", model.last_repair["validation_error"])
        self.assertEqual(model.calls, 2)
        rejected = await run_turn(self.state, "Хочется красивые места", self.tools, FakeModel(first, first))
        self.assertEqual(rejected.error_code, "model_invalid_json")
        self.assertEqual(rejected.trip_spec, self.state.trip_spec)

    async def test_validation_reloads_prices_and_evidence_from_catalogue(self):
        from travel_agent.domain import Plan
        data = self.plan.model_dump(mode="json")
        data.update(total={"amount_minor": 100}, breakdown={"hotel": {"amount_minor": 100}},
                    component_ids=["client-invented"], evidence=[])
        forged = Plan.model_validate(data)
        checked = await self.tools.validate_plan(forged, self.spec)
        self.assertEqual(checked.total.amount_minor, 10900000)
        self.assertNotIn("client-invented", checked.component_ids)
        self.assertEqual(checked.evidence[0].source_kind, "synthetic")
        self.assertEqual(forged.total.amount_minor, 100)

    async def test_change_delta_uses_catalogue_baseline_price(self):
        from travel_agent.domain import Plan
        data = self.plan.model_dump(mode="json")
        data.update(total={"amount_minor": 100}, breakdown={"hotel": {"amount_minor": 100}})
        self.state.selected_plan = Plan.model_validate(data)
        turn = await self.turn({"budget": {"amount_minor": 10000000}, "evidence": {"budget": "100 тысяч"}}, "Теперь 100 тысяч")
        self.assertEqual(turn.change_preview.price_delta, -1200000)
        self.assertEqual(turn.change_preview.proposed_plan.total.amount_minor, 9700000)

    async def test_duration_and_exact_dates_must_agree(self):
        from travel_agent.tools import allowed
        self.state.trip_spec.duration_days = 4
        turn = await self.turn({})
        self.assertEqual(turn.status, "needs_input")
        self.assertTrue(any("календарных" in question for question in turn.questions))
        self.assertEqual(turn.telemetry.tool_calls, [])
        for days, expected in [(4, False), (6, True)]:
            spec = full_spec(duration_days=days)
            plan = (await self.tools.search_packages(spec))[0]
            self.assertEqual(allowed(plan, spec), expected)

    async def test_cheaper_goal_is_explicit_and_does_not_invent_a_budget(self):
        unchanged = await self.turn({})
        self.assertEqual(unchanged.change_preview.proposed_plan.id, self.plan.id)
        response = {"optimization": "cheaper", "evidence": {"optimization": "подешевле"}}
        cheaper = await self.turn(response, "Сделай подешевле")
        self.assertEqual(cheaper.trip_spec.budget.amount_minor, 12000000)
        self.assertEqual(cheaper.change_preview.price_delta, -1200000)
        self.state.selected_plan = cheaper.change_preview.proposed_plan
        no_cheaper = await self.turn(response, "Ещё подешевле")
        self.assertEqual(no_cheaper.status, "choosing")
        self.assertIsNone(no_cheaper.change_preview)
        self.assertEqual(no_cheaper.options[0].id, self.state.selected_plan.id)
        self.assertIn("нет варианта дешевле", no_cheaper.assistant_message)

    async def test_total_deadline(self):
        class Slow(FakeModel):
            async def extract(self, *args):
                await asyncio.sleep(1)
        turn = await run_turn(self.state, "дешевле", self.tools, Slow(), timeout=.01)
        self.assertEqual(turn.error_code, "turn_timeout")

    async def test_locks_not_silently_changed(self):
        self.state.trip_spec.locked_component_ids = [self.plan.component_ids[1]]
        turn = await self.turn({"patch": {"budget": {"amount_minor": 10000000}}, "evidence": {"budget": "100"}}, "100")
        self.assertEqual(turn.status, "no_solution")

    async def test_unavailable_is_not_silent_demo(self):
        turn = await run_turn(State(trip_spec=self.spec), "найди", UnavailableTools(), FakeModel({}))
        self.assertEqual(turn.error_code, "tools_unavailable")
        self.assertEqual(turn.data_mode, "unavailable")
        self.assertEqual(turn.options, [])

    async def test_unknown_dates_not_invented(self):
        self.state.trip_spec.dates = None
        turn = await self.turn({})
        self.assertEqual(turn.status, "needs_input")
        self.assertIsNone(turn.trip_spec.dates)

    async def test_foreign_destination_not_changed(self):
        turn = await self.turn({}, state=State(trip_spec=full_spec(country="Турция", destination="Анталья")))
        self.assertEqual(turn.status, "needs_input")
        self.assertEqual(turn.trip_spec.destination, "Анталья")
        self.assertEqual(turn.telemetry.tool_calls, [])


class PatchTests(unittest.TestCase):
    def test_reject_bad_money_types(self):
        for bad in (-1, 1.2, True, "100"):
            with self.assertRaises(ValidationError):
                Money(amount_minor=bad)

    def test_evidence_required_for_mutation(self):
        intent = Intent.model_validate({"patch": {"origin": "Казань"}})
        with self.assertRaises(ValueError):
            apply_intent(full_spec(), intent, "сделай дешевле")

    def test_nested_patch_preserves_other_constraints(self):
        intent = Intent.model_validate({"patch": {"hard_constraints": {"free_cancellation": True}}, "evidence": {"hard_constraints": "бесплатная отмена"}})
        spec = apply_intent(full_spec(), intent, "Нужна бесплатная отмена")
        self.assertTrue(spec.hard_constraints.free_cancellation)
        self.assertTrue(spec.hard_constraints.no_night_flights)

    def test_model_cannot_write_booking_or_prices(self):
        for key in ("booking", "checkout_allowed", "options", "total", "selected_plan"):
            with self.assertRaises(ValidationError):
                Intent.model_validate({"patch": {key: True}})

    def test_wrong_thousands_conversion_is_rejected(self):
        intent = Intent.model_validate({"patch": {"budget": {"amount_minor": 300000}}, "evidence": {"budget": "30 тысяч рублей"}})
        with self.assertRaisesRegex(ValueError, "3000000"):
            apply_intent(full_spec(), intent, "Теперь 30 тысяч рублей")

    def test_shared_explicit_budget_scope_evidence(self):
        intent = Intent.model_validate({"patch": {"budget": {"amount_minor": 10000000}, "budget_scope": "hotel"}, "evidence": {"budget": "100 тысяч рублей на отель"}})
        self.assertEqual(apply_intent(full_spec(), intent, "100 тысяч рублей на отель").budget_scope, "hotel")

    def test_repeated_known_fields_are_not_changes(self):
        intent = Intent.model_validate({"patch": {"origin": "Москва", "travellers": {"adults": 2}, "budget": {"amount_minor": 10000000}}, "evidence": {"budget": "100 тысяч"}})
        spec = apply_intent(full_spec(), intent, "100 тысяч")
        self.assertEqual(spec.origin, "Москва")
        self.assertEqual(spec.budget.amount_minor, 10000000)

    def test_all_validation_errors_fit_one_repair(self):
        intent = Intent.model_validate({"patch": {"budget": {"amount_minor": 300000}, "origin": "Тула"}, "evidence": {"budget": "30 тысяч рублей"}})
        with self.assertRaises(ValueError) as caught:
            apply_intent(full_spec(), intent, "Из Тулы, 30 тысяч рублей")
        self.assertIn("3000000", str(caught.exception))
        self.assertIn("evidence for origin", str(caught.exception))

    def test_snapshot_never_allows_checkout_without_ready_plan(self):
        from travel_agent.domain import Snapshot
        payload = {"session_id": "example", "request_id": "request", "revision": 0,
                   "status": "choosing", "trip_spec": {}, "assistant_message": "Выберите поездку",
                   "data_mode": "synthetic", "checkout_allowed": True}
        with self.assertRaises(ValidationError):
            Snapshot.model_validate(payload)
        payload.update(checkout_allowed=False, status="booked_demo")
        with self.assertRaises(ValidationError):
            Snapshot.model_validate(payload)

    def test_month_does_not_justify_exact_dates(self):
        intent = Intent.model_validate({"patch": {"dates": {"start": "2026-11-01", "end": "2026-11-05"}}, "evidence": {"dates": "в ноябре"}})
        with self.assertRaisesRegex(ValueError, "exact calendar days"):
            apply_intent(TripSpec(), intent, "На четыре дня в ноябре")

    def test_abbreviated_date_citation_requires_unique_exact_anchors(self):
        from travel_agent.domain import expand_date_excerpt
        message = "Старт десятого ноября 2026, возвращение пятнадцатого."
        self.assertEqual(expand_date_excerpt("десятого ноября 2026... пятнадцатого", message),
                         "десятого ноября 2026, возвращение пятнадцатого")
        for quote in ["десятого ноября 2025... пятнадцатого", "пятнадцатого...десятого"]:
            self.assertEqual(expand_date_excerpt(quote, message), quote)
        repeated = "десятого или десятого? Возвращение пятнадцатого."
        self.assertEqual(expand_date_excerpt("десятого...пятнадцатого", repeated), "десятого...пятнадцатого")

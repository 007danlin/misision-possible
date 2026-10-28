import json
import unittest
from unittest.mock import AsyncMock

from travel_agent.domain import State, TripSpec
from travel_agent.demo_tools import DemoTools
from travel_agent.fast_intent import fast_intent
from travel_agent.model import QwenModel, Settings
from travel_agent.runner import run_turn


class DirectionLatencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_sea_followup_only_calls_ranking_and_preserves_context(self):
        state = State(search_mode='hotels', trip_spec=TripSpec(
            origin='Каргополь', preferences=['без перелётов'],
            budget={'amount_minor': 5000000}, include_transport=True))
        model = QwenModel(Settings())
        model.extract = AsyncMock(return_value=(json.dumps({
            'choices': [{'id': 'sochi', 'facts': [0]}], 'question': 'none'}), {}))
        result = await run_turn(state, 'к морю', DemoTools(), model)
        self.assertEqual(result.trip_spec.origin, 'Каргополь')
        self.assertEqual(result.trip_spec.preferences, ['без перелётов'])
        self.assertEqual(result.trip_spec.budget, state.trip_spec.budget)
        self.assertEqual(result.trip_spec.travel_setting, 'sea')
        self.assertEqual(result.destination_options[0]['id'], 'sochi')
        self.assertEqual(result.telemetry.model_calls, 1)
        context = model.extract.call_args.args[0]
        self.assertEqual(context['search_mode'], 'directions')
        self.assertEqual(context['trip_spec']['preferences'], ['без перелётов'])
        self.assertEqual({d['id'] for d in context['candidates']}, {'sochi', 'gelendzhik', 'anapa'})

    def test_negation_combined_requests_and_selected_destinations_need_semantics(self):
        state = State(search_mode='hotels')
        for message in ('не хочу к морю', 'к морю, но не Сочи', 'к морю на два дня', 'море или горы'):
            with self.subTest(message=message):
                self.assertIsNone(fast_intent(state, message))
        state.trip_spec.destination = 'Казань'
        self.assertIsNone(fast_intent(state, 'к морю'))

    async def test_plain_sea_from_kargopol_needs_no_model(self):
        state = State(search_mode='hotels', trip_spec=TripSpec(origin='Каргополь', include_transport=True), history=['Отправляемся из Каргополь'])
        model = QwenModel(Settings())
        model.extract = AsyncMock(side_effect=AssertionError('Unnecessary inference'))
        result = await run_turn(state, 'к морю', DemoTools(), model)
        self.assertEqual(result.telemetry.model_calls, 0)
        self.assertEqual(len(result.destination_options), 3)
        self.assertEqual(result.trip_spec.origin, 'Каргополь')
        self.assertLess(result.telemetry.total_ms, 1000)

    def test_simple_choices_never_drop_prior_exclusions_or_short_trip(self):
        from travel_agent.inspiration import simple_direction_choices, direction_options
        for spec, history in [
            (TripSpec(travel_setting='sea', duration_days=2), []),
            (TripSpec(travel_setting='sea'), ['Не хочу Сочи']),
            (TripSpec(travel_setting='sea', preferences=['без перелётов']), []),
        ]:
            self.assertIsNone(simple_direction_choices(spec, 'к морю', history, direction_options(spec)))

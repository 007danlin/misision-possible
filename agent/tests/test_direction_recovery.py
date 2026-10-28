import asyncio
import json
import unittest
from unittest.mock import AsyncMock

from travel_agent.demo_tools import DemoTools
from travel_agent.domain import State, TripSpec
from travel_agent.inspiration import direction_context, direction_options
from travel_agent.model import ModelError, QwenModel, Settings
from travel_agent.runner import run_turn


class DirectionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranking_timeout_keeps_origin_and_wishes_and_can_resume(self):
        original = 'Хочу на природу, в лес. Дикая природа.'
        state = State(search_mode='hotels', history=[original],
                      questions=['Из какого города отправляетесь?'],
                      selection={'pending_origin_request': original})
        model = QwenModel(Settings())
        model.extract = AsyncMock(side_effect=[(json.dumps({
            'patch': {'origin': 'Омск', 'travel_setting': 'forest'},
            'evidence': {'origin': 'из Омска', 'travel_setting': 'в лес'},
        }), {}), ModelError('model_timeout')])
        turn = await run_turn(state, 'Отправляемся из Омска', DemoTools(), model)
        self.assertEqual(turn.status, 'needs_input')
        self.assertEqual(turn.trip_spec.origin, 'Омск')
        self.assertEqual(turn.trip_spec.travel_setting, 'forest')
        self.assertIn(original, turn.selection['pending_direction_request'])
        self.assertNotIn('pending_origin_request', turn.selection)
        self.assertIsNone(state.trip_spec.origin)
        resumed = State(search_mode='hotels', trip_spec=turn.trip_spec,
                        selection=turn.selection, questions=turn.questions)
        model.extract = AsyncMock(return_value=(json.dumps({
            'nearby_quote': '', 'choices': [{'id': 'altai', 'facts': [0]}], 'question': 'none',
        }), {}))
        recovered = await run_turn(resumed, 'Повтори подбор', DemoTools(), model)
        self.assertEqual(recovered.destination_options[0]['id'], 'altai')
        self.assertEqual(recovered.trip_spec.origin, 'Омск')
        self.assertEqual(recovered.telemetry.model_calls, 1)
        self.assertEqual(model.extract.call_args.args[0]['search_mode'], 'directions')
        self.assertIn(original, model.extract.call_args.args[0]['message'])
        self.assertNotIn('pending_direction_request', recovered.selection)

    async def test_outer_deadline_does_not_erase_successful_extraction(self):
        model = QwenModel(Settings())
        async def extract(context, repair, timeout):
            if context['search_mode'] == 'directions':
                await asyncio.sleep(10)
            return json.dumps({'patch': {'origin': 'Омск', 'travel_setting': 'forest'},
                               'evidence': 'Из Омска в лес'}), {}
        model.extract = extract
        turn = await run_turn(State(search_mode='hotels'), 'Из Омска в лес',
                              DemoTools(), model, timeout=.15)
        self.assertEqual(turn.status, 'needs_input')
        self.assertEqual(turn.trip_spec.origin, 'Омск')
        self.assertEqual(turn.trip_spec.travel_setting, 'forest')
        self.assertIn('Повтори подбор', turn.assistant_message)

    def test_compact_context_retains_exclusions_and_catalogue_evidence(self):
        spec = TripSpec(origin='Омск', travel_setting='forest', preferences=['без перелётов'])
        candidates = direction_options(spec)
        context = direction_context(spec, 'В лес, без Селигера',
                                    ['В лес', 'Хочу поближе', 'Хочу поближе'],
                                    [{'id': 'karelia', 'reason': 'rendered duplicate', 'photo_key': 'photo'}],
                                    candidates)
        self.assertEqual(context['history'], ['Хочу поближе'])
        self.assertEqual(context['previous_choices'], ['karelia'])
        self.assertEqual(context['trip_spec']['preferences'], ['без перелётов'])
        self.assertEqual(context['candidates'][0]['facts'], candidates[0]['facts'])
        self.assertEqual(context['candidates'][0]['limits'], candidates[0]['limits'])


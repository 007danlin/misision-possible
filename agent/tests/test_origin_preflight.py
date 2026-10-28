import json
import unittest
from unittest.mock import AsyncMock

from travel_agent.domain import State
from travel_agent.demo_tools import DemoTools
from travel_agent.model import QwenModel, Settings
from travel_agent.origin_followup import needs_initial_origin
from travel_agent.runner import run_turn


class OriginPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def test_question_precedes_any_inference(self):
        for message in ('хочу к морю', 'на природу на выходные, бюджет 30 тысяч'):
            model = QwenModel(Settings())
            model.extract = AsyncMock(side_effect=AssertionError('Model must not run'))
            turn = await run_turn(State(search_mode='hotels'), message, DemoTools(), model)
            self.assertEqual(turn.questions, ['Из какого города отправляетесь?'])
            self.assertEqual(turn.telemetry.model_calls, 0)
            self.assertEqual(turn.telemetry.tool_calls, [])
            self.assertEqual(turn.selection['pending_origin_request'], message)
            self.assertLess(turn.telemetry.total_ms, 1000)

    def test_existing_origin_and_hotel_requests_are_not_intercepted(self):
        for message in ('из Тулы хочу к морю', 'Москва — хочу на море',
                        'отель у моря', 'гостиница на выходные', 'питер, хочу в горы'):
            self.assertFalse(needs_initial_origin(State(search_mode='hotels'), message))
        self.assertFalse(needs_initial_origin(State(search_mode='hotels', trip_spec={'origin': 'Тула'}), 'к морю'))

    async def test_reply_parses_original_wishes(self):
        original = 'на природу на выходные, бюджет 30 тысяч'
        state = State(search_mode='hotels', questions=['Из какого города отправляетесь?'],
                      selection={'pending_origin_request': original})
        model = QwenModel(Settings())
        model.extract = AsyncMock(return_value=(json.dumps({
            'action': 'clarify', 'questions': ['Какие даты поездки?']
        }), {}))
        turn = await run_turn(state, 'Тула', DemoTools(), model)
        context = model.extract.call_args_list[0].args[0]
        self.assertIn(original, context['message'])
        self.assertIn('Тула', context['message'])
        self.assertNotIn('pending_origin_request', turn.selection)
        self.assertEqual(state.selection['pending_origin_request'], original)

    async def test_ranking_does_not_run_without_origin(self):
        model = QwenModel(Settings())
        model.extract = AsyncMock(return_value=(json.dumps({
            'action': 'search', 'patch': {'travel_setting': 'sea'},
            'evidence': {'travel_setting': 'к морю'}
        }), {}))
        state = State(search_mode='hotels', history=['Давайте подберём отдых'])
        turn = await run_turn(state, 'к морю', DemoTools(), model)
        self.assertIn('Из какого города', turn.questions[0])
        self.assertEqual(turn.trip_spec.travel_setting, 'sea')
        self.assertEqual(turn.telemetry.model_calls, 0)

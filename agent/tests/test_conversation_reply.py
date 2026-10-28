import unittest
from travel_agent.conversation_reply import conversation_reply
from travel_agent.domain import State
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from test_agent import FakeModel


class ConversationReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_polite_replies_and_product_explanations_preserve_results_without_search(self):
        state=State(search_mode='hotels',trip_spec={'destination':'Сочи','stay_nights':5,'travellers':{'adults':2},'budget':{'amount_minor':4000000}},hotel_options=[{'id':'hotel','name':'Отель'}],selection={'considered':10},search_url='https://ostrovok.ru/')
        before=state.model_dump_json()
        for message,topic in [('Спасибо!','Пожалуйста'),('Привет','Здравствуйте'),('Что значит предварительная цена?','ориентир'),('Это настоящее бронирование?','учебное')]:
            turn=await run_turn(state,message,DemoTools(),FakeModel())
            self.assertIn(topic,turn.assistant_message)
            self.assertEqual(turn.trip_spec,state.trip_spec)
            self.assertEqual(turn.hotel_options,state.hotel_options)
            self.assertEqual(turn.selection,state.selection)
            self.assertEqual(turn.search_url,state.search_url)
            self.assertEqual(turn.telemetry.model_calls,0)
            self.assertEqual(turn.telemetry.tool_calls,[])
            self.assertEqual(state.model_dump_json(),before)

    async def test_politeness_does_not_lose_a_pending_question(self):
        state=State(search_mode='hotels',assistant_message='Из какого города отправляетесь?')
        turn=await run_turn(state,'Спасибо',DemoTools(),FakeModel())
        self.assertEqual(turn.status,'needs_input')
        self.assertEqual(turn.questions,[state.assistant_message])
        self.assertIn(state.assistant_message,turn.assistant_message)

    def test_combined_wishes_still_go_through_normal_extraction(self):
        for message in ['Привет, хочу в Сочи','Спасибо, но измени даты','Что значит предварительная цена? И добавь бассейн','Большое спасибо, давай другой отель']:
            self.assertIsNone(conversation_reply(message))

if __name__=='__main__':unittest.main()

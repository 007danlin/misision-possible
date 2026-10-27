import unittest
from unittest.mock import patch
from travel_agent.domain import State
from travel_agent.runner import run_turn
from travel_agent.demo_tools import DemoTools
from travel_agent import journey
from test_agent import FakeModel
from test_journey import spec

class AlternativesTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  p=patch.dict('os.environ',{'JOURNEY_DATA_SOURCE':'synthetic'});p.start();self.addCleanup(p.stop)
 async def test_replace_excludes_previous_and_preserves_constraints(self):
  s=spec();h=journey.reprice(s,'sample-sochi-1');state=State(search_mode='hotels',trip_spec=s,hotel_options=[h]);r=await run_turn(state,'Все три мимо, давай другие',DemoTools(),FakeModel({'action':'replace_options'}));self.assertEqual(r.status,'choosing');self.assertTrue(all(h['id']!='sample-sochi-1' for h in r.hotel_options));self.assertEqual(r.trip_spec.budget,s.budget);self.assertEqual(r.trip_spec.dates,s.dates);self.assertEqual(r.trip_spec.hard_constraints,s.hard_constraints)
 async def test_exhaustion_is_explicit_and_restore_clears_exclusions(self):
  s=spec();state=State(search_mode='hotels',trip_spec=s,hotel_options=[journey.reprice(s,h['id']) for h in journey.candidates(s)]);r=await run_turn(state,'Замени все',DemoTools(),FakeModel({'action':'replace_options'}));self.assertEqual(r.status,'no_solution');self.assertIn('не осталось',r.assistant_message);state.trip_spec=r.trip_spec;r=await run_turn(state,'Верни прежние',DemoTools(),FakeModel({'action':'restore_options'}));self.assertEqual(r.status,'choosing');self.assertEqual(r.trip_spec.excluded_hotel_ids,[])
 async def test_locked_hotel_requires_permission_before_replacing(self):
  s=spec();s.keep_hotel=True;state=State(search_mode='hotels',trip_spec=s,hotel_options=[journey.reprice(s,'sample-sochi-1')]);r=await run_turn(state,'Покажи другое',DemoTools(),FakeModel({'action':'replace_options'}));self.assertEqual(r.status,'needs_input');self.assertTrue(r.trip_spec.keep_hotel);self.assertEqual(r.trip_spec.excluded_hotel_ids,[])
 async def test_ambiguous_request_does_not_run_search(self):
  state=State(search_mode='hotels',trip_spec=spec());r=await run_turn(state,'500 евро, переведи',DemoTools(),FakeModel({'questions':['Какой бюджет в рублях?'],'action':'clarify'}));self.assertEqual(r.status,'needs_input');self.assertEqual(r.questions,['Какой бюджет в рублях?']);self.assertEqual(r.hotel_options,[])
 async def test_public_review_question_uses_sample_evidence(self):
  h={'id':'real','name':'Реальный','source_kind':'public','reviews':200,'review_items':[{'id':'1','text':'Тихо'}],'review_summary':{'Тишина':{'mention_ids':['1'],'positive_ids':['1'],'negative_ids':[]}}};state=State(search_mode='hotels',trip_spec=spec(),hotel_options=[h]);r=await run_turn(state,'Что пишут про тишину?',DemoTools(),FakeModel({}));self.assertIn('1 отзыв из 200',r.assistant_message);self.assertIn('положительных отзывов — 1',r.assistant_message);self.assertNotIn('выборк',r.assistant_message)

class LanguageGuardTests(unittest.TestCase):
 def test_clarifications_are_atomic_and_do_not_guess(self):
  from travel_agent.fast_intent import clarify_ambiguous_request
  from travel_agent.domain import Intent,apply_intent
  for text in ['На 4 или 6 ночей, ещё не решил','Даты 25–14 декабря 2026 года','Как в прошлый раз, но я не рассказывала условия']:
   i=clarify_ambiguous_request(text);self.assertIsNotNone(i);self.assertTrue(i.questions);self.assertEqual(apply_intent(spec(),i,text),spec())
  i=Intent(patch={'budget':{'amount_minor':1}},questions=['Уточните бюджет?']);self.assertEqual(apply_intent(spec(),i,'неясно'),spec())
  self.assertIsNone(clarify_ambiguous_request('На 5 ночей, 14–25 декабря'))
 def test_polarity_and_price_order(self):
  from travel_agent.fast_intent import protect_explicit_polarity
  from travel_agent.domain import Intent,apply_intent
  for text,key,value in [('Отель обязательно без бассейна.','pool',False),('Без спа даже не предлагай.','spa',True),('Не показывай без парковки','parking',True)]:
   i=protect_explicit_polarity(Intent(remove_hotel_preferences=[key],evidence={'remove_hotel_preferences':text}),text)
   self.assertEqual(getattr(apply_intent(spec(),i,text).hotel_preferences,key),value)
  i=protect_explicit_polarity(Intent(),'Отсортируй по полной цене, начиная с самых доступных.');self.assertEqual(i.optimization,'cheaper')
 def test_hotel_budget_survives_separate_road_sentence(self):
  from travel_agent.fast_intent import protect_hotel_budget_scope
  from travel_agent.domain import Intent,apply_intent
  text='На отель не больше 35 тысяч рублей. Дорогу по-прежнему учитываем отдельно.'
  i=protect_hotel_budget_scope(Intent(patch={'budget':{'amount_minor':3500000}},evidence={'budget':text}),text);s=apply_intent(spec(),i,text);self.assertEqual(s.hotel_budget.amount_minor,3500000);self.assertEqual(s.trip_budget.amount_minor,12000000)

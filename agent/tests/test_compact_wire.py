import json,unittest
from travel_agent.compact_wire import decode
from travel_agent.model import canonical_intent
from travel_agent.domain import Intent,TripSpec,apply_intent
class CompactWireTests(unittest.TestCase):
 def test_complete_family_roundtrip(self):
  msg='В Сочи, 2 взрослых и 5 детей, на 5 ночей, до 100 тысяч рублей на отель, нужен бассейн'
  raw='{"e":0,"to":"Сочи","a":2,"c":5,"n":5,"rub":100000,"bs":"hotel","pool":true}'
  i=Intent.model_validate_json(canonical_intent(decode(raw,msg),msg));s=apply_intent(TripSpec(),i,msg)
  self.assertEqual(s.destination,'Сочи');self.assertEqual(s.travellers.children,[None]*5);self.assertEqual(s.travellers.adults,2);self.assertEqual(s.budget.amount_minor,10000000);self.assertTrue(s.hotel_preferences.pool)
 def test_followup_preserves_unmentioned_fields(self):
  s=TripSpec(destination='Сочи',travellers={'adults':2,'children':[3,4,5,6,7]},dates={'start':'2026-11-10','end':'2026-11-15'},budget={'amount_minor':10000000},hotel_preferences={'pool':True})
  msg='Бассейн не важен, нужна парковка'
  i=Intent.model_validate_json(canonical_intent(decode('{"e":0,"rm":["pool"],"parking":true}',msg),msg));r=apply_intent(s,i,msg)
  self.assertIsNone(r.hotel_preferences.pool);self.assertTrue(r.hotel_preferences.parking);self.assertEqual(s.travellers,r.travellers);self.assertEqual(s.dates,r.dates);self.assertEqual(s.budget,r.budget)
 def test_dates_and_ages_exact(self):
  d=json.loads(decode('{"e":0,"d":["2026-11-12","2026-11-16"],"c":[3,4,5,6,7]}','test'))
  self.assertEqual(d['dates']['end'],'2026-11-16');self.assertEqual(d['travellers']['children'],[3,4,5,6,7])
 def test_source_and_duplicate_and_unknown_fields_rejected(self):
  for raw in ('{"e":1}','{"e":false}','{"e":0,"e":0}','{"e":0,"invent":true}','{"e":0,"c":11}','{"e":0,"rub":true}','{"e":0,"rub":1.001}'):
   with self.assertRaises(ValueError):decode(raw,'test')
 def test_long_message_uses_original_protocol(self):
  with self.assertRaises(ValueError):decode('{"e":0}','x'*501)
 def test_exact_cents(self):
  self.assertEqual(json.loads(decode('{"e":0,"rub":500.25}','test'))['budget']['amount_minor'],50025)

 def test_context_uses_same_units_as_output(self):
  from travel_agent.compact_wire import encode
  value={'trip_spec':{'budget':{'amount_minor':10000000,'currency':'RUB'},'hotel_budget':{'amount_minor':10000000},'dates':{'start':'2026-11-12','end':'2026-11-16'},'travellers':{'adults':2,'children':[3,4,5,6,7]},'hotel_preferences':{'pool':True},'keep_hotel':True}}
  encoded=encode(value)['trip_spec']
  self.assertEqual(encoded['rub'],100000);self.assertEqual(encoded['old_hotel_rub'],100000)
  self.assertEqual(encoded['d'],[20261112,20261116]);self.assertTrue(encoded['keep'])
  self.assertEqual(encoded['c'],[3,4,5,6,7]);self.assertEqual(value['trip_spec']['budget']['amount_minor'],10000000)

 def test_integer_dates_and_transport_fields(self):
  d=json.loads(decode('{"e":0,"d":[20261112,20261116],"transport":true,"keep":true,"reserve":0}', 'test'))
  self.assertEqual(d['dates'],{'start':'2026-11-12','end':'2026-11-16'})
  self.assertTrue(d['include_transport']);self.assertTrue(d['keep_hotel']);self.assertEqual(d['expense_reserve']['amount_minor'],0)

class BudgetWireTests(unittest.TestCase):
 def test_period_is_part_of_the_money_field(self):
  for key,period in [('night_rub','night'),('stay_rub','stay')]:
   d=json.loads(decode(json.dumps({'e':0,key:20000}),'test'))
   self.assertEqual(d['budget']['amount_minor'],2000000);self.assertEqual(d['budget_period'],period)
 def test_conflicting_units_require_repair(self):
  for raw in ('{"e":0,"night_rub":20,"rub":30}','{"e":0,"night_rub":20,"bp":"stay"}','{"e":0,"bp":"stay","night_rub":20}'):
   with self.assertRaises(ValueError):decode(raw,'test')

class CompactProtocolTests(unittest.IsolatedAsyncioTestCase):
 async def invoke(self,message='Хочу в Сочи',repair=None,prefill=False,raw='{"e":0,"to":"Сочи"}',finish='stop'):
  import httpx,os
  from unittest.mock import patch
  from travel_agent.model import QwenModel,Settings
  captured=[]
  def respond(request):
   captured.append(json.loads(request.content))
   return httpx.Response(200,json={'choices':[{'message':{'content':raw},'finish_reason':finish}],'usage':{'completion_tokens':0 if prefill else 10}})
  original=httpx.AsyncClient
  with patch.dict(os.environ,{'HOTEL_COMPACT_WIRE':'1'}),patch('travel_agent.model.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(respond),**kw)):
   result=await QwenModel(Settings()).extract({'message':message,'search_mode':'hotels','trip_spec':{}},repair,2,prefill=prefill)
  return result,captured[0]
 async def test_short_protocol_decodes_with_exact_original_evidence(self):
  (raw,_),payload=await self.invoke()
  self.assertEqual(json.loads(raw),{'destination':'Сочи','evidence':'Хочу в Сочи'})
  self.assertIn('grammar',payload);self.assertNotIn('response_format',payload)
 async def test_long_messages_keep_full_protocol(self):
  (_, _),payload=await self.invoke('x'*501)
  self.assertNotIn('grammar',payload);self.assertEqual(payload['response_format']['type'],'json_schema')
 async def test_repair_reuses_stable_wire_prefix(self):
  _,initial=await self.invoke()
  (raw,_),repaired=await self.invoke(repair={'previous_output':'{}','validation_error':'missing city'})
  self.assertEqual(initial['messages'][0],repaired['messages'][0])
  self.assertIn('grammar',repaired);self.assertNotIn('response_format',repaired)
  self.assertIn('missing city',repaired['messages'][-1]['content'])
  self.assertEqual(json.loads(raw)['destination'],'Сочи')
 async def test_invalid_wire_goes_to_existing_validation_retry(self):
  (raw,_),_=await self.invoke(raw='{"e":3,"to":"Сочи"}')
  self.assertIn('wire_error',json.loads(raw))
 async def test_prefill_produces_no_answer(self):
  (raw,usage),payload=await self.invoke(prefill=True,raw='',finish='length')
  self.assertEqual(payload['max_tokens'],0);self.assertEqual(raw,'');self.assertEqual(usage['completion_tokens'],0)

class GroundedGrammarTests(unittest.TestCase):
 def test_duration_does_not_enable_nightly_budget(self):
  from travel_agent.compact_wire import grammar
  for text in ('На 5 ночей до 40 тысяч на отель','На семь ночей, максимум 60 тысяч за жильё'):
   result=grammar(text)
   self.assertNotIn('night_rub',result)
   self.assertNotIn('night',next(line for line in result.splitlines() if line.startswith('period ::=')))
 def test_explicit_nightly_prices_are_available(self):
  from travel_agent.compact_wire import grammar
  for text in ('20 тысяч за ночь','5000 рублей в сутки','4000 / ночь'):
   self.assertIn('night_rub',grammar(text))

 def test_calendar_output_needs_calendar_reference(self):
  from travel_agent.compact_wire import grammar
  date_key=json.dumps('"d":')
  for text in ('На четыре ночи до 40 тысяч рублей','На 5 ночей в ноябре 2026','Вдвоем до 20 тысяч рублей за ночь'):
   self.assertNotIn(date_key,grammar(text).splitlines()[1])
  for text in ('С 10 по 15 ноября 2026','2026-11-10 — 2026-11-15','12.11.2026 — 15.11.2026','С первого по пятое ноября'):
   self.assertIn(date_key,grammar(text).splitlines()[1])

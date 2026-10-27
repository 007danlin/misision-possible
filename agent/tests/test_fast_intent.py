import json
import unittest
from travel_agent.domain import State,TripSpec,Intent,apply_intent
from travel_agent.fast_intent import fast_intent,protect_child_count,protect_stay_length,protect_adult_count,protect_explicit_forest,protect_hotel_budget_scope
from travel_agent.model import canonical_intent, compact_state

class FastIntentTests(unittest.TestCase):
 def test_five_children_never_become_three(self):
  message='В Сочи с 5 детей, на 5 ночей. Возрасты старших: 3, 4, 5 лет; младших уточню.'
  intent=Intent(patch={'travellers':{'children':[3,4,5]},'stay_nights':5},evidence={'travellers':'5 детей','stay_nights':'5 ночей'})
  fixed=protect_child_count(intent,message,TripSpec())
  self.assertEqual(apply_intent(TripSpec(),fixed,message).travellers.children,[3,4,5,None,None])
 def test_child_count_cannot_invent_ages(self):
  for message in ('Нас трое взрослых и пятеро детей. На пять ночей.', 'В Сочи с 5 детей, на 5 ночей'):
   intent=Intent(patch={'travellers':{'children':[5]*5}},evidence={'travellers':message})
   fixed=protect_child_count(intent,message,TripSpec())
   self.assertEqual(apply_intent(TripSpec(),fixed,message).travellers.children,[None]*5)
 def test_repeated_child_count_keeps_known_ages(self):
  previous=TripSpec(travellers={'adults':3,'children':[3,5,7,10,12]})
  message='Всё ещё 5 детей, теперь нужен завтрак'
  intent=Intent(patch={'travellers':{'children':[5]*5}},evidence={'travellers':message})
  result=apply_intent(previous,protect_child_count(intent,message,previous),message)
  self.assertEqual(result.travellers.children,previous.travellers.children)
 def test_child_count_with_actual_ages_is_kept(self):
  for message,ages in [('5 детей: 3, 5, 7, 10 и 12',[3,5,7,10,12]),('5 детей, всем по 5 лет',[5]*5)]:
   intent=Intent(patch={'travellers':{'children':ages}},evidence={'travellers':message})
   result=apply_intent(TripSpec(),protect_child_count(intent,message,TripSpec()),message)
   self.assertEqual(result.travellers.children,ages)
 def test_age_list_keeps_five_children_and_adults(self):
  s=State(search_mode='hotels',trip_spec={'travellers':{'adults':2,'children':[None]*5},'hotel_preferences':{'pool':True},'stay_nights':5},assistant_message='Сколько лет каждому из 5 детей?')
  for message in ('3, 4, 5, 6, 7 лет','Возраст детей: 3, 4, 5, 6, 7'):
   result=apply_intent(s.trip_spec,fast_intent(s,message),message)
   self.assertEqual(result.travellers.children,[3,4,5,6,7]);self.assertEqual(result.travellers.adults,2);self.assertTrue(result.hotel_preferences.pool)
  self.assertIsNone(fast_intent(s,'3, 4, 5 лет'))
 def test_explanation_shortcut_does_not_swallow_new_wishes(self):
  state=State(search_mode='hotels',hotel_options=[{'id':'a','name':'Первый'},{'id':'b','name':'Второй'}],trip_spec={'travellers':{'adults':3,'children':[3,5,7,10,12]},'preferences':['подальше от лифта']})
  for message in ('Почему ты выбрал второй отель?', 'Почему рекомендуешь именно второй вариант?', 'Почему вы предложили второй?'):
   intent=fast_intent(state,message)
   self.assertEqual(intent.action,'explain');self.assertEqual(intent.hotel_reference,2)
   self.assertEqual(apply_intent(state.trip_spec,intent,message),state.trip_spec)
  for message in ('Почему второй отель? И добавь бассейн', 'Почему второй, хочу дешевле', 'Почему не второй отель?'):
   self.assertIsNone(fast_intent(state,message))

 def test_freeform_always_uses_model(self):
  for m in ('Хочу на море с бабушкой, важно без лестниц','На 5 ночей, но если дорого, лучше три','Дешевле, но со спа'):
   self.assertIsNone(fast_intent(State(),m))
 def test_cheaper_preserves_constraints(self):
  s=State(trip_spec={'travellers':{'adults':2,'children':[3,4,5,6,7]},'hotel_preferences':{'pool':True,'parking':False},'stay_nights':5,'budget':{'amount_minor':10000000}})
  m='Теперь дешевле';i=fast_intent(s,m);self.assertEqual(i.optimization,'cheaper');self.assertEqual(apply_intent(s.trip_spec,i,m),s.trip_spec)
 def test_quoted_budget_arithmetic_does_not_need_model_retry(self):
  msg='До 100 тысяч рублей, на 5 ночей'
  raw=json.dumps({'budget':{'amount_minor':1000000},'dates':{'start':None,'end':None},'stay_nights':5,'evidence':msg})
  intent=Intent.model_validate_json(canonical_intent(raw,msg));r=apply_intent(TripSpec(),intent,msg)
  self.assertEqual(r.budget.amount_minor,10000000);self.assertIsNone(r.dates)
 def test_unquoted_budget_cannot_be_corrected_or_accepted(self):
  msg='До 100 тысяч рублей'
  i=Intent.model_validate_json(canonical_intent(json.dumps({'budget':{'amount_minor':3000000},'evidence':'30 тысяч рублей'}),msg))
  with self.assertRaises(ValueError):apply_intent(TripSpec(),i,msg)
 def test_explicit_false_kept_in_model_context(self):
  self.assertIs(compact_state({'hotel_preferences':{'parking':False}})['hotel_preferences']['parking'],False)

 def test_explicit_nights_not_lost_with_budget_maximum(self):
  msg='На семь ночей, максимум 60 тысяч за жильё'
  i=protect_stay_length(Intent(),msg,TripSpec())
  self.assertEqual(apply_intent(TripSpec(),i,msg).stay_nights,7)
  for msg in ('Не на пять ночей','Если недорого, на пять ночей','На пять или семь ночей','Не меньше пяти ночей'):
   self.assertIsNone(protect_stay_length(Intent(),msg,TripSpec()).patch.stay_nights)

 def test_adults_and_children_both_preserved(self):
  msg='Поедем вдвоём с 5 детей'
  i=protect_child_count(Intent(),msg,TripSpec());i=protect_adult_count(i,msg)
  r=apply_intent(TripSpec(),i,msg)
  self.assertEqual(r.travellers.adults,2);self.assertEqual(len(r.travellers.children),5)
 def test_budget_shortcut_retains_dates_and_children(self):
  s=State(trip_spec={'dates':{'start':'2026-11-10','end':'2026-11-15'},'travellers':{'adults':2,'children':[3,4,5,6,7]}})
  msg='Бюджет 50 тысяч рублей на отель за весь отдых'
  i=fast_intent(s,msg);r=apply_intent(s.trip_spec,i,msg)
  self.assertEqual(r.budget.amount_minor,5000000);self.assertEqual(r.dates,s.trip_spec.dates);self.assertEqual(r.travellers,s.trip_spec.travellers)

 def test_empty_model_fields_do_not_erase_previous_family(self):
  s=TripSpec(destination='Сочи',travellers={'adults':2,'children':[3,4,5,6,7]},budget={'amount_minor':10000000},travel_setting='sea')
  msg='Хочу ещё парковку'
  raw={'destination':None,'travellers':{'adults':None,'children':[]},'budget':None,'travel_setting':None,'hotel_preferences':{'parking':True},'evidence':msg}
  i=Intent.model_validate_json(canonical_intent(json.dumps(raw),msg));r=apply_intent(s,i,msg)
  self.assertEqual(r.travellers,s.travellers);self.assertEqual(r.budget,s.budget);self.assertEqual(r.destination,'Сочи');self.assertEqual(r.travel_setting,'sea');self.assertTrue(r.hotel_preferences.parking)
 def test_nested_nights_are_mapped_without_fabricating_dates(self):
  msg='На 5 ночей, до 100 тысяч рублей'
  raw={'dates':{'start':None,'end':None,'stay_nights':5},'budget':{'amount_minor':100000,'budget_period':'stay'},'evidence':msg}
  i=Intent.model_validate_json(canonical_intent(json.dumps(raw),msg));r=apply_intent(TripSpec(),i,msg)
  self.assertEqual(r.stay_nights,5);self.assertIsNone(r.dates);self.assertEqual(r.budget.amount_minor,10000000)

 def test_explicit_forest_is_not_lost_but_negative_is_not_inverted(self):
  msg='Уедем вдвоём, хочется леса и уединения.'
  self.assertEqual(apply_intent(TripSpec(),protect_explicit_forest(Intent(),msg),msg).travel_setting,'forest')
  for msg in ('Не хочу в лес','Хочу море или лес','Лес не обязателен'):
   self.assertIsNone(protect_explicit_forest(Intent(),msg).patch.travel_setting)

 def test_whole_stay_is_not_whole_holiday(self):
  msg='45 тысяч рублей за всё проживание'
  i=protect_hotel_budget_scope(Intent(patch={'budget_scope':'whole_trip'},evidence={'budget_scope':msg}),msg)
  self.assertEqual(apply_intent(TripSpec(),i,msg).budget_scope,'hotel')
  msg='45 тысяч на отель и дорогу'
  self.assertIsNone(protect_hotel_budget_scope(Intent(),msg).patch.budget_scope)

 def test_forest_keeps_explicit_remoteness_as_a_separate_wish(self):
  msg='Уедем вдвоём подальше от города, хочется леса и уединения.'
  i=Intent(add_preferences=['уединение'],evidence={'add_preferences':msg})
  spec=apply_intent(TripSpec(),protect_explicit_forest(i,msg),msg)
  self.assertEqual(spec.travel_setting,'forest')
  self.assertEqual(set(spec.preferences),{'уединение','подальше от города'})
  negative='Не хочу подальше от города, хочу в лес'
  self.assertEqual(protect_explicit_forest(Intent(),negative).add_preferences,[])

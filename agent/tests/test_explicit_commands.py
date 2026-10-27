import unittest
from travel_agent.domain import State,apply_intent
from travel_agent.fast_intent import fast_intent

class ExplicitCommandsTests(unittest.TestCase):
 def setUp(self):
  self.state=State(search_mode='hotels',trip_spec={'destination':'Казань','dates':{'start':'2026-11-10','end':'2026-11-16'},'travellers':{'adults':3,'children':[3,5,7,10,12]},'budget':{'amount_minor':18000000},'budget_scope':'hotel','hotel_preferences':{'pool':True,'parking':True},'preferences':['тишина','подальше от лифта']})
 def test_compound_change_preserves_every_untouched_requirement(self):
  m='Бассейн больше не обязателен, зато завтрак обязателен. Бюджет снизим до 120 тысяч рублей на всё проживание. Остальные пожелания сохрани.'
  intent=fast_intent(self.state,m);self.assertIsNotNone(intent)
  new=apply_intent(self.state.trip_spec,intent,m)
  self.assertIsNone(new.hotel_preferences.pool);self.assertTrue(new.hotel_preferences.breakfast);self.assertTrue(new.hotel_preferences.parking)
  self.assertEqual(new.budget.amount_minor,12000000);self.assertEqual(new.budget_period,'stay')
  for key in ('destination','dates','travellers','preferences','hard_constraints'):self.assertEqual(getattr(new,key),getattr(self.state.trip_spec,key))
 def test_explicit_edits_with_different_wording(self):
  for m in ('Убери бассейн; добавь завтрак и парковку; до 90 тысяч рублей на отель', 'Бассейн не важен. Нужны завтрак и парковка. Уменьши бюджет до 90 тысяч рублей на отель'):
   i=fast_intent(self.state,m);self.assertIsNotNone(i,m);s=apply_intent(self.state.trip_spec,i,m)
   self.assertIsNone(s.hotel_preferences.pool);self.assertTrue(s.hotel_preferences.breakfast);self.assertEqual(s.budget.amount_minor,9000000)
 def test_partial_or_ambiguous_edits_never_bypass_model(self):
  for m in ('Добавь завтрак, но только если он бесплатный','Нужен бассейн или спа','Убери бассейн и найди тихий номер','Добавь завтрак. И поближе к морю','Бассейн не нужен','Нужна парковка без доплаты','Бассейн не обязателен. Бассейн обязателен','До 40 тысяч рублей. До 50 тысяч рублей','Добавь завтрак, убери парковку, где-нибудь в лесу','Не добавь завтрак','Почему нужен бассейн?','Бассейн обязателен?','Уменьши бюджет до 30 тысяч долларов'):
   self.assertIsNone(fast_intent(self.state,m),m)
 def test_period_and_decimal_price(self):
  for text,amount,period in [('До 12,5 тысяч рублей за ночь',1250000,'night'),('До 12.5 тысяч рублей за ночь',1250000,'night'),('До 90 тысяч рублей за всё проживание',9000000,'stay')]:
   i=fast_intent(self.state,text);self.assertIsNotNone(i,text);s=apply_intent(self.state.trip_spec,i,text);self.assertEqual(s.budget.amount_minor,amount);self.assertEqual(s.budget_period,period)

 def test_scope_alone_does_not_reset_nightly_period(self):
  self.state.trip_spec.budget_period='night'
  m='Добавь завтрак. До 15 тысяч рублей на отель'
  i=fast_intent(self.state,m);s=apply_intent(self.state.trip_spec,i,m)
  self.assertEqual(s.budget_period,'night');self.assertEqual(s.budget_scope,'hotel')

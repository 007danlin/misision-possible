import unittest,time,json
from travel_agent import transport,tutu
from travel_agent.domain import State,Intent,apply_intent
from travel_agent.hotel_selection import demo_quote
from travel_agent.fast_intent import fast_intent,protect_hotel_budget_scope,protect_hotel_question,protect_explicit_polarity
from travel_agent.places import nearby_places
from test_public_content import base,spec

class TransportTests(unittest.TestCase):
 def test_modes_reprice_transfers_and_overnight(self):
  h=base();s=spec();q=demo_quote(h,s);j=transport.build(h,s,q);self.assertEqual({a['id'] for a in j['alternatives']},{'flight','train','car'});amounts=[]
  for mode in ['flight','train','car']:
   s.transport_mode=mode;r=transport.build(h,s,q);amounts.append(r['total_minor']);self.assertEqual(r['total_minor'],sum(r['breakdown'].values()));self.assertEqual(r['breakdown']['hotel'],q['total_minor']);self.assertEqual(r['transport']['id'],mode)
   if mode=='car':self.assertEqual(r['breakdown']['transfers'],0);self.assertTrue(all(x['kind']=='car' for x in r['segments']))
   if mode=='train':self.assertTrue(r['transport']['overnight']);self.assertLess(r['segments'][0]['departure'][:10],str(s.dates.start))
  self.assertEqual(len(set(amounts)),3)
 def test_family_composition_survives_transport_and_transfer_changes(self):
  h=base();h['content']={'transfer_service':{'listed':True}}
  s=spec(travellers={'adults':3,'children':[0,7,17]})
  original=s.model_dump(mode='json');q=demo_quote(h,s)
  for mode in ['flight','train','car']:
   for provider in ['estimate','hotel']:
    changed=s.model_copy(update={'transport_mode':mode,'transfer_provider':provider})
    j=transport.build(h,changed,q)
    self.assertEqual(j['breakdown']['hotel'],q['total_minor'])
    self.assertEqual(j['total_minor'],sum(j['breakdown'].values()))
    self.assertEqual(j['child_seats'],3)
    self.assertEqual(j['vehicles'],2)
    self.assertEqual(changed.dates,s.dates);self.assertEqual(changed.travellers,s.travellers)
    self.assertFalse(j['can_book'],'unknown child policies must remain blocking')
    if mode=='car':self.assertEqual(j['breakdown']['transfers'],0)
    else:self.assertEqual(j['transfer_choice']['provider'],provider)
  self.assertEqual(s.model_dump(mode='json'),original)
 def test_origin_not_assumed_and_missing_mode_not_substituted(self):
  h=base();s=spec(origin=None);self.assertIsNone(transport.build(h,s,demo_quote(h,s)));s.origin='Владимир';s.transport_mode='flight';self.assertIsNone(transport.build(h,s,demo_quote(h,s)));s.transport_mode='car';self.assertEqual(transport.build(h,s,demo_quote(h,s))['segments'][0]['origin'],'Владимир')
 def test_owned_tickets_cost_and_connections(self):
  h=base();s=spec(transport_owned=True,owned_transport={'arrival':'2026-11-10T12:00:00+03:00','departure':'2026-11-15T18:00:00+03:00','terminal':'airport','paid_total_minor':2500000});j=transport.build(h,s,demo_quote(h,s));self.assertEqual(j['breakdown']['transport'],2500000);self.assertEqual(j['segments'][1]['departure'],'2026-11-10T12:45:00+03:00');s.owned_transport.paid_total_minor=None;j=transport.build(h,s,demo_quote(h,s));self.assertTrue(j['total_incomplete']);self.assertFalse(j['can_book'])
 def test_owned_tickets_keep_other_transport_choices(self):
  h=base();s=spec(transport_owned=True,owned_transport={'arrival':'2026-11-10T12:00:00+03:00','departure':'2026-11-15T18:00:00+03:00','terminal':'airport','paid_total_minor':2500000});q=demo_quote(h,s);j=transport.build(h,s,q)
  self.assertEqual({a['id'] for a in j['alternatives']},{'flight','train','car'})
  for alternative in j['alternatives']:
   changed=s.model_copy(update={'transport_owned':False,'owned_transport':None,'transport_mode':alternative['id']})
   expected=transport.build(h,changed,q)
   self.assertEqual(alternative['trip_total_minor'],expected['total_minor'])
   self.assertEqual(alternative['price_delta'],expected['total_minor']-j['total_minor'])
  self.assertTrue(s.transport_owned);self.assertEqual(s.owned_transport.paid_total_minor,2500000)
 def test_strict_constraints_are_preserved(self):
  h=base();s=spec(hard_constraints={'no_connections':True},transport_mode='train');j=transport.build(h,s,demo_quote(h,s));self.assertFalse(j['can_book']);self.assertEqual(next(c for c in j['checks'] if c['code']=='no_connections')['status'],'unknown');s.hard_constraints.no_connections=False;s.hard_constraints.no_night_travel=True;self.assertFalse(transport.build(h,s,demo_quote(h,s))['can_book'])
 def test_cached_train_reference(self):
  s=spec();h=base();h['rail_reference']={'Москва|Сочи':{'retrieved':time.time(),'out':{'minutes':1400,'price_minor':400000,'departure_time':'10:30'},'back':{'minutes':1500,'price_minor':500000,'departure_time':'17:20'},'source':'Туту · кэш','source_url':tutu.SOURCE}};s.transport_mode='train';j=transport.build(h,s,demo_quote(h,s));self.assertEqual(j['breakdown']['transport'],1800000);self.assertIn('T10:30',j['segments'][0]['departure']);self.assertIn('Туту',j['transport']['source']);self.assertEqual(j['segments'][0]['duration_minutes'],1400)
 def test_real_nearby_ranking_and_distance(self):
  h=base();h['map_points']=[{'name':'Парк','lat':43.601,'lng':39.701,'type':'PARK'},{'name':'Пляж','lat':43.602,'lng':39.702,'type':'BEACH'},{'name':'Далеко','lat':10.,'lng':10.}];p=nearby_places(h,spec(travel_setting='sea'));self.assertEqual(p[0]['name'],'Пляж');self.assertEqual(len(p),2);self.assertEqual(p[0]['distance_kind'],'straight')
 def test_commands_retain_budget_dates(self):
  s=State(search_mode='hotels',trip_spec=spec());i=fast_intent(s,'Лучше поездом');changed=apply_intent(s.trip_spec,i,'Лучше поездом');self.assertEqual(changed.transport_mode,'train');self.assertEqual(changed.budget,s.trip_spec.budget);self.assertEqual(changed.dates,s.trip_spec.dates);self.assertEqual(fast_intent(s,'Отправляемся из Санкт-Петербург').patch.origin,'Санкт-Петербург');self.assertTrue(fast_intent(s,'Билеты уже куплены').patch.transport_owned)
 def test_guard_generalization(self):
  self.assertEqual(protect_hotel_question(Intent(action='reviews',hotel_reference=3),'Чем привлекателен третий отель?').action,'explain');i=protect_explicit_polarity(Intent(),'Варианты без парковки не показывай.');self.assertTrue(i.patch.hotel_preferences.parking);self.assertFalse(i.questions)
  text='На проживание максимум 30 тысяч рублей. Билеты считаем отдельно.';i=protect_hotel_budget_scope(Intent(patch={'include_transport':False,'budget':{'amount_minor':3000000},'budget_scope':'hotel'},evidence={'budget':text,'include_transport':text,'budget_scope':text}),text);s=apply_intent(spec(),i,text);self.assertTrue(s.include_transport);self.assertEqual(s.trip_budget.amount_minor,15000000)
 def test_jsonp_is_data_not_code(self):
  row={'travelTimeInSeconds':'7200','departureTime':'09:00:00','arrivalTime':'11:00:00','categories':[{'price':1000}],'trainNumber':'X'};self.assertEqual(tutu.parse('n('+json.dumps({'trips':[row]})+')')[0]['price_minor'],100000)
  with self.assertRaises(ValueError):tutu.parse('n(alert(1))')

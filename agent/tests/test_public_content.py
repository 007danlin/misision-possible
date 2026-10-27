import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from travel_agent import public_content as pc,journey
from travel_agent.domain import TripSpec
from travel_agent.hotel_selection import select_hotels
from travel_agent.trip_context import weather_context,transfer_estimate

def base():return dict(id='real_hotel',name='Настоящий отель',url='https://ostrovok.ru/hotel/russia/sochi/mid123/real_hotel/',source_kind='public',destination='Сочи',coordinates={'lat':43.6,'lng':39.7},reference_nightly_minor=400000,amenity_codes=['has_pool'],rating=9,reviews=200,images=[],amenities=[])
def page(hid='real_hotel'):
 d={'hotel':{'id':hid,'policies':{'checkInCheckOut':{'value':{'checkInTimeStart':{'hours':15,'minutes':0},'checkOutTimeEnd':{'hours':12,'minutes':0}}}},'location':{'latitude':43.6,'longitude':39.7},'roomGroups':[{'nameStruct':{'mainName':'Стандарт','beddingType':'Две кровати'},'size':20}],'amenityGroups':[]},'reviews':{'total':200,'list':[{'id':1,'reviewType':'OST','reviewPlus':'Чистый номер и тихо ночью, вкусные завтраки каждый день','reviewMinus':'Шум в коридоре утром','rating':8,'reviewDate':'2026-10-01'},{'id':2,'reviewType':'TA','reviewPlus':'Do not import'},{'id':3,'reviewType':'OST','reviewPlus':'Тихо и чисто, подходит для детей','rating':9,'reviewDate':'2026-10-02'}]}}
 return '<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':d}})+'</script>'
def spec(**extra):return TripSpec(**(dict(origin='Москва',destination='Сочи',dates={'start':'2026-11-10','end':'2026-11-15'},travellers={'adults':2},budget_scope='booking',budget={'amount_minor':15000000})|extra))
class ContentTests(unittest.TestCase):
 def test_identity_and_url_boundary(self):
  for url in ['http://ostrovok.ru/hotel/russia/sochi/mid123/a/','https://ostrovok.ru.evil.com/hotel/russia/sochi/mid123/a/','https://ostrovok.ru@127.0.0.1/hotel/russia/sochi/mid123/a/']:self.assertFalse(pc.valid_url(url))
  with self.assertRaises(ValueError):pc.parse_details(page('wrong'),base())
 def test_real_reviews_bounded_excerpts_and_evidence(self):
  h=pc.parse_details(page(),base());self.assertEqual(h['reviews'],200);self.assertEqual(h['review_sample_size'],2);self.assertEqual(h['content']['checkin_from'],'15:00')
  self.assertEqual(h['review_summary']['Тишина']['positive_ids'],['1','3']);self.assertEqual(h['review_summary']['Тишина']['negative_ids'],['1']);self.assertLessEqual(sum(len(r['text'].split()) for r in h['review_items']),24);self.assertNotIn('room_capacity',h['content'])
 def test_cache_preserves_details_and_canonical_repricing(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(pc,'CACHE',Path(directory)):
   h=pc.parse_details(page(),base());pc.remember(h);pc.remember(dict(base(),reference_nightly_minor=500000));saved=pc.recall(h['id']);self.assertEqual(len(saved['review_items']),2);self.assertEqual(saved['reference_nightly_minor'],500000)
   q=journey.reprice(spec(),h['id']);self.assertEqual(q['source_kind'],'public');self.assertEqual(q['journey']['source_kind'],'estimate');self.assertEqual(q['journey']['total_minor'],sum(q['journey']['breakdown'].values()));self.assertTrue(any(c['status']=='unknown' for c in q['journey']['checks']))
 def test_unknown_children_refund_not_success(self):
  h=pc.parse_details(page(),base())
  for s in [spec(travellers={'adults':2,'children':[4]}),spec(hard_constraints={'free_cancellation':True})]:
   hotels,_=select_hotels([h],s)
   self.assertTrue(hotels,'unconfirmed supplier terms must not erase a possible trip')
   self.assertFalse(hotels[0]['journey']['can_book'])
   self.assertTrue(any(c['blocking'] and c['status']=='unknown' for c in hotels[0]['journey']['checks']))
 def test_late_arrival_not_waived(self):
  h=pc.parse_details(page(),base());h['content']['checkin_until']='14:00';self.assertEqual(select_hotels([h],spec(transport_mode='flight'))[0],[])
 def test_transfer_estimate_uses_coordinates(self):
  a=base();b=dict(a,coordinates={'lat':43.45,'lng':39.96});self.assertGreater(transfer_estimate(a,spec())['minutes'],transfer_estimate(b,spec())['minutes'])
class AsyncContentTests(unittest.IsolatedAsyncioTestCase):
 async def test_detail_failure_no_fake_reviews(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(pc,'CACHE',Path(directory)),patch.object(pc,'fetch_page',side_effect=ValueError()):
   h=await pc.enrich(base());self.assertEqual(h['name'],base()['name']);self.assertEqual(h['content_status'],'unavailable');self.assertEqual(h['review_items'],[])
 async def test_distant_dates_show_clearly_labelled_near_term_forecast(self):
  from datetime import datetime,timedelta
  from zoneinfo import ZoneInfo
  from unittest.mock import AsyncMock
  now=datetime.now(ZoneInfo('Europe/Moscow')).date()
  forecast={'kind':'forecast','days':[{'date':str(now),'min':8,'max':12,'condition':'Облачно'}]}
  with patch('travel_agent.trip_context.met_forecast',AsyncMock(return_value=forecast)) as met:
   w=await weather_context(base(),spec(dates={'start':'2027-06-01','end':'2027-06-05'}))
  self.assertEqual(w['kind'],'forecast');self.assertEqual(w['scope'],'upcoming');self.assertIn('На даты поездки прогноза',w['text'])
  self.assertEqual(met.call_args.args[1].dates.start,now);self.assertLessEqual(met.call_args.args[1].dates.end,now+timedelta(days=4))

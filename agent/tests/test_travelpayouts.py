import unittest,copy,os,asyncio,json
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import httpx
from travel_agent import travelpayouts as tp,transport,public_content as pc
from travel_agent.hotel_selection import demo_quote
from test_public_content import spec,base,page
class FlightDataTests(unittest.TestCase):
 def payload(self):return {'success':True,'data':{'AER':{'0':{'price':26920,'departure_at':'2026-11-10T10:20:00+03:00','return_at':'2026-11-15T16:00:00+03:00','expires_at':'2026-11-01T19:00:00Z','duration_to':230,'duration_back':210,'airline':'UT'}}}}
 def test_dates_expiry_and_complete_durations(self):
  s=spec();now=datetime(2026,10,27,tzinfo=timezone.utc);d=self.payload();r=tp.parse(d,s,now);self.assertEqual(r['roundtrip_minor'],2692000);self.assertEqual(r['minutes'],230)
  for key,value in [('departure_at','2026-11-11T10:20:00+03:00'),('expires_at','2026-10-01T00:00:00Z'),('duration_back',None),('price',-1)]:
   invalid=copy.deepcopy(d);invalid['data']['AER']['0'][key]=value;self.assertIsNone(tp.parse(invalid,s,now))
 def test_fare_changes_price_times_and_direct_check(self):
  s=spec(hard_constraints={'no_connections':True});h=base();r=tp.parse(self.payload(),s,datetime(2026,10,27,tzinfo=timezone.utc));r['expires_at']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat();h['air_reference']={tp.key(s):r};j=transport.build(h,s,demo_quote(h,s));self.assertEqual(j['breakdown']['transport'],5384000);self.assertEqual(j['segments'][0]['departure'],'2026-11-10T10:20:00+03:00');self.assertEqual(j['segments'][0]['arrival'],'2026-11-10T14:10:00+03:00');self.assertEqual(next(c for c in j['checks'] if c['code']=='no_connections')['status'],'pass');s.dates.start=s.dates.start+timedelta(days=1);self.assertNotIn('Aviasales',transport.build(h,s,demo_quote(h,s))['transport']['source'])
 def test_auto_compares_stitching_before_rejecting_hotels(self):
  s=spec();h=base();r=tp.parse(self.payload(),s,datetime(2026,10,27,tzinfo=timezone.utc));r['expires_at']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat();r['departure']='2026-11-10T23:30:00+03:00';h['air_reference']={tp.key(s):r};j=transport.build(h,s,demo_quote(h,s));self.assertEqual(j['transport']['kind'],'train');self.assertTrue(j['can_book']);s.transport_mode='flight';self.assertFalse(transport.build(h,s,demo_quote(h,s))['can_book'])
 def test_hotel_transfer_is_real_service_but_not_live_quote(self):
  s=spec(transfer_provider='hotel');h=base();self.assertIsNone(transport.build(h,s,demo_quote(h,s)));h['content']={'transfer_service':{'listed':True,'services':['Трансфер от аэропорта']}};j=transport.build(h,s,demo_quote(h,s));self.assertEqual(j['transfer_choice']['provider'],'hotel');self.assertEqual(j['transfer_choice']['status'],'on_request');self.assertTrue(all(x.get('provider')=='hotel' for x in j['segments'] if x['kind']=='transfer'));self.assertEqual(j['transfer_choice']['source_url'],h['url'])
 def test_public_transfer_metadata(self):
  raw=page().replace('"amenityGroups": []','"amenityGroups": [{"name":"Трансфер","amenities":[{"name":"Трансфер от аэропорта (платный)"}]}]');h=pc.parse_details(raw,base());self.assertTrue(h['content']['transfer_service']['listed']);self.assertEqual(h['content']['transfer_service']['charges'],[])
class ProviderBoundaryTests(unittest.IsolatedAsyncioTestCase):
 async def test_token_only_in_header_and_no_key_is_no_call(self):
  tp._cache.clear();requests=[]
  def handle(req):requests.append(req);return httpx.Response(200,json={'success':True,'data':{}})
  original=httpx.AsyncClient
  with patch.dict(os.environ,{'TRAVELPAYOUTS_TOKEN':'unit-test-not-a-secret'}),patch.object(tp.httpx,'AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
   self.assertIsNone(await tp.prepare(spec()));self.assertEqual(len(requests),1);self.assertEqual(requests[0].headers['X-Access-Token'],'unit-test-not-a-secret');self.assertNotIn('unit-test',str(requests[0].url))
  with patch.dict(os.environ,{'TRAVELPAYOUTS_TOKEN':''}):self.assertIsNone(await tp.prepare(spec()))
 async def test_redirect_follows_same_identity_and_blocks_other_host(self):
  original=httpx.AsyncClient;seen=[]
  def handle(req):
   seen.append(req.url)
   return httpx.Response(301,headers={'location':'https://evil.example/hotel/russia/sochi/mid123/real_hotel/'})
  with patch.object(pc.httpx,'AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handle),**kw)):
   with self.assertRaises(ValueError):await pc.fetch_page(base()['url'])
  self.assertEqual(len(seen),1)
  def valid(req):
   if '/sochi/' in str(req.url):return httpx.Response(301,headers={'location':'/hotel/russia/sirius/mid123/real_hotel/'})
   return httpx.Response(200,text=page())
  with patch.object(pc.httpx,'AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(valid),**kw)):self.assertIn('__NEXT_DATA__',await pc.fetch_page(base()['url']))

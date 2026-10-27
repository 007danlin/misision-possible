"""Real Qwen; fixed catalogue isolates inference and ensures selection comparability."""
import asyncio,json,os,sys,time
from pathlib import Path
from unittest.mock import patch
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from travel_agent.domain import State
from travel_agent.runner import run_turn
from travel_agent.model import QwenModel,Settings
from travel_agent.demo_tools import DemoTools
base={'destination':'Сочи','travellers':{'adults':2,'children':[3,4,5,6,7]},'stay_nights':5,'budget':{'amount_minor':10000000},'budget_scope':'hotel','hotel_preferences':{'pool':True}}
fixtures=[dict(id=str(i),name='Отель '+str(i),reference_nightly_minor=(i+1)*100000,amenity_codes=['has_pool','has_parking','has_pets'],rating=9-i/10,reviews=30,distance_m=700,stars=4,beach_m=800) for i in range(5)]
async def search(s):return fixtures,'https://ostrovok.ru/hotel/russia/sochi/'
CASES=[
 ('family','Хочу в Сочи на пять ночей. Нас двое взрослых и пятеро детей. Бассейн обязателен, на отель выделили сто тысяч рублей.',{}, {'destination':'Сочи','stay_nights':5,'travellers.adults':2,'travellers.children':[None]*5,'hotel_preferences.pool':True,'budget.amount_minor':10000000}),
 ('dates','В Казани нас будет трое взрослых, нужен завтрак и парковка. С 12 по 16 ноября 2026, бюджет 45 тысяч рублей за всё проживание.',{}, {'destination':'Казань','travellers.adults':3,'dates.start':'2026-11-12','dates.end':'2026-11-16','hotel_preferences.breakfast':True,'hotel_preferences.parking':True,'budget.amount_minor':4500000}),
 ('forest','Уедем вдвоём подальше от города, хочется леса и уединения. На семь ночей, максимум 60 тысяч за жильё, с собакой.',{}, {'travel_setting':'forest','travellers.adults':2,'stay_nights':7,'budget.amount_minor':6000000,'hard_constraints.pets':True}),
 ('followup','Лучше поедем в Санкт-Петербург. Остальные пожелания сохрани, только добавь завтрак.',base, {'destination':'Санкт-Петербург','travellers.children':[3,4,5,6,7],'travellers.adults':2,'stay_nights':5,'budget.amount_minor':10000000,'hotel_preferences.pool':True,'hotel_preferences.breakfast':True}),
 ('remove','Бассейн не важен, но парковка обязательна. Остальные условия прежние.',base, {'destination':'Сочи','travellers.children':[3,4,5,6,7],'budget.amount_minor':10000000,'hotel_preferences.pool':None,'hotel_preferences.parking':True}),
 ('night','Давай ограничим бюджет на отель до 20 тысяч рублей за ночь. Состав гостей оставим.',base, {'budget.amount_minor':2000000,'budget_period':'night','travellers.children':[3,4,5,6,7],'hotel_preferences.pool':True}),
 ('shift','Перенеси на два дня позже, гости и условия прежние.',dict(base,dates={'start':'2026-11-10','end':'2026-11-15'}), {'dates.start':'2026-11-12','dates.end':'2026-11-17','travellers.children':[3,4,5,6,7],'budget.amount_minor':10000000,'hotel_preferences.pool':True})]
def field(d,path):
 for k in path.split('.'):d=d.get(k) if isinstance(d,dict) else None
 return d
class BenchModel(QwenModel):
 async def extract(self,context,repair,timeout):
  if repair:print("REPAIR",repair,flush=True)
  raw,usage=await super().extract(context,repair,timeout)
  if os.getenv("BENCH_TRACE"):print("EXTRACT",raw,flush=True)
  return raw,usage
async def main():
 transport_timings=[]
 original_post=httpx.AsyncClient.post
 async def timed_post(client,*args,**kwargs):
  start=time.monotonic();response=await original_post(client,*args,**kwargs)
  body=response.json();timings=body.get('timings',{})
  transport_timings.append({'http_seconds':round(time.monotonic()-start,3),'prompt_ms':timings.get('prompt_ms'),'generation_ms':timings.get('predicted_ms')})
  return response
 mode=os.getenv('HOTEL_COMPACT_WIRE','0');report=[]
 for name,message,spec,expected in CASES:
  if len(sys.argv)>1 and name not in sys.argv[1:]:continue
  transport_timings.clear()
  state=State(search_mode='hotels',trip_spec=spec)
  with patch('travel_agent.ostrovok.search_hotels',side_effect=search),patch.object(httpx.AsyncClient,'post',timed_post):
   t=time.monotonic();r=await run_turn(state,message,DemoTools(),BenchModel(Settings(timeout=180)))
  actual=r.trip_spec.model_dump(mode='json');failures={k:{'expected':v,'actual':field(actual,k)} for k,v in expected.items() if field(actual,k)!=v}
  if r.status=='error':failures['status']=r.error_code
  item={'case':name,'seconds':round(time.monotonic()-t,2),'model_timing':list(transport_timings),'calls':r.telemetry.model_calls,'tokens':r.telemetry.usage,'failures':failures,'spec':actual,'hotel_ids':[h['id'] for h in r.hotel_options]};report.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
  Path('.runtime/latency-'+mode+'.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 assert not any(x['failures'] for x in report),'Semantic regression: see report'
asyncio.run(main())

import asyncio,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from travel_agent.domain import State
from travel_agent.runner import run_turn
from travel_agent.model import QwenModel,Settings
from travel_agent.demo_tools import DemoTools
async def main():
 report=[]
 for msg in ['Уедем вдвоём подальше от города, хочется леса и уединения. На семь ночей, максимум 60 тысяч за жильё, с собакой.','В Казани нас будет трое взрослых, нужен завтрак и парковка. С 12 по 16 ноября 2026, бюджет 45 тысяч рублей за всё проживание.']:
  t=time.monotonic();r=await run_turn(State(search_mode='hotels'),msg,DemoTools(),QwenModel(Settings(timeout=180)))
  entry={'message':msg,'seconds':round(time.monotonic()-t,2),'status':r.status,'spec':r.trip_spec.model_dump(mode='json'),'answer':r.assistant_message,'calls':r.telemetry.model_calls};report.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
 Path('.runtime/bench-hotel-freeform.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 a,b=[x['spec'] for x in report]
 assert a['travel_setting']=='forest' and a['travellers']['adults']==2 and a['stay_nights']==7 and a['budget']['amount_minor']==6000000 and a['hard_constraints']['pets']
 assert b['destination']=='Казань' and b['travellers']['adults']==3 and b['dates']=={'start':'2026-11-12','end':'2026-11-16'} and b['budget']['amount_minor']==4500000 and b['hotel_preferences']['breakfast'] and b['hotel_preferences']['parking'] and b['budget_scope']=='hotel' and report[1]['status']=='choosing'
asyncio.run(main())

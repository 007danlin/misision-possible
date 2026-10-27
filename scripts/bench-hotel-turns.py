import asyncio,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from travel_agent.domain import State
from travel_agent.runner import run_turn
from travel_agent.model import QwenModel,Settings
from travel_agent.demo_tools import DemoTools

async def main():
 model=QwenModel(Settings(timeout=180));state=State(search_mode='hotels');report=[]
 cases=['Планируем семейный отдых в Сочи: двое взрослых и 5 детей. Хотим на пять ночей, уложиться в 100 тысяч рублей за отель. Обязательно нужен бассейн.','3, 4, 5, 6, 7 лет','Найди подешевле, остальные условия сохрани','Почему второй?']
 for msg in cases:
  start=time.monotonic();r=await run_turn(state,msg,DemoTools(),model);elapsed=round(time.monotonic()-start,2)
  data={'message':msg,'elapsed':elapsed,'status':r.status,'spec':r.trip_spec.model_dump(mode='json'),'answer':r.assistant_message,'telemetry':r.telemetry.model_dump(),'hotel_count':len(r.hotel_options)};report.append(data);print(json.dumps(data,ensure_ascii=False),flush=True)
  if r.status=='error':break
  assert len(r.trip_spec.travellers.children)==5
  if msg==cases[0]:assert r.trip_spec.travellers.adults==2 and r.trip_spec.stay_nights==5 and r.trip_spec.budget.amount_minor==10000000 and r.trip_spec.hotel_preferences.pool
  state=State(search_mode='hotels',revision=state.revision+1,trip_spec=r.trip_spec,hotel_options=r.hotel_options,assistant_message=r.assistant_message,questions=r.questions,search_url=r.search_url,selection=r.selection)
 Path('.runtime/bench-hotel-turns.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
asyncio.run(main())

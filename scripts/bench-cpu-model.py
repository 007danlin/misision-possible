"""Measure the real configured inference server; no travel-source calls or shortcuts."""
import asyncio,json,os,sys,time,argparse,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from travel_agent.model import QwenModel,Settings
from dataclasses import replace

async def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--timeout',type=float,default=300);p.add_argument('--repeat',type=int,default=1);p.add_argument('--limit',type=int,default=3);args=p.parse_args()
 import travel_agent.model
 hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(travel_agent.model.__file__).parent.glob('*.py')}
 model=QwenModel(replace(Settings.from_env(),timeout=args.timeout));rows=[];out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
 cases=[('initial','Из Москвы в Сочи с 10 по 15 ноября 2026 года, двое взрослых. 150 тысяч рублей на отель, дорогу и оба трансфера. Нужен бассейн.'),('change','Отель оставь, но лучше поездом. Без ночных переездов.'),('complex','Бассейн больше не обязателен, зато нужны завтрак и парковка. Бюджет 90 тысяч рублей на всю поездку, остальные условия сохрани.')]
 for cycle in range(args.repeat):
  for label,message in cases[:args.limit]:
   context={'today':'2026-10-27','search_mode':'hotels','trip_spec':{},'message':message,'history':[],'last_assistant_message':'','last_questions':[],'displayed_hotels':[]};start=time.monotonic();row={'source_hashes':hashes,'label':label,'cycle':cycle,'model':model.settings.model,'endpoint':model.settings.base_url,'compact_wire':os.getenv('HOTEL_COMPACT_WIRE','0')}
   try:row['output'],row['usage']=await model.extract(context,None,args.timeout)
   except Exception as e:row['error']=str(e)
   row['seconds']=round(time.monotonic()-start,3);rows.append(row);out.write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps(row,ensure_ascii=False),flush=True)
asyncio.run(main())

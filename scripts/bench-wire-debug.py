import asyncio,sys,os,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
import httpx
from travel_agent.domain import State
from travel_agent.runner import run_turn
from travel_agent.model import QwenModel,Settings
from travel_agent.demo_tools import DemoTools
original=httpx.AsyncClient.post
async def traced(self,*args,**kwargs):
 r=await original(self,*args,**kwargs)
 if 'chat/completions' in str(args[0]):
  body=r.json();print('RAW',body.get('choices',[{}])[0].get('message'),body.get('timings'),flush=True)
 return r
httpx.AsyncClient.post=traced
class Debug(QwenModel):
 async def extract(self,context,repair,timeout):
  if repair:print('REPAIR',repair,flush=True)
  return await super().extract(context,repair,timeout)
async def main():
 msg='Хочется провести семь ночей в лесу с собакой, нас двое, до 60 тысяч рублей на проживание. Важна тишина.'
 r=await run_turn(State(search_mode='hotels'),msg,DemoTools(),Debug(Settings(timeout=180)))
 print(r.model_dump_json())
asyncio.run(main())

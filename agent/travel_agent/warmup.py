"""Prefill stable hotel instructions; no result is saved as a user answer."""
import asyncio,json,time
from datetime import datetime
from zoneinfo import ZoneInfo
from .model import QwenModel,Settings
async def warmup():
    model=QwenModel(Settings.from_env())
    context={'today':datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat(),'search_mode':'hotels','trip_spec':{},'message':'Начать поиск','last_assistant_message':'','last_questions':[],'displayed_hotels':[]}
    started=time.monotonic()
    _,usage=await model.extract(context,None,model.settings.timeout,prefill=True)
    print(json.dumps({'warmup':'ready','seconds':round(time.monotonic()-started,3),'usage':usage}),flush=True)
if __name__=='__main__':asyncio.run(warmup())

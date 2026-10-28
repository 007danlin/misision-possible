"""Exercise production run_turn with real Qwen and fixed supplier fixtures.

Every reply is checked for semantic changes, preserved fields, a useful question
and immutable input. Outputs are saved after each turn and can be replayed.
"""
import argparse, asyncio, copy, hashlib, json, os, re, sys, time
from contextlib import ExitStack
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[os.environ.get('EVAL_AGENT_PATH',str(ROOT/'agent')),str(ROOT/'agent/evals')]
os.environ.setdefault('HOTEL_COMPACT_WIRE','1')
from dialogue_cases_20261028 import CASES
from travel_agent.domain import State
from travel_agent.demo_tools import DemoTools
from travel_agent.model import QwenModel,Settings,PROMPT_VERSION
from travel_agent.runner import run_turn


def get(value,path):
    for key in path.split('.'):
        if not isinstance(value,dict): return None
        value=value.get(key)
    return value

def leaves(value,prefix=''):
    if isinstance(value,dict) and value:
        return {p:v for k,x in value.items() for p,v in leaves(x,prefix+'.'+k if prefix else k).items()}
    return {prefix:value}

def hashes():
    return {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(sys.modules['travel_agent.runner'].__file__).parent.glob('*.py')}

class RecordedModel(QwenModel):
    def __init__(self,timeout,replay=None):
        super().__init__(replace(Settings.from_env(),timeout=timeout))
        self.calls=[];self.replay=iter(replay) if replay is not None else None
    async def extract(self,context,repair,timeout,**kwargs):
        if self.replay is None:
            raw,usage=await super().extract(context,repair,timeout,**kwargs)
        else:
            item=next(self.replay);raw,usage=item['raw'],item.get('usage',{})
        self.calls.append({'raw':raw,'usage':usage,'mode':context.get('search_mode'),'repair':repair})
        return raw,usage


def fixtures(stack):
    saved={}
    async def search(spec):
        hotels=[]
        for i in range(1,10):
            h=dict(id=f'fixture-{spec.destination}-{i}',name=f'Проверочный отель {i}',source_kind='public',destination=spec.destination,
                url='https://ostrovok.ru/hotel/russia/sochi/mid123/fixture/',coordinates={'lat':43.6,'lng':39.7},reference_nightly_minor=100000+i*10000,
                amenity_codes=['has_pool','has_parking','has_fitness','has_spa','has_pets'],rating=9,stars=5,distance_m=300,beach_m=300,reviews=2,
                content={'checkin_from':'14:00','checkin_until':'23:59','checkout_until':'12:00'},images=[],amenities=[],review_items=[{'id':'r1','text':'Тихо и чисто','theme':'Тишина'}],review_summary={})
            saved[h['id']]=copy.deepcopy(h)
            hotels.append(h)
        return hotels,'https://ostrovok.ru/hotel/russia/sochi/'
    stack.enter_context(patch.dict(os.environ,{'JOURNEY_DATA_SOURCE':'public'}))
    stack.enter_context(patch('travel_agent.ostrovok.search_hotels',AsyncMock(side_effect=search)))
    stack.enter_context(patch('travel_agent.public_content.enrich',AsyncMock(side_effect=lambda h:h)))
    stack.enter_context(patch('travel_agent.public_content.remember',side_effect=lambda h:saved.update({h['id']:copy.deepcopy(h)})))
    stack.enter_context(patch('travel_agent.public_content.recall',side_effect=lambda ident:copy.deepcopy(saved.get(ident))))
    stack.enter_context(patch('travel_agent.trip_context.weather_context',AsyncMock(return_value={'kind':'seasonal','text':'Проверочная погода'})))
    for target in ['travel_agent.transport.prepare_road','travel_agent.tutu.prepare','travel_agent.travelpayouts.prepare']:
        stack.enter_context(patch(target,AsyncMock(return_value=None)))

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('cases',nargs='*');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--timeout',type=float,default=60);parser.add_argument('--replay',type=Path);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    source=hashes();rows=[];previous=json.loads(args.replay.read_text()) if args.replay else []
    replay={(r['case'],r['step']):r.get('model_outputs',[]) for r in previous}
    def save():
        (args.output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        summary={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'cases':len(set(r['case'] for r in rows)),'turns':len(rows),'passed':sum(r['passed'] for r in rows),'failed':[f"{r['case']}:{r['step']}" for r in rows if not r['passed']], 'model_calls':sum(r.get('telemetry',{}).get('model_calls',0) for r in rows),'mode':'recorded outputs' if args.replay else 'real local Qwen3.5-9B; supplier and weather fixtures','prompt_version':PROMPT_VERSION,'source_hashes':source,'source_files_unchanged':source==hashes()}
        (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    with ExitStack() as stack:
        fixtures(stack)
        for case in CASES:
            if args.cases and case['id'] not in args.cases: continue
            state=State(search_mode='hotels',trip_spec=copy.deepcopy(case['initial']),assistant_message=case['assistant'],questions=case['questions'])
            for i,item in enumerate(case['steps'],1):
                key=(case['id'],i)
                if args.replay and key not in replay: continue
                model=RecordedModel(args.timeout,replay.get(key) if args.replay else None)
                start=time.monotonic();before=state.model_dump_json();old=state.trip_spec.model_dump(mode='json');errors=[]
                row={'case':case['id'],'step':i,'message':item['message'],'expected':item,'before_spec':old}
                try:
                    turn=await run_turn(state,item['message'],DemoTools(),model,timeout=args.timeout)
                    data=turn.model_dump(mode='json');new=data['trip_spec'];row.update(data)
                    if turn.status=='error':errors.append('agent error: '+str(turn.error_code))
                    if state.model_dump_json()!=before:errors.append('input state mutated')
                    for p,want in item['expected'].items():
                        if get(new,p)!=want:errors.append(f'{p}: expected {want!r}, got {get(new,p)!r}')
                    allowed=set(item['expected'])|set(item['allow'])
                    # Currency is fixed by the RUB-only domain, not a user edit.
                    for money_field in ('budget','hotel_budget','trip_budget','expense_reserve'):
                        if any(p.startswith(money_field+'.') for p in item['expected']):
                            allowed.add(money_field+'.currency')
                    oldleaves,newleaves=leaves(old),leaves(new)
                    for p in oldleaves.keys()|newleaves.keys():
                        if any(p==a or p.startswith(a+'.') or a.startswith(p+'.') for a in allowed):continue
                        if oldleaves.get(p)!=newleaves.get(p):errors.append(f'unexpected change {p}: {oldleaves.get(p)!r} → {newleaves.get(p)!r}')
                    if item['status'] and turn.status!=item['status']:errors.append(f"status: expected {item['status']}, got {turn.status}")
                    if item['question'] and (not turn.questions or not re.search(item['question'],' '.join(turn.questions),re.I)):errors.append('missing useful question')
                    if item['contains'] and item['contains'] not in turn.assistant_message:errors.append('answer lost requested hotel: '+item['contains'])
                    if not turn.assistant_message.strip():errors.append('empty assistant reply')
                    if turn.status!='error':
                        state=State(search_mode='hotels',revision=state.revision+1,trip_spec=turn.trip_spec,history=(state.history+[item['message']])[-10:],hotel_options=turn.hotel_options,assistant_message=turn.assistant_message,questions=turn.questions,search_url=turn.search_url,selection=turn.selection)
                except Exception as e:errors.append(f'{type(e).__name__}: {e}')
                row.update(seconds=round(time.monotonic()-start,2),passed=not errors,errors=errors,model_outputs=model.calls)
                rows.append(row);save();print(json.dumps({k:row[k] for k in ('case','step','passed','seconds','errors')},ensure_ascii=False),flush=True)
    save()
    print(json.dumps({'turns':len(rows),'passed':sum(r['passed'] for r in rows),'failed':sum(not r['passed'] for r in rows)},ensure_ascii=False),flush=True)
    if any(not row['passed'] for row in rows):
        raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())

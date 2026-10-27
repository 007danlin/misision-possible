"""Run real Qwen extraction over a fixed corpus; persist every result immediately."""
import asyncio,json,os,sys,time,argparse,statistics,hashlib
from dataclasses import replace
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'agent'));sys.path.insert(0,str(root/'agent/evals'));os.environ.setdefault('HOTEL_COMPACT_WIRE','1')
from language_cases_20261027 import CASES
from travel_agent.domain import TripSpec,Intent,apply_intent
from travel_agent.model import QwenModel,Settings,canonical_intent,PROMPT_VERSION,ModelError
from travel_agent.fast_intent import protect_child_count,protect_stay_length,protect_adult_count,protect_explicit_forest,protect_hotel_budget_scope,protect_explicit_polarity,clarify_ambiguous_request,protect_hotel_question,protect_journey_language
BASE=TripSpec(origin='Москва',destination='Сочи',include_transport=True,dates={'start':'2026-11-10','end':'2026-11-15'},travellers={'adults':2},budget={'amount_minor':12000000},budget_scope='booking',hotel_preferences={'pool':True},hard_constraints={'no_night_flights':True})
def get(d,path):
 for key in path.split('.'):
  if not isinstance(d,dict):return None
  d=d.get(key)
 return d
def source_hashes():
 import travel_agent.model,travel_agent.compact_wire,travel_agent.fast_intent,travel_agent.domain
 return {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(travel_agent.model.__file__).parent.glob('*.py')}

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('cases',nargs='*');parser.add_argument('--output',type=Path,default=root/'.runtime/evals/language');parser.add_argument('--timeout',type=float,default=90);parser.add_argument('--environment',default='configured inference endpoint');args=parser.parse_args()
 hashes=source_hashes()
 out=args.output;out.mkdir(parents=True,exist_ok=True);results=[];model=QwenModel(replace(Settings.from_env(),timeout=args.timeout));selected=set(args.cases);cases=[c for c in CASES if not selected or c['id'] in selected]
 for c in cases:
  old=TripSpec() if c['empty'] else BASE.model_copy(deep=True);message=c['message'];context={'today':'2026-10-27','search_mode':'hotels','trip_spec':old.model_dump(mode='json',exclude_defaults=True),'message':message,'history':[],'last_assistant_message':'Показал три варианта. Что изменим?','last_questions':[],'displayed_hotels':[{'position':i+1,'name':n} for i,n in enumerate(['Отель Первый','Отель Второй','Отель Третий'])]};start=time.monotonic();row={'id':c['id'],'group':c['group'],'message':message};errors=[];repair=None;calls=[]
  try:
   for attempt in range(2):
    call_start=time.monotonic()
    remaining=args.timeout-(time.monotonic()-start)
    if remaining<=0:raise ModelError('model_timeout')
    raw,usage=await model.extract(context,repair,remaining)
    calls.append({'seconds':round(time.monotonic()-call_start,3),'usage':usage,'raw_output':raw})
    try:
     row["raw_model_output"]=raw;intent=clarify_ambiguous_request(message) or Intent.model_validate_json(canonical_intent(raw,message));intent=protect_child_count(intent,message,old);intent=protect_stay_length(intent,message,old);intent=protect_adult_count(intent,message);intent=protect_explicit_forest(intent,message);intent=protect_hotel_budget_scope(intent,message);intent=protect_journey_language(protect_hotel_question(protect_explicit_polarity(intent,message),message),message);new=apply_intent(old,intent,message);break
    except Exception as e:
     calls[-1]['validation_error']=str(e)[:2000]
     if attempt:raise
     repair={'validation_error':str(e)[:800],'previous_output':raw[:5000]}
   row.update(intent=intent.model_dump(mode='json',exclude_defaults=True),spec=new.model_dump(mode='json'),model_calls=attempt+1,usage=usage)
   for path,want in c['expected'].items():
    got=get(row['spec'],path)
    if got!=want:errors.append(f'{path}: expected {want!r}, got {got!r}')
   for path,want in c['intent'].items():
    got=get(intent.model_dump(mode='json'),path)
    if got!=want:errors.append(f'intent.{path}: expected {want!r}, got {got!r}')
   if c['ask'] and not intent.questions:errors.append('clarification required')
   if c['preserve']:
    for path in ['origin','destination','dates','budget','travellers']:
     if path not in c['expected'] and not any(x.startswith(path+'.') for x in c['expected']) and get(row['spec'],path)!=get(old.model_dump(mode='json'),path):errors.append('unexpected change: '+path)
   if c['group']=='injection' and new!=old:errors.append('untrusted instruction changed trip')
   if c['group']=='unverified' and not (new.preferences or new.hard_constraints.other or intent.questions):errors.append('unsupported requirement lost')
  except Exception as e:row['error']=str(e);errors.append(type(e).__name__)
  row['model_attempts']=calls
  row.update(seconds=round(time.monotonic()-start,2),passed=not errors,errors=errors);results.append(row);(out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps({'id':row['id'],'passed':row['passed'],'seconds':row['seconds'],'errors':errors},ensure_ascii=False),flush=True)
 (out/'summary.json').write_text(json.dumps({'source_hashes':hashes,'source_files_unchanged':hashes==source_hashes(),'cases':len(results),'passed':sum(r['passed'] for r in results),'failed':[r['id'] for r in results if not r['passed']],'environment':args.environment,'endpoint':model.settings.base_url,'model':model.settings.model,'compact_wire':os.getenv('HOTEL_COMPACT_WIRE'),'timeout_seconds':args.timeout,'latency_seconds':{'median':statistics.median(r['seconds'] for r in results),'p95':sorted(r['seconds'] for r in results)[max(0,int(len(results)*.95)-1)],'max':max(r['seconds'] for r in results)},'prompt_version':PROMPT_VERSION},ensure_ascii=False,indent=2))
asyncio.run(main())

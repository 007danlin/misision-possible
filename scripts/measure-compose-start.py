"""Time Compose build/start and health milestones without logging configuration secrets."""
import argparse,json,subprocess,time,urllib.request,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--url',default='http://127.0.0.1:8080/health');p.add_argument('--project');p.add_argument('--override',action='append',default=[]);p.add_argument('--model-only',action='store_true');p.add_argument('--build',action='store_true');a=p.parse_args()
secret=Path('.runtime/secrets/travelpayouts.env')
if secret.exists() and not os.getenv('TRAVELPAYOUTS_TOKEN'):
 for line in secret.read_text().splitlines():
  if line.startswith('TRAVELPAYOUTS_TOKEN='):os.environ['TRAVELPAYOUTS_TOKEN']=line.split('=',1)[1].strip()
cmd=['docker','compose','-f','docker-compose.yml']
for f in a.override:cmd+=['-f',f]
if a.project:cmd+=['-p',a.project]
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);row={'milestones_seconds':{},'build_requested':a.build,'project':a.project or 'odin-request'};start=time.monotonic()
with out.with_suffix('.log').open('w') as log:
 up=subprocess.Popen(cmd+['up','-d']+(['--build'] if a.build else [])+(['model'] if a.model_only else []),stdout=log,stderr=subprocess.STDOUT)
 while time.monotonic()-start<900:
  status=up.poll()
  if status is not None and 'exit_code' not in row:
   row['compose_up_seconds']=round(time.monotonic()-start,3);row['exit_code']=status
  if status not in (None,0):break
  raw=subprocess.run(cmd+['ps','--format','json'],capture_output=True,text=True)
  for line in raw.stdout.splitlines():
   item=json.loads(line);key=item['Service']
   if item.get('Health')=='healthy':row['milestones_seconds'].setdefault(key,round(time.monotonic()-start,3))
  try:
   with urllib.request.urlopen(a.url,timeout=2) as response:
    if response.status==200:
     row.setdefault('http_available_seconds',round(time.monotonic()-start,3))
     required={'model'} if a.model_only else {'model','agent','app'}
     if status==0 and required.issubset(row['milestones_seconds']):row['ready_seconds']=round(time.monotonic()-start,3);break
  except Exception:pass
  time.sleep(1)
 if up.poll() is None:up.terminate();up.wait(timeout=10)
 row['success']='ready_seconds' in row;out.write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row),flush=True)
 if not row['success']:raise SystemExit(1)

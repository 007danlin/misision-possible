"""Record Compose build, early progress UI and inference readiness without secrets.

Run from the repository root. Supply an unused project for an empty-volume run;
--reuse records restart milestones without deleting the model cache.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--project', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--url', default='http://127.0.0.1:8080')
p.add_argument('--override', action='append', default=[])
p.add_argument('--timeout', type=int, default=1800)
p.add_argument('--reuse', action='store_true')
p.add_argument('--no-build', action='store_true')
a = p.parse_args()
cmd = ['docker', 'compose', '--env-file', '/dev/null', '-p', a.project, '-f', 'docker-compose.yml']
for override in a.override:
    cmd += ['-f', override]
# Explicitly test repository defaults; do not silently inherit the developer's
# host inference endpoint or optional API credentials.
env = {k: v for k, v in os.environ.items() if not k.startswith(('LLM_', 'MODEL_', 'AGENT_', 'JOURNEY_DATA_', 'TRAVELPAYOUTS_', 'DOCKER_DEFAULT_PLATFORM', 'COMPOSE_'))}
existing = subprocess.run(['docker','volume','ls','-q','--filter', 'label=com.docker.compose.project='+a.project], capture_output=True, text=True, check=True).stdout.strip()
if existing and not a.reuse:
    raise SystemExit('Project already has volumes. Use a new project or --reuse; nothing was deleted.')
a.output.parent.mkdir(parents=True, exist_ok=True)
report = {'project': a.project, 'empty_project_volumes': not bool(existing), 'build_requested': not a.no_build, 'milestones_seconds': {}, 'phases': [], 'ready': False, 'success': False, 'builder': env.get('BUILDX_BUILDER', 'default')}
report['source_sha256'] = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
    'docker-compose.yml', 'infra/model/start.py', 'infra/model/Dockerfile',
    'agent/travel_agent/model.py', 'agent/travel_agent/compact_wire.py',
    'agent/travel_agent/warmup.py', 'agent/bootstrap.py', 'agent/Dockerfile',
    'backend/core/startup.go', 'backend/core/main.go', 'backend/core/web/startup.html')}
configuration = json.loads(subprocess.run(cmd+['config','--format','json'], env=env, capture_output=True, text=True, check=True).stdout)
report['limits'] = {name: {key: service.get(key) for key in ('cpuset','mem_limit','memswap_limit')} for name,service in configuration['services'].items()}
model_mount = next(v for v in configuration['services']['model']['volumes'] if v['target']=='/models')
assert model_mount['type']=='volume', 'Use a named volume, not host weights'
model_volume = configuration['volumes'][model_mount['source']]
assert not model_volume.get('external'), 'External cached weights are excluded from a cold check'
volume_name = model_volume['name']
found = subprocess.run(['docker','volume','inspect',volume_name], capture_output=True, text=True).returncode==0
if found and not a.reuse:
    raise SystemExit('The resolved model volume already exists; refusing to report a cold download')
report['model_volume_initially_absent'] = not found
lock_path = configuration['services']['model']['build'].get('args',{}).get('MODEL_LOCK','docs/local-runtime.json')
lock = json.loads(Path(lock_path).read_text())
report['model_lock'] = {key:lock.get(key) for key in ('base_model','alias','model_revision','model_files')}
agent_env = configuration['services']['agent']['environment']
assert agent_env['LLM_PROVIDER'] == 'llama_cpp', 'Cold check must use local inference'
assert agent_env['LLM_BASE_URL'] == 'http://model:8082/v1', 'Host inference is excluded from this check'
assert not agent_env.get('LLM_API_KEY'), 'Cold check must not depend on an API key'
assert agent_env['LLM_MODEL'] == lock['alias'], 'Configured model alias differs from the pinned weights'
resource_tool = Path('scripts/cpu-resources.py')
def resources(suffix):
    if resource_tool.exists():
        subprocess.run([sys.executable, str(resource_tool), '--container', a.project+'-model-1', '--output', str(a.output.with_suffix('.'+suffix+'.json'))], check=True)
resources('resources-before')
info = subprocess.run(['docker','info','--format','{{json .}}'], capture_output=True, text=True, check=True)
info = json.loads(info.stdout)
report['docker'] = {key: info.get(key) for key in ('Architecture','NCPU','MemTotal','ServerVersion','OperatingSystem')}
started = time.monotonic()
last_phase, last_status = None, 0
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def elapsed():
    return round(time.monotonic()-started, 3)
def read(route):
    try:
        with client.open(a.url.rstrip('/')+route, timeout=3) as response:
            return response.status, response.read(64*1024)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, b''
def save():
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
log_path = a.output.with_suffix('.log')
with log_path.open('w') as log, a.output.with_suffix('.progress.jsonl').open('w') as progress:
    up = subprocess.Popen(cmd+['up','-d']+([] if a.no_build else ['--build']), env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        while time.monotonic()-started < a.timeout:
            code = up.poll()
            if code is not None:
                report.setdefault('compose_exit_code', code)
                report['milestones_seconds'].setdefault('compose_up_finished', elapsed())
                if code:
                    report['failure']='compose_up_failed'
                    break
            status, content = read('/health')
            if status == 200:
                report['milestones_seconds'].setdefault('web_process', elapsed())
            status, content = read('/api/runtime/status')
            if status == 200:
                state = json.loads(content)
                row = {'seconds': elapsed(), **state}
                progress.write(json.dumps(row, ensure_ascii=False)+'\n')
                progress.flush()
                if last_phase != state['phase']:
                    last_phase = state['phase']
                    report['phases'].append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                if 'startup_page' not in report['milestones_seconds']:
                    page_status, page = read('/')
                    if page_status == 200 and 'Готовим помощника'.encode() in page:
                        report['milestones_seconds']['startup_page'] = elapsed()
                if state.get('ready'):
                    ready_status, _ = read('/ready')
                    if ready_status == 200:
                        report['ready'] = True
                        report['milestones_seconds'].setdefault('ready', elapsed())
            if time.monotonic()-last_status >= 10:
                raw = subprocess.run(cmd+['ps','--all','--format','json'], env=env, capture_output=True, text=True)
                rows = [json.loads(line) for line in raw.stdout.splitlines() if line.strip()]
                report['services'] = [{k:r.get(k) for k in ('Service','State','Health','ExitCode')} for r in rows]
                for item in rows:
                    if item.get('Health')=='healthy':
                        report['milestones_seconds'].setdefault(item['Service']+'_healthy', elapsed())
                last_status = time.monotonic()
                save()
            services = report.get('services', [])
            if report['ready'] and code == 0 and len(services) == 3 and all(s.get('Health') == 'healthy' for s in services):
                report['success'] = True
                break
            time.sleep(1)
    finally:
        if up.poll() is None:
            up.terminate()
            try:
                up.wait(timeout=10)
            except subprocess.TimeoutExpired:
                up.kill()
                up.wait()
        if not report['success']:
            report.setdefault('failure', 'startup_timeout')
        report['total_seconds'] = elapsed()
        save()
        with a.output.with_suffix('.services.log').open('w') as logs:
            subprocess.run(cmd+['logs','--no-color'], env=env, stdout=logs, stderr=subprocess.STDOUT)
resources('resources-after')
print(json.dumps(report, ensure_ascii=False), flush=True)
raise SystemExit(0 if report['success'] else 1)

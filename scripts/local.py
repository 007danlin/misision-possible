#!/usr/bin/env python3
"""Project-local launcher. No shared Ollama, global model cache or Docker services."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
PID_FILE = RUNTIME / 'processes.json'
LOCK = json.loads((ROOT / 'docs/local-runtime.json').read_text())
MODEL = RUNTIME / 'models' / LOCK['model_directory'] / LOCK['model_entry']
ENGINE = RUNTIME / 'inference/llama-b11853/llama-server'
PYTHON = ROOT / 'agent/.venv/bin/python'


def running(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def fingerprint(pid):
    try:
        command = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True).strip()
        started = subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart='], text=True).strip()
        return {'command': command, 'started': started}
    except subprocess.CalledProcessError:
        return None


def owned(info):
    current = fingerprint(info['pid']) if running(info['pid']) else None
    if not current or current['started'] != info.get('fingerprint', {}).get('started'):
        return False
    # macOS Python may exec its framework binary after Popen returns; birth time
    # and working directory stay stable, unlike argv[0].
    try:
        cwd = subprocess.check_output(['lsof', '-a', '-p', str(info['pid']), '-d', 'cwd', '-Fn'], text=True)
    except subprocess.CalledProcessError:
        return False
    return 'n' + info['cwd'] in cwd.splitlines()


def save(data):
    temp = PID_FILE.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2)+'\n')
    temp.replace(PID_FILE)


def wait_http(url, timeout=180):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(.5)
    raise RuntimeError(f'Not ready: {url}; inspect .runtime/logs/')


def start(without_model=False):
    for directory in ('logs', 'data/trips', 'bin', 'cache/go-build', 'cache/go-mod', 'tmp'):
        (RUNTIME / directory).mkdir(parents=True, exist_ok=True)
    processes = json.loads(PID_FILE.read_text()) if PID_FILE.exists() else {}
    env = os.environ.copy()
    env.update({
        'LLM_PROVIDER': 'llama_cpp', 'LLM_BASE_URL': 'http://127.0.0.1:18082/v1',
        'LLM_MODEL': LOCK['alias'], 'LLM_API_KEY': '',
        'HOTEL_COMPACT_WIRE': os.environ.get('HOTEL_COMPACT_WIRE', '1'),
        'AGENT_TOOLS_MODE': 'demo', 'AGENT_PORT': '15051', 'AGENT_BIND_HOST': '127.0.0.1',
        'AGENT_TURN_TIMEOUT_SECONDS': os.environ.get('AGENT_TURN_TIMEOUT_SECONDS', '180'), 'AGENT_HOST': '127.0.0.1',
        'PORT': '18080', 'LOCAL_DEMO_MODE': 'true',
        'LOCAL_WEB_DIR': str(ROOT / 'backend/core/web'),
        'TRIP_DATA_DIR': str(RUNTIME / 'data/trips'),
        'PYTHONDONTWRITEBYTECODE': '1',
        'XDG_CACHE_HOME': str(RUNTIME / 'cache'), 'TMPDIR': str(RUNTIME / 'tmp'),
    })
    token_file = RUNTIME / 'secrets/travelpayouts.env'
    if token_file.exists():
        for line in token_file.read_text().splitlines():
            if line.startswith('TRAVELPAYOUTS_TOKEN=') and not env.get('TRAVELPAYOUTS_TOKEN'):
                env['TRAVELPAYOUTS_TOKEN'] = line.split('=', 1)[1].strip()
    def launch(name, command, cwd):
        old = processes.get(name, {})
        if old and owned(old):
            print(f'{name}: already running (PID {old["pid"]})', flush=True)
            return False
        port = {'qwen': 18082, 'agent': 15051, 'core': 18080}[name]
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError as error:
                raise RuntimeError(f'Port {port} is occupied by another process; it was left untouched') from error
        log = (RUNTIME / 'logs' / (name+'.log')).open('ab')
        child = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        log.close()
        processes[name] = {'pid': child.pid, 'command': [str(x) for x in command], 'cwd': str(cwd), 'fingerprint': fingerprint(child.pid)}
        save(processes)
        print(f'{name}: PID {child.pid}', flush=True)
        return True
    model_started = False
    if not without_model:
        if not ENGINE.exists() or not MODEL.exists():
            raise RuntimeError('Project-local runtime/model missing; see docs/local-setup.md')
        model_started = launch('qwen', [str(ENGINE), '-m', str(MODEL), '--host', '127.0.0.1', '--port', '18082',
                        '--ctx-size', '8192', '--parallel', '1', '--n-gpu-layers', '99',
                        '--alias', LOCK['alias'], '--jinja', '--chat-template-kwargs', '{"enable_thinking":false}',
                        '--reasoning-budget', '0', '--spec-type', 'none',
                        '--checkpoint-min-step', '64', '--ubatch-size', '128', '--ctx-checkpoints', '8', '--cache-ram', '1024'], ROOT)
        print('Loading Qwen into memory (once at startup)…', flush=True)
        wait_http('http://127.0.0.1:18082/health')
    if not PYTHON.exists():
        raise RuntimeError('agent/.venv missing; see docs/local-setup.md')
    agent_started = launch('agent', [str(PYTHON), 'main.py'], ROOT / 'agent')
    if not without_model and (model_started or agent_started):
        print('Preparing hotel-search instructions…', flush=True)
        try:
            with (RUNTIME / 'logs/warmup.log').open('ab') as log:
                warmed = subprocess.run([str(PYTHON), '-m', 'travel_agent.warmup'],
                    cwd=ROOT / 'agent', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=65)
            if warmed.returncode:
                print('Instruction warmup unavailable; first request may take longer (logs/warmup.log).', flush=True)
        except subprocess.TimeoutExpired:
            print('Instruction warmup timed out; services remain available.', flush=True)
    core = RUNTIME / 'bin/core'
    if not core.exists():
        raise RuntimeError('Build .runtime/bin/core first; see docs/local-setup.md')
    launch('core', [str(core)], ROOT / 'backend/core')
    wait_http('http://127.0.0.1:18080/health', timeout=20)
    print('Ready: http://127.0.0.1:18080' + (' (model deliberately not started)' if without_model else ''), flush=True)


def stop():
    processes = json.loads(PID_FILE.read_text()) if PID_FILE.exists() else {}
    for name in ('core', 'agent', 'qwen'):
        info = processes.get(name)
        if not info or not running(info['pid']):
            continue
        # Never stop an unrelated process if a saved PID was recycled.
        if not owned(info):
            print(f'{name}: PID changed ownership, left untouched', flush=True)
            continue
        os.kill(info['pid'], signal.SIGTERM)
        deadline = time.monotonic() + 10
        while running(info['pid']) and time.monotonic() < deadline:
            time.sleep(.1)
        if running(info['pid']):
            raise RuntimeError(f'{name} has not stopped yet; PID record retained')
        print(f'{name}: stopped PID {info["pid"]}', flush=True)
    if PID_FILE.exists():
        PID_FILE.unlink()


def status():
    processes = json.loads(PID_FILE.read_text()) if PID_FILE.exists() else {}
    for name, info in processes.items():
        print(f'{name}: {"running" if running(info["pid"]) else "stopped"}, PID {info["pid"]}')
    print('Data:', RUNTIME / 'data/trips')
    print('Model:', MODEL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--without-model', action='store_true', help='UI/state testing without local AI load')
    args = parser.parse_args()
    try:
        {'start': lambda: start(args.without_model), 'stop': stop, 'status': status}[args.action]()
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""Install project-scoped dependencies, pinned inference runtime and model."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
LOCK = json.loads((ROOT / 'docs/local-runtime.json').read_text())


def download(url, target, expected_hash=None):
    if target.exists() and (not expected_hash or hashlib.file_digest(target.open('rb'), 'sha256').hexdigest() == expected_hash):
        print('Exists:', target.name, flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.part')
    print('Downloading:', target.name, flush=True)
    with urllib.request.urlopen(url, timeout=60) as source, partial.open('wb') as output:
        while chunk := source.read(1024 * 1024):
            output.write(chunk)
    if expected_hash and hashlib.file_digest(partial.open('rb'), 'sha256').hexdigest() != expected_hash:
        raise RuntimeError('Checksum mismatch: ' + str(partial))
    partial.replace(target)


def main():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('This local launcher targets Apple Silicon. Use the backend Compose on other platforms and configure an inference endpoint.')
    if sys.version_info < (3, 12):
        raise RuntimeError('Python 3.12+ is required')
    archive = RUNTIME / 'inference/llama-b11853-macos-arm64.tar.gz'
    download('https://github.com/ggml-org/llama.cpp/releases/download/b11853/' + LOCK['runtime_asset'], archive, LOCK['runtime_sha256'])
    engine = archive.parent / 'llama-b11853/llama-server'
    if not engine.exists():
        with tarfile.open(archive) as source:
            source.extractall(archive.parent, filter='data')
    download('https://raw.githubusercontent.com/ggml-org/llama.cpp/b11853/LICENSE', engine.parent / 'LICENSE')
    model_dir = RUNTIME / 'models' / LOCK['model_directory']
    for model_file in LOCK['model_files']:
        download('https://huggingface.co/' + LOCK['quantization_repository'] + '/resolve/' + LOCK.get('model_revision', 'main') + '/' + model_file['file'],
                 model_dir / model_file['file'], model_file['sha256'])
    download('https://huggingface.co/' + LOCK['base_model'] + '/raw/main/LICENSE', model_dir / 'LICENSE')
    python = ROOT / 'agent/.venv/bin/python'
    if not python.exists():
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / 'agent/.venv')], check=True)
    import os
    env = os.environ.copy()
    env["PIP_CACHE_DIR"] = str(RUNTIME / "cache/pip")
    (RUNTIME / "tmp").mkdir(parents=True, exist_ok=True)
    env["TMPDIR"] = str(RUNTIME / "tmp")
    subprocess.run([str(python), '-m', 'pip', 'install', '.'], cwd=ROOT / 'agent', env=env, check=True)
    for variable, directory in (('GOCACHE', 'cache/go-build'), ('GOMODCACHE', 'cache/go-mod')):
        path = RUNTIME / directory
        path.mkdir(parents=True, exist_ok=True)
        env[variable] = str(path)
    (RUNTIME / 'bin').mkdir(parents=True, exist_ok=True)
    subprocess.run(['go', 'build', '-o', str(RUNTIME / 'bin/core'), '.'], cwd=ROOT / 'backend/core', env=env, check=True)
    print('Ready. Start with: python3 scripts/local.py start', flush=True)


if __name__ == '__main__':
    main()

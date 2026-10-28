"""Verify pinned downloads, cache verification of unchanged files, run CPU inference."""
import hashlib
import http.client
import urllib.error
import json
import os
from pathlib import Path
import time
import urllib.request


def fingerprint(path, model):
    stat = path.stat()
    return {'sha256': model['sha256'], 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'ctime_ns': stat.st_ctime_ns, 'inode': stat.st_ino}


def mark_verified(path, model):
    stamp = path.with_suffix(path.suffix + '.verified.json')
    temporary = stamp.with_suffix('.tmp')
    temporary.write_text(json.dumps(fingerprint(path, model)))
    temporary.replace(stamp)


def verified(path, model):
    if not path.is_file() or path.stat().st_size != model['size_bytes']:
        return False
    stamp = path.with_suffix(path.suffix + '.verified.json')
    try:
        if json.loads(stamp.read_text()) == fingerprint(path, model):
            return True
    except (OSError, ValueError):
        pass
    valid = hash_file(path, model['size_bytes']).hexdigest() == model['sha256']
    if valid:
        mark_verified(path, model)
    return valid


def report(phase, message, downloaded=0, total=0, speed=0, elapsed=0, attempt=1):
    status = {'phase': phase, 'message': message, 'downloaded_bytes': downloaded,
              'total_bytes': total, 'percent': round(100 * downloaded / total, 2) if total else 0,
              'bytes_per_second': round(speed), 'elapsed_seconds': round(elapsed, 1), 'attempt': attempt}
    destination = os.getenv('MODEL_STATUS_FILE')
    if destination:
        path = Path(destination)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(status, ensure_ascii=False))
        temporary.replace(path)
    print(message + (f' {status["percent"]:.1f}% ({downloaded / 1e6:.0f}/{total / 1e6:.0f} MB, {speed / 1e6:.1f} MB/s)' if total else ''), flush=True)


def hash_file(path, total):
    digest = hashlib.sha256()
    received = 0
    last = 0
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
            received += len(chunk)
            if time.monotonic() - last >= 2 or received == total:
                report('verifying', 'Проверяем целостность модели', received, total)
                last = time.monotonic()
    return digest


def ensure_weights(target, lock):
    model = lock['model_files'][0]
    if verified(target, model):
        report('weights_ready', 'Модель найдена в кэше, повторное скачивание не нужно')
        return 'verified_cache'
    url = ('https://huggingface.co/' + lock['quantization_repository'] + '/resolve/'
           + lock['model_revision'] + '/' + model['file'])
    part = target.with_suffix('.part')
    total = model['size_bytes']
    started = time.monotonic()
    for attempt in range(1, 6):
        offset = part.stat().st_size if part.exists() else 0
        if offset > total:
            part.unlink()
            offset = 0
        digest = hash_file(part, total) if offset else hashlib.sha256()
        # A completed interrupted download can be verified without another request.
        if offset == total:
            if digest.hexdigest() == model['sha256']:
                part.replace(target)
                mark_verified(target, model)
                return 'downloaded_and_verified'
            part.unlink()
            offset = 0
            digest = hashlib.sha256()
        request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
        report('downloading', 'Скачиваем модель' if not offset else 'Продолжаем загрузку модели', offset, total, elapsed=time.monotonic()-started, attempt=attempt)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if offset and response.status == 206:
                    if response.headers.get('Content-Range', '') != f'bytes {offset}-{total-1}/{total}':
                        raise OSError('Unexpected partial response')
                elif offset:
                    # A server may ignore Range. Never append a full response.
                    offset, digest = 0, hashlib.sha256()
                received, initial = offset, offset
                sample_started, announced = time.monotonic(), 0
                with part.open('ab' if offset else 'wb') as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if received > total:
                            raise RuntimeError('Model exceeds pinned size')
                        if time.monotonic() - announced >= 2 or received == total:
                            speed = (received-initial) / max(.001, time.monotonic()-sample_started)
                            report('downloading', 'Скачиваем модель', received, total, speed, time.monotonic()-started, attempt)
                            announced = time.monotonic()
            if received < total:
                raise OSError('Download interrupted before expected size')
            if digest.hexdigest() != model['sha256']:
                part.unlink(missing_ok=True)
                raise RuntimeError('Model checksum mismatch; refusing to start')
            part.replace(target)
            mark_verified(target, model)
            report('weights_ready', 'Модель загружена, контрольная сумма совпала', total, total)
            return 'downloaded_and_verified'
        except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            if attempt == 5:
                report('error', 'Не удалось скачать модель после пяти попыток. Проверьте доступ в интернет.')
                raise RuntimeError('Model download failed after five attempts') from error
            report('retrying', f'Соединение прервалось. Повторяем загрузку (попытка {attempt + 1} из 5)', part.stat().st_size if part.exists() else 0, total, elapsed=time.monotonic()-started, attempt=attempt+1)
            time.sleep(min(2 ** attempt, 16))


def main():
    lock = json.loads(Path('/runtime/model-lock.json').read_text())
    target = Path('/models') / lock['model_files'][0]['file']
    started = time.monotonic()
    print(json.dumps({'phase':'verify_weights','model':lock['alias']}), flush=True)
    report('starting', 'Проверяем наличие модели')
    try:
        source = ensure_weights(target, lock)
    except Exception:
        report('error', 'Не удалось подготовить модель. Подробности в docker compose logs model.')
        raise
    print(json.dumps({'phase':'weights_ready','source':source,'seconds':round(time.monotonic()-started,3)}), flush=True)
    report('loading', 'Загружаем модель в память')
    threads = str(max(1, int(os.getenv('MODEL_THREADS', '4'))))
    os.execv('/runtime/llama-server', [
        'llama-server', '-m', str(target), '--host', '0.0.0.0', '--port', '8082',
        '--ctx-size', str(max(2048, int(os.getenv('MODEL_CONTEXT', '4096')))), '--parallel', '1', '--n-gpu-layers', '0',
        '--alias', lock['alias'], '--jinja', '--chat-template-kwargs', '{"enable_thinking":false}',
        '--reasoning-budget', '0', '--threads', threads, '--threads-batch', threads,
        '--batch-size', '512', '--ubatch-size', '128', '--spec-type', 'none',
        '--ctx-checkpoints', str(max(0, int(os.getenv('MODEL_CHECKPOINTS', '2')))),
        '--checkpoint-min-step', '64', '--cache-ram', str(max(0, int(os.getenv('MODEL_CACHE_RAM', '0')))), '--metrics',
        *(['--no-repack'] if os.getenv('MODEL_REPACK', '1') == '0' else []),
    ])


if __name__ == '__main__':
    main()

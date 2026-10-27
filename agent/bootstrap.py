"""Keep first-start model downloads independent of Compose healthcheck deadlines."""
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def wait_for_model():
    if os.getenv('WAIT_FOR_MODEL') != '1' or os.getenv('LLM_PROVIDER', 'llama_cpp') != 'llama_cpp':
        return
    base = os.getenv('LLM_BASE_URL', 'http://model:8082/v1').rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise RuntimeError('Invalid local model endpoint')
    health = base.removesuffix('/v1') + '/health'
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    announced = None
    while True:
        try:
            with client.open(health, timeout=3) as response:
                if response.status == 200:
                    print('Модель загружена. Начинаем подготовку первого ответа.', flush=True)
                    return
        except urllib.error.HTTPError as error:
            error.close()
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        now = time.monotonic()
        if announced is None or now-announced >= 15:
            print('Ожидаем завершения загрузки модели. Прогресс: http://localhost:8080', flush=True)
            announced = now
        time.sleep(2)


def main():
    wait_for_model()
    os.execv(sys.executable, [sys.executable, 'main.py'])


if __name__ == '__main__':
    main()

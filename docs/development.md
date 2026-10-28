# Разработка и проверки

Основной стек — `docker compose up --build` из корня репозитория. Структура:

- `backend/core/` — Go HTTP API, файловые сессии, встроенный UI.
- `agent/` — Python gRPC, модель условий поездки, адаптеры и тесты.
- `infra/model/` — Docker-образ, загрузка и запуск llama.cpp.
- `docs/` — архитектура, источники, инструкции и результаты проверок.
- `scripts/` — локальные команды проверки, eval и браузерные сценарии.

## Go Core

Нужна версия Go из `backend/core/go.mod`. Из корня:

```sh
sh scripts/check-go.sh all
```

Команда проверяет форматирование, `go vet`, race-тесты и сборку Core. Отдельные этапы: `format`, `vet`, `test`, `stress`, `build`. CI выполняет те же проверки.

## Python agent

Нужен Python из `agent/.python-version`. Установка окружения разработки:

```sh
cd agent
python3 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt . ruff==0.14.2
.venv/bin/python -m ruff check main.py bootstrap.py export_schemas.py travel_agent evals tests
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python ../scripts/test-model-bootstrap.py
.venv/bin/python ../scripts/test-agent-bootstrap.py
```

Python/Go proto должны совпадать, кроме `option go_package`. Это проверяется тестом Core и Agent CI. При изменении wire-контракта обновляются обе схемы и сгенерированные файлы.

Языковые и диалоговые eval с реальной моделью описаны в [agent/README.md](../agent/README.md). Они требуют запущенной модели; unit-тесты используют управляемые зависимости.

## Браузерный путь

`scripts/ui-public-journey.cjs` проверяет полный сценарий через UI, `scripts/ui-random-journeys.cjs` — разные диалоги и восстановление состояния. Локальные зависимости: Node.js, Chrome и Playwright Core из `.runtime/browser/node_modules`. Они нужны для разработки, запуск приложения в Docker их не требует.

После изменения встроенных файлов UI пересоберите `app`. Для модели/агента пересобирайте соответствующий сервис. Нативный запуск Mac/Metal описан отдельно в [local-setup.md](local-setup.md).

Отчёты прежних проверок в `docs/validation/` и `agent/evals/results/` сохранены с их датами и исходными конфигурациями. Они могут упоминать компоненты, удалённые позднее; это исторические свидетельства, а не инструкции запуска.

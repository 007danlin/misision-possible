# Qwen-agent «О!дин запрос»

Существующий Python gRPC agent расширен разбором поездок, сохранением условий и ToolRegistry.
Core управляет сессией и учебной покупкой; LLM не назначает цены и не пишет в хранилище.

**Запуск всего приложения:** `python3 scripts/local.py start` из корня репозитория.
Модель и runtime находятся в `.runtime/` проекта. Общая Ollama не используется.
[Подробности автономного запуска](../docs/local-setup.md).

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m evals.run --output evals/results/qwen-project-local.json
```

Первая команда проверяет код с подставной моделью, вторая реально вызывает локальную Qwen.
Для hosted endpoint задайте LLM_PROVIDER=dashscope/openai_compatible, LLM_BASE_URL,
LLM_MODEL, LLM_API_KEY; ключ не коммитится. Скрытого fallback на фикстуры нет.

gRPC: Predict (инфраструктурный smoke), RunTurn (Qwen), Evaluate (кодовая проверка действий).
[Контракт и ограничения](../docs/agent.md).

## Проверка формулировок и многошаговых уточнений

Из корня репозитория, с работающей локальной моделью:

```sh
PYTHONPATH=agent:agent/tests agent/.venv/bin/python -m unittest discover -s agent/tests
agent/.venv/bin/python scripts/eval-language.py --output .runtime/evals/language
agent/.venv/bin/python scripts/eval-dialogues.py --timeout 90 --output .runtime/evals/dialogues
```

`eval-language.py` проверяет отдельные формулировки, `eval-dialogues.py` — целые цепочки через производственный `run_turn`: бюджет, даты, гости, сохранение условий, отрицания, вопросы, смена направления и транспорта. В диалоговом прогоне Qwen настоящая; отели, погода и внешние транспортные сервисы заменены фиксированными данными, чтобы проверять язык и переходы состояния независимо от доступности поставщиков. Ответы модели, ревизии входных условий, ошибки и хеши исходников сохраняются после каждой реплики.

Любой провал даёт ненулевой код завершения. Записанные реальные ответы можно повторно проверить без inference:

```sh
agent/.venv/bin/python scripts/eval-dialogues.py --replay .runtime/evals/dialogues/results.json --output .runtime/evals/dialogues-replay
agent/.venv/bin/python scripts/eval-language.py --replay .runtime/evals/language/results.json --output .runtime/evals/language-replay
```

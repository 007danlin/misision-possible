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

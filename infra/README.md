# Инфраструктура

Рабочая конфигурация находится в корневом [docker-compose.yml](../docker-compose.yml). Запуск из корня: `docker compose up --build`.

| Сервис | Сборка | Назначение |
|---|---|---|
| `app` | `backend/core/Dockerfile` | Go Core и UI на localhost:8080 |
| `agent` | `agent/Dockerfile` | Python gRPC и адаптеры данных |
| `model` | `infra/model/Dockerfile` | llama.cpp и локальная Qwen |

`model/start.py` загружает веса по закреплённому манифесту, проверяет SHA-256 и запускает модель. `agent/bootstrap.py` ждёт модель и прогревает контексты. Core начинает показывать подготовку до завершения прогрева. Внутренние порты модели и агента на хост не публикуются.

Volumes `models`, `trips`, `hotel-content`, `startup` сохраняют веса, поездки, контент и состояние запуска. Логи доступны через `docker compose logs app agent model`; Core также предоставляет `/metrics`.

Старые dev/server Compose, Auth/Chat/Notif, NATS, Redis, PostgreSQL, Traefik и Grafana/Alloy удалены из текущего состава. Их прежние реализации доступны в истории Git. Корневой Compose остаётся единственным поддерживаемым контейнерным запуском продукта; отдельный AMD64 override используется только для проверки совместимости.

[Архитектура](../docs/agent.md) · [диагностика](../docs/runtime.md) · [передача секретов](../docs/secrets.md). `.env.example` и `secrets.env.age` находятся в корне по инструкции организаторов.

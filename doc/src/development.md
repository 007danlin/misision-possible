# Разработка

Проект `misison-possible`. Автор бэкенда — `ghost_err`.

## Структура

- `backend/auth/` — HTTP API пользователей, сессий и 2FA.
- `backend/core/` — HTTP API с проверкой токена через Auth и вызовом агента.
- `backend/notif/` — обработка событий NATS и отправка email.
- `backend/chat/` — заготовка сервиса, HTTP-сервер пока не реализован.
- `agent/` — Python gRPC-сервис; сейчас возвращает демонстрационное приветствие.
- `frontend/` — каталог для интерфейса, реализация пока отсутствует.
- `infra/` — Docker Compose, Traefik и мониторинг.

## Локальный запуск

Из корня репозитория (нужны Docker и Docker Compose v2):

```sh
docker compose -f infra/docker-compose.dev.yml up --build
```

Traefik принимает запросы на `http://localhost`: `/api/auth` и `/api/core`.
Панель Traefik — `http://localhost:8089`, Grafana — `http://localhost:3000`.
Compose запускает также PostgreSQL, Redis, NATS, агент и Notif.
Локальные пароль БД и pepper предназначены только для разработки.
Без SMTP-настроек письма и коды подтверждения выводятся в логи Notif.

```sh
docker compose -f infra/docker-compose.dev.yml logs notif
```

## Серверные настройки

Скопируйте `infra/server.env.example` в `infra/server.env`. Укажите уникальные `POSTGRES_PASSWORD`
и `PEPPER`. Сервисы собираются из исходников на месте. Эти секреты нужно сохранять между перезапусками.
Для постоянных JWT-ключей задайте согласованную пару Ed25519 в base64
через `JWT_PUBLIC_KEY` и `JWT_PRIVATE_KEY`; без них ключи временные.
Для отправки почты задайте `SMTP_USER` и `SMTP_PASSWORD`.
Файл `server.env` исключён из Git.

```sh
docker compose --env-file infra/server.env -f infra/docker-compose.server.yml up -d --build
```

Серверный Compose использует маршруты для `localhost`; перед внешним
развёртыванием настройте домен, TLS и доступ к портам инфраструктуры.

## Проверки

Go-сервисы используют Go 1.27.1 и `GOEXPERIMENT=runtimesecret`.

```sh
sh scripts/check-go.sh
```

Скрипт проверяет форматирование, запускает `go vet`, тесты с race detector
и сборку. Допустимы отдельные режимы: `format`, `vet`, `test`, `stress`, `build`.
После запуска Compose можно выполнить:

```sh
python3 scripts/smoke.py
python3 scripts/check-monitoring.py
```

Smoke-проверка требует локальной почтовой заглушки; проверка мониторинга
использует локальную Grafana с учётной записью `admin:admin`.

## GitHub Actions

Проверки запускаются на push, pull request и вручную.

Backend: форматирование → `go vet` → тесты с race detector → сборка.
На каждом этапе `auth`, `core`, `notif`, `chat` проверяются отдельными заданиями.
Следующий этап начинается после успешного завершения предыдущего.
Для локальной проверки одного сервиса: `sh scripts/check-go.sh test auth`.

Agent: Ruff проверяет исходники и тесты, затем выполняются тесты через
настоящий локальный gRPC-сервер и проверка установленных зависимостей.
Сгенерированные protobuf-файлы исключены из линтера.

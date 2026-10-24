# Core Service

Core проверяет Bearer-токен через Auth `/api/auth/users/me`, затем вызывает
агента по gRPC. Через Traefik API доступен по `http://localhost/api/core/`.

| Метод | Путь | Токен | Описание |
|---|---|---|---|
| POST | `/api/core/handle` | Да | Принимает `name`, вызывает агента |
| GET | `/health` | Нет | Проверка живости |

```sh
curl http://localhost/api/core/handle \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"name":"Alice"}'
```

```json
{"status":"ok","caller":"123","agent_message":"hello Alice from agent"}
```

Используйте настоящий access-токен из Auth. Демонстрационные строки вроде
`demo-admin` не принимаются. Неактивный пользователь или недействительный
токен дают 401; недоступность Auth — 503; неправильное тело — 400;
ошибка агента — 502. Вызов агента ограничен двумя секундами.

Адрес агента задают AGENT_HOST и AGENT_PORT. Контракт —
`backend/core/proto/predict.proto`, Python-копия — `agent/proto/predict.proto`.
RPC `model.Predictor/Predict` принимает `name`, `caller` и возвращает
`message`, `caller`. Историческое имя namespace сохранено для совместимости.

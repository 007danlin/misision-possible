# Формат ошибок

Auth возвращает ошибки в следующем формате:

```json
{
  "error": {
    "code": "ERR_INVALID_CREDENTIALS",
    "message": "Неверный email или пароль"
  }
}
```

**Правило для фронта:** ветвиться по `error.code`, а не по HTTP статусу и не по `message` (текст может поменяться/локализоваться, код — нет).

## Общие коды Auth

| Код | HTTP | Когда |
|---|---|---|
| `ERR_UNAUTHORIZED` | 401 | Нет токена или он битый |
| `ERR_TOKEN_EXPIRED` | 401 | access_token протух → иди в `/auth/refresh` |
| `ERR_FORBIDDEN` | 403 | Токен ок, но прав не хватает (например не admin) |
| `ERR_VALIDATION` | 400 | Не прошла валидация тела запроса |
| `ERR_NOT_FOUND` | 404 | Ресурса не существует |
| `ERR_RATE_LIMITED` | 429 | Слишком частые запросы |
| `ERR_INTERNAL` | 500 | Мы накосячили, шли скрин в чат |

## Коды auth-сервиса

| Код | HTTP | Когда |
|---|---|---|
| `ERR_INVALID_CREDENTIALS` | 401 | Неверный email/пароль на логине |
| `ERR_EMAIL_NOT_VERIFIED` | 403 | Пытается залогиниться неверифицированный юзер |
| `ERR_EMAIL_TAKEN` | 409 | Email уже занят при регистрации |
| `ERR_ACCOUNT_BANNED` | 403 | Юзера забанил админ |
| `ERR_INVALID_2FA_CODE` | 401 | Неверный код 2FA |
| `ERR_INVALID_VERIFICATION_CODE` | 400 | Неверный/просроченный код из письма |
| `ERR_INVALID_REFRESH_TOKEN` | 401 | Refresh просрочен/отозван → нужен полный релогин |

## Отличия сервисов

Auth возвращает только `code` и `message`, без `details` и `retry_after`.
При включённой 2FA логин возвращает HTTP 200 с `requires_2fa: true`
и `pending_token`.

Core возвращает ошибку строкой: `{"error":"invalid JSON body"}`.
У Chat пока нет HTTP API, Notif обрабатывает события NATS и пишет ошибки в логи.

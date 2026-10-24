# Регистрация и верификация email

## POST /auth/register

Создаёт юзера со статусом `unverified`. Логин на этом шаге ещё невозможен — сначала нужно подтвердить email.

**Headers:** без Authorization

**Request:**
```json
{
  "email": "user@example.com",
  "password": "supersecret123",
  "username": "gopher"
}
```

**Response 201:**
```json
{
  "user_id": "123",
  "status": "verification_sent"
}
```

**Response 409** (`ERR_EMAIL_TAKEN`):
```json
{
  "error": { "code": "ERR_EMAIL_TAKEN", "message": "Email уже используется" }
}
```

**Response 400** (`ERR_VALIDATION`) — см. [общий формат ошибок](../errors.md)

---

## POST /auth/verify-email

Подтверждает код из письма, переводит юзера в `active`. При успехе сразу отдаёт токены, отдельно логиниться не нужно.

**Request:**
```json
{
  "user_id": "123",
  "code": "483920"
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "rt_9f8e7d6c...",
  "expires_in": 900
}
```

**Response 400** (`ERR_INVALID_VERIFICATION_CODE`):
```json
{
  "error": { "code": "ERR_INVALID_VERIFICATION_CODE", "message": "Код неверный или устарел" }
}
```

---

## POST /auth/resend-verification

Присылает новый код, если старый не пришёл/протух. **Rate-limit: 1 раз в 60 секунд.**

**Request:**
```json
{ "user_id": "123" }
```

**Response 200:**
```json
{ "status": "success", "message": "verification_sent" }
```

**Response 429** (`ERR_RATE_LIMITED`):
```json
{
  "error": { "code": "ERR_RATE_LIMITED", "message": "Подожди перед повторной отправкой" }
}
```

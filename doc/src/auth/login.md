# Логин и сессии

## POST /auth/login

**Request:**
```json
{
  "email": "user@example.com",
  "password": "supersecret123"
}
```

**Response 200 — без 2FA:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "rt_9f8e7d6c...",
  "expires_in": 900
}
```

**Response 200 — если включена 2FA:**
```json
{
  "requires_2fa": true,
  "pending_token": "pt_ab12cd34..."
}
```
Фронт должен показать форму ввода кода из Google Authenticator и отправить его на `/auth/2fa/verify`.

**Response 401** (`ERR_INVALID_CREDENTIALS`)

**Response 403** (`ERR_EMAIL_NOT_VERIFIED`):
```json
{
  "error": { "code": "ERR_EMAIL_NOT_VERIFIED", "message": "Подтверди email перед входом" }
}
```
Фронт в этом случае должен предложить кнопку "отправить код повторно" → `/auth/resend-verification`.

**Response 403** (`ERR_ACCOUNT_BANNED`)

---

## POST /auth/2fa/verify

**Request:**
```json
{
  "pending_token": "pt_ab12cd34...",
  "code": "123456"
}
```

**Response 200:** та же пара токенов, что и в обычном логине.

**Response 401** (`ERR_INVALID_2FA_CODE`)

---

## POST /auth/refresh

**Request:**
```json
{ "refresh_token": "rt_9f8e7d6c..." }
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "rt_NEW_TOKEN...",
  "expires_in": 900
}
```
⚠️ Refresh-токен **ротируется** — старый после этого запроса больше не работает, сохраняй новый вместо старого.

**Response 401** (`ERR_INVALID_REFRESH_TOKEN`) — нужен полный релогин через `/auth/login`.

---

## POST /auth/logout

**Headers:** `Authorization: Bearer <access_token>`

**Request:** пустое тело

**Response 200:**
```json
{ "status": "success", "message": "logged_out" }
```

---

## POST /auth/logout-all

Разлогинивает со всех устройств/сессий.

**Headers:** `Authorization: Bearer <access_token>`

**Response 200:**
```json
{ "status": "logged_out_all", "sessions_revoked": 3 }
```

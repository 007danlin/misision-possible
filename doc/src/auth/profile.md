# Профиль пользователя

Все эндпоинты здесь требуют `Authorization: Bearer <access_token>`.

## GET /users/me

**Response 200:**
```json
{
  "user_id": 123,
  "email": "user@example.com",
  "nickname": "gopher",
  "avatar_url": "https://cdn.example.com/avatars/gopher.png",
  "role": "user",
  "status": "active",
  "totp_enabled": false,
  "created_at": "2026-07-06T12:00:00Z"
}
```

---

## PATCH /users/me

Меняет только не-security поля (nickname/avatar). Для смены пароля/email — отдельные эндпоинты ниже.

**Request:**
```json
{
  "nickname": "new_nickname",
  "avatar_url": "https://cdn.example.com/avatars/new.png"
}
```
Оба поля опциональны, шли только то что меняешь.

**Response 200:** обновлённый объект юзера (как в `GET /users/me`)

---

## POST /users/me/change-password

**Request:**
```json
{
  "current_password": "oldSecret123",
  "new_password": "newSecret456"
}
```

**Response 200:**
```json
{ "status": "success", "message": "password_changed" }
```
После смены пароля все сессии кроме текущей отзываются автоматически.

**Response 401** (`ERR_INVALID_CREDENTIALS`) — неверный текущий пароль

---

## POST /users/me/change-email

Двухшаговый процесс: сначала запрос кода на новый email, потом подтверждение.

**Шаг 1 — запрос:**
```json
{ "new_email": "newmail@example.com" }
```
**Response 200:**
```json
{ "status": "success", "message": "verification_sent_to_new_email" }
```

**Шаг 2 — подтверждение:**
```
POST /users/me/change-email/confirm
```
```json
{ "code": "483920" }
```
**Response 200:**
```json
{ "status": "email_changed", "email": "newmail@example.com" }
```

Старый email продолжает работать для логина, пока новый не подтверждён кодом.

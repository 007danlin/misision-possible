# Admin-эндпоинты

Все эндпоинты требуют `Authorization: Bearer <access_token>` от юзера с `role: admin`. Иначе — `403 ERR_FORBIDDEN`.

## GET /admin/users

**Query params:** `?page=1&limit=20&search=gopher`

**Response 200:**
```json
{
  "users": [
    {
      "user_id": 123,
      "email": "user@example.com",
      "nickname": "gopher",
      "role": "user",
      "status": "active",
      "created_at": "2026-07-06T12:00:00Z"
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 137
}
```

---

## GET /admin/users/:id

**Response 200:** полный объект юзера (как `GET /users/me`, но для любого id)

**Response 404** (`ERR_NOT_FOUND`)

---

## PATCH /admin/users/:id/ban

**Request:** пустое тело. Причина бана сейчас не обрабатывается.

**Response 200:**
```json
{ "status": "banned", "user_id": "123" }
```
При бане все активные сессии юзера отзываются немедленно (не ждёт истечения access_token).

---

## PATCH /admin/users/:id/unban

**Request:** пустое тело

**Response 200:**
```json
{ "status": "unbanned", "user_id": "123" }
```

---

## PATCH /admin/users/:id/role

**Request:**
```json
{ "role": "admin" }
```

**Response 200:**
```json
{ "status": "role_updated", "user_id": "123", "role": "admin" }
```

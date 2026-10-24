# Восстановление пароля

## POST /auth/forgot-password

**Headers:** без Authorization

**Request:**
```json
{ "email": "user@example.com" }
```

**Response 200** (всегда одинаковый, даже если email не найден — чтобы не палить существование аккаунта):
```json
{ "status": "success", "message": "reset_email_sent" }
```

---

## POST /auth/reset-password

**Request:**
```json
{
  "code": "483920",
  "new_password": "newSuperSecret456"
}
```

**Response 200:**
```json
{ "status": "success", "message": "password_reset" }
```
После этого действия **все существующие сессии юзера отзываются** — на всех устройствах потребуется заново залогиниться.

**Response 400** (`ERR_INVALID_VERIFICATION_CODE`) — код неверный или устарел

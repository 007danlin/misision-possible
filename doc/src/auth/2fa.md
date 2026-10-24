# Двухфакторная аутентификация (2FA)

Требует `Authorization: Bearer <access_token>` на всех трёх шагах.

## POST /users/me/2fa/enable

Генерирует TOTP-секрет. Фронт должен показать QR-код (из `otpauth_url`) для сканирования в Google Authenticator / Authy.

**Request:** пустое тело

**Response 200:**
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "otpauth_url": "otpauth://totp/misison-possible:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=misison-possible"
}
```
⚠️ На этом шаге 2FA ещё **не активна** — только после подтверждения кодом.

---

## POST /users/me/2fa/confirm

Юзер вводит первый код из приложения, чтобы подтвердить что сканирование прошло успешно.

**Request:**
```json
{ "code": "123456" }
```

**Response 200:**
```json
{ "status": "success", "message": "2fa_enabled" }
```

**Response 401** (`ERR_INVALID_2FA_CODE`)

---

## POST /users/me/2fa/disable

Требует пароль + текущий код 2FA — нельзя отключить одной кнопкой без пруфа.

**Request:**
```json
{
  "password": "supersecret123",
  "code": "123456"
}
```

**Response 200:**
```json
{ "status": "success", "message": "2fa_disabled" }
```

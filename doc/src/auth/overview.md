# Auth Service — обзор

Отвечает за: регистрацию, вход, сессии (JWT), профиль пользователя, 2FA, управление юзерами (admin).

**Base URL:** `http://localhost/api/auth` через Traefik. При запуске Auth
без Docker: `http://localhost:8080/api/auth`. Пути на страницах Auth
указаны относительно этого префикса.

## Карта эндпоинтов

| Метод | Путь | Нужен токен | Описание |
|---|---|---|---|
| POST | `/auth/register` | нет | Регистрация |
| POST | `/auth/verify-email` | нет | Подтверждение email кодом |
| POST | `/auth/resend-verification` | нет | Повторно прислать код |
| POST | `/auth/login` | нет | Вход |
| POST | `/auth/2fa/verify` | нет (pending_token) | Подтверждение 2FA при входе |
| POST | `/auth/refresh` | нет (refresh_token) | Обновить access_token |
| POST | `/auth/logout` | да | Выйти с текущего устройства |
| POST | `/auth/logout-all` | да | Выйти со всех устройств |
| POST | `/auth/forgot-password` | нет | Запросить сброс пароля |
| POST | `/auth/reset-password` | нет | Сбросить пароль по коду |
| GET | `/users/me` | да | Свой профиль |
| PATCH | `/users/me` | да | Изменить профиль |
| POST | `/users/me/change-password` | да | Сменить пароль |
| POST | `/users/me/change-email` | да | Сменить email (2 шага) |
| POST | `/users/me/change-email/confirm` | да | Подтверждение нового email |
| POST | `/users/me/2fa/enable` | да | Начать подключение 2FA |
| POST | `/users/me/2fa/confirm` | да | Подтвердить подключение 2FA |
| POST | `/users/me/2fa/disable` | да | Отключить 2FA |
| GET | `/admin/users` | да (admin) | Список юзеров |
| GET | `/admin/users/:id` | да (admin) | Юзер по id |
| PATCH | `/admin/users/:id/ban` | да (admin) | Забанить |
| PATCH | `/admin/users/:id/unban` | да (admin) | Разбанить |
| PATCH | `/admin/users/:id/role` | да (admin) | Сменить роль |

## Общая схема пользователя

```json
{
  "user_id": 123,
  "email": "user@example.com",
  "nickname": "gopher",
  "avatar_url": "https://...",
  "role": "user",
  "status": "active",
  "totp_enabled": false,
  "created_at": "2026-07-06T12:00:00Z"
}
```

Подробности по каждой группе эндпоинтов — в соседних страницах.

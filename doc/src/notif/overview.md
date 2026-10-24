# Notif Service — обзор

Notif — подписчик на события NATS. Он слушает события Auth и subject для будущих событий Chat и выполняет минимальную обработку: печать уведомления или отправку в интеграцию с email/push-сервисом.

## NATS subjects

| Subject | Событие | Логика |
|---|---|---|
| `auth.user.registered` | Новый пользователь | Формирует сообщение о подтверждении email |
| `auth.user.email_change_requested` | Смена email | Отправляет код подтверждения на новый адрес |
| `auth.user.password_reset_requested` | Сброс пароля | Формирует сообщение о сбросе пароля |
| `chat.message.sent` | Сообщение в чате | Выводит пуш-уведомление получателю |

## Пример payload

```json
{
  "user_id": "u_123",
  "email": "user@example.com",
  "code": "483920"
}
```

## Запуск

```bash
cd backend/notif
NATS_URL=nats://localhost:4222 go run .
```

## Реализация

- Подписка на несколько NATS subjects.
- Простой `RenderMessage`-роутер по subject.
- Отправка email через Gmail/Yandex SMTP. Без SMTP_USER или SMTP_PASSWORD
  используется локальная заглушка, которая выводит письмо и код в логи.
- Обработчик `chat.message.sent` выводит уведомление в лог; Chat пока не публикует события.

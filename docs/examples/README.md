# Примеры Snapshot

Контракт: `agent/travel_agent/domain.py::Snapshot`, экспорт
`agent/schemas/Snapshot.schema.json`.

Все восемь файлов получены от настоящего Go Core:

- `session-needs-input.json` — уточнение неполного запроса.
- `session-choosing-destinations.json` — выбор направления.
- `session-choosing-plans.json` — варианты поездки.
- `session-ready.json` — выбранная поездка, оформление разрешено.
- `session-change-preview.json` — новое предложение, оформление заблокировано до принятия.
- `session-no-solution.json` — бюджет не позволяет подобрать поездку в учебном каталоге.
- `session-error.json` — inference-служба намеренно остановлена; покупки нет.
- `session-booked-demo.json` — явное учебное оформление через Core.

Основные семь состояний сохраняет реальный Qwen smoke:

```sh
TRIP_SMOKE_EXAMPLES=docs/examples python3 scripts/trip-smoke.py
```

Error снят отдельно при недоступной inference-службе. Все восемь ответов проверены
моделью Snapshot. Цены и бронирования учебные. Cookie владения сессией в файлах нет.
Примеры предназначены для контракта UI, не для восстановления чужой сессии.

"""Frozen before the first run on 27 Oct; not used to tune the prompt.

Authored during implementation, not an independent human acceptance study.
The initial state for 'selected' is the existing evaluation's Sochi booking.
"""

CASES = [
    ("h01_yaroslavl_four_nights", "Два взрослых, из Москвы в Ярославль. Заезд 3 ноября 2026, выезд 7 ноября 2026. Лимит 50 тысяч рублей на дорогу, гостиницу, трансферы и сборы.", "empty", "choosing", {"destination": "Ярославль", "dates.start": "2026-11-03", "dates.end": "2026-11-07", "budget.amount_minor": 5000000, "budget_scope": "booking", "travellers.adults": 2}),
    ("h02_december", "Мы вдвоём отправимся из Москвы в Казань с 8 по 11 декабря 2026. На билеты туда и обратно, отель, трансферы и сборы выделяем 45 тысяч рублей.", "empty", "choosing", {"origin": "Москва", "destination": "Казань", "dates.start": "2026-12-08", "dates.end": "2026-12-11", "budget.amount_minor": 4500000, "travellers.adults": 2}),
    ("h03_no_scope", "Из Москвы во Владимир с 20 по 23 ноября 2026, два взрослых, 35 тысяч рублей.", "empty", "needs_input", {"destination": "Владимир", "budget_scope": None, "dates.start": "2026-11-20", "dates.end": "2026-11-23"}),
    ("h04_whole_reserve", "На весь отдых теперь 130 тысяч рублей. Из них 20 тысяч рублей оставим на питание и прочие расходы вне бронирования.", "selected", "choosing", {"budget.amount_minor": 13000000, "budget_scope": "whole_trip", "expense_reserve.amount_minor": 2000000, "destination": "Сочи"}),
    ("h05_one_day_later", "Перенеси выезд и возвращение на один день позже, всё остальное сохрани.", "selected", "choosing", {"dates.start": "2026-11-11", "dates.end": "2026-11-16", "destination": "Сочи", "travellers.adults": 2}),
    ("h06_cancel_and_cheaper", "Сделай дешевле, но бесплатная отмена обязательна.", "selected", "choosing", {"hard_constraints.free_cancellation": True, "budget.amount_minor": 12000000, "hard_constraints.no_night_flights": True}),
    ("h07_unsupported_city", "Поменяем направление на Томск. Остальное пусть останется.", "selected", "no_solution", {"destination": "Томск", "origin": "Москва", "dates.start": "2026-11-10"}),
    ("h08_january", "Теперь даты с 10 по 15 января 2027 года, остальные условия прежние.", "selected", "no_solution", {"dates.start": "2027-01-10", "dates.end": "2027-01-15", "destination": "Сочи"}),
    ("h09_child_age", "Ещё возьмём с собой ребёнка семи лет.", "selected", "no_solution", {"travellers.adults": 2, "travellers.children": [7]}),
    ("h10_hotel_scope", "На сам отель готовы потратить максимум 45 тысяч рублей, остальные условия сохраняем.", "selected", "choosing", {"budget_scope": "hotel", "budget.amount_minor": 4500000, "dates.start": "2026-11-10"}),
    ("h11_no_exact_days", "Из Москвы в Казань на пять дней в декабре, двое взрослых. До 50 тысяч рублей на дорогу, гостиницу, трансферы и сборы.", "empty", "needs_input", {"dates": None, "duration_days": 5, "destination": "Казань", "travellers.adults": 2}),
    ("h12_no_budget_relaxation", "На дорогу, проживание, трансферы и сборы теперь только 20 тысяч рублей. Направление и даты не меняй.", "selected", "no_solution", {"budget.amount_minor": 2000000, "destination": "Сочи", "dates.start": "2026-11-10", "dates.end": "2026-11-15"}),
]

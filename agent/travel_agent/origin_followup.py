"""Resolve a known city only when it answers the current departure question."""

import re

from .domain import Intent


def canonical_city(value):
    """Recognize a complete city name/alias, never arbitrary residual prose."""
    from .ostrovok import CITIES

    names = {
        name: name.title()
        for name in CITIES
        if name not in {"карелия", "алтай", "селигер"}
    }
    names.update({
        "питер": "Санкт-Петербург", "питера": "Санкт-Петербург",
        "спб": "Санкт-Петербург", "петербург": "Санкт-Петербург",
        "петербурга": "Санкт-Петербург", "санкт петербург": "Санкт-Петербург",
        "санкт-петербурга": "Санкт-Петербург", "санкт петербурга": "Санкт-Петербург",
        "москвы": "Москва", "казани": "Казань", "ярославля": "Ярославль",
        "владимира": "Владимир", "нижнего новгорода": "Нижний Новгород",
        "адлера": "Адлер", "анапы": "Анапа", "краснодара": "Краснодар",
        "калининграда": "Калининград", "кисловодска": "Кисловодск",
        "геленджика": "Геленджик", "мурманска": "Мурманск",
    })
    text = " ".join(value.casefold().replace("ё", "е").split())
    return names.get(text)


def origin_followup(state, message):
    question = state.questions[0] if state.questions else state.assistant_message
    if state.trip_spec.origin or not re.search(
        r"из какого города|город отправления|откуда (?:вы )?(?:отправ|поед|ед)",
        question, re.I,
    ):
        return None
    # Wishes, alternatives and combined messages still need the model; a bare
    # destination reply is never stolen by the departure shortcut.
    text = " ".join(message.casefold().replace("ё", "е").split()).rstrip(".! ")
    text = re.sub(r"^(?:(?:отправляемся|выезжаем|вылетаем|едем)\s+)?из\s+", "", text)
    city = canonical_city(text)
    if not city:
        return None
    return Intent(
        action="change", patch={"origin": city}, evidence={"origin": message}
    )


def needs_initial_origin(state, message):
    """Conservative preflight for a new trip idea; retain prose for later parsing."""
    if (state.search_mode != "hotels" or state.history or state.questions
            or state.trip_spec.origin or state.trip_spec.destination
            or state.hotel_options or state.selection):
        return False
    # Any possible departure cue stays with semantic parsing, including cities
    # outside our catalogue. Hotel-only requests do not require a departure.
    if re.search(
        r"\b(?:из|от|живу|живем|живём|нахожусь|находимся|отправлен\w*|"
        r"старт\w*|вылет\w*|выезд\w*|отел\w*|отель|гостиниц\w*|from)\b|→|->",
        message, re.I,
    ):
        return False
    # A city mentioned anywhere could be an implicit departure (e.g. Москва —
    # хочу к морю); leave these cases to the model instead of asking twice.
    from .ostrovok import CITIES
    text = message.casefold().replace("ё", "е")
    if any(re.search(r"(?<!\w)" + re.escape(city) + r"(?!\w)", text) for city in CITIES):
        return False
    if re.search(r"\b(?:питер|спб|мск)\b", text):
        return False
    return bool(re.search(
        r"\b(?:мор[ею]|природу|горы|лес|отдохнуть|отдых|поездк\w*|путешеств\w*|выходные)\b",
        text,
    ))

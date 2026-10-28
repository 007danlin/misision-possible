"""Guard explicit operations against unrelated defaults emitted by a small model."""

import re
from .domain import Intent


AMENITIES = {
    "pool": "бассейн",
    "parking": "парковк",
    "spa": "спа",
    "breakfast": "завтрак",
    "fitness": "тренажерн",
}


def rejected_destination(message, name):
    """Return an explicit rejection clause, never a mere city mention."""
    if not name:
        return None
    name = re.escape(name.casefold().replace("ё", "е"))
    for clause in re.split(r"[.!?;\n]", message.casefold().replace("ё", "е")):
        place = r"(?<!\w)" + name + r"(?!\w)"
        if re.search(
            r"(?:только\s+не|кроме|исключи(?:ть)?|не\s+(?:предлаг\w*|рассматрив\w*|хочу|хотим))\s+(?:в\s+)?" + place
            + r"|" + place + r"\s+(?:не\s+(?:предлаг\w*|рассматрив\w*|хочу|хотим|нужен|нужна)|исключи(?:ть)?)",
            clause,
        ):
            return clause.strip(' ,:—-')
    return None


def explicit_clarification(message):
    text = message.casefold().replace("ё", "е")
    if re.search(r"\d\s*(?:евро|доллар\w*|usd|eur|€|\$)", text) and re.search(
        r"бюджет|лимит|потрат|переведи|на (?:отель|поездк|все)", text
    ):
        return Intent(
            action="clarify",
            questions=[
                "Укажите бюджет в рублях: я не буду самостоятельно выбирать курс и пересчитывать вашу сумму."
            ],
        )
    if re.search(r"\b(?:нас|едем|взросл\w*|человек)\b", text) and re.search(
        r"то ли .{1,25}то ли", text
    ):
        return Intent(
            action="clarify",
            questions=[
                "Сколько человек поедет? Сохраню прежний состав, пока вы не определитесь."
            ],
        )
    for stem in AMENITIES.values():
        word = stem + r"\w*"
        positive = re.search(
            r"(?:обязательно|нужен|нужна|нужно|требуется)\s+" + word, text
        )
        negative = re.search(
            r"(?:отел\w*|гостиниц\w*|вариант\w*)\s+без\s+"
            + word
            + r"(?!\s+не\s+(?:предлаг|рассматрив|показыв))",
            text,
        )
        if positive and negative:
            return Intent(
                action="clarify",
                questions=[
                    "В запросе одновременно указаны требование к удобству и его отсутствие. Какой вариант нужен?"
                ],
            )
    return None


def ground_intent(intent, message, previous):
    if intent.questions:
        return intent
    text = message.casefold().replace("ё", "е")
    data = intent.model_dump(mode="json", exclude_unset=True)
    patch = data.setdefault("patch", {})
    evidence = data.setdefault("evidence", {})
    from .calendar_followup import calendar_range

    interval = calendar_range(message)
    if interval is not None:
        if interval.questions:
            return interval
        patch['dates'] = interval.patch.dates.model_dump(mode='json')
        evidence['dates'] = interval.evidence['dates']
    from .origin_followup import canonical_city

    for field in ("origin", "destination"):
        value = patch.get(field)
        if isinstance(value, str):
            patch[field] = canonical_city(value) or value
    # A small model can emit a rejected place as the requested destination.
    # Retain explicit exclusions as grounded wishes for later short replies.
    from .inspiration import CATALOGUE

    names = {d[key] for d in CATALOGUE for key in ("name", "destination")}
    names.update(x for x in (patch.get("destination"), previous.destination) if x)
    for name in sorted(names):
        rejection = rejected_destination(message, name)
        if rejection:
            if patch.get("destination", previous.destination) == name:
                if previous.destination == name:
                    patch["destination"] = None
                    evidence["destination"] = message[:500]
                else:
                    patch.pop("destination", None)
                    evidence.pop("destination", None)
            wishes = data.setdefault("add_preferences", [])
            if rejection not in wishes and rejection not in previous.preferences:
                wishes.append(rejection)
                evidence["add_preferences"] = message[:500]
        elif patch.get("destination") == name:
            removed = [p for p in previous.preferences if rejected_destination(p, name)]
            if removed:
                data.setdefault("remove_preferences", []).extend(removed)
                evidence["remove_preferences"] = message[:500]
    # Waterfront can mean a river, lake or canal; it does not imply seaside.
    water = re.search(
        r"\b(?:поближе|ближе|рядом|недалеко|у)\s+(?:(?:к|с|от)\s+)?"
        r"(?:вод[аеы]|рек[аеиой]+|озер[аоу]|озёр[аоу]|набережн\w*|канал\w*)\b",
        message, re.I,
    )
    if water and not re.search(r"\b(?:не|без|или|либо)\b", message, re.I):
        if patch.get("travel_setting") == "sea" and not re.search(
            r"\b(?:мор[еяю]|морской|пляж\w*)\b", message, re.I
        ):
            patch.pop("travel_setting")
        wishes = data.setdefault("add_preferences", [])
        if water[0] not in wishes:
            wishes.append(water[0])
        evidence["add_preferences"] = message if len(message) <= 500 else water[0]
    # A mention of one restriction does not authorize altering the others.
    topics = {
        "no_connections": r"пересад|прям\w*\s+(?:рейс|перелет|поезд)",
        "no_night_flights": r"(?:ноч|днем|дневн|утр|вечер).*(?:рейс|перелет|вылет|лететь)|(?:рейс|перелет|вылет|лететь).*(?:ноч|днем|дневн|утр|вечер)",
        "no_night_travel": r"ноч|дневн|днем|спать",
        "free_cancellation": r"отмен|возврат",
        "pets": r"питом|животн|собак|кошк|кот\b|щен|корги|мопс|терьер|пудел|лабрад|🐕|🐈|🐶|🐱",
    }
    constraints = patch.get("hard_constraints")
    if isinstance(constraints, dict):
        for key, topic in topics.items():
            if key == "pets" and constraints.get(key) is True:
                continue  # An animal/breed name need not be in a finite dictionary.
            if key in constraints and not re.search(topic, text):
                constraints.pop(key)
        if not constraints:
            patch.pop("hard_constraints")
    forbidden_connections = re.search(
        r"(?:без|никак\w*)\s+пересад\w*|пересад\w*\s+не\s+(?:нужн\w*|хочу|хотим)", text
    )
    allowed_connections = re.search(
        r"пересад\w*\s+(?:(?:теперь|снова)\s+)?(?:допустим\w*|разрешен\w*|можно)|(?:можно|разрешаю)\s+(?:с\s+)?пересад\w*",
        text,
    )
    if forbidden_connections or allowed_connections:
        patch.setdefault("hard_constraints", {})["no_connections"] = bool(
            forbidden_connections
        )
        evidence["hard_constraints"] = message[:500]
    travellers = patch.get("travellers", {})
    if travellers.get("children"):
        counted = re.search(
            r"(?:\d+|один|одного|два|двое|двух|три|трое|четыр\w*|пят\w*|шест\w*|сем\w*|восем\w*|девят\w*|десят\w*)\s+(?:дет\w*|ребен\w*)",
            text,
        )
        ages = re.search(
            r"возраст|(?:\d+|одного|двух|трех|четырех|пяти|шести|семи|восьми|девяти|десяти|одиннадцати|двенадцати|тринадцати|четырнадцати|пятнадцати|шестнадцати|семнадцати)\s*(?:лет|года?|годик\w*)",
            text,
        )
        joining = re.search(
            r"\bс\s+ребен\w*|(?:добав|поед|едем|путешеств|отдых).{0,25}(?:ребен|дет|сын|доч)|(?:сын|доч).{0,20}(?:поед|с нами)",
            text,
        )
        if not (counted or ages or joining):
            travellers.pop("children")
        if not travellers:
            patch.pop("travellers", None)
    hotel_only = bool(
        re.search(
            r"(?<!не )\bтолько\s+(?:отел\w*|гостиниц\w*|жилье)|без\s+(?:дороги|транспорта)",
            text,
        )
    )
    paid = r"(?:куплен\w*|купил[аи]?|оплачен\w*|оплатил[аи]?|на руках)"
    unpaid = re.search(r"(?:билет\w*|дорог[ау]).{0,20}\bне\s+(?:куп|опла)", text)
    if hotel_only:
        patch["include_transport"] = False
        evidence["include_transport"] = message[:500]
    elif unpaid:
        patch["transport_owned"] = False
        evidence["transport_owned"] = message[:500]
    elif re.search(r"(?:билет\w*|дорог[ау]\b).{0,25}" + paid, text):
        patch.update(transport_owned=True, include_transport=True)
        evidence.update(transport_owned=message[:500], include_transport=message[:500])
    if "keep_hotel" in patch:
        hotel = r"(?:отел\w*|гостиниц\w*)"
        operation = r"(?:остав\w*|сохран\w*|не\s+меня\w*|не\s+трог\w*|закреп\w*|фиксир\w*|замен\w*)"
        if patch["keep_hotel"] is False:
            operation = r"(?:меня\w*|замен\w*|фиксир\w*|закреп\w*)"
        if not re.search(
            hotel + r".{0,35}" + operation + r"|" + operation + r".{0,35}" + hotel, text
        ):
            patch.pop("keep_hotel")
    if "budget_scope" in patch and not re.search(
        r"бюджет|лимит|сумм|руб|тысяч|₽|на все\b|на всю поездк|только на отель", text
    ):
        patch.pop("budget_scope")
    # An explicit total-stay amount replaces a previous nightly ceiling even
    # when the model emits only the new sum and forgets the period.
    if "budget" in patch and re.search(
        r"за\s+(?:вс[её]\s+(?:проживание|время)|весь\s+(?:отдых|срок)|всю\s+поездку)",
        text,
    ) and not re.search(r"\b(?:или|либо|если)\b|не\s+за\s+(?:вс[её]|весь|всю)", text):
        patch["budget_period"] = "stay"
        evidence["budget_period"] = message[:500]
    if re.search(r"\b(?:подешевле|дешевле)\b", text) and not re.search(
        r"\bне\s+(?:подешевле|дешевле)\b", text
    ):
        data["optimization"] = "cheaper"
        evidence["optimization"] = message[:500]
    if data.get("optimization") == "cheaper" and data.get("action") == "replace_options":
        replacing = re.search(
            r"друг|нов[а-я]*\s+(?:вариант|отел|подбор)|следующ|замен|мимо|не\s+подход|не\s+нрав|ни\s+один|"
            r"ещ[её]\s+(?:вариант|отел|подбор)", text,
        )
        if not replacing:
            data["action"] = "change"
    if data.get("optimization") == "cheaper" and "budget" in patch:
        amount_words = r"\d|ноль|один|одн[аоу]|дв[аеу]|три|трех|четыр|пят|шест|сем|восем|девят|десят|двадцат|тридцат|сорок|пятьдесят|шестьдесят|семьдесят|восемьдесят|девяност|сто\b|сот|двести|триста|полтос|полтинник"
        if not re.search(amount_words, text):
            patch.pop("budget")  # "Cheaper" has no new spending ceiling.
    for key, stem in AMENITIES.items():
        word = stem + r"\w*"
        retain = re.search(
            word
            + r".{0,20}не\s+(?:убира|снима|исключа|отменя)\w*|не\s+(?:убира|снима|исключа|отменя)\w*.{0,20}"
            + word,
            text,
        )
        retain = retain or re.search(
            word + r"\s+(?:сохрани|сохранить|оставь|оставить)(?!\w)|"
            r"(?<!не )(?:сохрани|сохранить|оставь|оставить)\s+(?:требование\s+)?" + word,
            text,
        )
        if retain:
            old = getattr(previous.hotel_preferences, key)
            patch.setdefault("hotel_preferences", {})[key] = (
                old if old is not None else True
            )
            evidence["hotel_preferences"] = message[:500]
            data["remove_hotel_preferences"] = [
                k for k in data.get("remove_hotel_preferences", []) if k != key
            ]
    return Intent.model_validate(data)

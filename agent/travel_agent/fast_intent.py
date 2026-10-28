"""Exact, unambiguous UI commands. Anything outside this grammar still uses Qwen."""

import re
from .domain import Intent, explicit_ruble_amount

NUMBERS = {
    "один": 1,
    "одного": 1,
    "одна": 1,
    "двое": 2,
    "два": 2,
    "двух": 2,
    "трое": 3,
    "три": 3,
    "трех": 3,
    "трёх": 3,
    "четверо": 4,
    "четыре": 4,
    "четырех": 4,
    "пятеро": 5,
    "пять": 5,
    "пяти": 5,
    "шестеро": 6,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}
COUNT = r"(?:\d{1,2}|" + "|".join(NUMBERS) + ")"


def number(s):
    return int(s) if s.isdigit() else NUMBERS[s.lower()]


def child_count(message):
    matches = list(
        re.finditer(
            r"(?<!\w)(" + COUNT + r")\s+(?:детей|реб[её]нка|реб[её]нок|ребят)(?!\w)",
            message,
            re.I,
        )
    )
    if len(matches) != 1:
        return None
    m = matches[0]
    prefix = message[max(0, m.start() - 18) : m.start()]
    prefix = re.sub(r"вс[её]\s+ещ[её]\s*$", "", prefix, flags=re.I)
    if re.search(r"ещ[её]|дополнительно|плюс|добавь|добавим|добавить", prefix, re.I):
        return None
    return number(m.group(1)), m.group(0)


def protect_child_count(intent, message, previous):
    """A numeric count is authoritative; never reduce it to the ages returned by an LLM."""
    found = child_count(message)
    if not found:
        return intent
    count, quote = found
    if count > 10:
        raise ValueError(
            "travellers.children: maximum 10; never silently reduce the stated count"
        )
    data = intent.model_dump(exclude_unset=True)
    patch = data.setdefault("patch", {})
    travellers = patch.setdefault("travellers", {})
    ages = travellers.get("children")
    # A count is not an age. Small models may turn «пятеро детей» into
    # [5,5,5,5,5]. Only accept newly extracted ages when the message actually
    # contains age information; a repeated count keeps previously known ages.
    age_units = re.search(
        r"(?<!\w)" + COUNT + r"\s*(?:лет|год(?:а|ик(?:а|ов)?)?)(?!\w)", message, re.I
    )
    age_list = re.search(
        r"(?:возраст(?:а|ы)?(?:\s+детей)?|дети|детей|детям|им)\s*[:—,-]?\s*"
        + COUNT
        + r"(?:\s*(?:,|и)\s*"
        + COUNT
        + r"){1,9}",
        message,
        re.I,
    )
    named_age = re.search(
        r"(?:младш(?:ему|ей)|старш(?:ему|ей)|сыну|дочери|дочке|возрасте)\s*[:—-]?\s*"
        + COUNT,
        message,
        re.I,
    )
    if ages is None or not (age_units or age_list or named_age):
        ages = (
            list(previous.travellers.children)
            if len(previous.travellers.children) == count
            else []
        )
    if len(ages) > count:
        raise ValueError(
            "child ages exceed the explicitly stated count; clarify the ages"
        )
    ages = list(ages) + [None] * (count - len(ages))
    travellers["children"] = ages
    # Original message, not generated text, proves the corrected count.
    data.setdefault("evidence", {})["travellers"] = (
        message[:500] if len(message) <= 500 else quote
    )
    return Intent.model_validate(data)


def protect_added_children(intent, message, previous):
    """An explicit addition is a delta; preserve known guests and never invent ages."""
    text = message.lower().replace("ё", "е")
    pattern = (
        r"\b(?:добавь|добавим|добавить)\s+(?:(?:еще|пожалуйста)\s+)?(?:(?P<count>"
        + COUNT
        + r")\s+)?(?P<noun>ребенка|ребенок|детей)\b"
    )
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        return intent
    match = matches[0]
    start = max(text.rfind(c, 0, match.start()) for c in ".!?;") + 1
    end = min(
        [p for c in ".!?;" if (p := text.find(c, match.end())) >= 0] or [len(text)]
    )
    clause = text[start:end]
    if re.search(r"\b(?:если|или|либо)\b", clause) or re.search(
        r"\bне\s+(?:(?:хочу|нужно|надо|будем)\s+)?$", text[start : match.start()]
    ):
        return intent
    if not match["count"] and match["noun"] == "детей":
        return intent
    count = number(match["count"]) if match["count"] else 1
    ages = list(previous.travellers.children)
    if len(ages) + count > 10:
        return Intent(
            action="clarify",
            questions=[
                "В одной поездке можно указать не более 10 детей. Сколько детей поедет всего?"
            ],
        )
    tail = text[match.end() : end]
    age = re.match(
        r"\s+(?:в\s+возрасте\s+)?(\d{1,2})\s*(?:лет|года?|годик(?:а|ов)?)\b", tail
    )
    if age is None and count == 1:
        age = re.search(r"\b(?:ему|ей|ребенку)\s+(\d{1,2})\s*(?:лет|года?)\b", tail)
    if age is None and re.search(r"\d+\s*(?:лет|года?)\b", tail):
        return intent
    value = int(age[1]) if age else None
    if value is not None and value > 17:
        return Intent(
            action="clarify",
            questions=[
                "Сколько лет ребёнку? Для детского размещения укажите возраст от 0 до 17 лет."
            ],
        )
    data = intent.model_dump(exclude_unset=True)
    data.setdefault("patch", {}).setdefault("travellers", {})["children"] = (
        ages + [value] * count
    )
    data.setdefault("evidence", {})["travellers"] = message[:500]
    # A standard missing-age question is handled after the explicit count is saved.
    if data.get("questions") and all(
        re.search(r"возраст|сколько\s+лет", q, re.I) for q in data["questions"]
    ):
        data["questions"] = []
    data["action"] = "change"
    return Intent.model_validate(data)


def fast_intent(state, message):
    clarification = clarify_ambiguous_request(message)
    if clarification:
        return clarification
    from .hotel_criteria import numeric_command

    proximity = numeric_command(message)
    if proximity is not None:
        return proximity
    text = " ".join(message.strip().lower().replace("ё", "е").split()).rstrip(".!?")

    def result(patch=None, **extra):
        evidence = {k: message for k in (patch or {})}
        evidence.update(
            {k: message for k in extra if k not in {"action", "hotel_reference"}}
        )
        return Intent.model_validate(
            dict(patch=patch or {}, evidence=evidence, **extra)
        )

    # Incremental family edits must not replace known children or invent an age.
    m = re.fullmatch(
        r"(?:добавь|добавим|добавить)\s+(?:(?:еще|пожалуйста)\s+)?(?:(?P<count>"
        + COUNT
        + r")\s+)?(?P<noun>ребенка|ребенок|детей)(?:\s+(?P<age>\d{1,2})\s*(?:лет|года?|годик(?:а|ов)?))?(?:\s*[,;]\s*возраст\s+(?:уточню|скажу|сообщу)\s+(?:позже|потом))?",
        text,
    )
    if m:
        if not m["count"] and m["noun"] == "детей":
            return Intent(
                action="clarify", questions=["Сколько детей добавим в поездку?"]
            )
        count = number(m["count"]) if m["count"] else 1
        age = int(m["age"]) if m["age"] is not None else None
        if (
            age is not None
            and age > 17
            or count + len(state.trip_spec.travellers.children) > 10
        ):
            return Intent(
                action="clarify",
                questions=[
                    "Укажите не более 10 детей, возраст каждого — от 0 до 17 лет."
                ],
            )
        return result(
            {
                "travellers": {
                    "children": list(state.trip_spec.travellers.children)
                    + [age] * count
                }
            },
            action="change",
        )
    if state.trip_spec.travellers.children.count(None) == 1:
        m = re.fullmatch(r"(?:(?:ему|ей|ребенку)\s+)?(\d{1,2})\s*(?:лет|года?)?", text)
        if m and 0 <= int(m[1]) <= 17 and "лет" in state.assistant_message:
            ages = list(state.trip_spec.travellers.children)
            ages[ages.index(None)] = int(m[1])
            return result({"travellers": {"children": ages}}, action="change")
    if text == "подобрать поездку":
        return result(action="search")
    if text in {"покажи другие отели", "все отели замени"}:
        return result(action="replace_options")
    m = re.fullmatch(
        r"(?:лучше|давай|поедем) (поездом|самолетом|на машине|на автомобиле)", text
    )
    if m:
        return result(
            {
                "transport_mode": {
                    "поездом": "train",
                    "самолетом": "flight",
                    "на машине": "car",
                    "на автомобиле": "car",
                }[m[1]],
                "include_transport": True,
                "transport_owned": False,
            },
            action="change",
        )
    m = re.fullmatch(r"отправляемся из (.{1,100})", message.strip(), re.I)
    if m:
        return result({"origin": m[1].strip()}, action="change")
    if text == "без пересадок":
        return result({"hard_constraints": {"no_connections": True}}, action="change")
    if text in {"билеты уже куплены", "билеты я уже купил"}:
        return result(
            {"transport_owned": True, "include_transport": True}, action="change"
        )
    if text in {"хочу интересное рядом", "что интересного рядом", "покажи места рядом"}:
        return result(action="nearby")
    if text in {"отель оставь, поменяй дорогу", "отель оставь, меняем только дорогу"}:
        return result({"keep_hotel": True}, action="explain")
    if text in {
        "покажи другие варианты",
        "замени все варианты",
        "ничего не нравится, покажи другое",
        "другие варианты",
    }:
        return result(action="replace_options")
    if text in {"верни прежние варианты", "покажи прежние варианты"}:
        return result(action="restore_options")
    if text in {
        "добавь дорогу и трансферы",
        "добавь дорогу и трансфер",
        "с дорогой и трансферами",
    }:
        return result({"include_transport": True}, action="change")
    if text in {"только отель, без дороги", "только отель без дороги"}:
        return result({"include_transport": False}, action="change")
    if text in {"отель оставь", "оставь этот отель"}:
        return result({"keep_hotel": True}, action="change")
    if text in {"можно сменить отель", "отель можно поменять"}:
        return result({"keep_hotel": False}, action="change")
    if re.fullmatch(
        r"резерв(?: на (?:личные|другие) расходы)?\s+\d[\d ]*\s*(?:тысяч(?:и)?|тыс|рублей|руб|₽)",
        text,
    ):
        amount = explicit_ruble_amount(message)
        if amount is not None:
            return result(
                {"expense_reserve": {"amount_minor": amount}}, action="change"
            )
    if text in {
        "подешевле",
        "теперь дешевле",
        "найди подешевле, остальные условия сохрани",
        "найди подешевле, остальные пожелания сохрани",
        "найди вариант подешевле, остальные условия оставь",
    }:
        return result(optimization="cheaper", action="change")
    # Full-match only: an explanation with additional wishes must still use Qwen.
    explained = re.fullmatch(
        r"почему\s+(?:(?:ты|вы)\s+)?(?:(?:выбрал|выбрали|предложил|предложили|рекомендуешь|рекомендуете)\s+)?(?:именно\s+)?(первый|второй|третий)(?:\s+(?:отель|вариант))?",
        text,
    )
    if explained and state.hotel_options:
        return result(
            action="explain",
            hotel_reference={"первый": 1, "второй": 2, "третий": 3}[explained[1]],
        )
    if text in {
        "почему второй",
        "почему первый",
        "почему третий",
        "объясни, почему выбрал эти отели",
        "почему эти",
        "сравни варианты",
    }:
        return result(
            action="explain",
            hotel_reference={
                "почему первый": 1,
                "почему второй": 2,
                "почему третий": 3,
            }.get(text),
        )
    if text in {
        "хочу на природу, в лес. дикая природа",
        "хочу в лес",
        "хочу на природу, в лес",
        "хочу на природу",
    }:
        return result(
            {
                "travel_setting": "forest" if "лес" in text else "nature",
                "destination": None,
            },
            action="inspire",
        )
    if text in {
        "бассейн больше не обязателен",
        "бассейн больше не обязателен. остальное оставь",
        "бассейн не важен",
    }:
        return result(remove_hotel_preferences=["pool"], action="change")
    for region, city in [
        ("Карелия", "Сортавала"),
        ("Алтай", "Чемал"),
        ("Селигер", "Осташков"),
        ("Сочи", "Сочи"),
        ("Петербург", "Санкт-Петербург"),
    ]:
        if (
            text
            == f"выбираю {region}, ищем в районе {city}. остальные пожелания сохрани".lower()
        ):
            return result({"destination": city})
    m = re.fullmatch(r"(?:на\s+)?(" + COUNT + r")\s+(?:детей|ребенка|ребенок)", text)
    if m and number(m[1]) <= 10:
        return result({"travellers": {"children": [None] * number(m[1])}})
    m = re.fullmatch(r"(" + COUNT + r")\s+взросл(?:ый|ых|ого)", text)
    if m and 1 <= number(m[1]) <= 20:
        return result({"travellers": {"adults": number(m[1])}})
    m = re.fullmatch(r"(?:на\s+)?(" + COUNT + r")\s+ноч(?:ь|и|ей)", text)
    if m:
        return result({"stay_nights": number(m[1])})
    if (
        state.trip_spec.travellers.children
        and any(a is None for a in state.trip_spec.travellers.children)
        and "лет" in state.assistant_message
    ):
        m = re.fullmatch(
            r"(?:(?:им|возраст детей:)\s+)?(\d{1,2}(?:(?:\s*,\s*|\s+и\s+|\s+)\d{1,2})*)\s*(?:лет|года)?",
            text,
        )
        if m:
            ages = [int(x) for x in re.findall(r"\d+", m[1])]
            if len(ages) == len(state.trip_spec.travellers.children) and all(
                0 <= a <= 17 for a in ages
            ):
                return result({"travellers": {"children": ages}})
    m = re.fullmatch(
        r"(?:бюджет\s+|до\s+)?\d[\d ]*\s*(?:тысяч(?:и)?|тыс|рублей|руб|₽)(?:\s+рублей)?(?:\s+на отель)?(?:\s+за весь отдых)?",
        text,
    )
    if m:
        amount = explicit_ruble_amount(message)
        if amount is not None:
            patch = {"budget": {"amount_minor": amount}}
            if "на отель" in text:
                patch["budget_scope"] = "hotel"
            if "за весь отдых" in text:
                patch["budget_period"] = "stay"
            return result(patch)
    presets = {
        "в сочи на 5 ночей, двое взрослых, до 40 тысяч рублей на отель. хочу бассейн": {
            "destination": "Сочи",
            "stay_nights": 5,
            "travellers": {"adults": 2},
            "budget": {"amount_minor": 4000000},
            "budget_scope": "hotel",
            "hotel_preferences": {"pool": True},
        },
        "в казань на 3 ночи, двое взрослых, до 25 тысяч рублей на отель, не дальше 2 км от центра": {
            "destination": "Казань",
            "stay_nights": 3,
            "travellers": {"adults": 2},
            "budget": {"amount_minor": 2500000},
            "budget_scope": "hotel",
            "hotel_preferences": {"max_center_m": 2000},
        },
    }
    if text in presets:
        return result(presets[text])
    from .explicit_commands import explicit_commands

    return explicit_commands(state, message)


def protect_stay_length(intent, message, previous):
    """Keep a single explicit night count even if a small model skips that field.

    Alternatives/conditions and changes to already dated stays remain model work.
    """
    if (
        previous.dates
        or intent.patch.dates
        or re.search(r"\b(?:если|или|либо)\b", message, re.I)
    ):
        return intent
    matches = list(
        re.finditer(r"(?<!\w)(" + COUNT + r")\s+ноч(?:ь|и|ей)(?!\w)", message, re.I)
    )
    if len(matches) != 1:
        return intent
    m = matches[0]
    n = number(m[1])
    if re.search(
        r"(?:не|меньше|больше|минимум|максимум|около|до|от)\s+(?:(?:чем|на)\s+)?$",
        message[max(0, m.start() - 30) : m.start()],
        re.I,
    ):
        return intent
    if not 1 <= n <= 60:
        return intent
    data = intent.model_dump(exclude_unset=True)
    data.setdefault("patch", {})["stay_nights"] = n
    data.setdefault("evidence", {})["stay_nights"] = m[0]
    return Intent.model_validate(data)


def protect_adult_count(intent, message):
    if re.search(r"\b(?:если|или|либо|не)\b", message, re.I):
        return intent
    matches = list(
        re.finditer(
            r"(?<!\w)(" + COUNT + r")\s+взросл(?:ый|ых|ого)(?!\w)", message, re.I
        )
    )
    matches += list(re.finditer(r"\bвдво[её]м\b", message, re.I))
    if len(matches) != 1:
        return intent
    m = matches[0]
    count = 2 if m[0].lower().startswith("вдво") else number(m[1])
    if not 1 <= count <= 20:
        return intent
    data = intent.model_dump(exclude_unset=True)
    data.setdefault("patch", {}).setdefault("travellers", {})["adults"] = count
    # A combined adults/children patch needs evidence for both; preserve the original excerpt.
    evidence = data.setdefault("evidence", {})
    if len(message) <= 500:
        evidence["travellers"] = message
    elif not evidence.get("travellers"):
        evidence["travellers"] = m[0]
    return Intent.model_validate(data)


def protect_explicit_forest(intent, message):
    """A plainly requested forest is a setting, never merely an ignored soft wish."""
    if intent.action == "explain":
        return intent
    for clause in re.split(r"[.!?;]", message):
        match = re.search(
            r"\b(?:лес(?:а|у|е|ом)?|дик(?:ая|ую|ой)\s+природ[ауеы])\b", clause, re.I
        )
        if not match or re.search(
            r"\b(?:не|без|или|либо)\b|неваж|необяз", clause, re.I
        ):
            continue
        if not re.search(
            r"хоч|хот|ищ|отдых|поед|поех|уед|нуж|мечт|в\s+лес", clause, re.I
        ):
            continue
        data = intent.model_dump(exclude_unset=True)
        data.setdefault("patch", {})["travel_setting"] = "forest"
        data.setdefault("evidence", {})["travel_setting"] = match[0]
        # Forest alone does not retain an explicit wish to stay away from town.
        # Keep the quoted soft requirement for ranking/verification as well.
        if len(message) <= 500 and re.search(r"\bподальше от города\b", clause, re.I):
            wishes = data.setdefault("add_preferences", [])
            if "подальше от города" not in wishes:
                wishes.append("подальше от города")
            data["evidence"]["add_preferences"] = message
        return Intent.model_validate(data)
    return intent


def protect_hotel_budget_scope(intent, message):
    # “За всё проживание” means the full hotel stay, not the entire holiday.
    if explicit_ruble_amount(message) is None:
        return intent
    clauses = [
        c for c in re.split(r"[.!?;]", message) if explicit_ruble_amount(c) is not None
    ]
    scope_text = clauses[0] if len(clauses) == 1 else message
    if re.search(
        r"всю поездк|вс[её] путешеств|дорог|перел[её]т|трансфер|питани",
        scope_text,
        re.I,
    ):
        return intent
    match = re.search(
        r"(?:на|за)\s+(?:(?:вс[её]|весь|только)\s+)?(?:отель|проживание|жиль[её])",
        scope_text,
        re.I,
    )
    if not match:
        return intent
    data = intent.model_dump(exclude_unset=True)
    data.setdefault("patch", {})["budget_scope"] = "hotel"
    data.setdefault("evidence", {})["budget_scope"] = match[0]
    if data.get("patch", {}).get("include_transport") is False and not re.search(
        r"только (?:отель|гостиниц)|без дорог|убери.*(?:дорог|трансфер)", message, re.I
    ):
        data["patch"].pop("include_transport", None)
    return Intent.model_validate(data)


def protect_explicit_polarity(intent, message):
    """Distinguish removing a criterion from explicitly excluding a facility."""
    data = intent.model_dump(exclude_unset=True)
    changes = {}
    evidence = {}
    for key, stem in [
        ("pool", "бассейн"),
        ("spa", "спа"),
        ("parking", "парковк"),
        ("fitness", "тренажерн[а-я ]*зал"),
        ("breakfast", "завтрак"),
    ]:
        word = stem + r"\w*"
        text = message.lower().replace("ё", "е")
        positive = re.search(
            r"без\s+"
            + word
            + r"\s+(?:даже\s+)?не\s+(?:предлаг|показыв|рассматрив)\w*|не\s+(?:предлаг|показыв|рассматрив)\w*\s+(?:отел\w*\s+)?без\s+"
            + word,
            text,
        )
        negative = re.search(
            r"(?:отель|гостиниц\w*|вариант\w*)\s+(?:обязательно\s+)?без\s+" + word, text
        )
        if (
            positive
            and negative
            and positive.start() < negative.end()
            and negative.start() < positive.end()
        ):
            negative = None
        if positive and negative:
            label = {
                "pool": "бассейн",
                "spa": "спа",
                "parking": "парковка",
                "fitness": "тренажёрный зал",
                "breakfast": "завтрак",
            }[key]
            data["questions"] = [
                "Уточните: " + label + " нужен или его нужно исключить?"
            ]
            continue
        found = positive or negative
        if found:
            changes[key] = bool(positive)
            evidence["hotel_preferences"] = message[:500]
    if changes:
        data.setdefault("patch", {}).setdefault("hotel_preferences", {}).update(changes)
        data["remove_hotel_preferences"] = [
            k for k in data.get("remove_hotel_preferences", []) if k not in changes
        ]
        data.setdefault("evidence", {}).update(evidence)
    if re.search(
        r"без\s+(?:возможност\w+\s+)?бесплатн\w+\s+отмен\w+.{0,20}не\s+(?:рассматрив|предлаг|подход)\w*",
        message,
        re.I,
    ):
        data.setdefault("patch", {}).setdefault("hard_constraints", {})[
            "free_cancellation"
        ] = True
        data.setdefault("evidence", {})["hard_constraints"] = message[:500]
    if re.search(
        r"отсортир\w*.*(?:цен|стоимост).*?(?:доступн|дешев|возрастан)|(?:сначала|начиная с)\s+(?:самых\s+)?(?:дешев|доступн)",
        message,
        re.I,
    ):
        data["optimization"] = "cheaper"
        data.setdefault("evidence", {})["optimization"] = message[:500]
    return Intent.model_validate(data)


def clarify_ambiguous_request(message):
    """Do not choose an arbitrary date/count when the user explicitly has not chosen."""
    from .grounding import explicit_clarification

    explicit = explicit_clarification(message)
    if explicit is not None:
        return explicit
    text = message.lower().replace("ё", "е")
    question = None
    duration = re.search(
        r"(?<!\w)("
        + COUNT
        + r")\s+(?:или|либо)\s+("
        + COUNT
        + r")\s+(ноч\w*|дн\w*|день)",
        text,
    )
    if duration:
        question = (
            "На сколько "
            + ("ночей" if duration[3].startswith("ноч") else "дней")
            + " планируем поездку: "
            + duration[1]
            + " или "
            + duration[2]
            + "?"
        )
    dates = re.search(
        r"(?<!\d)(\d{1,2})\s*[–—-]\s*(\d{1,2})\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)",
        text,
    )
    if dates and int(dates[1]) >= int(dates[2]):
        question = "Выезд должен быть позже заезда. Уточните обе даты, пожалуйста."
    if re.search(r"как\s+в\s+прошл\w+\s+раз", text) and re.search(
        r"не\s+(?:рассказывал|рассказывала|сообщал|сообщала)", text
    ):
        question = "У меня нет условий той поездки. Какие направление, даты, состав гостей и бюджет повторить?"
    return Intent(action="clarify", questions=[question]) if question else None


def protect_hotel_question(intent, message):
    if (
        intent.action == "reviews"
        and intent.hotel_reference
        and not re.search(
            r"отзыв|гост[ьи]|жалоб|жалу|пишут|говорят|шум|тишин|чистот", message, re.I
        )
    ):
        return intent.model_copy(update={"action": "explain"})
    return intent


def protect_journey_language(intent, message):
    """Keep clearly stated transport choices and quoted/meta instructions scoped."""
    text = message.lower().replace("ё", "е")
    if re.search(
        r"(?:игнорируй|забудь|обойди) (?:все )?(?:правила|инструкции)|(?:секретн\w*|api)[ -]*(?:api[ -]*)?ключ|в отзыве (?:написано|сказано).*инструкци",
        text,
    ):
        return Intent(
            action="clarify",
            questions=[
                "Могу помочь с выбором поездки. Условия поездки не изменены; оплата и реальные заказы здесь не выполняются."
            ],
        )
    data = intent.model_dump(mode="json", exclude_unset=True)
    patch = data.setdefault("patch", {})
    evidence = data.setdefault("evidence", {})
    # Hotel/guest edits cannot silently remove the road and both transfers.
    if patch.get("include_transport") is False and not re.search(
        r"только (?:отель|гостиниц)|без (?:дороги|транспорта)|(?:убери|исключи|не нужна?).*(?:дорог|транспорт)",
        text,
    ):
        patch.pop("include_transport")
    mode = None
    if re.search(
        r"(?<!не )\bполетим\b|\b(?:лучше|давай|хочу|предпочту) (?:на )?самолет", text
    ):
        mode = "flight"
    if re.search(
        r"\b(?:лучше|давай|поедем|хочу) (?:на )?поездом|\bпредпочту железную дорогу",
        text,
    ):
        mode = "train"
    if re.search(r"\b(?:поедем|лучше|давай) на (?:своей )?машине", text):
        mode = "car"
    if mode:
        patch.update(transport_mode=mode, include_transport=True, transport_owned=False)
        for k in ["transport_mode", "include_transport", "transport_owned"]:
            evidence[k] = message
        if data.get("action") == "replace_options" and not re.search(
            r"замени.*отел|другие.*отел|другую.*подбор", text
        ):
            data["action"] = "change"
    if re.search(
        r"ночью (?:ехать|ездить|добираться) не (?:хотим|хочу|будем)|без ночных (?:переезд|участк)|не (?:хотим|хочу) (?:ехать|ездить) ночью",
        text,
    ):
        patch.setdefault("hard_constraints", {})["no_night_travel"] = True
        evidence["hard_constraints"] = message
    if (
        patch.get("transport_owned")
        and re.search(
            r"трансфер.*(?:нуж|остав|добав)|(?:нуж|остав|добав).*трансфер", text
        )
        and not re.search(r"только (?:отель|гостиниц)", text)
    ):
        patch["include_transport"] = True
        evidence["include_transport"] = message
    return Intent.model_validate(data)

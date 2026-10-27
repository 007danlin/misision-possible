"""Ground numeric hotel filters in user language before domain validation.

Qualitative proximity uses the same visible radii as the extraction prompt.
Explicit limits always win; unsupported comparisons ask instead of inverting them.
"""
import re
from decimal import Decimal

WORDS = {'одного': 1, 'один': 1, 'одной': 1, 'одна': 1,
         'двух': 2, 'два': 2, 'две': 2, 'трех': 3, 'три': 3,
         'четырех': 4, 'четыре': 4, 'пяти': 5, 'пять': 5,
         'шести': 6, 'шесть': 6, 'семи': 7, 'семь': 7,
         'восьми': 8, 'восемь': 8, 'девяти': 9, 'девять': 9,
         'десяти': 10, 'десять': 10, 'полутора': 1.5, 'полтора': 1.5,
         'половины': .5, 'полкилометра': .5, 'пары': 2, 'пару': 2,
         'ста': 100, 'сто': 100, 'двухсот': 200, 'двести': 200,
         'трехсот': 300, 'триста': 300, 'пятисот': 500, 'пятьсот': 500,
         'тысячи': 1000, 'тысяча': 1000, 'тысячу': 1000}
NUMBER = r'(?:\d+(?:[.,]\d+)?|' + '|'.join(WORDS) + ')'
DISTANCE = re.compile(r'(?<![\w.,])(' + NUMBER + r')\s*(километр\w*|км|метр\w*|м)(?!\w)')
TARGETS = {'max_center_m': (r'\bцентр(?:а|е|у|ом)?\b', 'центра', 2000),
           'max_beach_m': (r'\b(?:пляж\w*|мор[еяю]|побереж\w*)', 'пляжа', 1000)}
NUMERIC_KEYS = {*TARGETS, 'min_rating', 'min_stars'}
NEAR = r'\b(?:около|рядом|недалеко|неподалеку|поближе|ближе|близко|вблизи)\b|\bв\s+(?:самом\s+)?центре\b|\bпеш\w*\s+доступност\w*'
REMOVE = r'не\s*(?:важ\w*|обязател\w*|принципиал\w*)|неваж\w*|необязател\w*|не\s+имеет\s+значения|без\s+ограничени\w*|(?:убери|сними|отмени)\s+(?:фильтр|ограничени\w*|требовани\w*)|можно\s+(?:и\s+)?(?:далеко|дальше)'


def number(text):
    return Decimal(str(WORDS[text])) if text in WORDS else Decimal(text.replace(',', '.'))


def clauses(message):
    # Preserve decimal commas/points, but isolate unrelated counts and budgets.
    return re.split(r'(?<!\d)[,.;!?]|[,.;!?](?!\d)|\s+(?:и|но|зато)\s+', message.lower().replace('ё', 'е'))


def numeric_requirements(message):
    values, removed, questions, inferred = {}, set(), [], set()
    mentioned_targets=[key for key,(pattern,_,_) in TARGETS.items() if re.search(pattern,message,re.I)]

    def record(key, value, qualitative=False):
        if qualitative and key in values:
            return  # An explicit distance takes precedence over a proximity default.
        if key in removed or key in values and key not in inferred and values[key] != value:
            questions.append('Указаны разные условия для одного фильтра. Какое из них использовать?')
        values[key] = value
        if qualitative:inferred.add(key)
        else:inferred.discard(key)

    for clause in clauses(message):
        clause = re.sub(r'\b(одно|двух|трех|четырех|пяти)звезд\w*', lambda m: {'одно':'одной'}.get(m[1],m[1])+' звезд', clause)
        targets = [key for key, (pattern, _, _) in TARGETS.items() if re.search(pattern, clause)]
        if not targets and len(mentioned_targets)==1 and re.fullmatch(r'\s*(?:до|не\s+дальше|не\s+более|максимум)\s+'+DISTANCE.pattern+r'\s*',clause):
            targets=mentioned_targets
        conditional = re.search(r'\b(?:если|или|либо)\b', clause)
        for key in targets:
            _, label, radius = TARGETS[key]
            if key == 'max_center_m' and re.search(r'(?:торгов\w*|выставочн\w*|медицинск\w*|делов\w*|бизнес[ -]?)\s*центр', clause):
                questions.append('Какой именно центр вы имеете в виду? Укажите название или адрес.')
                continue
            if conditional:
                questions.append(f'Какое расстояние до {label} использовать как обязательное условие?')
                continue
            if re.search(REMOVE, clause) or re.search(r'не\s+(?:нужно|надо|обязательно)\s+(?:быть\s+)?(?:рядом|близко|в\s+центре)', clause):
                if key in values:
                    questions.append('Нужно сохранить ограничение расстояния или убрать его?')
                removed.add(key)
                continue
            distances = list(DISTANCE.finditer(clause))
            comparison = re.sub(r'не\s+(?:дальше|более|больше)', 'максимум', clause)
            if re.search(r'не\s+(?:ближе|менее|меньше)|подальше|вдали|не\s+(?:хочу\s+)?(?:рядом|около|близко|в\s+(?:самом\s+)?центре)|\bдалеко\s+от|\b(?:дальше|более|больше)\s+(?:чем\s+)?' + NUMBER + r'|\bминимум\b|' + NUMBER + r'\s*[–—-]\s*' + NUMBER + r'|\bот\s+' + NUMBER + r'\s*(?:до|[–—-]|км|километр|м\b|метр)', comparison):
                questions.append(f'Уточните расположение: какое расстояние до {label} вам подходит?')
            elif len(distances) > 1 or distances and len(targets) > 1:
                questions.append(f'Уточните максимальное расстояние до {label} одним значением.')
            elif distances:
                match = distances[0]
                meters = number(match[1]) * (1000 if match[2].startswith(('км', 'километр')) else 1)
                if meters <= 0 or meters > 100000 or meters != meters.to_integral_value() or re.search(r'[-−]\s*' + re.escape(match[0]), clause):
                    questions.append(f'Укажите расстояние до {label} больше нуля, например 500 м или 2 км.')
                else:
                    record(key, int(meters))
            elif re.search(r'\bполкилометра\b', clause):
                record(key, 500)
            elif re.search(r'\bминут\w*\b|\bчас\w*\b|(?:до|от|максимум)\s+\d+(?:[.,]\d+)?\s*(?:от\s+|до\s+)?(?:центра|пляжа|моря)\b|(?:центра|пляжа|моря)\s+(?:до\s+)?\d+', clause):
                questions.append(f'Укажите расстояние до {label} в метрах или километрах; время в пути зависит от маршрута.')
            elif re.search(NEAR, clause) and not re.search(r'\bне\s+(?:рядом|близко|около|недалеко|ближе|поближе)', clause):
                record(key, radius, qualitative=True)
        for key, pattern, label, maximum in [
            ('min_rating', r'рейтинг\w*|оценк\w*', 'Минимальный рейтинг', 10),
            ('min_stars', r'звезд\w*|[★☆]', 'Минимальное число звёзд', 5),
        ]:
            if not re.search(pattern, clause):
                continue
            if re.search(REMOVE, clause):
                removed.add(key)
                continue
            found = list(re.finditer(r'(?<![\w.,])(' + NUMBER + r')(?!\w)', clause))
            found = [m for m in found if not re.search(r'(?:/|из\s*)$', clause[:m.start()])
                     and not re.match(r'\s*(?:ноч\w*|дн\w*|лет|взросл\w*|руб\w*|тысяч\w*|км|метр\w*)\b', clause[m.end():])]
            if conditional or re.search(r'\bдо\b|не\s+выше|не\s+больше|максимум|не\s+более|от\s+' + NUMBER + r'\s*(?:до|[–—-])', clause) or len(found) > 1:
                questions.append(f'{label}: какое одно значение использовать как нижнюю границу?')
            elif len(found) == 1:
                value = number(found[0][1])
                if not 0 < value <= maximum or key == 'min_stars' and value != value.to_integral_value() or re.search(r'[-−]\s*$', clause[:found[0].start()]):
                    questions.append(f'{label}: укажите число больше нуля и не больше {maximum}.')
                else:
                    record(key, float(value) if key == 'min_rating' else int(value))
    return values, removed, list(dict.fromkeys(questions))


def ground_numeric_criteria(data, message):
    """Never let invented numbers or null defaults erase or narrow prior criteria."""
    patch = data.setdefault('patch', {})
    prefs = patch.get('hotel_preferences')
    if prefs is not None and not isinstance(prefs, dict):
        return data  # Keep malformed shapes visible to contract validation.
    prefs = dict(prefs or {})
    values, removed, questions = numeric_requirements(message)
    # Queries about existing hotels must not change search filters.
    if '?' in message and not re.search(r'\b(?:хочу|ищи|найди|нужен|нужна|добавь|убери)\b', message, re.I):
        values, removed, questions = {}, set(), []
    for key in NUMERIC_KEYS:
        prefs.pop(key, None)
    prefs.update(values)
    if prefs:
        patch['hotel_preferences'] = prefs
        data.setdefault('evidence', {})['hotel_preferences'] = message[:500]
    else:
        patch.pop('hotel_preferences', None)
    removals = data.get('remove_hotel_preferences', [])
    if isinstance(removals, list):
        removals = [key for key in removals if key not in NUMERIC_KEYS]
        data['remove_hotel_preferences'] = list(dict.fromkeys(removals + sorted(removed)))
        if removed:
            data.setdefault('evidence', {})['remove_hotel_preferences'] = message[:500]
    if questions:
        data['questions'] = list(dict.fromkeys(data.get('questions', []) + questions))[:6]
        data['action'] = 'clarify'
    return data


def numeric_command(message):
    """Only complete proximity commands can skip the language model."""
    text = ' '.join(message.lower().replace('ё', 'е').split()).rstrip('.!')
    target = r'(?:центр(?:а|е|у|ом)?|пляж(?:а|е|у|ем)?|мор[еяю]|побережь[еяю])'
    proximity = r'(?:(?:хочу|нужен|нужна|найди|ищи)\s+)?(?:отель\s+)?(?:около|рядом\s+с|недалеко\s+от|неподалеку\s+от|(?:по)?ближе\s+к|близко\s+к|вблизи|в(?:\s+самом)?)\s+' + target
    if not re.fullmatch(proximity, text):
        return None
    from .domain import Intent
    return Intent.model_validate(ground_numeric_criteria({}, message))

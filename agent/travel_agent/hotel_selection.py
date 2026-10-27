"""Explainable selection of real hotel metadata with explicitly simulated tariffs."""
import math
import re
from .domain import TripSpec

AMENITY_LABELS = {'pool': ('has_pool', 'Бассейн'), 'parking': ('has_parking', 'Парковка'),
                  'spa': ('has_spa', 'Спа'), 'fitness': ('has_fitness', 'Фитнес')}


def nights_for(spec):
    return (spec.dates.end-spec.dates.start).days if spec.dates else spec.stay_nights


def demo_quote(hotel, spec):
    """A deterministic stub adapter; this is never an Ostrovok booking rate."""
    base = hotel.get('reference_nightly_minor')
    if not base or not spec.travellers.adults:
        return None
    capacity = (hotel.get('content') or {}).get('room_capacity') or 2
    rooms = math.ceil((spec.travellers.adults + len(spec.travellers.children))/capacity)
    nightly = math.ceil(base / 10000)*10000 * rooms
    breakfast = spec.hotel_preferences.breakfast is True
    if breakfast:
        nightly += 65000 * (spec.travellers.adults + len(spec.travellers.children))
    if spec.hard_constraints.free_cancellation:
        nightly = math.ceil(nightly * 1.12 / 10000)*10000
    nights = nights_for(spec)
    return dict(base_room_nightly_minor=math.ceil(base / 10000)*10000, source_kind='demo', currency='RUB', nightly_minor=nightly,
                total_minor=nightly*nights if nights else None, nights=nights, rooms=rooms,
                breakfast=breakfast, free_cancellation=spec.hard_constraints.free_cancellation,
                explanation='Демонстрационный тариф для прототипа, рассчитан от справочной цены каталога. Наличие и стоимость на выбранные даты не подтверждены Островком.')


def select_hotels(candidates, spec, cheaper=False, include_conflicts=False):
    from . import journey
    chosen, rejected, base_prices = [], {}, []
    prefs = spec.hotel_preferences
    for original in candidates:
        hotel = dict(original)
        reasons, failures = [], []
        codes = hotel.get('amenity_codes', [])
        if spec.travel_setting in {'forest', 'nature', 'mountains'}:
            # Public catalogue does not prove wild forest on the property. Restrict
            # candidates to explicitly named rural formats, never urban apartments.
            rural = hotel.get('property_kind') in {'COTTAGE','CAMPING','GLAMPING'} or re.search(r'база\s*отдыха|гл[эе]мпинг|кемпинг|коттедж|шале|частный дом|турбаза|эко.?отель|загородн', hotel.get('name',''), re.I)
            if re.search(r'в центре|центра города|городск\w* квартир', hotel.get('name',''), re.I): rural = False
            if not rural: failures.append('загородный формат')
            else: reasons.append('Домик или загородный формат размещения')
        for field, (code, label) in AMENITY_LABELS.items():
            required = getattr(prefs, field)
            if required is True:
                if code in codes: reasons.append(label + ' в отеле')
                else: failures.append(label.lower())
            elif required is False and code in codes:
                failures.append('без ' + label.lower())
        for field, key, label in [('max_center_m', 'distance_m', 'До центра'), ('max_beach_m','beach_m','До пляжа')]:
            limit, distance = getattr(prefs,field), hotel.get(key)
            if limit is not None:
                if distance is None or distance > limit: failures.append(label.lower())
                else:
                    shown=(f'{distance/1000:.1f}'.rstrip('0').rstrip('.').replace('.',',')+' км') if distance>=1000 else f'{round(distance)} м'
                    reasons.append(f'{label} {shown}')
        if prefs.min_rating is not None and (hotel.get('rating') is None or hotel['rating'] < prefs.min_rating): failures.append('рейтинг')
        if prefs.min_stars is not None and (hotel.get('stars') is None or hotel['stars'] < prefs.min_stars): failures.append('звёздность')
        if spec.hard_constraints.pets:
            if 'has_pets' in codes: reasons.append('В каталоге разрешены питомцы; условия уточняются')
            else: failures.append('размещение с питомцем')
        quote = demo_quote(hotel,spec)
        value = quote and (quote['nightly_minor'] if spec.budget_period == 'night' else quote['total_minor'])
        trip = journey.quote(hotel, spec, quote) if journey.enabled(spec) and quote else None
        if journey.enabled(spec):
            if trip is None:
                failures.append('нет подключённого маршрута')
            else:
                hotel['journey'] = trip
                value = trip['total_minor']
                if not include_conflicts:
                    failures.extend(c['message'] for c in trip['checks'] if c['blocking'] and c['status'] == 'fail')
        if not failures and value is not None: base_prices.append(value)
        if spec.budget and not journey.enabled(spec):
            if value is None: failures.append('не хватает данных для цены')
            elif value > spec.budget.amount_minor:
                if not include_conflicts: failures.append('бюджет')
            else: reasons.append('В вашем бюджете')
        if failures:
            for reason in set(failures): rejected[reason]=rejected.get(reason,0)+1
            continue
        if prefs.breakfast is True: reasons.append('Завтрак учтён в стоимости' if hotel.get('source_kind')=='public' else 'Завтрак включён')
        if spec.hard_constraints.free_cancellation: reasons.append('Отмена требует подтверждения тарифа' if hotel.get('source_kind')=='public' else 'Бесплатная отмена')
        if trip and trip['can_book']:
            reasons.insert(0, 'Дорога на автомобиле включена; отдельные трансферы не нужны' if (trip.get('transport') or {}).get('kind')=='car' else 'Дорога и оба трансфера включены')
        if hotel.get('rating') is not None: reasons.append(f'Оценка гостей {hotel["rating"]:g}/10')
        if trip and not trip['can_book']: reasons.append('Есть условия, требующие уточнения перед оформлением')
        if not reasons: reasons.append('Подходит по заданным условиям каталога')
        score = (hotel.get('rating') or 0)*10 + min(math.log1p(hotel.get('reviews') or 0),8)
        if spec.travel_setting in {'forest','nature','mountains'} and re.search(r'пос[её]лок|деревня|дер\.|село',hotel.get('address',''),re.I): score += 15
        if prefs.max_center_m is not None: score += 15*(1-(hotel.get('distance_m') or 0)/max(prefs.max_center_m,1))
        if prefs.max_beach_m is not None: score += 15*(1-(hotel.get('beach_m') or 0)/max(prefs.max_beach_m,1))
        hotel.update(reasons=reasons, quote=quote, match_score=round(score,2), unverified=list(spec.preferences)+list(spec.hard_constraints.other)+(['Лес у дома и степень уединения'] if spec.travel_setting in {'forest','nature','mountains'} else []))
        # The reference price is only an input to the demo adapter, never a live offer.
        hotel.pop('reference_nightly_minor',None)
        chosen.append(hotel)
    cost = lambda h: (h.get('journey') or {}).get('total_minor') or (h.get('quote') or {}).get('nightly_minor') or float('inf')
    chosen.sort(key=lambda h: (cost(h), -h['match_score']) if cheaper else (-h['match_score'], cost(h)))
    info=dict(considered=len(candidates), matched=len(chosen), rejected=rejected,
              min_budget_minor=min(base_prices) if base_prices else None,
              pricing_mode='demo', journey_mode=journey.enabled(spec), sort='price' if cheaper else 'match',
              unverified=list(spec.preferences)+list(spec.hard_constraints.other)+(['Лес у дома и степень уединения'] if spec.travel_setting in {'forest','nature','mountains'} else []))
    return chosen[:3],info


def missing_hotel_questions(spec):
    from . import journey
    if not spec.destination: return ['В каком городе ищем отель?']
    if not spec.travellers.adults: return ['Сколько взрослых поедет? Будут ли дети?']
    if any(age is None for age in spec.travellers.children): return [f'Сколько лет каждому из {len(spec.travellers.children)} детей? Укажите возраста списком.']
    if not spec.dates and not spec.stay_nights: return ['На какие даты или на сколько ночей ищем отель?']
    if journey.enabled(spec):
        missing = journey.questions(spec)
        if missing: return missing
    if not spec.budget: return ['Какой общий бюджет на отель, дорогу и трансферы?'] if journey.enabled(spec) else ['Какой бюджет на проживание за весь отдых? Можно указать сумму за ночь.']
    return []


def rub(amount):
    return f'{amount/100:,.0f}'.replace(',',' ')+' ₽'


def response_text(hotels, info, spec, patch, cheaper=False):
    changed=[]
    labels={'destination':'направление','dates':'даты','budget':'бюджет','travellers':'состав гостей','hotel_preferences':'пожелания к отелю','stay_nights':'число ночей','hard_constraints':'обязательные условия','preferences':'пожелания'}
    for key,label in labels.items():
        if key in patch:changed.append(label)
    intro=('Учёл '+', '.join(changed)+'. ') if changed else ('Сравнил варианты по цене. ' if cheaper else 'Проверил ваши условия. ')
    if not hotels:
        text=intro+f'Среди {info["considered"]} отелей сейчас нет варианта, который проходит все условия. '
        if info['min_budget_minor'] and spec.budget and info['min_budget_minor']>spec.budget.amount_minor:
            text+='Самый доступный вариант с остальными пожеланиями — '+rub(info['min_budget_minor'])+(' за всю поездку' if info.get('journey_mode') else ' за ночь' if spec.budget_period=='night' else ' за проживание')+'. '
        elif info['rejected']:text+='Не подошли по условиям: '+', '.join(list(info['rejected'])[:4])+'. '
        return text+'Что готовы изменить? Самостоятельно условия не ослабляю.'
    first=hotels[0]
    text=intro+f'Сравнил {info["considered"]} отелей, вашим условиям соответствуют {info["matched"]}. '
    text+=('Сначала более доступные. ' if cheaper else 'Показываю лучшие по соответствию и оценкам гостей. ')
    text+=first['name']+' — '+'; '.join(first['reasons'][:3]).lower()+'.'
    if any(h.get('journey') and not h['journey']['can_book'] for h in hotels):
        text+=' Расчёт сохранён: неподтверждённые услуги и ограничения перечислены в карточке; они не означают, что отель недоступен.'
    if info['unverified']:text+=' Отдельно уточнить у отеля: '+', '.join(info['unverified'][:3])+'.'
    return text


def explain_hotels(hotels, reference=None):
    selected=hotels[reference-1:reference] if reference else hotels
    if not selected:return 'Сначала подберём варианты, затем смогу сравнить их и объяснить выбор.'
    parts=[]
    for h in selected:
        text=h['name']+': '+('; '.join(h.get('reasons',[])) or 'данные доступны в карточке')+'.'
        quote=h.get('quote')
        if h.get('journey'): text+=' Вся поездка: '+rub(h['journey']['total_minor'])+'. Дорога и оба трансфера включены.'
        elif quote: text+=' Стоимость: '+rub(quote['total_minor'] or quote['nightly_minor'])+(' за проживание.' if quote['total_minor'] else ' за ночь.')
        text+=' Удобства: '+', '.join(h.get('amenities',[]))+'.'
        if h.get('unverified'):text+=' Требуют уточнения: '+', '.join(h['unverified'])+'.'
        parts.append(text)
    return '\n\n'.join(parts)

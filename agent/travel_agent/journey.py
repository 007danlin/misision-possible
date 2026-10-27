"""Deterministic, source-labelled hotel + transport + transfer quotes.

The model never supplies prices, schedules or validation outcomes. The same
function is used for search, edits and Core's pre-booking revalidation.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

CATALOGUE = json.loads(Path(__file__).with_name('journey_catalogue.json').read_text())
ZONE = ZoneInfo(CATALOGUE['timezone'])
ROUTES = CATALOGUE['routes']
ROUTES.update({'Санкт-Петербург':dict(kind='train',label='Поезд',origin_terminal='Москва · Ленинградский вокзал',terminal='Санкт-Петербург · Московский вокзал',out_departure='08:00',out_minutes=240,return_departure='18:00',return_minutes=240,roundtrip_minor=1000000,airport_buffer=45),
               'Владимир':dict(kind='train',label='Поезд',origin_terminal='Москва · вокзал',terminal='Владимир · вокзал',out_departure='09:00',out_minutes=120,return_departure='18:00',return_minutes=120,roundtrip_minor=300000,airport_buffer=45)})


def enabled(spec):
    return spec.include_transport or spec.budget_scope in {'whole_trip', 'booking'}


def candidates(spec):
    return [deepcopy(h) for h in CATALOGUE['hotels'] if h['destination'] == spec.destination]


def questions(spec):
    if not spec.origin:
        return ['Из какого города отправляетесь?']
    if not spec.dates:
        return ['На какие точные даты собрать дорогу, отель и трансферы?']
    if spec.transport_owned and not spec.owned_transport:
        return ['Укажите время прибытия, обратного отправления и аэропорт или вокзал в разделе «Ваши билеты». По ним рассчитаем трансферы.']
    if spec.duration_days and spec.duration_days != (spec.dates.end-spec.dates.start).days+1:
        return ['Даты и число дней различаются. Какие даты оставить для поездки?']
    if spec.budget_scope == 'whole_trip' and spec.expense_reserve is None:
        return ['Сколько из общего бюджета оставить на питание и личные расходы? Можно написать «резерв 0 рублей».']
    return []


def at(day, clock):
    return datetime.fromisoformat(f'{day}T{clock}').replace(tzinfo=ZONE)


def quote(hotel, spec, hotel_quote):
    """None means there is no connected route; never invent a supported route."""
    if hotel.get('source_kind')=='public':
        from .transport import build
        return build(hotel,spec,hotel_quote)
    route = ROUTES.get(spec.destination)
    content = hotel.get('content') or {}
    public = hotel.get('source_kind') == 'public'
    estimate = None
    original_content = content
    if public:
        from .trip_context import transfer_estimate
        estimate = transfer_estimate(hotel,spec)
        content = dict(content,room_capacity=2,vehicle_capacity=3,transfer_minutes=estimate['minutes'],transfer_oneway_minor=estimate['oneway_minor'],checkin_from=content.get('checkin_from') or '14:00',checkin_until=content.get('checkin_until') or '23:59',checkout_until=content.get('checkout_until') or '12:00',baggage='Багаж и класс автомобиля нужно подтвердить',children_allowed=None,child_seats=None,pets_allowed=None)
    if (not spec.dates or not spec.travellers.adults or spec.origin != CATALOGUE['origin']
            or not route or hotel.get('source_kind') not in {'synthetic','public'} or not content):
        return None
    guests = spec.travellers.adults + len(spec.travellers.children)
    cars = math.ceil(guests / content['vehicle_capacity'])
    children = spec.travellers.children
    out = at(spec.dates.start, route['out_departure'])
    arrival = out + timedelta(minutes=route['out_minutes'])
    back = at(spec.dates.end, route['return_departure'])
    back_arrival = back + timedelta(minutes=route['return_minutes'])
    collect_minutes = 45 if route['kind'] == 'flight' else 15
    transfer_start = arrival + timedelta(minutes=collect_minutes)
    transfer_end = transfer_start + timedelta(minutes=content['transfer_minutes'])
    checkin = at(spec.dates.start, content['checkin_from'])
    last_checkin = at(spec.dates.start, content['checkin_until'])
    checkout = at(spec.dates.end, content['checkout_until'])
    return_start = min(checkout, back - timedelta(minutes=route['airport_buffer'] + content['transfer_minutes']))
    return_end = return_start + timedelta(minutes=content['transfer_minutes'])
    transport_cost = route['roundtrip_minor'] * guests
    transfers_cost = content['transfer_oneway_minor'] * cars * 2
    breakdown = dict(hotel=hotel_quote['total_minor'], transport=transport_cost, transfers=transfers_cost, fees=0)
    total = sum(breakdown.values())
    reserve = spec.expense_reserve.amount_minor if spec.expense_reserve else 0
    ceiling = spec.trip_budget or (spec.budget if spec.budget_scope in {'booking', 'whole_trip'} else None)
    hotel_limit = spec.hotel_budget or (spec.budget if spec.budget_scope in {None, 'hotel'} else None)
    hotel_value = hotel_quote['nightly_minor'] if spec.budget_period == 'night' else hotel_quote['total_minor']
    checks = []

    def check(code, ok, message, blocking=True):
        checks.append(dict(code=code, status='unknown' if ok is None else 'pass' if ok else 'fail', message=message, blocking=blocking))

    check('dates', date.fromisoformat(CATALOGUE['start']) <= spec.dates.start < spec.dates.end <= date.fromisoformat(CATALOGUE['end']),
          'Расписание и тарифы рассчитаны для ноября–декабря 2026.')
    check('checkin', transfer_end <= last_checkin, 'Прибытие в отель ' + transfer_end.strftime('%d.%m %H:%M') + ', заселение до ' + content['checkin_until'] + '.')
    check('return', return_end + timedelta(minutes=route['airport_buffer']) <= back and return_start > max(checkin, transfer_end),
          f'До отправления оставлен запас {route["airport_buffer"]} мин.; выезд из отеля {return_start:%d.%m %H:%M}.')
    check('capacity', hotel_quote['rooms'] * content['room_capacity'] >= guests and cars * content['vehicle_capacity'] >= guests,
          f'Размещение для {guests} гостей; машин: {cars}, до {content["vehicle_capacity"]} пассажиров в каждой.')
    if children:
        check('children', content.get('children_allowed') and content.get('child_seats') and all(a is not None for a in children),
              'Возраст детей учтён; детские кресла включены в трансфер.')
    if spec.hard_constraints.pets:
        check('pets', content.get('pets_allowed'), 'Размещение и трансфер с питомцем должны быть подтверждены.')
    if spec.hard_constraints.no_night_flights and route['kind'] == 'flight':
        daylight = all(6 <= t.hour < 23 for t in [out, arrival, back, back_arrival]) and out.date() == arrival.date() and back.date() == back_arrival.date()
        check('no_night_flights', daylight, 'Перелёты проходят между 06:00 и 23:00 по местному времени.')
    if spec.hard_constraints.free_cancellation:
        check('cancellation', hotel_quote['free_cancellation'], 'В расчёте выбран возвратный состав поездки.')
    if spec.hard_constraints.other:
        check('other', None, 'Не подтверждены обязательные условия: ' + ', '.join(spec.hard_constraints.other))
    if ceiling:
        check('budget', total + reserve <= ceiling.amount_minor, 'Итог с резервом ' + f'{(total+reserve)/100:,.0f}'.replace(',', ' ') + ' ₽; общий лимит ' + f'{ceiling.amount_minor/100:,.0f}'.replace(',', ' ') + ' ₽.')
    if hotel_limit:
        check('hotel_budget', hotel_value <= hotel_limit.amount_minor, 'Стоимость проживания проверена отдельно от общего лимита.')
    if transfer_end < checkin:
        check('early_arrival', True, f'Приезд раньше заселения: ожидание до {content["checkin_from"]}. Ранний заезд не включён.', False)
    if public:
        for c in checks:
            if c['code']=='capacity':c.update(status='unknown',blocking=False,message=f'Расчёт: {hotel_quote["rooms"]} номеров по 2 места и {cars} автомобилей по 3 пассажира. Категория и вместимость требуют подтверждения.')
            if c['code']=='children':c.update(status='unknown',message='Размещение детей и наличие детских кресел не подтверждены поставщиком.')
            if c['code']=='cancellation':c.update(status='unknown',message='Бесплатная отмена для номера, дороги и трансферов не подтверждена на выбранные даты.')
            if c['code']=='checkin':
                if original_content.get('reception_24h') and transfer_end.date()==spec.dates.start:c.update(status='pass',message='По данным карточки стойка работает круглосуточно; расчётное прибытие '+transfer_end.strftime('%H:%M')+'.')
                elif not original_content.get('checkin_until'):c.update(status='unknown',blocking=False,message='Расчётное прибытие '+transfer_end.strftime('%H:%M')+'; предельное время заселения не указано.')
        check('supplier_confirmation',None,'Расписание, тариф, багаж, питание и доплаты нужно подтвердить. Сохранение плана не бронирует услуги.',False)
    cancellation_until = (out - timedelta(days=2)).isoformat() if hotel_quote['free_cancellation'] else None
    def segment(kind, label, origin, destination, start, end):
        return dict(kind=kind, label=label, origin=origin, destination=destination, departure=start.isoformat(), arrival=end.isoformat(), timezone=CATALOGUE['timezone'], duration_minutes=int((end-start).total_seconds()/60))
    segments = [
        segment(route['kind'], route['label'] + ' туда', route['origin_terminal'], route['terminal'], out, arrival),
        segment('transfer', 'Трансфер в отель', route['terminal'], hotel['name'], transfer_start, transfer_end),
        segment('transfer', 'Обратный трансфер', hotel['name'], route['terminal'], return_start, return_end),
        segment(route['kind'], route['label'] + ' обратно', route['terminal'], route['origin_terminal'], back, back_arrival),
    ]
    return dict(version=CATALOGUE['version'], source_kind='estimate' if public else 'synthetic', currency='RUB', total_minor=total,
                breakdown=breakdown, reserve_minor=reserve, budget_minor=ceiling.amount_minor if ceiling else None,
                segments=segments, checks=checks, can_book=all(c['status']=='pass' for c in checks if c['blocking']),
                vehicles=cars, child_seats=len(children), baggage=content['baggage'],
                cancellation_until=None if public else cancellation_until, checkin_from=checkin.isoformat(), checkout_until=checkout.isoformat(),
                transfer_estimate=estimate, unknown_costs=['Сборы и доплаты объекта на месте; см. правила'] if public else [],
                notice='Отель, фото, удобства и доступные отзывы — с публичной страницы Островка. Общая сумма, дорога и трансферы — оценка для планирования; наличие на даты и фактическое расписание не подтверждены.' if public else CATALOGUE['notice'])


def reprice(spec, hotel_id):
    """Rebuild only from canonical catalogue data, never a serialized price."""
    from .hotel_selection import select_hotels
    pool = [h for h in candidates(spec) if h['id'] == hotel_id]
    if not pool:
        from .public_content import recall
        h=recall(hotel_id)
        if h and h.get('destination')==spec.destination:pool=[h]
    # Keep an over-budget or incompatible proposal visible for explicit correction.
    results, _ = select_hotels(pool, spec, include_conflicts=True)
    return results[0] if results else None


def review_answer(hotel, message=''):
    reviews = hotel.get('review_items') or []
    if not reviews:
        return 'Отзывы можно прочитать на странице отеля на Островке.'
    if hotel.get('source_kind')=='public':
        import re
        from .public_content import THEMES
        themes=[theme for theme,pattern in THEMES.items() if re.search(pattern,message,re.I)] or list(THEMES)
        parts=[]
        for theme in themes:
            s=hotel.get('review_summary',{}).get(theme,{})
            if s.get('mention_ids'):parts.append(f'{theme}: положительных отзывов — {len(s["positive_ids"])}, с замечаниями — {len(s["negative_ids"])}.')
        count=len(reviews);word='отзыв' if count%10==1 and count%100!=11 else 'отзыва' if count%10 in {2,3,4} and count%100 not in {12,13,14} else 'отзывов'
        return hotel['name']+f': показываем {count} {word}'+(f' из {hotel["reviews"]} на Островке. ' if hotel.get('reviews') else '. ')+(' '.join(parts) if parts else 'Среди показанных отзывов нет отзывов на эту тему.')+' Прочитать их целиком можно в разделе «Отзывы».'
    return hotel['name'] + ': ' + ' '.join(f'{r["theme"]}: {r["text"]}' for r in reviews[:3]) + ' Все тексты доступны в разделе «Отзывы»; происхождение — в информации о расчёте.'

"""Planning alternatives. No carrier inventory, booking or fabricated flight numbers."""
from datetime import datetime,timedelta
from pathlib import Path
import json,math,time,threading
import httpx
from .trip_context import distance

CENTRES={'Москва':(55.7558,37.6173),'Сочи':(43.5855,39.7231),'Казань':(55.7961,49.1064),'Ярославль':(57.6261,39.8938),'Сортавала':(61.703,30.691),'Санкт-Петербург':(59.9343,30.3351),'Владимир':(56.129,40.406)}
STATIONS={'Москва':(55.776,37.655),'Сочи':(43.5914,39.7277),'Казань':(55.7886,49.099),'Ярославль':(57.6253,39.833),'Сортавала':(61.6967,30.6913),'Санкт-Петербург':(59.9303,30.3623),'Владимир':(56.1295,40.4202)}
AIRPORTS={'Москва':(55.9726,37.4146),'Сочи':(43.4499,39.9566),'Казань':(55.6062,49.2787),'Санкт-Петербург':(59.8003,30.2625)}
# These are explicit planning assumptions for a known corridor, not a timetable.
RAIL={frozenset(('Москва','Сочи')):(1500,1600000),frozenset(('Москва','Казань')):(750,800000),frozenset(('Москва','Ярославль')):(210,350000),frozenset(('Москва','Сортавала')):(900,1000000),frozenset(('Москва','Санкт-Петербург')):(240,1000000),frozenset(('Москва','Владимир')):(120,300000),frozenset(('Санкт-Петербург','Сортавала')):(240,500000)}
AIR={frozenset(('Москва','Сочи')):(240,1800000),frozenset(('Москва','Казань')):(100,1200000),frozenset(('Москва','Санкт-Петербург')):(90,1000000),frozenset(('Санкт-Петербург','Сочи')):(270,2200000),frozenset(('Санкт-Петербург','Казань')):(150,1600000)}
_ROAD={};_lock=threading.Lock();_last=0

def city_point(name):
    if name in CENTRES:return CENTRES[name]
    p=Path(__file__).with_name('cities.json')
    if p.exists():
        matches=[c for c in json.loads(p.read_text())['cities'] if c['name'].casefold()==(name or '').casefold()]
        if len(matches)==1:return matches[0]['lat'],matches[0]['lng']
    return None

def road_key(origin,destination):return origin+'|'+destination

async def prepare_road(spec):
    """At most one request/second globally; city-pair cache, no route scraping."""
    global _last
    a,b=city_point(spec.origin),city_point(spec.destination)
    if not a or not b or spec.origin==spec.destination:return
    key=road_key(spec.origin,spec.destination);cached=_ROAD.get(key)
    if cached and time.time()-cached['retrieved']<86400:return
    with _lock:
        if time.monotonic()-_last<1.1:return
        _last=time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5,headers={'User-Agent':'OPlan-Hackathon/1.0 (local travel planner)'}) as client:
            r=await client.get(f'https://routing.openstreetmap.de/routed-car/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}',params={'overview':'false','steps':'false'});r.raise_for_status();v=r.json()['routes'][0]
        km=v['distance']/1000;minutes=math.ceil(v['duration']/60)
        if not 1<km<20000 or not 1<minutes<30000:return
        _ROAD[key]={'km':km,'minutes':minutes,'retrieved':time.time(),'source_url':'https://routing.openstreetmap.de/about.html','source':'OSRM · © OpenStreetMap contributors'}
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError):pass

def available(spec,hotel):
    a,b=city_point(spec.origin),city_point(spec.destination)
    if not a or not b or spec.origin==spec.destination:return []
    pair=frozenset((spec.origin,spec.destination));options=[]
    for mode,table,label in [('flight',AIR,'Самолёт'),('train',RAIL,'Поезд')]:
        if pair not in table:continue
        mins,cost=table[pair]
        options.append(dict(id=mode,kind=mode,label=label,minutes=mins,roundtrip_minor=cost,price_unit='person',terminal=(AIRPORTS if mode=='flight' else STATIONS)[spec.destination],terminal_name=spec.destination+(' · аэропорт' if mode=='flight' else ' · вокзал'),origin_terminal=spec.origin+(' · аэропорт' if mode=='flight' else ' · вокзал'),buffer=120 if mode=='flight' else 45,collect=45 if mode=='flight' else 15,connections=None,assumptions='Плановый прямой путь. Время и тариф — редакционные ориентиры; рейс, пересадки, багаж и наличие на даты не подтверждены.',source_url='https://www.rzd.ru/' if mode=='train' else 'https://www.aeroflot.ru/',source='Редакционная модель; расписание поставщика не подключено',benefit='Быстрее на дальнем направлении' if mode=='flight' else 'Прибытие в город, меньше времени на формальности',tradeoff='Нужен запас в аэропорту; багаж оплачивается по тарифу' if mode=='flight' else 'Дальняя дорога может включать ночь; места и багаж зависят от тарифа'))
    rail=(hotel.get('rail_reference') or {}).get(road_key(spec.origin,spec.destination))
    if rail and time.time()-rail.get('retrieved',0)<21600:
        for option in options:
            if option['kind']=='train':
                option.update(minutes=rail['out']['minutes'],return_minutes=rail['back']['minutes'],roundtrip_minor=rail['out']['price_minor']+rail['back']['price_minor'],out_clock=rail['out']['departure_time'],back_clock=rail['back']['departure_time'],source=rail['source'],source_url=rail['source_url'],reference_checked_at=datetime.fromtimestamp(rail['retrieved']).isoformat(),assumptions='Время и базовая цена взяты из кэша Туту в обе стороны. Дни курсирования, наличие мест, категория и цена на ваши даты не проверены. Это ориентир для планирования, не предложение билетов.')
    from .travelpayouts import key as air_key,valid_for
    air=(hotel.get('air_reference') or {}).get(air_key(spec))
    if air and valid_for(air,spec):
        for option in options:
            if option['kind']=='flight':option.update(minutes=air['minutes'],return_minutes=air['return_minutes'],roundtrip_minor=air['roundtrip_minor'],exact_departure=air['departure'],exact_return=air['return_departure'],source=air['source'],source_url=air['source_url'],connections=0,reference_checked_at=datetime.fromtimestamp(air['retrieved']).isoformat(),assumptions='Кэш прямых перелётов Aviasales на ваши даты; цена на одного взрослого туда-обратно. Наличие, багаж и итоговый тариф требуют перепроверки. Путь до аэропорта отправления не включён.')
    road=_ROAD.get(road_key(spec.origin,spec.destination)) or (hotel.get('road_routes') or {}).get(road_key(spec.origin,spec.destination))
    direct=distance(a,b);km=road['km'] if road else direct*1.35;moving=road['minutes'] if road else math.ceil(km/65*60)
    # Rest estimate: 15 minutes every 2 hours, 8-hour overnight rest after 10h driving.
    rest=(moving//120)*15+max(0,(moving-1)//600)*480
    options.append(dict(id='car',kind='car',label='Автомобиль',minutes=moving+rest,roundtrip_minor=math.ceil(km*2*.09*65/100)*10000,price_unit='car',terminal=b,terminal_name=spec.destination,origin_terminal=spec.origin,buffer=0,collect=0,connections=0,road_km=round(km),driving_minutes=moving,rest_minutes=rest,source_url=road['source_url'] if road else 'https://github.com/hflabs/city',source=road['source'] if road else 'Оценка по координатам HFLabs / DaData',assumptions=('OSRM: путь по дорогам без живых пробок. ' if road else 'Путь ≈ расстояние по прямой × 1,35; средняя скорость 65 км/ч. ')+'Отсчёт от центра города отправления. Своё авто на 4 человека; топливо 9 л/100 км × 65 ₽/л; платные дороги, парковки и ночлег не включены. Отдых: 15 мин/2 ч, 8 ч после 10 ч езды.',benefit='До отеля на своём авто; стоимость делится на гостей',tradeoff='Нужен свой автомобиль и водитель; дополнительные расходы и остановки'))
    for option in options:
        if option['kind'] in {'flight','train'}:
            option['assumptions'] += ' Полное время включает ожидание в терминале и трансфер до отеля; дорога из дома до терминала отправления не рассчитана.'
    return options

def road_snapshot(spec):
    key=road_key(spec.origin,spec.destination)
    return {key:_ROAD[key]} if key in _ROAD else {}

def build(hotel,spec,q,route=None,alternatives=True):
    from .journey import at
    if not spec.origin or not spec.dates or not spec.travellers.adults:return None
    options=available(spec,hotel)
    owned=spec.owned_transport if spec.transport_owned else None
    if spec.transport_owned and not owned:return None
    if owned:
        point=(AIRPORTS if owned.terminal=='airport' else STATIONS).get(spec.destination)
        if not point:return None
        route=dict(id='owned',kind='owned',label='Ваши билеты',minutes=0,roundtrip_minor=owned.paid_total_minor or 0,price_unit='booking',terminal=point,terminal_name=spec.destination+(' · аэропорт' if owned.terminal=='airport' else ' · вокзал'),origin_terminal=spec.origin,buffer=120 if owned.terminal=='airport' else 45,collect=45 if owned.terminal=='airport' else 15,connections=None,source='Время и оплаченная сумма указаны вами',source_url=None,assumptions='Приложение не проверяет билеты у перевозчика. Время прибытия и обратного отправления — из ваших данных.',benefit='Уже приобретённая дорога сохранена',tradeoff='Проверяются переданные вами даты и стыковки')
    elif route is None:
        if spec.transport_mode=='auto':
            # A conflicting cheap flight must not hide a viable train/car trip.
            auto_options=[o for o in options if spec.transfer_provider!='hotel' or o['kind']!='car']
            route=next((option for option in auto_options if (candidate:=build(hotel,spec,q,option,False)) and not any(c['blocking'] and c['status']=='fail' for c in candidate['checks'])),auto_options[0] if auto_options else None)
        else:route=next((r for r in options if r['id']==spec.transport_mode),None)
    if not route:return None
    route=dict(route);guests=spec.travellers.adults+len(spec.travellers.children);car=route['kind']=='car';cars=math.ceil(guests/(4 if car else 3));c=hotel.get('content') or {};coords=hotel.get('coordinates') or {};point=route['terminal'];hotelpoint=(coords.get('lat',point[0]),coords.get('lng',point[1]));local_km=distance(point,hotelpoint)*1.5
    if car:
        extra_minutes=math.ceil(local_km/30*60);route['minutes']+=extra_minutes;route['roundtrip_minor']+=math.ceil(local_km*2*.09*65/100)*10000
    transfer_minutes=0 if car else max(20,math.ceil(local_km/35*60+15));unit=math.ceil((800+local_km*45)/100)*10000;transfers=0 if car else unit*cars*2
    service=c.get('transfer_service') or {};hotel_transfer=spec.transfer_provider=='hotel' and not car
    if hotel_transfer and not service.get('listed'):return None
    transfer_choice={'provider':'hotel' if hotel_transfer else 'estimate','label':'Трансфер отеля по запросу' if hotel_transfer else 'Трансфер до отеля','source_url':hotel.get('url') if hotel_transfer else None,'status':'on_request' if hotel_transfer else 'estimate','notice':'Услуга указана в карточке Островка. Стоимость в плане остаётся оценочной: отель ещё не подтвердил тариф, маршрут и время.' if hotel_transfer else 'Расчёт по расстоянию; поставщик и подача не подтверждены.'}
    checkin=at(spec.dates.start,c.get('checkin_from') or '14:00');checkout=at(spec.dates.end,c.get('checkout_until') or '12:00')
    if owned:arrival=owned.arrival;back=owned.departure;out=arrival;back_arrival=back
    else:
        arrival=at(spec.dates.start,'12:00');out=arrival-timedelta(minutes=route['minutes']);back=checkout+timedelta(minutes=transfer_minutes+route['buffer']+30);back_arrival=back+timedelta(minutes=route.get('return_minutes',route['minutes']))
        if route.get('out_clock'):
            out=at(spec.dates.start,route['out_clock']);arrival=out+timedelta(minutes=route['minutes']);out-=timedelta(days=(arrival.date()-spec.dates.start).days);arrival=out+timedelta(minutes=route['minutes']);back=at(spec.dates.end,route['back_clock']);back_arrival=back+timedelta(minutes=route.get('return_minutes',route['minutes']))
        if route.get('exact_departure'):
            out=datetime.fromisoformat(route['exact_departure']);arrival=out+timedelta(minutes=route['minutes']);back=datetime.fromisoformat(route['exact_return']);back_arrival=back+timedelta(minutes=route['return_minutes'])
    ts=arrival+timedelta(minutes=route['collect']);te=ts+timedelta(minutes=transfer_minutes);rs=min(checkout,back-timedelta(minutes=route['buffer']+transfer_minutes));re=rs+timedelta(minutes=transfer_minutes)
    if car:te=arrival;rs=checkout;back=checkout;back_arrival=back+timedelta(minutes=route['minutes'])
    transport=route['roundtrip_minor']*(cars if route['price_unit']=='car' else guests if route['price_unit']=='person' else 1)
    breakdown=dict(hotel=q['total_minor'],transport=transport,transfers=transfers,fees=0);total=sum(breakdown.values());reserve=spec.expense_reserve.amount_minor if spec.expense_reserve else 0;ceiling=spec.trip_budget or (spec.budget if spec.budget_scope in {'booking','whole_trip'} else None);limit=spec.hotel_budget or (spec.budget if spec.budget_scope=='hotel' else None);checks=[]
    def check(code,status,text,blocking=True):checks.append(dict(code=code,status='unknown' if status is None else 'pass' if status else 'fail',message=text,blocking=blocking))
    check('dates',spec.dates.start<spec.dates.end,'Даты проживания согласованы.')
    if not owned:check('departure_future',out>datetime.now(out.tzinfo),'Расчётное отправление должно быть в будущем.')
    check('checkin',te.date()==spec.dates.start and (not c.get('checkin_until') or c.get('reception_24h') or te<=at(spec.dates.start,c['checkin_until'])),'Расчётное прибытие в отель '+te.strftime('%d.%m %H:%M')+'.')
    check('return',rs>max(checkin,te) and (car or re+timedelta(minutes=route['buffer'])<=back),'Выезд из отеля '+rs.strftime('%d.%m %H:%M')+f'; запас перед отправлением {route["buffer"]} мин.')
    def night(a,b):
        t=a
        while t<b:
            if t.hour<6 or t.hour>=23:return True
            t+=timedelta(minutes=30)
        return b.hour<6 or b.hour>=23
    overnight=False if owned else night(out,arrival) or night(back,back_arrival)
    if spec.hard_constraints.no_night_flights and route['kind']=='flight':check('no_night_flights',not overnight,'Проверены плановые часы перелёта: без участков 23:00–06:00.')
    if spec.hard_constraints.no_night_travel:check('no_night_travel',None if owned else not overnight,'Ночные участки '+('неизвестны для ваших билетов' if owned else 'есть' if overnight else 'в расчёте отсутствуют')+'.')
    if spec.hard_constraints.no_connections:check('no_connections',True if car or route.get('exact_departure') else None,'Автомобиль без пересадок.' if car else 'Найден прямой перелёт на ваши даты. Наличие билетов нужно проверить.' if route.get('exact_departure') else 'Прямой вариант заложен в расчёт, но отсутствие пересадок на даты не подтверждено.')
    if owned and owned.paid_total_minor is None:
        check('owned_price',None,'Стоимость ваших билетов не указана; весь бюджет поездки пока не проверен.',bool(ceiling))
    check('capacity',None,'Вместимость номеров '+('и автомобиля' if car else 'и машины для трансфера')+' нужно уточнить перед поездкой.',False)
    if spec.travellers.children:check('children',None,'Условия размещения детей и детские кресла нужно подтвердить.')
    if spec.hard_constraints.pets:check('pets',None,'Перевозка и размещение питомца не подтверждены.')
    if spec.hard_constraints.free_cancellation:check('cancellation',None,'Отмена по выбранному тарифу не подтверждена.')
    if spec.hard_constraints.other:check('other',None,'Нужно подтвердить: '+', '.join(spec.hard_constraints.other))
    if ceiling:
        excess=total+reserve-ceiling.amount_minor
        amount=f'{max(0,excess)/100:,.0f}'.replace(',',' ')+' ₽'
        check('budget',excess<=0,'Поездка укладывается в общий бюджет.' if excess<=0 else f'Стоимость с резервом выше бюджета на {amount}. Измените условия или увеличьте бюджет.')
    if limit:
        fits=(q['nightly_minor'] if spec.budget_period=='night' else q['total_minor'])<=limit.amount_minor
        check('hotel_budget',fits,'Проживание укладывается в бюджет на отель.' if fits else 'Стоимость проживания выше бюджета на отель.')
    if te<checkin:check('early_arrival',True,'До заселения потребуется ожидание; ранний заезд не включён.',False)
    check('supplier_confirmation',None,'Цены и плановые часы требуют подтверждения; сохранение плана не бронирует услуги.',False)
    def seg(kind,label,start,end,origin,destination,hotel_end=False):return dict(kind=kind,label=label,origin=origin,destination=destination,departure=start.isoformat(),arrival=end.isoformat(),timezone='Europe/Moscow',duration_minutes=int((end-start).total_seconds()/60),ends_at_hotel=hotel_end,estimated=not owned)
    if hotel_transfer:check('hotel_transfer',None,'Трансфер отеля выбран для плана. Запрос ещё не отправлен; подача и тариф не подтверждены.',False)
    if car:segments=[seg('car','На своём автомобиле',out,arrival,spec.origin,hotel['name'],True),seg('car','Обратная дорога',back,back_arrival,hotel['name'],spec.origin)]
    else:segments=[seg(route['kind'],route['label']+' туда',out,arrival,route['origin_terminal'],route['terminal_name']),seg('transfer','Трансфер в отель',ts,te,route['terminal_name'],hotel['name'],True),seg('transfer','Обратный трансфер',rs,re,hotel['name'],route['terminal_name']),seg(route['kind'],route['label']+' обратно',back,back_arrival,route['terminal_name'],route['origin_terminal'])]
    if hotel_transfer:
        for segment in segments:
            if segment['kind']=='transfer':segment['label']='Трансфер отеля по запросу';segment['provider']='hotel'
    if owned:
        for segment in segments:
            if segment['kind']=='owned':segment['duration_minutes']=None;segment['time_partial']='arrival' if segment is segments[0] else 'departure'
            else:segment['estimated']=True
    route.update(total_transport_minor=transport,total_transfers_minor=transfers,full_out_minutes=int((te-out).total_seconds()/60)+route['buffer'],full_return_minutes=int((back_arrival-rs).total_seconds()/60),overnight=overnight if not owned else None,baggage='В пределах вашего автомобиля' if car else 'Нормы багажа по билету нужно уточнить',departure=out.isoformat(),arrival=te.isoformat(),return_departure=rs.isoformat(),return_arrival=back_arrival.isoformat())
    if owned:route['full_out_minutes']=None;route['full_return_minutes']=None
    unknown=['Сборы объекта и доплаты на месте']+(['Платные дороги, парковки, ночлег в пути'] if car else ['Багаж и доплаты перевозчика'])
    if owned and owned.paid_total_minor is None:unknown.append('Стоимость уже купленных билетов не указана и не включена в итог')
    result=dict(transfer_choice=None if car else transfer_choice,total_incomplete=bool(owned and owned.paid_total_minor is None),version='public-trip-v2',source_kind='estimate',currency='RUB',total_minor=total,breakdown=breakdown,reserve_minor=reserve,budget_minor=ceiling.amount_minor if ceiling else None,segments=segments,checks=checks,can_book=all(c['status']=='pass' for c in checks if c['blocking']),vehicles=cars,child_seats=len(spec.travellers.children),baggage=route['baggage'],cancellation_until=None,checkin_from=checkin.isoformat(),checkout_until=checkout.isoformat(),transfer_estimate=None if car else dict(terminal={'lat':point[0],'lng':point[1]},minutes=transfer_minutes,assumptions='Оценка трансфера по координатам: путь × 1,5, 35 км/ч + 15 мин; 800 ₽ + 45 ₽/км. Подача и пробки не подтверждены.'),unknown_costs=unknown,transport=route,notice='Отель, фото и доступные отзывы — с Островка. Цена поездки и часы дороги — оценка; наличие и тарифы на даты не подтверждены.',alternatives=[])
    if alternatives:
        alternative_spec=spec.model_copy(update={"transport_owned":False,"owned_transport":None}) if owned else spec
        for option in options:
            alternate=build(hotel,alternative_spec,q,option,False)
            if alternate:result['alternatives'].append(dict(alternate['transport'],trip_total_minor=alternate['total_minor'],price_delta=alternate['total_minor']-total,can_book=alternate['can_book'],issues=[c['message'] for c in alternate['checks'] if c['blocking'] and c['status']!='pass']))
    return result

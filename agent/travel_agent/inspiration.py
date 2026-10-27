"""Small editorial direction guide. Hotel facts always come from the catalogue."""
NATURE = [
    dict(id='karelia', name='Карелия', destination='Сортавала', scene='forest', reason='Леса и озёра. Ищем домики и базы отдыха в окрестностях Сортавалы.', source_url='https://ostrovok.ru/hotel/russia/sortavala/'),
    dict(id='altai', name='Алтай', destination='Чемал', scene='mountains', reason='Горы и долина Катуни. Сравним загородные варианты в районе Чемала.', source_url='https://ostrovok.ru/hotel/russia/altai_republic_chemal/'),
    dict(id='seliger', name='Селигер', destination='Осташков', scene='forest', reason='Отдых у воды. Посмотрим домики и базы вокруг Осташкова.', source_url='https://ostrovok.ru/hotel/russia/ostashkov/'),
]

def direction_options(spec):
    from .journey import enabled, ROUTES
    from .trip_context import SEASONS
    if enabled(spec):
        cities=["Сортавала","Ярославль","Владимир"] if spec.travel_setting in {"nature","forest","mountains"} else ["Сочи","Санкт-Петербург","Казань"]
        output=[]
        for city in cities:
            route=ROUTES[city];guests=(spec.travellers.adults or 2)+len(spec.travellers.children);nights=(spec.dates.end-spec.dates.start).days if spec.dates else spec.stay_nights or 3
            low=route["roundtrip_minor"]*guests+350000*nights+300000;high=route["roundtrip_minor"]*guests+800000*nights+800000
            reason=SEASONS.get(city,"")
            if spec.origin == "Москва":reason+=f" Из Москвы: около {route['out_minutes']/60:g} ч в одну сторону; ориентир всей поездки {low//100:,}–{high//100:,} ₽ на {guests} гостей и {nights} ночи. Это диапазон при условном размещении в одном номере; точный расчёт после выбора.".replace(","," ")
            elif not spec.origin:reason+=" Укажите город отправления — тогда рассчитаем дорогу и стоимость поездки."
            else:reason+=" Полная дорога из вашего города пока не рассчитана."
            output.append(dict(id=city,name=city,destination=city,scene="forest" if city=="Сортавала" else "sea" if city=="Сочи" else "city",reason=reason))
        return output

    if spec.travel_setting in {'forest','nature','mountains'}:
        return [dict(d) for d in NATURE]
    return [dict(id='sochi',name='Сочи',destination='Сочи',scene='sea',reason='Отдых у моря и прогулки.'),
            dict(id='petersburg',name='Петербург',destination='Санкт-Петербург',scene='city',reason='Архитектура, музеи и прогулки по городу.'),
            dict(NATURE[0])]

def inspiration_text(spec, directions):
    from .journey import enabled
    if enabled(spec):return "Сравним направления по сезону, времени в пути и ориентиру общей стоимости: "+"; ".join(d["name"] for d in directions)+". Выберите место, затем подберём настоящие отели."

    if spec.travel_setting in {'forest','nature','mountains'}:
        return ('Хочется ближе к дикой природе — лес, домик и меньше городской суеты. '
                'Начнём с направления: 1 — Карелия, 2 — Алтай, 3 — Селигер. '
                'Буду искать домики и базы отдыха, а не городские квартиры. '
                'Какое место ближе вашей идее? Можно выбрать карточку или написать словами.')
    return 'Можно начать с идеи: 1 — Сочи, 2 — Петербург, 3 — Карелия. Что ближе: море, городские впечатления или природа?'

"""Authored dialogue acceptance cases: changes, untouched fields and useful replies.

Frozen expectations are user semantics, independent of model output and shortcuts.
Supplier/network services are fixtures in the runner; language inference is real.
"""
BASE = {
    'origin':'Москва', 'destination':'Сочи',
    'dates':{'start':'2026-11-10','end':'2026-11-15'},
    'travellers':{'adults':2,'children':[]},
    'budget':{'amount_minor':12000000}, 'budget_scope':'hotel',
    'hotel_preferences':{'pool':True,'parking':True},
    'preferences':['тихо','подальше от лифта'],
}
CASES=[]

def step(message, expected=None, *, allow=(), status=None, question=None, contains=None):
    return dict(message=message,expected=expected or {},allow=list(allow),status=status,question=question,contains=contains)

def add(name, steps, initial=None, assistant='', questions=None):
    CASES.append(dict(id=name,initial=BASE if initial is None else initial,assistant=assistant,questions=questions or [],steps=steps))

add('family-add-remove',[
    step('С нами ещё один ребёнок, ему 7 лет',{'travellers.children':[7]}),
    step('Добавь ещё ребёнка 5 лет',{'travellers.children':[7,5]}),
    step('Теперь нас трое взрослых',{'travellers.adults':3}),
    step('Дети не поедут, только взрослые',{'travellers.children':[]}),
    step('Нас снова двое взрослых',{'travellers.adults':2}),
])
add('family-age-clarification',[
    step('Добавь ребёнка',{'travellers.children':[None]},status='needs_input',question='лет'),
    step('Ему 6 лет',{'travellers.children':[6]}),
    step('Добавь двух детей',{'travellers.children':[6,None,None]},status='needs_input',question='лет'),
    step('Возраст детей: 6, 4 и 9 лет',{'travellers.children':[6,4,9]}),
])
add('budget-periods-and-decimals',[
    step('Теперь на проживание 65 тысяч рублей за весь отдых',{'budget.amount_minor':6500000,'budget_scope':'hotel','budget_period':'stay'},allow=['hotel_budget']),
    step('Лучше до 12,5 тысяч рублей за ночь',{'budget.amount_minor':1250000,'budget_period':'night'},allow=['hotel_budget']),
    step('Давай 70 000 рублей за всё проживание',{'budget.amount_minor':7000000,'budget_period':'stay'},allow=['hotel_budget']),
    step('Подешевле, бассейн и парковку сохрани'),
])
add('calendar-edits',[
    step('Перенеси всю поездку на два дня позже',{'dates.start':'2026-11-12','dates.end':'2026-11-17'}),
    step('На день раньше',{'dates.start':'2026-11-11','dates.end':'2026-11-16'}),
    step('Заезд 8 декабря, выезд 12 декабря 2026 года',{'dates.start':'2026-12-08','dates.end':'2026-12-12'},allow=['stay_nights','duration_days','checkin_date']),
    step('А теперь с 20 по 25 декабря 2026',{'dates.start':'2026-12-20','dates.end':'2026-12-25'},allow=['stay_nights','duration_days','checkin_date']),
    step('Оставь эти даты, добавь завтрак',{'hotel_preferences.breakfast':True}),
])
add('direction-corrections',[
    step('Нет, давай лучше в Казань. Даты и бюджет те же',{'destination':'Казань'}),
    step('Передумал, лучше Питер',{'destination':'Санкт-Петербург'}),
    step('Город отправления теперь Казань',{'origin':'Казань'}),
    step('Вернёмся к Сочи, остальные условия прежние',{'destination':'Сочи'}),
])
add('amenity-changes',[
    step('Завтрак обязателен',{'hotel_preferences.breakfast':True}),
    step('Убери требование бассейна, парковку сохрани',{'hotel_preferences.pool':None}),
    step('Нет, бассейн всё же нужен',{'hotel_preferences.pool':True}),
    step('Спортзал тоже нужен',{'hotel_preferences.fitness':True}),
    step('Не дальше 500 метров от пляжа',{'hotel_preferences.max_beach_m':500}),
    step('От центра максимум 1,5 километра',{'hotel_preferences.max_center_m':1500}),
    step('Удалённость от центра теперь не важна',{'hotel_preferences.max_center_m':None}),
    step('Рейтинг не меньше 8,5 и от четырёх звёзд',{'hotel_preferences.min_rating':8.5,'hotel_preferences.min_stars':4}),
])
add('explicit-negations',[
    step('Отели без бассейна не предлагай',{'hotel_preferences.pool':True}),
    step('Бассейн не нужен как критерий',{'hotel_preferences.pool':None}),
    step('Ищем гостиницу без бассейна',{'hotel_preferences.pool':False}),
    step('Бесплатная отмена обязательна',{'hard_constraints.free_cancellation':True}),
    step('Можно и без бесплатной отмены',{'hard_constraints.free_cancellation':False}),
    step('Без парковки даже не рассматривай',{'hotel_preferences.parking':True}),
])
add('travel-changes',[
    step('Добавь дорогу туда и обратно и оба трансфера',{'include_transport':True}),
    step('Лучше поездом',{'transport_mode':'train','include_transport':True,'transport_owned':False}),
    step('Никаких пересадок',{'hard_constraints.no_connections':True}),
    step('Пересадки допустимы',{'hard_constraints.no_connections':False}),
    step('На своей машине',{'transport_mode':'car','include_transport':True}),
    step('Билеты уже куплены',{'transport_owned':True,'include_transport':True},status='needs_input'),
    step('Ищем только отель без дороги',{'include_transport':False},allow=['trip_budget','budget_scope','budget','hotel_budget']),
])
add('questions-are-not-criteria',[
    step('Покажи подходящие отели'),
    step('Почему именно второй отель?',contains='Проверочный отель 2'),
    step('У второго есть бассейн?',contains='Проверочный отель 2'),
    step('Что гости третьего пишут о чистоте?',contains='Проверочный отель 3'),
    step('А завтрак в первом включён?',contains='Проверочный отель 1'),
    step('Какие минусы в отзывах второго?',contains='Проверочный отель 2'),
    step('Что интересного рядом со вторым отелем?'),
    step('Сравни первый и третий'),
])
add('replace-and-restore',[
    step('Покажи подходящие отели'),
    step('Эти все не нравятся, покажи совершенно другие',allow=['excluded_hotel_ids']),
    step('Верни прежнюю подборку',{'excluded_hotel_ids':[]}),
])
add('new-short-dialogue',[
    step('В Казань',{'destination':'Казань'},status='needs_input'),
    step('Нас двое',{'travellers.adults':2},status='needs_input'),
    step('На четыре ночи',{'stay_nights':4},status='needs_input'),
    step('Бюджет 35 тысяч рублей только на отель',{'budget.amount_minor':3500000,'budget_scope':'hotel'},allow=['hotel_budget','budget_period']),
    step('И нужен завтрак',{'hotel_preferences.breakfast':True}),
],initial={})
add('partial-checkin-and-length',[
    step('12 ноября 2026',{'checkin_date':'2026-11-12'},status='needs_input'),
    step('На 4 ночи',{'dates.start':'2026-11-12','dates.end':'2026-11-16','stay_nights':4,'checkin_date':None}),
    step('Перенеси заезд на 15 ноября 2026',{'dates.start':'2026-11-15','dates.end':'2026-11-19'},allow=['checkin_date']),
],initial={**BASE,'dates':None})

for i,text in enumerate(['питер','ПЕТЕРБУРГ','спб','из Питера','Из Санкт-Петербурга','москва','Из Москвы','Казань','Нижний Новгород']):
    city='Санкт-Петербург' if i<5 else 'Москва' if i<7 else text
    add(f'origin-answer-{i+1}',[step(text,{'origin':city},status='needs_input',question='оставить')],initial={**BASE,'origin':None,'include_transport':True,'budget_scope':'whole_trip'},assistant='Учёл ваши пожелания. Из какого города отправляетесь?')
for i,(text,value) in enumerate([('0',0),('без резерва',0),('Ничего не оставляем отдельно',0),('10 тысяч',1000000),('15 000 рублей',1500000),('Оставим 12,5 тысяч рублей на еду',1250000)]):
    add(f'reserve-answer-{i+1}',[step(text,{'expense_reserve.amount_minor':value})],initial={**BASE,'include_transport':True,'budget_scope':'whole_trip'},assistant='Сколько из общего бюджета оставить на питание и личные расходы?',questions=['Сколько из общего бюджета оставить на питание и личные расходы?'])
for i,text in enumerate(['Нас то ли двое, то ли четверо, не решили','На 4 или 7 ночей','До 40 или 60 тысяч рублей, ещё не решили','Нужен бассейн и одновременно отель без бассейна','31 ноября 2026','С 20 по 15 ноября 2026','Бюджет 600 евро, переведи в рубли','Сделай как в прошлый раз, но я про него не рассказывал','В Питер или Казань, не могу выбрать']):
    add(f'ambiguous-{i+1}',[step(text,status='needs_input',question='.')])
for i,text in enumerate(['Спасибо!','Привет','Есть ли у третьего парковка?','А можно с собакой в этот отель?','Сколько будет стоить первый?','Что значит предварительная цена?','Можешь объяснить условия отмены?']):
    add(f'no-silent-edit-{i+1}',[step('Покажи подходящие отели'),step(text)])
for i,(text,expected) in enumerate([
 ('В Ярославль вдвоём на три ночи, 30 тысяч рублей на отель. Завтрак и парковка обязательны',{'destination':'Ярославль','travellers.adults':2,'stay_nights':3,'budget.amount_minor':3000000,'budget_scope':'hotel','hotel_preferences.breakfast':True,'hotel_preferences.parking':True}),
 ('хочу в сочи, нас 2 взрослых и 2 детей 4 и 9 лет. На 5 ночей, до 80 тысяч рублей на жильё',{'destination':'Сочи','travellers.adults':2,'travellers.children':[4,9],'stay_nights':5,'budget.amount_minor':8000000,'budget_scope':'hotel'}),
 ('Казань. 1 взрослый. 2 ночи. Бюджет 15000 рублей на отель. Без детей',{'destination':'Казань','travellers.adults':1,'stay_nights':2,'budget.amount_minor':1500000,'budget_scope':'hotel','travellers.children':[]}),
 ('Из Питера в Москву с 12 по 16 ноября 2026, двое взрослых, 100 тысяч рублей на всю поездку. На еду оставим 20 тысяч рублей',{'origin':'Санкт-Петербург','destination':'Москва','dates.start':'2026-11-12','dates.end':'2026-11-16','travellers.adults':2,'budget.amount_minor':10000000,'expense_reserve.amount_minor':2000000,'budget_scope':'whole_trip'}),
]):
    add(f'new-compound-{i+1}',[step(text,expected,allow=['hotel_budget','trip_budget','include_transport','budget_period','hard_constraints','stay_nights','checkin_date'])],initial={})

add('dated-stay-length-corrections',[
    step('На 3 ночи',{'stay_nights':3,'dates.end':'2026-11-13'}),
    step('Лучше на семь ночей',{'stay_nights':7,'dates.end':'2026-11-17'}),
    step('На четыре дня',{'duration_days':4,'stay_nights':3,'dates.end':'2026-11-13'}),
])

# Additional fresh paraphrases, authored after fixes; reported separately.
add('fresh-money-total',[step('Проживание теперь 48 000 рублей за весь срок',{'budget.amount_minor':4800000,'budget_period':'stay'},allow=['hotel_budget','budget_scope'])],initial={**BASE,'budget_period':'night'})
add('fresh-money-higher',[step('Бюджет можно увеличить до 80 тысяч рублей',{'budget.amount_minor':8000000},allow=['hotel_budget'])])
add('fresh-no-children',[step('Дети остаются дома, поедем только взрослые',{'travellers.children':[]})],initial={**BASE,'travellers':{'adults':2,'children':[4,9]}})
add('fresh-child-correction',[step('Детям не 4 и 9, а 5 и 10 лет',{'travellers.children':[5,10]})],initial={**BASE,'travellers':{'adults':2,'children':[4,9]}})
add('fresh-party-change',[step('На самом деле нас 1 взрослый и 3 детей, возраст 2, 8 и 12 лет',{'travellers.adults':1,'travellers.children':[2,8,12]})])
add('fresh-dates-shift',[step('Сдвинь даты поездки на 3 дня вперёд',{'dates.start':'2026-11-13','dates.end':'2026-11-18'})])
add('fresh-checkout-only',[step('Заезд оставь, выезд теперь 18 ноября 2026',{'dates.start':'2026-11-10','dates.end':'2026-11-18'},allow=['stay_nights','duration_days','checkin_date'])])
add('fresh-parking-removal',[step('Парковка больше не важна',{'hotel_preferences.parking':None})])
add('fresh-breakfast-removal',[step('Завтраки больше не обязательны, бассейн сохрани',{'hotel_preferences.breakfast':None})],initial={**BASE,'hotel_preferences':{'pool':True,'parking':True,'breakfast':True}})
add('fresh-flight-constraints',[step('Только дневные рейсы, пересадки разрешаю',{'hard_constraints.no_night_flights':True,'hard_constraints.no_connections':False})],initial={**BASE,'hard_constraints':{'no_connections':True}})
add('fresh-car-to-flight',[step('Вместо своей машины лучше самолётом',{'transport_mode':'flight','include_transport':True,'transport_owned':False})],initial={**BASE,'transport_mode':'car'})
add('fresh-cheaper-preserve',[step('Я хочу подешевле, но не без бассейна')])
add('fresh-reserve-zero',[step('Никаких дополнительных расходов отдельно не резервируем',{'expense_reserve.amount_minor':0})],initial={**BASE,'budget_scope':'whole_trip','include_transport':True},assistant='Сколько из общего бюджета оставить на питание и личные расходы?',questions=['Сколько из общего бюджета оставить на питание и личные расходы?'])
add('fresh-pet-question',[step('Покажи подходящие отели'),step('Пускают ли с кошкой во второй отель?',contains='Проверочный отель 2')])
add('fresh-pet-selected-question',[step('Покажи подходящие отели'),step('Можно приехать с питомцем в выбранный отель?')])
add('fresh-breakfast-question',[step('Покажи подходящие отели'),step('Сколько стоит добавить завтрак к первому варианту?',contains='завтрак')])
add('fresh-polite-change',[step('Спасибо, но лучше на три ночи',{'stay_nights':3,'dates.end':'2026-11-13'})])
add('fresh-compare-only',[step('Покажи подходящие отели'),step('Поясни, чем отличаются эти варианты, ничего не меняй',contains='Проверочный отель')])

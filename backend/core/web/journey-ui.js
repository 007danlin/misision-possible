'use strict';
const journeyNames={hotel:'Проживание',transport:'Дорога туда-обратно',transfers:'Оба трансфера',fees:'Сборы'};
function tripAmount(h){return (h.journey?.total_minor??h.quote?.total_minor??h.quote?.nightly_minor??0)+(h.transfer_addon?.total_minor||0);}
function tripTime(iso){return new Date(iso).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Moscow'});}
function fold(title,cls='trip-fold'){const d=node('details',null,cls);d.append(node('summary',title));return d;}
function sourceInfo(h){
 const d=fold('О стоимости и бронировании','trip-source');
 d.append(node('p','Стоимость предварительная. Номера, питание и условия отмены нужно уточнить на выбранные даты.'));
 d.append(node('p','Демонстрационный режим: без оплаты и реального бронирования.'));
 if(h.source_kind==='public'){d.append(externalLink('Отель на Островке ↗',h.url,'text-button'));if(h.content_status==='cached_stale')d.append(node('p','Сведения могут быть неактуальны. Проверьте их перед поездкой.'));}
 return d;
}
function journeyCostText(h,key){
 const j=h.journey;
 if(!j)return key==='hotel'?money({amount_minor:h.quote?.total_minor}):'Не включено';
 if(j.route_missing&&['transport','transfers'].includes(key))return 'Не рассчитано';
 if(key==='transfers'&&j.transport?.kind==='car')return 'Не нужен: едем на автомобиле';
 if(key==='fees'&&!j.breakdown.fees)return '—';
 if(key==='transport'&&j.total_incomplete)return 'Стоимость билетов не указана';
 return money({amount_minor:j.breakdown[key]});
}
function journeyCost(h){
 const j=h.journey;if(!j)return node('div');
 const d=fold('Состав стоимости');
 for(const [key,value]of Object.entries(j.breakdown)){if(key==='fees'&&!value)continue;const row=node('div',null,'trip-cost-row');row.append(node('span',journeyNames[key]||key),node('strong',journeyCostText(h,key)));d.append(row);}
 if(j.reserve_minor){const row=node('div',null,'trip-cost-row');row.append(node('span','Отдельно: резерв на личные расходы'),node('strong',money({amount_minor:j.reserve_minor})));d.append(row);}
 if(j.budget_minor)d.append(node('p',(j.route_missing?'Остаток после отеля и резерва, до расчёта дороги: ':'Остаток бюджета с учётом резерва: ')+money({amount_minor:j.budget_minor-j.total_minor-j.reserve_minor}),'context-note'));
 for(const text of j.unknown_costs||[])if(!/сборы|доплаты объекта/i.test(text))d.append(node('p',text,'context-note'));
 return d;
}
function journeyRoute(h,opened=false){
 const j=h.journey;if(!j)return node('div');
 const d=fold('Дорога и трансферы');d.open=opened;
 if(j.route_missing){d.append(node('p','В приложении пока нет расчёта дороги и трансферов для выбранных условий. Отели доступны на Островке; показанная сумма включает только проживание.','context-note'));return d;}
 d.append(node('p','Местное время · Москва (UTC+3)','context-note'));
 const list=node('ol',null,'trip-timeline');
 for(const [i,s]of j.segments.entries()){
  const item=node('li');item.append(node('strong',s.label),node('p',s.origin+' → '+s.destination),node('p',(s.time_partial==='arrival'?'Прибытие '+tripTime(s.arrival):s.time_partial==='departure'?'Отправление '+tripTime(s.departure):tripTime(s.departure)+' — '+tripTime(s.arrival)),'trip-time'));
  if(s.kind==='transfer')item.append(node('small',j.vehicles+' авто · '+j.baggage+(j.child_seats?' · детских кресел: '+j.child_seats:'')));
  list.append(item);
  if(s.ends_at_hotel||(i===1&&!j.transport)){const stay=node('li',null,'trip-stay');stay.append(node('strong','Проживание'),node('p','Заселение с '+tripTime(j.checkin_from)),node('p','Выезд до '+tripTime(j.checkout_until)));list.append(stay);}
 }
 d.append(list);if(j.transfer_estimate)d.append(node('p','Время и стоимость трансфера предварительные. Время подачи, багаж и детские кресла уточните при заказе.','context-note'));return d;
}
function journeyChecks(h){
 const j=h.journey;if(!j)return node('div');
 const issues=j.checks.filter(c=>c.status!=='pass'||!c.blocking);
 const ready=j.can_book||(j.budget_override_accepted&&!j.checks.some(c=>c.blocking&&c.status!=='pass'&&!['budget','hotel_budget'].includes(c.code)));
 const d=fold(ready?'Что проверить перед поездкой':j.checks.some(c=>c.blocking&&c.status==='fail')?'Что нужно изменить':'Уточним условия поездки',ready?'trip-fold trip-checks':'trip-fold trip-checks trip-conflict');
 d.open=!ready;
 for(const c of j.checks){const agreed=j.budget_override_accepted&&['budget','hotel_budget'].includes(c.code)&&c.status!=='pass';const p=node('p',(agreed?'Согласовано: ':c.status==='pass'?'✓ ':c.status==='fail'?'! ':'? ')+c.message,c.status==='pass'||agreed?'':'warning');d.append(p);}
 if(issues.some(c=>c.code==='early_arrival'))d.append(node('p','Ранний заезд не добавлен к стоимости.','context-note'));
 return d;
}
function hotelContentPanel(h){
 const wrap=node('div',null,'hotel-information'),c=h.content||{},q=h.quote||{};
 if(h.source_kind==='public'){wrap.append(publicRoomPanel(h),publicReviewPanel(h),locationPanel(h));if(h.journey)wrap.append(transportChoices(h),journeyRoute(h),journeyChecks(h));return wrap;}
 const room=fold('Номер и условия');
 if(c.description)room.append(node('p',c.description));
 room.append(node('h3',c.room||'Категория номера не подтверждена'));
 if(c.beds)room.append(node('p',c.beds+' · до '+c.room_capacity+' гостей в номере'));
 room.append(node('p',q.breakfast?'Завтрак включён в расчёт':'Без питания'));
 room.append(node('p',h.journey?.cancellation_until?'Отмена без штрафа до '+tripTime(h.journey.cancellation_until):q.free_cancellation?'Условия отмены требуют подтверждения поставщика':'Невозвратный расчёт'));
 if(c.checkin_from)room.append(node('p','Заезд '+c.checkin_from+'–'+c.checkin_until+' · выезд до '+c.checkout_until));
 if(c.pets_allowed===false)room.append(node('p','Размещение с питомцами не предусмотрено'));
 if(!h.journey)room.append(node('p','Категорию, вместимость, точные сроки отмены и сборы на месте нужно подтвердить у объекта.','context-note'));
 wrap.append(room,reviewPanel(h));
 if(h.journey)wrap.append(journeyRoute(h),journeyChecks(h));
 return wrap;
}
function reviewPanel(h){
 if(h.source_kind==='public')return publicReviewPanel(h);
 const reviews=h.review_items||[],d=fold('Отзывы'+(h.reviews?' · '+h.reviews:''));
 if(!reviews.length){d.append(node('p','Отзывы об этом отеле пока недоступны.'));return d;}
 d.append(node('p','Доступно '+reviews.length+' отзыва. Можно посмотреть то, что важно вам.','context-note'));
 const filter=node('select');filter.setAttribute('aria-label','Тема отзывов');
 for(const t of ['Все темы',...new Set(reviews.map(r=>r.theme))]){const o=node('option',t);o.value=t;filter.append(o);}
 const list=node('div',null,'review-list');
 const render=()=>{list.replaceChildren();for(const r of reviews.filter(r=>filter.value==='Все темы'||r.theme===filter.value)){const item=node('article',null,'review-item');item.append(node('strong',r.rating+'/10 · '+r.theme),node('p',r.text),node('small',r.date+' · '+r.traveller));list.append(item);}};
 filter.onchange=render;render();d.append(filter,list);return d;
}
function journeyComparison(hotels){
 const d=fold('Сравнить варианты');
 const controls=node('div',null,'comparison-select'),hint=node('p','Выберите 2–3 варианта для сравнения.','context-note'),grid=node('div',null,'trip-comparison');
 const cheapest=Math.min(...hotels.map(tripAmount));
 for(const h of hotels){const item=node('article');item.append(node('h3',h.name),node('strong',money({amount_minor:tripAmount(h)})));
  if(h.journey){item.append(node('p','Трансферы: '+journeyCostText(h,'transfers')),node('p',h.journey.route_missing?'Дорога и трансферы не рассчитаны':h.journey.transport?travelDuration(h.journey.transport.full_out_minutes)+' до отеля':'Дорога: '+(h.journey.segments[0]?.duration_minutes??'—')+' мин.'),node('p',h.source_kind==='public'?'Отмена: тариф ещё не подтверждён':h.journey.cancellation_until?'Отмена до '+tripTime(h.journey.cancellation_until):'Без возврата'));}
  item.append(node('p',(h.quote?.breakfast?'С питанием':'Без питания')+(h.source_kind==='public'?' в расчёте':'')),node('p','До центра: '+(h.distance_m==null?'неизвестно':(h.distance_m/1000).toFixed(1)+' км')),node('p','Оценка '+(h.rating??'неизвестна')+(h.reviews?' · '+plural(h.reviews,'отзыв','отзыва','отзывов'):'')));
  const concerns=Object.entries(h.review_summary||{}).filter(([,s])=>s.negative_ids.length>=2).map(([t,s])=>t+': '+plural(s.negative_ids.length,'гость отметил','гостя отметили','гостей отметили')+' недостатки').join('; ');
  if(concerns)item.append(node('p',concerns,'context-note'));
  if(h.unverified?.length)item.append(node('p','Уточнить: '+h.unverified.join(', '),'context-note'));
  if(tripAmount(h)===cheapest)item.append(node('p','Самый доступный вариант','context-note'));item.append(button('Открыть вариант',()=>openDetail(h.id),'text-button'));grid.append(item);const label=node('label'),check=node('input');check.type='checkbox';check.checked=true;check.onchange=()=>{item.hidden=!check.checked;hint.textContent=controls.querySelectorAll('input:checked').length<2?'Для сравнения выберите хотя бы два варианта.':'Сравниваем одни даты и состав гостей.';};label.append(check,document.createTextNode(h.name));controls.append(label);
 }
 d.append(controls,hint,grid);return d;
}
function renderJourneyPreview(){
 const p=state.journey_preview;if(!p)return;
 const over=hotelOverBudget(p.proposed_hotel);
 const box=node('section',null,'trip-preview');box.append(node('h2',over?'Выбранная поездка дороже бюджета':'Обновим поездку?'),node('p',over?'Стоимость этого варианта выше нового лимита. Можно поискать дешевле, вернуться к прежнему плану или продолжить с этой стоимостью.':'Прежний план сохранён. Изменение вступит в силу после вашего подтверждения.'));
 const table=node('table');const header=node('tr');for(const t of ['','Было','Стало'])header.append(node('th',t));table.append(header);
 const rows=[['Откуда',p.previous_spec.origin||'Не указан',p.proposed_spec.origin||'Не указан'],['Дорога',p.previous_hotel.journey?.transport?.label||'Без дороги',p.proposed_hotel.journey?.transport?.label||'По новому плану'],['Трансфер',p.previous_hotel.journey?.transfer_choice?.label||(p.previous_hotel.journey?.transport?.kind==='car'?'Не нужен: на автомобиле':p.previous_hotel.journey?'Оба трансфера включены':'Не включён'),p.proposed_hotel.journey?.transfer_choice?.label||(p.proposed_hotel.journey?.transport?.kind==='car'?'Не нужен: на автомобиле':p.proposed_hotel.journey?'Оба трансфера включены':'Не включён')],['Отель',p.previous_hotel.name,p.proposed_hotel.name],['Даты',dateRange(p.previous_spec.dates),dateRange(p.proposed_spec.dates)],['Гости',hotelGuestComposition(p.previous_spec),hotelGuestComposition(p.proposed_spec)]];
 const tripBudget=s=>s.trip_budget||(['whole_trip','booking'].includes(s.budget_scope)?s.budget:null);
 const hotelBudget=s=>s.hotel_budget||(s.budget_scope==='hotel'?s.budget:null);
 const amount=m=>m?money(m):'Не указан';
 if(tripBudget(p.previous_spec)||tripBudget(p.proposed_spec))rows.push(['Бюджет на поездку',amount(tripBudget(p.previous_spec)),amount(tripBudget(p.proposed_spec))]);
 if(hotelBudget(p.previous_spec)||hotelBudget(p.proposed_spec))rows.push(['Бюджет на отель',amount(hotelBudget(p.previous_spec))+(hotelBudget(p.previous_spec)?p.previous_spec.budget_period==='night'?' за ночь':' за проживание':''),amount(hotelBudget(p.proposed_spec))+(hotelBudget(p.proposed_spec)?p.proposed_spec.budget_period==='night'?' за ночь':' за проживание':'')]);
 if(p.previous_spec.expense_reserve||p.proposed_spec.expense_reserve)rows.push(['На личные расходы',amount(p.previous_spec.expense_reserve),amount(p.proposed_spec.expense_reserve)]);
 for(const k of ['hotel','transport','transfers','fees'].filter(k=>k!=='fees'||p.previous_hotel.journey?.breakdown.fees||p.proposed_hotel.journey?.breakdown.fees))rows.push([journeyNames[k],journeyCostText(p.previous_hotel,k),journeyCostText(p.proposed_hotel,k)]);
 rows.push(['Итого',money({amount_minor:tripAmount(p.previous_hotel)}),money({amount_minor:tripAmount(p.proposed_hotel)})]);
 for(const row of rows){const tr=node('tr');row.forEach(v=>tr.append(node('td',v)));table.append(tr);}box.append(table,node('strong',signedMoney(p.price_delta)+' к прежней поездке'));
 box.append(journeyChecks(p.proposed_hotel),journeyRoute(p.proposed_hotel));
 const actions=node('div',null,'trip-actions');
 if(over&&!p.proposed_spec.keep_hotel)actions.append(button('Найти в новом бюджете',()=>submitMessage('Найди вариант подешевле, остальные условия оставь'),'primary',true));
 actions.append(button(over?'Продолжить с этой стоимостью':'Принять изменения',()=>act('accept_journey_change'),over?'secondary':'primary',true),button('Оставить прежний план',()=>act('discard_journey_change'),'secondary',true));box.append(actions);$('results').append(box);
}

function renderSavedHotelSearch(){
 const saved=state.journey_recovery,hotel=saved.hotel,options=saved.previous_options||[];
 const title=state.status==='needs_input'?'Уточним детали — ваш выбор сохранён':state.status==='error'?'Не удалось пересчитать — ваш выбор сохранён':'Новые условия требуют уточнения';
 const box=stateBox(title,state.assistant_message);
 box.append(node('p','Отели и цены ниже сохранены по прежним условиям. Новые условия из чата применим после уточнения и пересчёта.','context-note'));
 if(state.trip_spec?.transport_owned&&!state.trip_spec.owned_transport)box.append(button('Ваши билеты',()=>ownedTicketsDialog(hotel?.id||state.selected_hotel?.id),'primary',true));
 box.append(button(hotel?'Вернуться к прежней поездке':'Вернуть прежнюю подборку',()=>act('restore_journey'),'secondary',true));
 if(state.status==='error'&&lastMessage)box.append(button('Повторить запрос',()=>submitMessage(lastMessage),'secondary',true));
 $('results').append(box);
 const cards=node('div',null,'cards saved-hotel-options');
 for(const h of hotel?[hotel]:options){
  const card=node('article',null,'card'),body=node('div',null,'card-body');
  body.append(node('h3',h.name),node('p',hotelGuestComposition(saved.spec||{})),node('p',saved.spec?.dates?dateRange(saved.spec.dates):'Даты из сохранённого поиска'),node('strong',money({amount_minor:tripAmount(h)})),node('small','Стоимость по прежним условиям','context-note'));
  card.append(hotelPhoto(h),body);cards.append(card);
 }
 $('results').append(cards);$('option-count').textContent=options.length||'';
}

'use strict';
const $ = id => document.getElementById(id);
const hotelMode = new URLSearchParams(location.search).get('mode') !== 'demo';
const sessionKey = hotelMode ? 'oplan-hotels-session' : 'odin-session';
let state = null, working = false, detailID = null, transcript = [], transcriptRevision = -1;
let pending = null, retryOperation = null, progressTimer = null, lastMessage = '';
const actionNames = new Set(['select_destination', 'select_plan', 'accept_change', 'confirm_booking_demo', 'select_hotel', 'clear_hotel_selection', 'confirm_hotel_booking','update_hotel_stay','accept_journey_change','discard_journey_change','restore_journey','change_transport']);
const money = value => value && Number.isFinite(value.amount_minor)
  ? new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(value.amount_minor / 100) + ' ₽' : '—';
const signedMoney = amount => (amount > 0 ? '+' : amount < 0 ? '−' : '') + money({amount_minor: Math.abs(amount)});
const breakdownNames = {transport: 'Дорога туда-обратно', hotel: 'Проживание', transfers: 'Оба трансфера', fees: 'Сборы'};
const cities = {sochi: 'Сочи', kazan: 'Казань', vladimir: 'Владимир', yaroslavl: 'Ярославль'};
const images = {A: '/assets/stay-a.webp', B: '/assets/stay-b.jpg', C: '/assets/stay-c.jpg'};
const examples = [
  ['Море на двоих', 'Из Москвы в Сочи, 10–15 ноября 2026, двое взрослых, до 120 тысяч рублей на дорогу, отель и трансферы со сборами, без ночных рейсов.', 'A', 'Поездка к морю с дорогой, проживанием и трансферами.'],
  ['Пока не знаем куда', 'Мы с девушкой хотим куда-нибудь на 4 дня в ноябре. До 40 тысяч рублей на двоих. Хочется красивого места и недолгой дороги.', 'B', 'Начните с настроения. Направление выберем вместе.'],
  ['Выходные в Ярославле', 'Из Москвы в Ярославль, 6–8 ноября 2026, двое взрослых, до 40 тысяч рублей на дорогу, отель, трансферы и сборы.', 'C', 'Небольшое путешествие с прогулками и новым городом.'],
];
function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function button(text, handler, cls = 'primary', mutation = false) {
  const b = node('button', text, cls);
  b.type = 'button'; b.onclick = handler;
  if (mutation) { b.dataset.mutation = ''; b.disabled = working || !!pending; }
  return b;
}
function readLocal(key) { try { return localStorage.getItem(key); } catch { return null; } }
function writeLocal(key, value) { try { localStorage.setItem(key, value); } catch { /* Backend state remains authoritative. */ } }
function saveConversation() {
  if (!state) return;
  writeLocal('odin-chat-' + state.session_id, JSON.stringify({revision: state.revision, messages: transcript.slice(-100)}));
}
function bubble(text, role) {
  if (!text) return;
  const e = node('div', null, 'bubble ' + role);
  e.append(node('small', role === 'user' ? 'Вы' : 'О!План'), document.createTextNode(text));
  $('chat').append(e);
  const chat=$('chat');
  chat.scrollTop = e.scrollHeight>chat.clientHeight-24 ? chat.scrollTop+e.getBoundingClientRect().top-chat.getBoundingClientRect().top : chat.scrollHeight;
}
function addMessage(text, role) {
  if (!text) return;
  transcript.push({role, text});
  if (transcript.length > 100) transcript.shift();
  bubble(text, role); saveConversation();
}
function assistantText(snapshot) {
  const message = snapshot.assistant_message || '';
  return [...new Set([message, ...(snapshot.questions || []).filter(q => !message.includes(q))].filter(Boolean))].join('\n\n');
}
function restoreConversation() {
  let saved;
  try { saved = JSON.parse(readLocal('odin-chat-' + state.session_id)); } catch { /* Recover from server. */ }
  if(Array.isArray(state.messages) && state.messages.length){
    transcript=state.messages.filter(m=>m&&['user','assistant'].includes(m.role)&&typeof m.text==='string');transcriptRevision=state.revision;
  } else if (saved && saved.revision <= state.revision && Array.isArray(saved.messages)) {
    transcript = saved.messages.filter(m => m && ['user', 'assistant'].includes(m.role) && typeof m.text === 'string').slice(-100);
    transcriptRevision = saved.revision;
  } else {
    transcript = (state.history || []).filter(m => typeof m === 'string' && !actionNames.has(m)).map(text => ({text, role: 'user'}));
    transcriptRevision = -1;
  }
  $('chat').replaceChildren();
  transcript.forEach(m => bubble(m.text, m.role));
  if (transcriptRevision !== state.revision || !transcript.length) addMessage(assistantText(state), 'assistant');
  transcriptRevision = state.revision; saveConversation();
  lastMessage = [...transcript].reverse().find(m => m.role === 'user')?.text || '';
}
function dateText(date) {
  if (!date) return 'Уточним дату';
  return new Intl.DateTimeFormat('ru-RU', {day: 'numeric', month: 'short', timeZone: 'UTC'}).format(new Date(date + 'T12:00:00Z')).replace('.', '');
}
function dateRange(dates) { return dates ? dateText(dates.start) + ' — ' + dateText(dates.end) : 'Даты уточним в диалоге'; }
function plural(n, one, few, many) { const t = n % 10, h = n % 100; return n + ' ' + (h >= 11 && h <= 14 ? many : t === 1 ? one : t >= 2 && t <= 4 ? few : many); }
function planDates(plan) {
  if (plan.dates) return plan.dates;
  // Earlier persisted plans use destination:start:A IDs and always span five nights.
  const parts = plan.id.split(':');
  if (/^\d{4}-\d{2}-\d{2}$/.test(parts[1])) {
    const end = /^\d{4}-\d{2}-\d{2}$/.test(parts[2]) ? parts[2]
      : new Date(Date.parse(parts[1]) + 5 * 86400000).toISOString().slice(0, 10);
    return {start: parts[1], end};
  }
  return null;
}
function planNights(plan) { const d = planDates(plan); return d ? Math.round((Date.parse(d.end) - Date.parse(d.start)) / 86400000) : null; }
function variant(plan) { return plan.id.split(':').pop(); }
function destination(plan) { return cities[plan.id.split(':')[0]] || state.trip_spec?.destination || 'Ваша поездка'; }
function priceCaption(plan) {
  const nights = planNights(plan);
  return 'за услуги поездки · двое' + (nights ? ' · ' + plural(nights, 'ночь', 'ночи', 'ночей') : '');
}
function cancellation(plan) {
  if ((plan.tradeoffs || []).some(t => /невозврат|без бесплатной отмены/i.test(t))) return {text: 'Невозвратный тариф', refundable: false};
  const check = (plan.checks || []).find(c => c.code === 'free_cancellation');
  // Only the documented synthetic A/C catalogue confirms this property; pass alone is not proof for arbitrary data.
  if (check?.status === 'pass' && ['A', 'C'].includes(variant(plan)) && (plan.evidence || []).some(e => e.source_kind === 'synthetic'))
    return {text: 'Бесплатная отмена (демо)', refundable: true};
  return {text: 'Условия отмены — в проверках', refundable: null};
}
function photo(key, big = false) {
  const frame = node('div', null, big ? 'detail-photo' : 'card-photo');
  const img = node('img'); img.src = images[key] || images.A;
  img.alt = 'Иллюстрация размещения; не фотография конкретного предложения';
  frame.append(img);
  return frame;
}
function priceNode(plan) {
  const p = node('div', money(plan.total), 'price'); p.append(node('small', priceCaption(plan))); return p;
}
function actionButton(parent, title, type, extra = {}, cls = 'primary') {
  parent.append(button(title, () => act(type, extra), cls, true));
}
function fillPrompt(text) {
  $('message').value = text; mobileView('chat'); resizeComposer(); $('message').focus(); $('message').setSelectionRange(0,0); $('message').scrollTop=0;
}
function fillIdeaPrompt(text) {
  const origin = state?.trip_spec?.origin?.trim();
  fillPrompt(origin ? 'Город отправления: ' + origin + '. ' + text : text);
}
function mobileView(view) {
  document.querySelector('.workspace').dataset.mobileView = view;
  $('mobile-chat').setAttribute('aria-pressed', String(view === 'chat'));
  $('mobile-results').setAttribute('aria-pressed', String(view === 'results'));
  if(view==='chat')resizeComposer();
}
function openDetail(id) {
  detailID = id; render(); document.querySelector('.plans').scrollTop = 0; mobileView('results'); $('results').focus({preventScroll: true});
}
function backToOptions() { detailID = null; render(); document.querySelector('.plans').scrollTop = 0; }
function updateControls() {
  document.querySelectorAll('[data-mutation]').forEach(b => b.disabled = working || !!pending || b.dataset.blocked==='true');
  $('send').disabled = working || !!pending || !state || !!(state.booking || state.hotel_booking);
  $('new').disabled = working || !!pending; if($('history'))$('history').disabled=working||!!pending;
  $('edit').disabled = !state || !!(state.booking || state.hotel_booking);
  $('message').disabled = !!(state?.booking || state?.hotel_booking);
  $('message').placeholder = (state?.booking || state?.hotel_booking) ? 'Начните новую поездку, чтобы продолжить' : state?.selected_plan ? 'Что поменяем в вашей поездке?' : 'Куда хочется, когда и на какой бюджет?';
}
const progressCopy = {
  create: ['Готовим поездку', 'Сохраняем новую сессию.'],
  restore: ['Возвращаем вашу поездку', 'Загружаем сохранённые условия.'],
  turn: ['Подбираем вашу поездку', 'Учитываем пожелания и проверяем варианты.'],
  change: ['Пересчитываем поездку', 'Прежний выбор остаётся на месте.'],
  select_destination: ['Ищем варианты', 'Проверяем даты, гостей и бюджет.'],
  select_plan: ['Проверяем ваш выбор', 'Сверяем стоимость и условия поездки.'],
  accept_change: ['Проверяем изменения', 'Сохраняем подтверждённый вариант.'],
  confirm_booking_demo: ['Сохраняем поездку', 'Сохраняем подтверждение. Оплаты нет.'],
};
function busy(value, operation = 'turn') {
  working = value; clearInterval(progressTimer); progressTimer = null;
  $('progress').hidden = !value; $('results').setAttribute('aria-busy', String(value));
  $('busy').textContent = value ? 'Запрос выполняется' : (state?.booking || state?.hotel_booking) ? 'Поездка оформлена' : 'Можно написать своими словами';
  $('busy').classList.toggle('is-loading', value);
  updateControls(); if(state)renderSuggestions();
  if (hotelMode) {
    $('progress').hidden = true;
    if (!value) { TravelWindow.stop(); return; }
    if (['turn','change'].includes(operation) && pending?.message) {
      if(state?.hotel_options?.length){detailID=null;render();}
      TravelWindow.start($('results'),!!state?.hotel_options?.length,'/api/sessions/'+state.session_id+'/progress?key='+encodeURIComponent(pending.body.idempotency_key),pending.message);
      mobileView('results');
    }
    return;
  }
  if (!value) return;
  const [title, detail] = progressCopy[operation] || progressCopy.turn;
  $('progress-title').textContent = title; $('progress-detail').textContent = detail;
  const start = performance.now();
  const update = () => {
    const seconds = Math.floor((performance.now() - start) / 1000);
    $('progress-elapsed').textContent = seconds + ' с';
    $('progress-hint').textContent = seconds >= 20 ? 'Повторять запрос не нужно' : ['turn', 'change'].includes(operation) ? 'Учитываем ваши пожелания' : 'Проверяем данные';
  };
  update(); progressTimer = setInterval(update, 1000);
}
class APIError extends Error {
  constructor(message, status, code) { super(message); this.status = status; this.code = code; }
}
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 315000);
  try {
    const response = await fetch(path, {method: body !== undefined ? 'POST' : 'GET', headers: body !== undefined ? {'Content-Type': 'application/json'} : {}, body: body !== undefined ? JSON.stringify(body) : undefined, signal: controller.signal, credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) throw new APIError(data.error?.message || 'Не удалось выполнить запрос.', response.status, data.error?.code);
    return data;
  } finally { clearTimeout(timeout); }
}
function clearError() { $('error').textContent = ''; $('error').hidden = true; $('retry').hidden = true; retryOperation = null; }
function showError(message, retry) {
  $('error').textContent = message; $('error').hidden = false;
  retryOperation = retry || null; $('retry').hidden = !retry;
  $('retry').textContent = pending ? 'Проверить и повторить запрос' : 'Повторить запрос';
}
function renderSummary() {
  const s = state.trip_spec || {}; $('summary').replaceChildren();
  const parts = [s.destination ? (s.origin ? s.origin + ' → ' : '') + s.destination : s.origin ? 'Из ' + s.origin : 'Ваша поездка по России', s.dates && dateRange(s.dates), s.travellers?.adults && plural(s.travellers.adults, 'взрослый', 'взрослых', 'взрослых')];
  if (hotelMode) { const globe = globeIcon(); globe.setAttribute('aria-hidden','true'); $('summary').append(globe, originControl(),node('span','→'),node('span',s.destination||'Куда поедем?')); }
  else parts.filter(Boolean).forEach(x => $('summary').append(node('span', x)));
  $('spec').replaceChildren();
  const conditions = [s.budget && ({booking: 'На услуги поездки', whole_trip: 'На весь отдых', hotel: 'На отель'}[s.budget_scope] || 'Бюджет') + ': ' + money(s.budget), s.expense_reserve && 'Другие расходы: ' + money(s.expense_reserve), s.hard_constraints?.no_night_flights && 'Без ночных рейсов', s.hard_constraints?.free_cancellation && 'Бесплатная отмена', s.hard_constraints?.pets && 'С питомцем', ...(s.preferences || [])];
  if (hotelMode) {
    const hp = s.hotel_preferences || {};
    conditions.unshift(s.destination, s.dates ? dateRange(s.dates) : s.stay_nights ? plural(s.stay_nights,'ночь','ночи','ночей') : null, s.travellers?.adults ? hotelGuests(s) : s.travellers?.children?.length ? plural(s.travellers.children.length,'ребёнок','ребёнка','детей') : null);
    Object.entries({pool:['Бассейн','Без бассейна'],parking:['Парковка','Без парковки'],spa:['Спа','Без спа'],fitness:['Фитнес','Без фитнеса'],breakfast:['Завтрак','Без завтрака']}).forEach(([k,v])=>{if(hp[k]!=null) conditions.push(v[hp[k]?0:1])});
    const distanceLabel=m=>m<1000?m.toLocaleString('ru-RU')+' м':(m/1000).toLocaleString('ru-RU')+' км';
    if(hp.max_center_m!=null) conditions.push('До центра ≤ '+distanceLabel(hp.max_center_m));
    if(hp.max_beach_m!=null) conditions.push('До пляжа ≤ '+distanceLabel(hp.max_beach_m));
    if(hp.min_rating!=null) conditions.push('Рейтинг от '+hp.min_rating);
    if(hp.min_stars!=null) conditions.push('От '+hp.min_stars+' ★');
    if(s.budget_period==='night') conditions.push('Бюджет за ночь');
  }
  conditions.filter(Boolean).forEach(t => $('spec').append(node('span', t, 'chip')));
  const info = state.telemetry;
  if (info) $('model-info').textContent = [info.model, info.provider, info.total_ms != null && 'Последний запрос: ' + (info.total_ms / 1000).toFixed(1) + ' с', info.model_calls != null && 'Вызовов модели: ' + info.model_calls].filter(Boolean).join(' · ');
}
function isHotelInspirationState() {
  if (!state || state.status !== 'needs_input') return false;
  const spec = state.trip_spec || {};
  // Choosing where to leave from does not start a destination search.
  const defaults = {transfer_provider: 'estimate', transport_mode: 'auto', travel_setting: 'any', budget_period: 'stay'};
  const hasValue = value => value != null && value !== false && value !== '' &&
    (typeof value !== 'object' || Object.values(value).some(hasValue));
  return !Object.entries(spec).some(([key, value]) =>
    !['origin', 'include_transport'].includes(key) && value !== defaults[key] && hasValue(value));
}
function renderSuggestions() {
  $('suggestions').replaceChildren();
  if(state?.trip_spec?.transport_owned&&!state.trip_spec.owned_transport&&!state.hotel_booking)$('suggestions').append(button('Ваши билеты',()=>ownedTicketsDialog(state.selected_hotel?.id),'suggestion'));
  if(state?.trip_spec?.owned_transport&&state.status==='needs_input')$('suggestions').append(button('Подобрать поездку',()=>submitMessage('Подобрать поездку'),'suggestion'));
  if (state.booking || state.hotel_booking) return;
  if (hotelMode) {
    if(working || pending) return;
    const spec=state.trip_spec||{},t=spec.travellers||{};
    const question=state.status==='needs_input'?(state.questions?.[0]||state.assistant_message||''):'';
    const budgetTarget=spec.include_transport&&spec.budget_scope!=='hotel'?'на всю поездку':'на отель';
    let prompts=[];
    if(state.selected_hotel && state.status==='hotel_checkout') {
      $('suggestions').append(button('Даты и гости',()=>editHotelStay(),'suggestion'),button('Другой отель',()=>act('clear_hotel_selection'),'suggestion'));return;
    }
    if(state.status==='error')prompts=[['Повторить запрос',lastMessage],['Изменить пожелания','Хочу изменить ']];
    else if(state.status==='needs_input'&&state.selection?.destination_suggestions?.length)prompts=state.selection.destination_suggestions.map(d=>[d.name,'Ищем отель: '+d.name+(d.country?', страна '+d.country:'')+'. Остальные условия сохрани.']);
    else if(/из какого города|город отправления|откуда (?:вы )?(?:отправ|поед|ед)/i.test(question))prompts=[['Москва','Отправляемся из Москвы'],['Санкт-Петербург','Отправляемся из Санкт-Петербурга'],['Другой город','Отправляемся из ']];
    else if(/точные даты|какие даты оставить/i.test(question))prompts=[['Указать даты','Хочу поехать с ']];
    else if(state.destination_options?.length && !isHotelInspirationState())prompts=state.destination_options.map(d=>[d.name,'Выбираю '+d.name+', ищем в районе '+d.destination+'. Остальные пожелания сохрани.']);
    else if(isHotelInspirationState())prompts=[['На природу','Хочу на природу, в лес. Дикая природа.'],['К морю','В Сочи на 5 ночей, двое взрослых, до 40 тысяч рублей на отель. Хочу бассейн.'],['В город','В Казань на 3 ночи, двое взрослых, до 25 тысяч рублей на отель, не дальше 2 км от центра.']];
    else if(!t.adults)prompts=[['Один взрослый','1 взрослый'],['Двое взрослых','2 взрослых'],['С детьми','2 взрослых и ']];
    else if(t.children?.some(a=>a==null))prompts=[['Возраст '+t.children.length+' детей','Возраст детей: '],['Изменить число детей','Поедет ']];
    else if(!spec.dates&&!spec.stay_nights)prompts=[['3 ночи','На 3 ночи'],['5 ночей','На 5 ночей'],['Неделя','На 7 ночей']];
    else if(!spec.budget)prompts=[['До 30 000 ₽','Бюджет 30 тысяч рублей '+budgetTarget+' за весь отдых'],['До 50 000 ₽','Бюджет 50 тысяч рублей '+budgetTarget+' за весь отдых'],['Другая сумма','Бюджет '+budgetTarget+' — ']];
    else if(/сколько.*(?:оставить|резерв)/i.test(question)&&spec.budget_scope==='whole_trip'&&spec.expense_reserve==null)prompts=[['Без отдельного резерва','Резерв на личные расходы 0 рублей'],['Оставить 10 000 ₽','Резерв на личные расходы 10 тысяч рублей'],['Другая сумма','Резерв на личные расходы — ']];
    else if(state.status==='no_solution'){
      prompts=[['Изменить бюджет','Мой бюджет '+budgetTarget+' теперь '],['Другие даты','Хочу изменить даты на ']];
      if(spec.hotel_preferences?.pool)prompts.push(['Без бассейна','Бассейн больше не обязателен']);
      else if(spec.hotel_preferences?.max_center_m)prompts.push(['Можно дальше','Теперь можно далеко от центра']);
    } else if(state.hotel_options?.length)prompts=[['Подешевле','Найди подешевле, остальные условия сохрани'],['Почему эти?','Объясни, почему выбрал эти отели'],['Другие даты','Хочу изменить даты на ']];
    else prompts=[['Уточнить пожелания','Хочется '],['Изменить направление','Лучше поехать в ']];
    prompts.forEach(([label,text])=>$('suggestions').append(button(label,()=>isHotelInspirationState()?fillIdeaPrompt(text):fillPrompt(text),'suggestion')));
    return;
  }
  const items = state.selected_plan ? [['Подешевле', 'Найди вариант подешевле, остальные условия оставь'], ['На неделю позже', 'Перенеси поездку на неделю позже, остальное оставь']]
    : state.revision === 0 ? examples.slice(0, 2).map(e => [e[0], e[1]]) : [['Уточнить бюджет', 'Мой бюджет — '], ['Уточнить даты', 'Хочу поехать ']];
  items.forEach(([title, value]) => $('suggestions').append(button(title, () => fillPrompt(value), '', false)));
}
function heading(title, subtitle, eyebrow) {
  const line = node('div', null, 'result-heading'), text = node('div');
  if (eyebrow) text.append(node('p', eyebrow, 'eyebrow'));
  text.append(node('h1', title)); if (subtitle) text.append(node('p', subtitle, 'subtitle'));
  line.append(text); return line;
}
function dataNote() { return node('p', 'Цены, наличие и условия учебные. Фотографии — иллюстрации, не изображения предлагаемых отелей.', 'data-note'); }
function stateBox(title, text, cls = '') {
  const box = node('div', null, 'state-box ' + cls); box.append(node('h2', title));
  if (text) box.append(node('p', text)); return box;
}
function planCard(plan) {
  const selected = state.selected_plan?.id === plan.id;
  const card = node('article', null, 'card' + (selected ? ' selected' : ''));
  card.dataset.planId = plan.id;
  const image = photo(variant(plan));
  const all = state.options || [], cheapest = all.length > 1 && plan.total.amount_minor === Math.min(...all.map(p => p.total.amount_minor));
  if (selected || cheapest) image.append(node('span', selected ? 'Ваш выбор' : 'Самая низкая цена', 'badge' + (selected ? ' green' : '')));
  const body = node('div', null, 'card-body');
  body.append(node('p', destination(plan), 'card-kicker'), node('h3', 'Вариант ' + variant(plan)), node('p', dateRange(planDates(plan)), 'card-subtitle'));
  const features = node('div', null, 'card-features'), term = cancellation(plan);
  features.append(node('p', 'Дорога + отель + трансферы'), node('p', term.text, 'term' + (term.refundable === false ? ' warning' : '')));
  body.append(features, priceNode(plan));
  const actions = node('div', null, 'card-actions');
  actions.append(button('Подробнее о поездке', () => openDetail(plan.id)));
  if (selected && state.checkout_allowed) actionButton(actions, 'Подтвердить поездку', 'confirm_booking_demo', {}, 'text-button');
  else if ((state.options || []).some(p => p.id === plan.id) && !state.change_preview && ['choosing', 'ready'].includes(state.status))
    actionButton(actions, selected ? 'Подтвердить выбранную поездку' : 'Выбрать поездку', 'select_plan', {plan_id: plan.id}, 'text-button');
  body.append(actions); card.append(image, body); return card;
}
function breakdown(plan) {
  const rows = node('div', null, 'breakdown');
  Object.keys(breakdownNames).filter(key => plan.breakdown?.[key]).forEach(key => rows.append(node('span', breakdownNames[key]), node('span', money(plan.breakdown[key]))));
  return rows;
}
function checks(plan) {
  const block = node('details', null, 'checks'); block.append(node('summary', 'Проверки и источники'));
  (plan.checks || []).forEach(c => block.append(node('p', (c.status === 'pass' ? '✓ ' : c.status === 'unknown' ? '? ' : '✕ ') + c.message)));
  (plan.evidence || []).forEach(e => block.append(node('p', (e.source_kind === 'synthetic' ? 'Учебный каталог' : e.source_kind) + ' · ' + e.scope)));
  return block;
}
function bookingPanel(plan, proposed = false) {
  const panel = node('aside', null, 'booking-panel');
  panel.append(node('h3', proposed ? 'Новый вариант поездки' : 'Стоимость услуг поездки'), node('p', dateRange(planDates(plan)), 'detail-meta'), breakdown(plan), priceNode(plan));
  const term = cancellation(plan);
  if (term.refundable === false) panel.append(node('p', 'Невозвратный тариф. Бесплатная отмена не предусмотрена.', 'terms-note'));
  if (proposed) actionButton(panel, 'Принять изменение', 'accept_change');
  else if (state.selected_plan?.id === plan.id && state.checkout_allowed) actionButton(panel, 'Подтвердить поездку', 'confirm_booking_demo');
  else if (!state.change_preview && ['choosing', 'ready'].includes(state.status) && (state.options || []).some(p => p.id === plan.id)) actionButton(panel, 'Выбрать поездку', 'select_plan', {plan_id: plan.id});
  else panel.append(node('p', 'Оформление станет доступно после проверки и подтверждения актуальных условий.', 'helper'));
  panel.append(node('p', 'Демонстрационный режим · без оплаты', 'helper'));
  return panel;
}
function changeDetails(before, after) {
  const block = node('section', null, 'change-details'); block.append(node('h3', 'Что изменилось'));
  let count = 0;
  const row = (label, old, next) => { const r = node('div', null, 'change-row'); r.append(node('span', label), node('span', old + ' → ' + next)); block.append(r); count++; };
  for (const key of Object.keys(breakdownNames)) {
    const old = before?.breakdown?.[key], next = after.breakdown?.[key];
    if (old && next && old.amount_minor !== next.amount_minor) row(breakdownNames[key], money(old), money(next));
  }
  const oldDates = before && planDates(before), newDates = planDates(after);
  if (oldDates && newDates && (oldDates.start !== newDates.start || oldDates.end !== newDates.end)) row('Даты', dateRange(oldDates), dateRange(newDates));
  if (before && cancellation(before).text !== cancellation(after).text) row('Отмена', cancellation(before).text, cancellation(after).text);
  if (!count) block.append(node('p', 'Состав и цена сохранены. Вариант повторно проверен по новым условиям.'));
  return block;
}
function renderDetails(plan, proposed = false) {
  const result = $('results');
  if (!proposed) result.append(button('← К подборке', backToOptions, 'back-button'));
  const title = node('div', null, 'detail-heading');
  if (!proposed) title.append(node('p', state.selected_plan?.id === plan.id ? 'Ваша выбранная поездка' : 'Подробнее о варианте', 'eyebrow'));
  title.append(node('h1', destination(plan) + ' · вариант ' + variant(plan)), node('p', dateRange(planDates(plan)) + ' · двое взрослых', 'detail-meta'));
  result.append(title);
  const grid = node('div', null, 'detail-grid' + (proposed ? ' preview-grid' : '')), content = node('div', null, 'detail-content');
  content.append(photo(variant(plan), true));
  if (proposed) {
    content.append(changeDetails(state.selected_plan, plan));
    const names = {dates: 'даты', travellers: 'гости', origin: 'город отправления', destination: 'направление', hard_constraints: 'обязательные условия', preferences: 'пожелания', budget_scope: 'состав бюджета', expense_reserve: 'резерв расходов'};
    const preserved = (state.change_preview.preserved || []).filter(x => names[x]).map(x => names[x]);
    if (preserved.length) content.append(node('p', 'Сохранено: ' + preserved.join(', ') + '.', 'preserved'));
  } else {
    content.append(node('h2', 'Что входит в вашу поездку'));
    const features = node('div', null, 'detail-features');
    const travel = node('div'); travel.append(node('strong', 'Дорога и проживание'), node('p', 'Путь туда-обратно, отель, оба трансфера и сборы включены в общую сумму.'));
    const terms = node('div'); terms.append(node('strong', cancellation(plan).text), node('p', 'Условия из учебного каталога. Подробная проверка доступна ниже.'));
    features.append(travel, terms); content.append(features);
    (plan.tradeoffs || []).filter(t => !/все цены|невозврат/i.test(t)).forEach(t => content.append(node('p', t, 'subtitle')));
  }
  content.append(checks(plan)); grid.append(content, bookingPanel(plan, proposed)); result.append(grid, dataNote());
}
function renderPreview() {
  const preview = state.change_preview;
  const banner = node('div', null, 'change-banner');
  banner.append(node('h2', 'Планы меняются. Вы решаете.'), node('div', signedMoney(preview.price_delta) + ' к прежнему плану', 'delta'), node('p', 'Прежний вариант сохранён. Новый станет выбранным после вашего подтверждения.'));
  $('results').append(banner); renderDetails(preview.proposed_plan, true);
}
function renderBooking() {
  const box = node('section', null, 'booking-success booking');
  box.append(node('div', '✓', 'success-mark'), node('h1', 'Поездка оформлена — в демо'), node('p', 'Всё сохранено. Можно вернуться к этой поездке после перезагрузки страницы.', 'subtitle'), node('p', 'Номер: ' + state.booking.demo_booking_id, 'booking-id'));
  const panel = node('div', null, 'booking-panel');
  if (state.selected_plan) panel.append(node('h3', destination(state.selected_plan)), node('p', dateRange(planDates(state.selected_plan)), 'detail-meta'), breakdown(state.selected_plan));
  panel.append(node('div', money(state.booking.total), 'price'), node('p', 'Услуги не куплены, деньги не списаны. Поездка сохранена в демонстрационном режиме.', 'subtitle'));
  box.append(panel, button('Спланировать новую поездку', start, 'primary', true)); $('results').append(box);
}
function renderEmpty() {
  const result = $('results');
  if (state.revision > 0 || Object.values(state.trip_spec || {}).some(x => x != null)) {
    result.append(heading('Уточним пару деталей', 'Ответьте помощнику слева — и здесь появятся подходящие варианты.', 'Собираем вашу поездку'));
    const questions = state.questions || [];
    if (questions.length) result.append(stateBox('Что осталось уточнить', questions.join('\n')));
    result.append(node('p', 'Из Москвы в Сочи, Казань, Владимир и Ярославль. Двое взрослых, 1–14 ночей в ноябре–декабре 2026 года.', 'context-note')); return;
  }
  const intro = node('div', null, 'empty-intro');
  intro.append(node('p', 'От идеи до вашей поездки', 'eyebrow'), node('h1', 'Куда хочется отправиться?'), node('p', 'Расскажите о планах слева. Сравним варианты и соберём поездку под ваши условия.', 'subtitle'));
  result.append(intro);
  const cards = node('div', null, 'cards inspiration');
  examples.forEach(([title, prompt, key, description]) => {
    const card = node('article', null, 'card'), body = node('div', null, 'card-body');
    body.append(node('h3', title), node('p', description), button('Попробовать этот запрос →', () => fillPrompt(prompt), 'text-button'));
    card.append(photo(key), body); cards.append(card);
  });
  const help = node('div', null, 'empty-help');
  [['Расскажите о планах', 'Можно начать с направления или настроения.'], ['Сравните варианты', 'Видна полная стоимость и условия отмены.'], ['Меняйте по ходу', 'Новые даты и бюджет — одним сообщением.']].forEach(([title, text]) => { const e = node('span'); e.append(node('b', title), document.createTextNode(text)); help.append(e); });
  result.append(cards, help, node('p', 'Учебный каталог: из Москвы в Сочи, Казань, Владимир и Ярославль. Двое взрослых, 1–14 ночей; ноябрь–декабрь 2026, выезд до 31 декабря.', 'context-note'), dataNote());
}
function renderDestinations() {
  $('results').append(heading('Выберите настроение поездки', 'У каждого направления свой характер. Выберите — и сравним варианты.', 'Куда отправимся?'));
  const cards = node('div', null, 'cards');
  (state.destination_options || []).forEach((d, i) => {
    const card = node('article', null, 'card destination-card'), body = node('div', null, 'card-body');
    body.append(node('h3', d.name), node('p', d.reason)); actionButton(body, 'Выбрать направление', 'select_destination', {destination_id: d.id});
    card.append(node('div', ['О!', 'Оо', 'О→', 'О!'][i % 4], 'destination-art'), body); cards.append(card);
  }); $('results').append(cards);
}
function allPlans() {
  const map = new Map();
  for (const p of [state.selected_plan, ...(state.options || [])].filter(Boolean)) if (!map.has(p.id)) map.set(p.id, p);
  return [...map.values()];
}
function render() {
  if (!state) return;
  writeLocal(sessionKey, state.session_id); renderSummary(); renderSuggestions();
  if(typeof cleanupHotelMaps==='function')cleanupHotelMaps();
  $('results').replaceChildren();
  if (hotelMode) { renderHotels(); updateControls(); return; }
  $('option-count').textContent = state.booking ? '' : (state.options || []).length || (state.destination_options || []).length || '';
  if (state.booking) renderBooking();
  else {
    if (state.status === 'error') {
      const box = stateBox('Не удалось обновить подборку', state.assistant_message || 'Прежние условия сохранены. Попробуйте ещё раз.', 'error-state');
      if (lastMessage) box.append(button('Повторить последний запрос', () => submitMessage(lastMessage), 'secondary', true));
      $('results').append(box);
    } else if (state.status === 'no_solution') $('results').append(stateBox('Подходящий вариант пока не найден', state.assistant_message, 'warning'));
    if (state.change_preview) renderPreview();
    else {
      const plans = allPlans(), detail = plans.find(p => p.id === detailID);
      if (detail) renderDetails(detail);
      else if (state.status === 'choosing' && (state.destination_options || []).length) renderDestinations();
      else if (plans.length) {
        const previous = ['needs_input', 'no_solution', 'error'].includes(state.status);
        $('results').append(heading(previous ? 'Ваш предыдущий выбор' : state.selected_plan ? 'Ваша поездка и другие варианты' : plans.length === 3 ? 'Три варианта под ваши планы' : plural(plans.length, 'вариант', 'варианта', 'вариантов') + ' для вашей поездки', previous ? 'Этот вариант сохранён, но ещё не подтверждён по новым условиям.' : 'Полная стоимость для двоих: дорога, проживание, трансферы и сборы.', state.trip_spec?.destination ? 'Ваша поездка · ' + state.trip_spec.destination : 'Подборка для вас'));
        const cards = node('div', null, 'cards'); plans.forEach(p => cards.append(planCard(p))); $('results').append(cards, dataNote());
      } else if (!['error', 'no_solution'].includes(state.status)) renderEmpty();
    }
  }
  updateControls();
}
function persistPending() {
  // Session storage keeps a lost-response retry across reloads without sharing operations with other tabs.
  try { if (pending) sessionStorage.setItem('oplan-pending', JSON.stringify(pending)); else sessionStorage.removeItem('oplan-pending'); } catch { /* Retained in memory. */ }
}
function adopt(snapshot, operation) {
  const windowFrom = hotelMode ? TravelWindow.capture() : null;
  state = snapshot; detailID = operation === 'select_plan' || operation === 'accept_change' ? state.selected_plan?.id : null;
  if(['nearby','transport'].includes(snapshot.selection?.open_panel))detailID=snapshot.selection.hotel_id;
  render(); if(hotelMode) TravelWindow.finish(windowFrom,$('results'));
  // A lost HTTP response may already be present in the restored server history.
  // Reconcile with that history instead of appending the same reply on retry.
  if(Array.isArray(state.messages) && state.messages.length) restoreConversation();
  else if(transcriptRevision !== state.revision) addMessage(assistantText(state), 'assistant');
  transcriptRevision = state.revision; saveConversation();
  if(snapshot.journey_preview || snapshot.journey_recovery || ['select_hotel','clear_hotel_selection','confirm_hotel_booking','update_hotel_stay','accept_journey_change','discard_journey_change','change_transport'].includes(operation)) {
    document.querySelector('.plans').scrollTop=0;
    $('results').focus({preventScroll:true});
  }
  if (state.hotel_options?.length || state.change_preview || state.booking || (state.options || []).length || (state.destination_options || []).length) mobileView('results');
}
async function executePending() {
  if (!pending || working) return;
  const operation = pending; clearError(); busy(true, operation.operation);
  try {
    const snapshot = await api(operation.path, operation.body);
    if(hotelMode) await TravelWindow.prepare(snapshot.hotel_options);
    pending = null; persistPending(); adopt(snapshot, operation.operation);
    if (operation.message && $('message').value.trim() === operation.message) { $('message').value = ''; resizeComposer(); }
    return snapshot;
  } catch (error) {
    if (error instanceof APIError && error.status < 500) {
      pending = null; persistPending();
      if (error.code === 'stale_revision' && state) {
        try { state = await api('/api/sessions/' + state.session_id); detailID = null; restoreConversation(); render(); } catch { /* Keep last known state, but no checkout after unknown revision. */ state.checkout_allowed = false; render(); }
        showError('Поездка обновилась в другой вкладке. Проверьте условия и отправьте сообщение ещё раз.');
      } else showError(error.message);
    } else {
      showError('Связь прервалась. Проверьте подключение и нажмите «Повторить запрос». Ваш выбор сохранён.', executePending);
    }
  } finally { busy(false); if(hotelMode && !$('results').children.length) render(); }
}
async function act(type, extra = {}) {
  if (working || pending || !state || state.booking || (state.hotel_booking && !tripExtraActions.has(type))) return;
  pending = {path: '/api/sessions/' + state.session_id + '/actions', body: {type, ...extra, expected_revision: state.revision, idempotency_key: crypto.randomUUID()}, operation: type, session: state.session_id};
  persistPending(); return await executePending();
}
async function submitMessage(message, operation) {
  if (working || pending || !state || state.booking || state.hotel_booking || !message.trim()) return;
  message = message.trim(); lastMessage = message; addMessage(message, 'user');
  pending = {path: '/api/sessions/' + state.session_id + '/turns', body: {message, expected_revision: state.revision, idempotency_key: crypto.randomUUID()}, operation: operation || (state.selected_plan ? 'change' : 'turn'), message, session: state.session_id};
  persistPending(); return await executePending();
}
async function start() {
  if (working || pending) return;
  clearError(); busy(true, 'create');
  try {
    state = await api('/api/sessions/', {search_mode: hotelMode ? 'hotels' : 'trip'}); detailID = null; transcript = []; transcriptRevision = state.revision;
    $('chat').replaceChildren(); $('message').value = ''; lastMessage = ''; render(); addMessage(assistantText(state), 'assistant'); mobileView('chat');
  } catch (error) { showError('Не удалось начать подбор. Попробуйте ещё раз.', start); }
  finally { busy(false); }
}
async function init() {
  const id = readLocal(sessionKey);
  if (id && /^[a-f0-9]{32}$/.test(id)) {
    busy(true, 'restore');
    try {
      state = await api('/api/sessions/' + id); restoreConversation(); render();
      try {
        const saved = JSON.parse(sessionStorage.getItem('oplan-pending'));
        if (saved?.session === id && saved.path === '/api/sessions/' + id + (saved.message ? '/turns' : '/actions') && saved.body?.idempotency_key) {
          pending = saved; showError('Не удалось получить результат предыдущего запроса. Нажмите «Повторить запрос», чтобы продолжить.', executePending);
        }
      } catch { /* Ignore corrupt local recovery data. */ }
      if (state.hotel_options?.length || state.options?.length || state.selected_plan || state.booking || state.destination_options?.length) mobileView('results');
      return;
    } catch (error) {
      if (!(error instanceof APIError && error.status === 404)) {
        showError('Не удалось загрузить сохранённую поездку. Проверьте соединение с сервером.', init); return;
      }
    } finally { busy(false); }
  }
  await start();
}
$('form').onsubmit = event => { event.preventDefault(); submitMessage($('message').value); };
$('message').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('form').requestSubmit(); } });
$('new').onclick = start;
$('history').onclick = showSearchHistory;
$('message').addEventListener('input',resizeComposer);
window.addEventListener('resize',resizeComposer);
$('edit').onclick = () => fillPrompt('');
$('retry').onclick = () => retryOperation?.();
$('mobile-chat').onclick = () => mobileView('chat');
$('mobile-results').onclick = () => mobileView('results');
$('about').onclick = () => $('about-dialog').showModal();
$('close-about').onclick = $('start-about').onclick = () => $('about-dialog').close();
configureMode();
init();

function configureMode() {
  if (!hotelMode) return;
  document.body.classList.add('smart-mode');
  document.querySelector('.topnav').textContent = 'Умный подбор';
  $('edit').textContent = '✎'; $('edit').setAttribute('aria-label', 'Изменить регион и условия');
  $('edit').onclick = editRegion;
  document.querySelector('.demo-tag').hidden = true;
  document.querySelector('.helper').textContent = '';
  document.querySelector('.assistant-heading p').textContent = 'Найдём место для вашей поездки';
  $('new').textContent = 'Новый поиск +';
  const dialog = $('about-dialog');
  for (const child of [...dialog.children]) if (!child.matches('.dialog-heading, details, #start-about')) child.remove();
  const text = node('p', 'Расскажите, какую поездку хотите. Помощник сравнит отели по вашим условиям и объяснит выбор. Если измените бюджет или даты, остальные пожелания сохранятся.');
  const note = node('p', 'Можно подобрать только отель или собрать поездку с дорогой и трансферами. Стоимость предварительная. Демонстрационный режим: без оплаты и реального бронирования.');
  dialog.insertBefore(text, dialog.querySelector('details')); dialog.insertBefore(note, dialog.querySelector('details'));
  const details = dialog.querySelector('details');
  details.hidden = true;
  for (const p of [...details.querySelectorAll('p')]) if (p.id !== 'model-info') p.remove();
}
function externalLink(text, url, cls = 'primary') {
  const a = node('a', text, cls);
  try { const parsed = new URL(url); const allowedHosts=['ostrovok.ru','help.ostrovok.ru','api.met.no','open-meteo.com','creativecommons.org','www.rzd.ru','www.aeroflot.ru']; if (parsed.protocol !== 'https:' || !allowedHosts.includes(parsed.hostname) || parsed.username || parsed.password) return node('span', 'Ссылка недоступна'); a.href = parsed.href; } catch { return node('span', 'Ссылка недоступна'); }
  a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
}
function hotelPhoto(h, big = false, onOpen = null) {
  const frame = onOpen ? button('', onOpen, 'card-photo hotel-photo-button') : node('div', null, big ? 'detail-photo' : 'card-photo');
  if (onOpen) frame.setAttribute('aria-label', 'Подробнее об отеле «' + h.name + '»');
  const img = node('img'); img.src = h.image_url; img.alt = h.name; img.loading = 'lazy';
  img.onerror = () => { img.remove(); frame.append(node('span', 'Фотография недоступна', 'photo-missing')); };
  frame.append(img); return frame;
}
function hotelFacts(h) {
  const facts = node('div', null, 'hotel-facts');
  if (h.rating != null) facts.append(node('span', String(h.rating).replace('.', ','), 'rating'), node('span', h.reviews ? plural(h.reviews, 'отзыв', 'отзыва', 'отзывов') : 'Оценка на Островке'));
  if (h.distance_m != null) facts.append(node('span', (h.distance_m / 1000).toLocaleString('ru-RU', {maximumFractionDigits: 1}) + ' км до центра'));
  return facts;
}
function hotelCard(h) {
  const card = node('article', null, 'card hotel-card'); card.dataset.hotelId = h.id;
  const body = node('div', null, 'card-body');
  const openHotel = () => openDetail(h.id);
  card.onclick = event => {
    if (event.target.closest('button, a, input, select, textarea, label, summary, [role=button], [role=link]')) return;
    openHotel();
  };
  const title = node('h3'); title.append(button(h.name, openHotel, 'hotel-name-button'));
  body.append(hotelFacts(h), title, node('p', h.address, 'card-subtitle'));
  const features = node('div', null, 'hotel-amenities'); (h.amenities || []).slice(0,3).forEach(x=>features.append(node('span', x)));
  body.append(features, matchReasons(h), hotelPrice(h));
  if(h.journey)body.append(node('p',h.journey.route_missing?'Только проживание · дорога и трансферы не рассчитаны':h.journey.transport?.kind==='car'?'Отель + поездка на автомобиле':'Отель + дорога + оба трансфера','trip-card-route'));
  const actions = node('div', null, 'card-actions');
  actions.append(button(h.journey?.route_missing?'Посмотреть отель':h.journey?'Выбрать поездку':'Выбрать отель', () => h.journey?.route_missing?openDetail(h.id):act('select_hotel',{hotel_id:h.id}), 'primary', true));
  body.append(actions);card.append(hotelPhoto(h, false, openHotel), body);return card;
}
function renderHotels() {
  if(state.journey_recovery){renderSavedHotelSearch();return;}
  if(state.journey_preview){renderJourneyPreview();return;}
  if(state.hotel_booking){renderHotelBooking();return;}
  if(state.selected_hotel && state.status==='hotel_checkout'&&!(detailID&&state.selection?.open_panel==='nearby')){renderHotelCheckout();return;}
  const hotels = state.hotel_options || [];
  $('option-count').textContent = hotels.length || '';
  $('spec').setAttribute('aria-label', 'Условия подбора');

  if (state.status === 'error') {
    const box = stateBox('Не удалось обновить поиск', state.assistant_message, 'error-state');
    if (lastMessage) box.append(button('Повторить последний запрос', () => submitMessage(lastMessage), 'secondary', true));
    box.append(externalLink('Открыть Островок ↗', state.search_url || 'https://ostrovok.ru/', 'text-button'));
    $('results').append(box);
  }
  const h = hotels.find(x=>x.id === detailID);
  if (h) {
    $('results').append(button('← К подборке', backToOptions, 'text-button'));
    const head = node('div', null, 'detail-heading');head.append(node('h1', h.name), node('p', h.address, 'subtitle'), hotelFacts(h));
    const grid = node('div', null, 'detail-grid'), content = node('div', null, 'detail-content'), side = node('aside', null, 'booking-panel');
    const mainPhoto=hotelPhoto(h,true);content.append(mainPhoto);
    const gallery=node('div',null,'hotel-gallery');(h.images||[]).forEach((url,i)=>{const b=button('',()=>{const img=mainPhoto.querySelector('img');if(img)img.src=url},'');b.setAttribute('aria-label','Фото '+(i+1));const img=node('img');img.src=url;img.alt='';b.append(img);gallery.append(b)});if(gallery.children.length>1)content.append(gallery);
    const features = node('div', null, 'hotel-amenities'); (h.amenities || []).forEach(t=>features.append(node('span', t)));content.append(features);
    content.append(matchReasons(h),hotelContentPanel(h));
    if (h.unverified?.length) content.append(node('p', 'Нужно уточнить у отеля: '+h.unverified.join(', '), 'context-note'));
    side.append(node('h2', h.journey?'Ваша поездка':'Ваше размещение'), node('p', state.trip_spec?.dates ? dateRange(state.trip_spec.dates) : plural(h.quote?.nights||0,'ночь','ночи','ночей'), 'detail-meta'), hotelPrice(h));
    if(h.journey?.route_missing)side.append(node('p','Полная стоимость поездки неизвестна. Можно продолжить подбор только проживания.','context-note'),button('Подобрать только отель',()=>{backToOptions();submitMessage('только отель, без дороги');},'primary',true));
    else side.append(button('Перейти к оформлению',()=>act('select_hotel',{hotel_id:h.id}),'primary',true));
    if (!h.journey && state.trip_spec?.travellers?.children?.length) side.append(node('p', 'На сайте укажите взрослых и возраст каждого ребёнка.', 'context-note'));

    if(h.journey)side.append(tripOverview(h),journeyCost(h));
    side.append(sourceInfo(h));
    grid.append(content, side);$('results').append(head, grid);return;
  }
  if (hotels.length) {
    $('results').append(heading(state.status === 'error' ? 'Предыдущая подборка сохранена' : hotels.length === 3 ? 'Три варианта под ваши планы' : 'Нашли '+hotels.length+' '+(hotels.length===1?'подходящий вариант':'подходящих варианта'), 'Сравните, почему они подходят, и выберите свой.', state.trip_spec?.destination || 'Подборка для вас'));
    $('results').append(sourceInfo(hotels[0]),button('Показать другие варианты',()=>submitMessage('Покажи другие варианты'),'text-button',true));
    if(state.trip_spec?.excluded_hotel_ids?.length)$('results').append(button('Вернуть прежние варианты',()=>submitMessage('Верни прежние варианты'),'text-button',true));
    const cards = node('div', null, 'cards');hotels.forEach(h=>cards.append(hotelCard(h)));$('results').append(cards);
    if(hotels.some(h=>h.journey)){ $('results').append(journeyComparison(hotels),sharePanel());return; }
    const note = node('div', null, 'live-source');note.append(node('p', state.selection?.considered ? 'Сравнили '+state.selection.considered+' отелей · подходят '+state.selection.matched+'.' : 'Карточки из каталога Островка.'), externalLink('Все отели на Островке ↗', state.search_url, 'text-button'));$('results').append(note,journeyComparison(hotels),sharePanel());return;
  }
  if (state.status === 'error') return;
  if (state.status === 'no_solution') { $('results').append(stateBox('Давайте немного изменим условия', state.assistant_message, 'warning'));if(state.trip_spec?.excluded_hotel_ids?.length)$('results').append(button('Вернуть прежние варианты',()=>submitMessage('Верни прежние варианты'),'secondary',true));if(state.trip_spec?.include_transport)$('results').append(button('Продолжить только с отелем',()=>submitMessage('Только отель, без дороги'),'secondary',true)); return; }
  // Origin-only updates may return directions, but the start screen stays in place.
  if(state.destination_options?.length && !isHotelInspirationState()){renderHotelDirections();return;}
  if (!isHotelInspirationState() && state.revision > 0 && state.status === 'needs_input') { const box=stateBox('Уточним одну деталь', state.assistant_message);if(state.trip_spec?.transport_owned&&!state.trip_spec.owned_transport)box.append(button('Ваши билеты',()=>ownedTicketsDialog(state.selected_hotel?.id),'primary',true));$('results').append(box); return; }
  if(lastMessage && !isHotelInspirationState()) { $('results').append(stateBox('Запрос сохранён', pending ? 'Связь прервалась. Нажмите «Проверить и повторить запрос» в чате — условия сохранятся.' : 'Продолжим в чате: уточните пожелания к поездке.')); return; }
  $('results').append(heading('Хорошая поездка начинается с идеи', 'Напишите, куда хочется. Соберём отель, дорогу и трансферы в один план.', 'Островок · О!План'));
  const cards = node('div', null, 'cards inspiration');
  [['К морю', 'В Сочи, 10–15 ноября 2026, двое взрослых, до 120 тысяч рублей на дорогу, отель и трансферы. Нужен бассейн.', 'A', 'Сочи, прогулки и несколько дней для себя.'], ['На выходные', 'В Казань на 3 ночи, двое взрослых, до 25 тысяч рублей на отель, рядом с центром.', 'B', 'Новый город, знакомый ритм отдыха.'], ['За впечатлениями', 'В Санкт-Петербург на 4 ночи, двое взрослых, до 30 тысяч рублей на отель. Рейтинг от 8,5.', 'C', 'Петербург: останется выбрать маршрут.']].forEach(([title, prompt, key, text])=>{
    const card=node('article',null,'card'),body=node('div',null,'card-body');body.append(node('h3',title),node('p',text),button('Начать с этой идеи →',()=>fillIdeaPrompt(prompt),'text-button'));const destinationPhotos = {A: ['sochi', 'Чёрное море и побережье Сочи'], B: ['kazan', 'Мечеть Кул-Шариф в Казанском кремле'], C: ['petersburg', 'Канал Грибоедова и Спас на Крови в Петербурге']};
    const [destination, alt] = destinationPhotos[key];
    const cover = node('div', null, 'card-photo'), image = node('img');
    image.src = '/assets/idea-' + destination + '.jpg'; image.alt = alt;
    image.decoding = 'async'; cover.append(image);
    card.append(cover,body);cards.append(card);
  });
  $('results').append(cards);
}

function regionName(spec) {
  const destination = (spec.destination || '').toLowerCase();
  const region = {'стамбул':'Турция','минск':'Беларусь','париж':'Франция','рим':'Италия','венеция':'Италия'}[destination];
  const providerRegion=spec===state.trip_spec?(state.selected_hotel||state.hotel_options?.[0])?.destination_region:null;
  return providerRegion?.countryName || spec.country || region || 'Страна не указана';
}
function matchReasons(h) {
  const list=node('ul',null,'match-reasons');
  (h.reasons || []).slice(0,3).forEach(reason=>list.append(node('li',reason)));
  return list;
}
function hotelPrice(h) {
  const block=node('div',null,'hotel-price');
  if(!h.quote){block.append(node('p','Цены на Островке','hotel-price-note'));return block;}
  block.append(node('strong',(h.source_kind==='public'?'≈ ':'')+money({amount_minor:tripAmount(h)})));
  if(h.journey){block.append(node('small',(h.journey.route_missing?'только проживание · дорога и трансферы не включены':h.journey.total_incomplete?'без стоимости ваших билетов':'за всю поездку')+' · '+hotelGuests()));if(h.journey.transport)block.append(node('small',h.journey.transport.label+' · '+(state.trip_spec?.origin||'Уточните отправление')+' → '+(state.trip_spec?.destination||'')));return block;}
  block.append(node('small',h.quote.nights ? 'за '+plural(h.quote.nights,'ночь','ночи','ночей')+' · '+plural(h.quote.rooms,'номер','номера','номеров') : 'за ночь · '+h.quote.rooms+' номер'+(h.quote.rooms===1?'':'а')));
  return block;
}
function editRegion() {
  if(working || pending)return;
  const d=node('dialog',null,'region-dialog'),form=node('form'),head=node('div',null,'dialog-heading');
  head.append(node('h2','Куда отправимся?'),button('×',()=>d.close(),'icon-button'));head.lastChild.setAttribute('aria-label','Закрыть');
  const country=node('input'),city=node('input');country.setAttribute('aria-label','Страна');city.setAttribute('aria-label','Город или регион');
  country.value=state.trip_spec?.country||'';country.placeholder='Необязательно';country.maxLength=100;
  city.value=state.trip_spec?.destination||'';city.placeholder='Например, Ялта, Карелия или Париж';city.required=true;city.maxLength=160;
  const cLabel=node('label','Страна, если нужно уточнить'),cityLabel=node('label','Город или регион');cLabel.append(country);cityLabel.append(city);
  const submit=node('button','Обновить направление','primary');submit.type='submit';form.append(cityLabel,cLabel,node('p','Проверим направление в поиске Островка. Даты, бюджет и остальные пожелания сохранятся.','context-note'),submit);d.append(head,form);d.onclose=()=>d.remove();document.body.append(d);d.showModal();
  form.onsubmit=e=>{e.preventDefault();if(!form.reportValidity()||!city.value.trim())return;d.close();submitMessage('Ищем отель: '+city.value.trim()+(country.value.trim()?', страна '+country.value.trim():'')+'. Остальные условия сохрани.')};
}

function globeIcon(){
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','globe');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.5');
 const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx','12');circle.setAttribute('cy','12');circle.setAttribute('r','9');
 const path=document.createElementNS(ns,'path');path.setAttribute('d','M3 12h18M12 3c-5 5-5 13 0 18M12 3c5 5 5 13 0 18');svg.append(circle,path);return svg;
}

function resizeComposer(){
 const input=$('message');if(!input)return;
 if(!input.getClientRects().length)return;
 input.style.height='auto';input.style.height=Math.min(input.scrollHeight,Math.max(90,Math.min(210,innerHeight*.24)))+'px';
 input.style.overflowY=input.scrollHeight>input.clientHeight?'auto':'hidden';
}
async function showSearchHistory(){
 if(working||pending)return;
 const previousFocus=document.activeElement,d=node('dialog',null,'history-dialog'),head=node('div',null,'dialog-heading'),list=node('div',null,'history-list');
 head.append(node('h2','История поисков'),button('×',()=>d.close(),'icon-button'));head.lastChild.setAttribute('aria-label','Закрыть историю');
 list.append(node('p','Загружаем ваши поиски…','context-note'));d.append(head,list);
 d.onclose=()=>{d.remove();if(previousFocus?.isConnected)previousFocus.focus();};document.body.append(d);d.showModal();
 try{
  const items=await api('/api/sessions/?mode='+ (hotelMode?'hotels':'trip'));list.replaceChildren();
  if(!items.length)list.append(node('p','Здесь появятся ваши поиски. Начните с идеи поездки.','context-note'));
  for(const item of items){
   const b=button('',async()=>{
    if(working||pending)return;
    list.querySelectorAll('.history-item').forEach(control=>control.disabled=true);
    busy(true,'restore');
    try{
     const snapshot=await api('/api/sessions/'+item.session_id);
     state=snapshot;detailID=null;lastMessage='';clearError();restoreConversation();render();
     $('message').value='';resizeComposer();
     mobileView(snapshot.hotel_booking||snapshot.booking||snapshot.selected_hotel||snapshot.hotel_options?.length||snapshot.destination_options?.length?'results':'chat');
     d.close();document.querySelector('.plans').scrollTop=0;$('results').focus({preventScroll:true});
    }catch{
     if(d.isConnected){list.querySelectorAll('.history-item').forEach(control=>control.disabled=false);list.prepend(node('p','Не удалось открыть поиск. Попробуйте ещё раз.','error'));}
    }finally{busy(false);}
   },'history-item');
   b.dataset.sessionId=item.session_id;
   const spec=item.trip_spec||{},meta=[spec.destination,spec.dates&&dateRange(spec.dates),hotelGuestComposition(spec)].filter(Boolean).join(' · ');
   b.append(node('strong',item.hotel_name||item.title),node('span',meta||'Выбираем направление'));
   const route=[item.transport_label,item.transfer_label].filter(Boolean).join(' · ');
   if(route)b.append(node('span',route,'history-route'));
   if(item.status==='hotel_booked'&&Number.isFinite(item.total_minor)&&item.currency==='RUB')b.append(node('span','Итого ≈ '+money({amount_minor:item.total_minor}),'history-total'));
   b.append(node('small',new Date(item.updated_at).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})+(item.status==='hotel_booked'?' · Оформлено':item.session_id===state.session_id?' · Открыт сейчас':'')));
   list.append(b);
  }
 }catch{list.replaceChildren(node('p','История временно недоступна. Закройте окно и попробуйте ещё раз.','error'));}
}

window.addEventListener('DOMContentLoaded',()=>{document.querySelector('.searchbar')?.append(preferencesControl());});

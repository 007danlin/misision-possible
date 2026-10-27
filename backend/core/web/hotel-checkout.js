'use strict';
const checkoutGuestDraft={};
function guestDraft(){
 const id=state.session_id;
 if(Object.hasOwn(checkoutGuestDraft,id))return checkoutGuestDraft[id];
 try{return sessionStorage.getItem('oplan-guest:'+id)||'';}catch{return '';}
}
function saveGuestDraft(value){
 checkoutGuestDraft[state.session_id]=value;
 try{sessionStorage.setItem('oplan-guest:'+state.session_id,value);}catch{/* Keep the draft in memory when browser storage is unavailable. */}
}
const directionPhotos={"Сортавала": {"image_url": "https://cdn.ostrovok.ru/t/640x400/extranet/dc/36/dc36c027cc0ba229f04c7776a3774ddbfc2488a8.PNG", "photo_source": "https://ostrovok.ru/hotel/russia/sortavala/mid13426149/uyutny_dom_private_house_9/?language=ru", "photo_name": "Частный дом Дом Гнездо Аиста Коттедж №2"}, "Осташков": {"image_url": "https://cdn.ostrovok.ru/t/640x400/extranet/6c/ba/6cba86d373fd90347be81beefcd2288e8c2b4f55.JPEG", "photo_source": "https://ostrovok.ru/hotel/russia/ostashkov/mid13428923/na_beregu_seligera_private_house_2/?language=ru", "photo_name": "Частный дом на Берегу Селигера"}, "Сочи": {"image_url": "https://cdn.ostrovok.ru/t/640x400/extranet/21/77/217787f8947cbdbdc5c766540d69a9a4e3437a56.JPEG", "photo_source": "https://ostrovok.ru/hotel/russia/sochi/mid7942708/bellagio_hotel_3/?language=ru", "photo_name": "Отель Спа Bellagio"}, "Санкт-Петербург": {"image_url": "https://cdn.ostrovok.ru/t/640x400/extranet/64/6f/646f71c392fa05b5a3524dab7967289219b30edf.JPEG", "photo_source": "https://ostrovok.ru/hotel/russia/st._petersburg/mid11235014/hotel_hovard_club/?language=ru", "photo_name": "Отель Hovard Club"}, "Чемал": {"image_url": "https://cdn.ostrovok.ru/t/640x400/extranet/fb/06/fb06801ac7e65ba56ed8495d692afaaef5b132af.JPEG", "photo_source": "https://ostrovok.ru/hotel/russia/altai_republic_chemal/mid13949591/recreation_camp_eko_hotel_v_gorakh_altaya_shale_leshiy/?language=ru", "photo_name": "База отдыха ЭКО отель в горах Алтая Шале Леший"}};
function hotelGuests(s=state.trip_spec) {
 const t=s?.travellers||{};
 return [t.adults&&plural(t.adults,'взрослый','взрослых','взрослых'),t.children?.length&&plural(t.children.length,'ребёнок','ребёнка','детей')].filter(Boolean).join(' · ');
}
function childAgesText(travellers={}) {
 const ages=travellers.children||[];
 return ages.length?'Возраст детей: '+ages.map(age=>age==null?'не указан':age===0?'до 1 года':plural(age,'год','года','лет')).join(', '):'';
}
function hotelGuestComposition(spec={}) {return [hotelGuests(spec),childAgesText(spec.travellers)].filter(Boolean).join(' · ');}
function checkoutSteps(done=false){
 const bar=node('div',null,'checkout-steps');['Выбор отеля','Оформление','Готово'].forEach((t,i)=>{const step=node('span',null,i===(done?2:1)?'current':'');step.append(node('b',i<(done?2:1)?'✓':String(i+1)),document.createTextNode(t));bar.append(step)});return bar;
}
function hotelTerms(h) {
 const q=h.quote,box=node('div',null,'checkout-terms');
 if(h.source_kind==='public'){box.append(node('h3','Что входит в стоимость'),node('p',plural(q.rooms,'номер','номера','номеров')+' · '+hotelGuests()),node('p',q.breakfast?'Питание учтено в стоимости':'Проживание без питания'),node('p','Перед бронированием уточните номер, питание, правила отмены и возможные доплаты.'),node('p',h.journey?(h.journey.transport?.kind==='car'?'Дорога на автомобиле учтена в стоимости; отдельные трансферы не нужны':'Дорога и оба трансфера учтены в стоимости'):h.transfer_addon?'Оба трансфера учтены в стоимости':'Дорога и трансферы не включены'));return box;}

 box.append(node('h3','В стоимость входит'),node('p',plural(q.rooms,'номер','номера','номеров')+' · '+hotelGuests()),node('p',q.breakfast?'Завтрак включён':'Без питания'),node('p',h.journey?.cancellation_until?'Отмена без штрафа до '+tripTime(h.journey.cancellation_until):q.free_cancellation?'Отмена предусмотрена в расчёте; точный срок не подтверждён':'Тариф без возврата'),node('p',h.journey?(h.journey.transport?.kind==='car'?'Дорога на автомобиле включена; отдельные трансферы не нужны':'Дорога и оба трансфера включены'):'Сборы на месте требуют уточнения'));
 return box;
}
function bookingSummary(h,dates,travellers=state.trip_spec?.travellers){
 const side=node('aside',null,'checkout-summary');side.append(hotelPhoto(h),node('h3',h.name),node('p',h.address,'context-note'));
 const stay=node('p',dates?dateRange(dates):plural(h.quote.nights,'ночь','ночи','ночей'),'checkout-stay');stay.id='checkout-stay';
 side.append(stay,node('p',hotelGuests({travellers}),'detail-meta'));if(childAgesText(travellers))side.append(node('p',childAgesText(travellers),'detail-meta guest-ages'));side.append(hotelPrice(h));
 const row=node('div',null,'checkout-total');row.append(node('span','Итого'),node('strong',money({amount_minor:tripAmount(h)})));side.append(row);if(h.journey)side.append(journeyCost(h));side.append(sourceInfo(h));return side;
}
function renderHotelCheckout(){
 const h=state.selected_hotel;if(!h)return;
 $('results').append(checkoutSteps(),button('← Выбрать другой отель',()=>act('clear_hotel_selection'),'text-button',true),heading('Остался один шаг','Проверьте детали поездки и укажите имя гостя.','Ваш выбор'));
 const grid=node('div',null,'checkout-grid'),form=node('form',null,'checkout-form'),spec=state.trip_spec||{},q=h.quote;
 const dates=node('section',null,'checkout-section');dates.append(node('h2','Даты и гости'));
 const controls=node('div',null,'stay-controls');
 for(const [label,value,focus] of [['Заезд',spec.dates?.start?dateText(spec.dates.start):'Выбрать дату','stay-in'],['Выезд',spec.dates?.end?dateText(spec.dates.end):'Выбрать дату','stay-out'],['Гости',hotelGuests()||'Указать гостей','stay-adults']]){
  const b=button('',()=>editHotelStay(focus),'stay-control');b.setAttribute('aria-label','Изменить '+(label==='Гости'?'гостей':label.toLowerCase()));b.append(node('small',label),node('strong',value),node('span','⌄','stay-chevron'));controls.append(b);
 }
 dates.append(controls);if(childAgesText(spec.travellers))dates.append(node('p',childAgesText(spec.travellers),'detail-meta guest-ages'));dates.append(node('p',plural(q.nights,'ночь','ночи','ночей'),'detail-meta'));
 const guests=node('section',null,'checkout-section');guests.append(node('h2','Кто поедет?'));
 const name=node('input');name.name='guest_name';name.id='guest-name';name.required=true;name.minLength=2;name.maxLength=100;name.autocomplete='name';name.placeholder='Например, Александр Иванов';
 name.value=guestDraft();name.oninput=()=>saveGuestDraft(name.value);
 const nameLabel=node('label','Имя и фамилия гостя');nameLabel.htmlFor=name.id;nameLabel.append(name);guests.append(nameLabel);
 const consent=node('label',null,'checkout-consent'),check=node('input');check.type='checkbox';check.id='booking-consent';check.required=true;
 consent.append(check,node('span','Демонстрационный режим: без оплаты и реального бронирования.'));
 const blocked=h.journey?.checks.some(c=>c.blocking&&c.status!=='pass'&&!['budget','hotel_budget'].includes(c.code));
 const submit=node('button','Подтвердить поездку','primary');submit.type='submit';submit.dataset.mutation='';submit.dataset.blocked=String(!!blocked);submit.disabled=working||!!pending||!!blocked;
 const over=hotelOverBudget(h),budgetAccept=node('input');budgetAccept.type='checkbox';budgetAccept.required=over;budgetAccept.id='budget-accept';
 const overLabel=node('label',null,'checkout-consent budget-overrun');overLabel.append(budgetAccept,node('span','Новая стоимость выше бюджета. Подтверждаю сумму '+money({amount_minor:tripAmount(h)})+'.'));
 form.append(dates);if(h.journey)form.append(tripOverview(h),transportChoices(h),journeyRoute(h),journeyChecks(h));form.append(guests,hotelTerms(h));if(over)form.append(overLabel);form.append(consent,submit);grid.append(form,bookingSummary(h,spec.dates));$('results').append(grid);
 form.onsubmit=e=>{e.preventDefault();if(!spec.dates){editHotelStay('stay-in');return;}if(!form.reportValidity())return;act('confirm_hotel_booking',{check_in:spec.dates.start,guest_name:name.value.trim(),confirm_prototype:check.checked,accept_budget_overrun:over&&budgetAccept.checked});};
}
function renderHotelBooking(){
 const b=state.hotel_booking,h=b.hotel;
 delete checkoutGuestDraft[state.session_id];
 try{sessionStorage.removeItem('oplan-guest:'+state.session_id);}catch{/* The confirmed name is already saved with the trip. */}
 $('results').append(checkoutSteps(true));
 const head=node('div',null,'booking-success');head.append(node('span','✓','success-seal'),node('p','Всё готово','card-kicker'),node('h1','Поездка оформлена'),node('p','Сохранили ваш выбор и все детали. Хорошего путешествия!','subtitle'));$('results').append(head);
 const grid=node('div',null,'checkout-grid'),content=node('div',null,'checkout-form'),info=node('section',null,'checkout-section');
 info.append(node('p','Номер поездки','detail-meta'),node('h2',b.id),node('p',b.guest_name),node('p',dateRange(b.dates)),node('p',hotelGuests({travellers:b.travellers})));
 if(childAgesText(b.travellers))info.append(node('p',childAgesText(b.travellers),'detail-meta guest-ages'));
 content.append(info);if(h.journey)content.append(journeyRoute(h,true),journeyChecks(h));content.append(hotelTerms(h),node('p','Демонстрационный режим: без оплаты и реального бронирования.','context-note'));
 const download=button('Скачать план поездки · PDF',()=>downloadHotelPlan(b,download),'primary');
 if(h.transfer_addon)content.append(addonRoute(h.transfer_addon));content.append(bookingExtras(b),sharePanel());
 content.append(download,button('Спланировать ещё одну поездку',start,'text-button'));
 grid.append(content,bookingSummary(h,b.dates,b.travellers));$('results').append(grid);
}
async function downloadHotelPlan(b,control){
 const label=control?.textContent;
 clearError();
 if(control){control.disabled=true;control.textContent='Готовим PDF…';control.setAttribute('aria-busy','true');}
 try{
  const bytes=await TripPDF.create(b,state.trip_spec||{});
  const a=document.createElement('a'),url=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));
  a.href=url;a.download='OPlan-'+b.id+'.pdf';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
 }catch(error){showError('Не удалось подготовить PDF. Попробуйте скачать план ещё раз.');}
 finally{if(control){control.disabled=false;control.textContent=label;control.removeAttribute('aria-busy');}}
}
function renderHotelDirections(){
 $('results').append(heading(['forest','nature'].includes(state.trip_spec?.travel_setting)?'Поближе к дикой природе':'Начнём с направления','Выберите место — даты, бюджет и пожелания сохранятся.','Есть идея'));
 const cards=node('div',null,'cards direction-cards');
 for(const d of state.destination_options){const card=node('article',null,'card direction-card'),visual=node('div',null,'direction-visual'),body=node('div',null,'card-body');const photo=directionPhotos[d.destination],img=node('img');img.src=d.image_url||photo?.image_url||images.B;img.alt=d.name;img.loading='eager';if(photo)img.title=photo.photo_name+' · Островок';visual.append(img);body.append(node('h3',d.name),node('p',d.reason),button('Выбрать '+d.name,()=>submitMessage('Выбираю '+d.name+', ищем в районе '+d.destination+'. Остальные пожелания сохрани.'),'primary',true));card.append(visual,body);cards.append(card)}
 $('results').append(cards);
}

function hotelOverBudget(h){if(h.journey)return h.journey.checks.some(c=>['budget','hotel_budget'].includes(c.code)&&c.status!=='pass');const s=state.trip_spec;if(!s?.budget)return false;return (s.budget_period==='night'?h.quote.nightly_minor:h.quote.total_minor)>s.budget.amount_minor;}
function editHotelStay(focusID='stay-in'){
 if(working||pending||!state.selected_hotel)return;
 const previousFocus=document.activeElement,s=state.trip_spec||{},t=s.travellers||{},d=node('dialog',null,'stay-dialog'),head=node('div',null,'dialog-heading'),form=node('form');
 head.append(node('h2','Даты и гости'),button('×',()=>d.close(),'icon-button'));head.lastChild.setAttribute('aria-label','Закрыть даты и гостей');
 function input(label,id,type,value){const l=node('label',label),i=node('input');i.id=id;i.type=type;i.value=value??'';i.required=true;l.append(i);return [l,i];}
 const [inLabel,checkIn]=input('Заезд','stay-in','date',s.dates?.start),[outLabel,checkOut]=input('Выезд','stay-out','date',s.dates?.end),[adultLabel,adults]=input('Взрослые','stay-adults','number',t.adults||1),[childLabel,children]=input('Дети','stay-children','number',t.children?.length||0);
 adults.min=1;adults.max=20;children.min=0;children.max=10;checkIn.min=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const fields=node('div',null,'stay-fields'),ages=node('div',null,'child-ages'),hint=node('p','','context-note');let ageValues=[...(t.children||[])];
 function renderAges(){ages.replaceChildren();const count=Math.max(0,Math.min(10,Number(children.value)||0));for(let i=0;i<count;i++){const l=node('label','Возраст ребёнка '+(i+1)),select=node('select');select.required=true;select.setAttribute('aria-label','Возраст ребёнка '+(i+1));const empty=node('option','Выберите');empty.value='';select.append(empty);for(let a=0;a<18;a++){const o=node('option',a===0?'До 1 года':plural(a,'год','года','лет'));o.value=a;select.append(o)}select.value=ageValues[i]??'';select.onchange=()=>ageValues[i]=select.value===''?null:Number(select.value);l.append(select);ages.append(l)}}
 // Keep hidden ages while editing the count; only visible children are submitted.
 children.oninput=renderAges;renderAges();
 function updateNights(){const n=(Date.parse(checkOut.value)-Date.parse(checkIn.value))/86400000;hint.textContent=Number.isFinite(n)&&n>0?plural(n,'ночь','ночи','ночей'):'Выберите даты поездки';checkOut.setCustomValidity(checkIn.value&&checkOut.value&&!(n>=1&&n<=60)?'От 1 до 60 ночей, выезд позже заезда':'');}
 checkIn.oninput=()=>{if(checkIn.value&&!checkOut.value){const e=new Date(checkIn.value+'T12:00:00Z');e.setUTCDate(e.getUTCDate()+(state.selected_hotel.quote.nights||1));checkOut.value=e.toISOString().slice(0,10)}updateNights()};checkOut.oninput=updateNights;updateNights();
 const error=node('p',null,'error'),submit=node('button','Сохранить и пересчитать','primary');submit.type='submit';
 fields.append(inLabel,outLabel,adultLabel,childLabel);form.append(fields,ages,hint,error,submit);d.append(head,form);d.onclose=()=>{d.remove();if(previousFocus?.isConnected)previousFocus.focus();};document.body.append(d);d.showModal();d.querySelector('#'+focusID)?.focus();
 form.onsubmit=async e=>{e.preventDefault();if(!form.reportValidity())return;submit.disabled=true;error.textContent='';const revision=state.revision;
  await act('update_hotel_stay',{stay:{check_in:checkIn.value,check_out:checkOut.value,adults:Number(adults.value),children:[...ages.querySelectorAll('select')].map(i=>Number(i.value))}});
  if(state.revision>revision)d.close();else{submit.disabled=false;error.textContent=$('error').textContent||'Не удалось обновить условия. Попробуйте ещё раз.';}
 };
}

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
// Destination photographs are independent of hotel offer images.
const directionPhotos={
  "Сортавала": {
    "image_url": "/assets/directions/karelia.jpg",
    "alt": "Сосновые острова и скалистые берега Ладожских шхер, Карелия",
    "author": "Yuriy Stolypin",
    "source": "https://commons.wikimedia.org/wiki/File:Summer%2C_August%2C_morning%2C_skerries.jpg",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/"
  },
  "Чемал": {
    "image_url": "/assets/directions/altai.jpg",
    "alt": "Лесистые горы и слияние рек Чемал и Катунь, Алтай",
    "author": "Ludvig14",
    "source": "https://commons.wikimedia.org/wiki/File:Chemal-KatunRiversConfluence_014_2458.jpg",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"
  },
  "Осташков": {
    "image_url": "/assets/directions/seliger.jpg",
    "alt": "Остров Вороний и лесные берега озера Селигер",
    "author": "Александр Байдуков",
    "source": "https://commons.wikimedia.org/wiki/File:Lake_Seliger._Ostashkov._View_of_Voroniy_Island.jpg",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"
  },
  "Сочи": {
    "image_url": "/assets/idea-sochi.jpg",
    "alt": "Чёрное море и побережье Сочи"
  },
  "Санкт-Петербург": {
    "image_url": "/assets/idea-petersburg.jpg",
    "alt": "Канал Грибоедова и Спас на Крови в Петербурге"
  },
  "Казань": {
    "image_url": "/assets/idea-kazan.jpg",
    "alt": "Мечеть Кул-Шариф в Казанском кремле"
  },
  "sochi_nature": {
    "image_url": "/assets/directions/sochi_nature.jpg",
    "alt": "Агурский водопад и лес в окрестностях Сочи",
    "author": "Alexander V. Solomin",
    "source": "https://commons.wikimedia.org/wiki/File:Upper_Agura_waterfall.JPG",
    "license": "CC0",
    "license_url": "http://creativecommons.org/publicdomain/zero/1.0/deed.en"
  },
  "gelendzhik": {
    "image_url": "/assets/directions/gelendzhik.jpg",
    "alt": "Пейзаж и достопримечательности: Геленджик",
    "author": "Alexxx1979",
    "source": "https://commons.wikimedia.org/wiki/File:Gelendzhik_View_of_the_city_IMG_8367_1725.jpg",
    "license": "CC BY-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/3.0"
  },
  "anapa": {
    "image_url": "/assets/directions/anapa.jpg",
    "alt": "Пейзаж и достопримечательности: Анапа",
    "author": "\nThis photography was created by Artem Topchiy (user Art-top). Other photos see here\n\n\n This photograph was taken with a Canon PowerShot S2 IS",
    "source": "https://commons.wikimedia.org/wiki/File:Anapa._Beach.JPG",
    "license": "CC BY 3.0",
    "license_url": "https://creativecommons.org/licenses/by/3.0"
  },
  "kislovodsk": {
    "image_url": "/assets/directions/kislovodsk.jpg",
    "alt": "Пейзаж и достопримечательности: Кисловодск",
    "author": "Vyacheslav Argenberg",
    "source": "https://commons.wikimedia.org/wiki/File:Kislovodsk_National_Park,_Valley_of_Roses,_Kislovodsk,_Russia.jpg",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0"
  },
  "murmansk": {
    "image_url": "/assets/directions/murmansk.jpg",
    "alt": "Пейзаж и достопримечательности: Мурманск и Кольский полуостров",
    "author": "Tom Thiel",
    "source": "https://commons.wikimedia.org/wiki/File:Murmansk_(cropped).jpg",
    "license": "CC BY 2.0",
    "license_url": "https://creativecommons.org/licenses/by/2.0"
  },
  "yaroslavl": {
    "image_url": "/assets/directions/yaroslavl.jpg",
    "alt": "Пейзаж и достопримечательности: Ярославль",
    "author": "Allmyexesliveintexas22",
    "source": "https://commons.wikimedia.org/wiki/File:Yaroslavl_Russia_Montage.jpg",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0"
  },
  "vladimir": {
    "image_url": "/assets/directions/vladimir.jpg",
    "alt": "Пейзаж и достопримечательности: Владимир",
    "author": "Vladimir-city",
    "source": "https://commons.wikimedia.org/wiki/File:%D0%92%D0%BB%D0%B0%D0%B4%D0%B8%D0%BC%D0%B8%D1%80,_%D0%B2%D0%B8%D0%B4_%D0%BD%D0%B0_%D0%A3%D1%81%D0%BF%D0%B5%D0%BD%D1%81%D0%BA%D0%B8%D0%B9_%D1%81%D0%BE%D0%B1%D0%BE%D1%80.JPG",
    "license": "CC BY-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/3.0"
  },
  "nizhny": {
    "image_url": "/assets/directions/nizhny.jpg",
    "alt": "Пейзаж и достопримечательности: Нижний Новгород",
    "author": "AlexTref871",
    "source": "https://commons.wikimedia.org/wiki/File:Nizhny_Novgorod_2025-04-29_Minin_and_Pozharsky_square_01.jpg",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0"
  },
  "kaliningrad": {
    "image_url": "/assets/directions/kaliningrad.jpg",
    "alt": "Пейзаж и достопримечательности: Калининград",
    "author": "A.Savin",
    "source": "https://commons.wikimedia.org/wiki/File:Kaliningrad_05-2017_img07_Fishery_Village.jpg",
    "license": "FAL",
    "license_url": "http://artlibre.org/licence/lal/en"
  },
  "moscow": {
    "image_url": "/assets/directions/moscow.jpg",
    "alt": "Пейзаж и достопримечательности: Москва",
    "author": "U.S. Department of State",
    "source": "https://commons.wikimedia.org/wiki/File:Saint_Basil%27s_Cathedral_and_the_Red_Square.jpg",
    "license": "Public domain",
    "license_url": ""
  },
  "minsk": {
    "image_url": "/assets/directions/minsk.jpg",
    "alt": "Пейзаж и достопримечательности: Минск",
    "author": "Homoatrox",
    "source": "https://commons.wikimedia.org/wiki/File:View_of_Minsk_(180819)_09.jpg",
    "license": "CC BY-SA 3.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/3.0"
  },
  "istanbul": {
    "image_url": "/assets/directions/istanbul.jpg",
    "alt": "Пейзаж и достопримечательности: Стамбул",
    "author": "Hunanuk",
    "source": "https://commons.wikimedia.org/wiki/File:Historical_peninsula_and_modern_skyline_of_Istanbul.jpg",
    "license": "CC0",
    "license_url": "http://creativecommons.org/publicdomain/zero/1.0/deed.en"
  },
  "paris": {
    "image_url": "/assets/directions/paris.jpg",
    "alt": "Пейзаж и достопримечательности: Париж",
    "author": "Yann Caradec from Paris, France",
    "source": "https://commons.wikimedia.org/wiki/File:La_Tour_Eiffel_vue_de_la_Tour_Saint-Jacques,_Paris_ao%C3%BBt_2014_(2).jpg",
    "license": "CC BY-SA 2.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/2.0"
  },
  "rome": {
    "image_url": "/assets/directions/rome.jpg",
    "alt": "Пейзаж и достопримечательности: Рим",
    "author": "Diliff",
    "source": "https://commons.wikimedia.org/wiki/File:Trevi_Fountain,_Rome,_Italy_2_-_May_2007.jpg",
    "license": "CC BY 3.0",
    "license_url": "https://creativecommons.org/licenses/by/3.0"
  },
  "venice": {
    "image_url": "/assets/directions/venice.jpg",
    "alt": "Пейзаж и достопримечательности: Венеция",
    "author": "kallerna",
    "source": "https://commons.wikimedia.org/wiki/File:Venezia_aerial_view.jpg",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0"
  }
};
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
 const supplierUnknown=c=>c.status==='unknown'&&['children','pets','cancellation','other','no_connections','no_night_travel'].includes(c.code);
 const submit=node('button','Подтвердить поездку','primary');submit.type='submit';
 const over=hotelOverBudget(h),budgetAccept=node('input');budgetAccept.type='checkbox';budgetAccept.required=over;budgetAccept.id='budget-accept';
 const overLabel=node('label',null,'checkout-consent budget-overrun');overLabel.append(budgetAccept,node('span','Новая стоимость выше бюджета. Подтверждаю сумму '+money({amount_minor:tripAmount(h)})+'.'));
 form.append(dates);if(h.journey)form.append(tripOverview(h),transportChoices(h),journeyRoute(h),journeyChecks(h));form.append(guests,hotelTerms(h));if(over)form.append(overLabel);if((h.journey?.checks||[]).some(supplierUnknown))form.append(node('p','Можно сохранить предварительный план. Неподтверждённые условия нужно уточнить у поставщиков перед бронированием.','context-note'));
 form.append(consent,submit);grid.append(form,bookingSummary(h,spec.dates));$('results').append(grid);
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
 const nature=['forest','nature','mountains'].includes(state.trip_spec?.travel_setting);
 $('results').append(heading(nature?'Природа и пейзажи':'Начнём с направления','Выберите место — даты, бюджет и пожелания сохранятся.','Есть идея'));
 const cards=node('div',null,'cards direction-cards');
 for(const d of state.destination_options){
  const card=node('article',null,'card direction-card'),visual=node('div',null,'direction-visual'),body=node('div',null,'card-body');
  const photo=directionPhotos[d.photo_key] || directionPhotos[d.id] || directionPhotos[d.destination];
  const fallback=()=>{visual.replaceChildren(TravelWindow.art(d.scene||'road'));visual.setAttribute('role','img');visual.setAttribute('aria-label','Иллюстрация направления: '+d.name);};
  if(photo){
   const img=node('img');img.src=photo.image_url;img.alt=photo.alt;img.loading='eager';img.onerror=fallback;visual.append(img);
  }else fallback();
  body.append(node('h3',d.name),node('p',d.reason));
  if(d.caveat)body.append(node('p',d.caveat,'direction-caveat'));
  if(d.source_url){const link=node('a','О направлении','direction-credit');link.href=d.source_url;link.target='_blank';link.rel='noopener noreferrer';body.append(link);}
  if(photo?.author){
   const credit=node('small',null,'direction-credit'),source=node('a','Фото: '+photo.author),license=node('a',photo.license);
   source.href=photo.source;license.href=photo.license_url;
   for(const link of [source,license]){link.target='_blank';link.rel='noopener noreferrer';}
   credit.append(source,document.createTextNode(' · '),license);body.append(credit);
  }
  body.append(button('Выбрать '+d.name,()=>submitMessage('Выбираю '+d.name+', ищем в районе '+d.destination+'. Остальные пожелания сохрани.'),'primary',true));
  card.append(visual,body);cards.append(card);
 }
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

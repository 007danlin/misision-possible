'use strict';
function sourceDate(value){return value?new Date(value).toLocaleDateString('ru-RU'):'дата не указана';}
function publicRoomPanel(h){
 const c=h.content||{},d=fold('Номера и правила');
 if(h.content_status==='unavailable')d.append(node('p','Не удалось загрузить подробности. Попробуйте открыть отель позже.'));
 const times=[c.checkin_from&&'Заезд с '+c.checkin_from,c.checkin_until&&'До '+c.checkin_until,c.checkout_until&&'Выезд до '+c.checkout_until,c.reception_24h&&'Стойка регистрации 24/7'].filter(Boolean);
 d.append(node('p',times.join(' · ')||'Часы заезда и выезда не указаны'));
 if(c.room_categories?.length){d.append(node('h3','Категории в отеле'));for(const r of c.room_categories){d.append(node('p',[r.name,r.beds,r.area_m2>0&&r.area_m2+' м²'].filter(Boolean).join(' · ')));}}
 d.append(node('p','Стоимость рассчитана для двухместных номеров. Вместимость, питание и условия отмены уточните на выбранные даты.','context-note'));
 if(c.charges?.length){d.append(node('h3','Возможные платежи на месте'));for(const x of c.charges)d.append(node('p',x.label+': '+x.price+' '+x.currency+' · '+x.unit+(x.included?' · указано как включённое':'')));}
 for(const s of c.policy_notes||[])d.append(node('p',s));
 const services=fold('Все удобства');for(const g of c.amenity_groups||[])services.append(node('h3',g.name),node('p',g.items.join(' · ')));if(c.amenity_groups?.length)d.append(services);
 d.append(node('p','Проверено '+sourceDate(h.content_checked_at)+(h.content_status==='cached_stale'?' · сведения могут быть неактуальны':''),'context-note'));return d;
}
function publicReviewPanel(h){
 const d=fold('Отзывы'+(h.reviews?' · '+h.reviews:''));const reviews=h.review_items||[];
 d.append(node('p','Оценка '+(h.rating??'не указана')+' / 10 · всего '+(h.reviews??'неизвестно')+' отзывов на Островке','context-note'));
 if(!reviews.length){d.append(node('p','Отзывы можно прочитать на странице отеля на Островке.'));return d;}
 d.append(node('p','Показываем '+plural(reviews.length,'отзыв','отзыва','отзывов')+' · все отзывы — на Островке','context-note'));
 const controls=node('div',null,'review-controls'),filter=node('select'),sort=node('select');filter.setAttribute('aria-label','Тема отзывов');sort.setAttribute('aria-label','Порядок отзывов');
 for(const t of ['Все темы','Тишина','Чистота','Питание','С детьми','Расположение']){const o=node('option',t);o.value=t;filter.append(o);}
 for(const [v,t] of [['new','Сначала новые'],['low','Сначала низкие оценки'],['high','Сначала высокие оценки']]){const o=node('option',t);o.value=v;sort.append(o);}
 const summary=node('div',null,'review-evidence'),list=node('div',null,'review-list');
 function render(){summary.replaceChildren();list.replaceChildren();const themes=filter.value==='Все темы'?Object.keys(h.review_summary||{}):[filter.value];
  for(const theme of themes){const s=h.review_summary?.[theme];if(!s?.mention_ids.length)continue;const box=node('div',null,'review-theme');box.append(node('strong',theme),node('p','Положительных отзывов: '+s.positive_ids.length+' · с замечаниями: '+s.negative_ids.length));
   if(s.positive_ids.length&&s.negative_ids.length)box.append(node('p','Впечатления различаются — есть упоминания и в плюсах, и в минусах.','context-note'));
   const evidence=button('Показать отзывы по теме',()=>{filter.value=theme;render();list.scrollIntoView({block:'nearest'});},'text-button');box.append(evidence);summary.append(box);
  }
  const selected=reviews.filter(r=>filter.value==='Все темы'||r.themes.includes(filter.value)).sort((a,b)=>sort.value==='new'?String(b.date).localeCompare(String(a.date)):sort.value==='low'?(a.rating??11)-(b.rating??11):(b.rating??-1)-(a.rating??-1));
  if(!selected.length)list.append(node('p','Среди показанных отзывов нет отзывов на эту тему. Попробуйте другую.'));
  for(const r of selected){const item=node('article',null,'review-item');item.id='review-'+r.id;item.append(node('strong',(r.rating??'—')+'/10'),node('small',[r.date,r.traveller].filter(Boolean).join(' · ')),...(r.themes.length?[node('p',r.themes.join(' · '),'context-note')]:[]));
   if(r.text){const details=fold('Фрагмент отзыва');details.append(node('blockquote',r.text));item.append(details);}else item.append(node('p','Читать полный отзыв можно на Островке.','context-note'));
   item.append(externalLink('Читать на Островке ↗',r.source_url,'text-button'));list.append(item);
  }
 }
 filter.onchange=sort.onchange=render;controls.append(filter,sort);d.append(controls,summary,list);render();return d;
}
const activeHotelMaps=[];
function cleanupHotelMaps(){for(const m of activeHotelMaps.splice(0))m.remove();}
function weatherPanel(h){
 const w=h.weather,box=node('div',null,'weather-panel');
 const temperature=value=>Number.isFinite(value)?(value>0?'+':'')+value.toLocaleString('ru-RU'):'—';
 box.append(node('h3',w?.kind==='forecast'?(w.scope==='upcoming'?'Погода в ближайшие дни':'Погода на даты поездки'):'Погода'));
 if(w){
  const days=w.days||[],values=days.flatMap(d=>[d.min,d.max]).filter(Number.isFinite);
  const summary=w.summary||(values.length?temperature(Math.min(...values))+'…'+temperature(Math.max(...values))+' °C':null);
  if(summary)box.append(node('strong',summary,'weather-summary'));
  if(w.text)box.append(node('p',w.text,'context-note'));
  if(w.reason)box.append(node('p',w.reason,'context-note'));
  for(const day of days.slice(0,7)){
   const row=node('div',null,'weather-day');
   row.append(node('span',dateText(day.date)),node('strong',temperature(day.min)+'…'+temperature(day.max)+' °C'),node('span',[day.condition,Number.isFinite(day.rain_probability)&&'Осадки '+day.rain_probability+'%'].filter(Boolean).join(' · ')));
   box.append(row);
  }
  if(w.source_url)box.append(externalLink(w.source_label||'Подробнее о погоде',w.source_url,'text-button'));
 }else box.append(node('p','Посмотрите температуру и прогноз осадков на даты поездки.','context-note'));
 const refresh=button('Обновить прогноз',async()=>{
  refresh.disabled=true;refresh.textContent='Обновляем погоду…';
  try{const r=await api('/api/sessions/'+state.session_id+'/context/'+encodeURIComponent(h.id));if(!r.weather)throw new Error('weather unavailable');h.weather=r.weather;box.replaceWith(weatherPanel(h));}
  catch{refresh.disabled=false;refresh.textContent='Попробовать ещё раз';const prior=box.querySelector('.weather-error');if(!prior)box.append(node('p','Не удалось обновить погоду. Попробуйте ещё раз позже.','weather-error context-note'));}
 },'text-button');
 box.append(refresh);return box;
}
function locationPanel(h){
 const d=fold('Расположение и погода');if(state.selection?.open_panel==='nearby'&&state.selection.hotel_id===h.id)d.open=true;d.append(node('p',h.address||'Адрес пока недоступен'));
 const points=[],c=h.coordinates||{},places=h.nearby_places||[];if(Number.isFinite(c.lat)&&Number.isFinite(c.lng))points.push({name:h.name,...c,hotel:true});const terminal=h.journey?.transfer_estimate?.terminal;if(terminal)points.push({name:h.journey.transport?.terminal_name||'Терминал',...terminal});
 for(const p of places.length?places:h.map_points||[]){if(points.length>=7)break;if(Number.isFinite(p.lat)&&Number.isFinite(p.lng))points.push(p);}
 const mapBox=node('div',null,'hotel-map'),status=node('p','Загружаем карту…','map-status');mapBox.setAttribute('aria-label','Карта отеля и мест рядом');d.append(mapBox,status);let map;
 const load=async()=>{if(!d.open||map||!points.length)return;try{const config=await(await fetch('/api/map-config')).json();if(!d.isConnected)return;map=L.map(mapBox,{scrollWheelZoom:false});activeHotelMaps.push(map);const layer=L.tileLayer(config.tile_url,{maxZoom:18,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'});layer.on('tileerror',()=>status.textContent='Не удалось загрузить карту. Адрес и места рядом указаны ниже.');layer.on('load',()=>status.textContent='Карта: © OpenStreetMap contributors. Метки мест — из карточки Островка.');layer.addTo(map);for(const [i,p]of points.entries()){const label=node('span',p.name);L.marker([p.lat,p.lng],{icon:L.divIcon({className:'map-marker'+(p.hotel?'':' place'),html:String(i+1),iconSize:[28,28],iconAnchor:[14,14]})}).bindPopup(label).addTo(map);}map.fitBounds(points.map(p=>[p.lat,p.lng]),{padding:[28,28],maxZoom:14});requestAnimationFrame(()=>map.invalidateSize());}catch{status.textContent='Карта временно недоступна; места и адрес остаются в списке.';}};
 d.addEventListener('toggle',load);if(d.open)setTimeout(load,0);
 const heading=node('h3','Что интересного рядом'),list=node('div',null,'place-list');d.append(heading,list);
 for(const p of places){const card=node('article',null,'place-card');card.append(node('strong',p.name),node('p',p.reason),node('p',(p.distance_m/1000).toLocaleString('ru-RU',{maximumFractionDigits:1})+' км '+(p.distance_kind==='straight'?'по прямой':'по данным карточки'),'context-note'));if(Number.isFinite(p.lat)&&Number.isFinite(p.lng))card.append(button('Показать на карте',async()=>{await load();map?.setView([p.lat,p.lng],14);mapBox.scrollIntoView({block:'nearest'});},'text-button'));list.append(card);}
 if(!places.length)list.append(node('p','Посмотрите, что находится рядом, на странице отеля.'));
 d.append(node('p','Расстояние по прямой не равно длине маршрута или времени в пути. Часы работы и доступность мест не подтверждены.','context-note'),externalLink('Места в карточке Островка ↗',h.url,'text-button'));const weather=weatherPanel(h);d.append(weather);let weatherRequested=false;d.addEventListener('toggle',()=>{if(d.open&&!weatherRequested&&!h.weather?.days?.length){weatherRequested=true;weather.querySelector('button')?.click();}});return d;
}

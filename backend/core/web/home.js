'use strict';
const form = document.getElementById('search');
const destination = document.getElementById('destination');
const checkin = document.getElementById('checkin'), checkout = document.getElementById('checkout');
const day = date => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,10);
const today = new Date(), tomorrow = new Date(today); tomorrow.setDate(today.getDate()+1);
checkin.min = day(today); checkin.value = day(today); checkout.min = day(tomorrow); checkout.value = day(tomorrow);
checkin.onchange = () => { const next = new Date(checkin.value + 'T12:00:00'); next.setDate(next.getDate()+1); checkout.min = day(next); if(checkout.value <= checkin.value) checkout.value = day(next); };
let cities = {};
fetch('/destinations.json').then(r=>r.json()).then(data=>{cities=data;for(const name of Object.keys(data)){const o=document.createElement('option');o.value=name;document.getElementById('cities').append(o);}}).catch(()=>{document.getElementById('search-error').hidden=false;document.getElementById('search-error').textContent='Не удалось загрузить направления. Обновите страницу.';});
form.onsubmit = event => {
 event.preventDefault(); const error = document.getElementById('search-error');
 const city = Object.keys(cities).find(k=>k.toLocaleLowerCase('ru')===destination.value.trim().toLocaleLowerCase('ru'));
 if (!city) {error.textContent='Выберите город из подсказок. Для другого направления откройте Островок.ru вверху страницы.';error.hidden=false;destination.focus();return;}
 if(checkout.value <= checkin.value){error.textContent='Дата выезда должна быть позже даты заезда.';error.hidden=false;return;}
 const format = x=>x.split('-').reverse().join('.');
 const query=new URLSearchParams({dates:format(checkin.value)+'-'+format(checkout.value),guests:document.getElementById('guests').value,language:'ru'});
 location.assign('https://ostrovok.ru/hotel/russia/'+cities[city]+'/?'+query);
};

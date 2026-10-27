'use strict';
// This renderer consumes actual server progress; time only changes the waiting hint.
const TravelWindow = (() => {
  let shell, timer, longTimer, active = 0, currentScene = 'road';
  const el = (tag, cls, text) => { const e=document.createElement(tag);e.className=cls||'';if(text)e.textContent=text;return e; };
  const scenes = {
    sea: '<path fill="#badedb" d="M0 140h260v160H0z"/><path fill="#6fa8e8" d="M0 175q55-12 120 0t140 0v125H0z"/><g class="ow-boat"><path fill="#1c4acf" d="m105 169 55 0-12 13h-32z"/><path fill="#fff9e9" d="M134 122v42h-27z"/><path stroke="#2450a4" stroke-width="3" d="M135 118v53"/></g><path class="ow-glint" stroke="#fff9df" stroke-width="4" stroke-linecap="round" d="M62 206h35m36 20h25m-68 25h52"/>',
    city: '<path fill="#c1d6ea" d="M0 166h260v134H0z"/><g fill="#f2e6cc"><path d="M15 132h60v104H15zM85 115h64v121H85zM165 145h80v91h-80z"/></g><path fill="#244fd5" d="m7 132 38-29 38 29zm70-17 40-30 40 30zm80 30 47-24 48 24z"/><path stroke="#8ba7cc" stroke-width="9" stroke-dasharray="14 13" d="M29 164h35m35-19h37m44 30h50M29 194h35m35-19h37m44 30h50"/><path class="ow-bird" fill="none" stroke="#23469b" stroke-width="3" stroke-linecap="round" d="M170 86q9-9 18 0 9-9 18 0"/>',
    mountains: '<path fill="#b4c7ea" d="m-20 223 96-145 94 145z"/><path fill="#234fd5" d="m70 255 99-160 122 160z"/><path fill="#fff8e9" d="m76 78-28 44 29-12 29 14zm93 17-26 42 25-10 28 12z"/><path fill="#b7e490" d="M0 236q72-30 132 0t128-3v67H0z"/>',
    forest: '<path fill="#cee8b0" d="M0 196q62-46 131-10t129 1v113H0z"/><g fill="#315f66"><path d="m33 89-39 107h78zm180 16-39 107h78z"/></g><g fill="#719e78"><path d="m84 124-34 89h68zm70-30-46 129h92z"/></g><path fill="#91bce1" d="M0 251q83-35 157-16t103-3v68H0z"/><path class="ow-glint" stroke="#f5f6d9" stroke-width="3" stroke-linecap="round" d="M65 269h38m50-16h27"/>',
    road: '<path fill="#b8d4e4" d="M0 176q65-59 129-6t131-6v136H0z"/><path fill="#b5e293" d="M0 205q61-45 126-10t134-6v111H0z"/><path fill="#fff4db" d="M131 176q-33 34 1 61t-10 63h79q11-38-33-65t-37-59z"/>'
  };
  function art(scene='road') {
    // Only static, authored shapes enter SVG markup. User/model text uses textContent.
    const wrap=el('div','ow-landscape');wrap.dataset.scene=scene;
    wrap.innerHTML='<svg viewBox="0 0 260 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs><linearGradient id="ow-sky" x2="0" y2="1"><stop stop-color="#dceaf3"/><stop offset="1" stop-color="#fff3d8"/></linearGradient></defs><rect width="260" height="300" fill="url(#ow-sky)"/><circle class="ow-sun" cx="183" cy="67" r="25" fill="#f2d67c"/><g class="ow-cloud" fill="#fffdf5"><rect x="37" y="62" width="67" height="18" rx="9"/><circle cx="61" cy="59" r="15"/><circle cx="80" cy="61" r="11"/></g>'+(scenes[scene]||scenes.road)+'<g class="ow-flyby" fill="none" stroke="#536e89" stroke-width="2" stroke-linecap="round"><path d="M60 100q6-6 12 0 6-6 12 0"/></g><g transform="translate(46 -12)"><g class="ow-plant"><path stroke="#486f57" stroke-width="3" fill="none" d="M45 285q-12-34-29-46"/><path fill="#78986d" d="M32 263Q-1 265 3 237q24-3 29 26"/><path fill="#a4c17c" d="M37 272q-5-33 20-32 2 21-20 32"/></g></g></svg>';
    return wrap;
  }
  function sceneFor(s={}) {
    if(['forest','nature'].includes(s.travel_setting))return 'forest';
    if(s.travel_setting==='mountains'||/чемал|алтай|гор/i.test(s.destination||''))return 'mountains';
    if(s.travel_setting==='sea'||/сочи|адлер|анапа|геленджик/i.test(s.destination||''))return 'sea';
    if(s.travel_setting==='city'||/петербург|питер/i.test(s.destination||''))return 'city';
    return 'road';
  }
  function illustration(scene='road', opened=true) {
    const mark=el('div','ow-mark'+(opened?' opened':''));
    const ring=el('div','ow-ring');ring.append(art(scene));
    ring.append(el('div','ow-dawn'),el('div','ow-reveal'),el('div','ow-warmth'));
    mark.append(el('div','ow-ground')); 
    mark.append(ring,el('span','ow-exclaim','!'));return mark;
  }
  function criteria(spec) {
    const items=[];
    const nights=spec.dates?Math.round((Date.parse(spec.dates.end)-Date.parse(spec.dates.start))/86400000):spec.stay_nights;
    if(spec.destination)items.push(spec.destination);
    if(nights)items.push(nights+' '+(nights===1?'ночь':nights<5?'ночи':'ночей'));
    const hp=spec.hotel_preferences||{};
    if(hp.pool)items.push('Бассейн');else if(['forest','nature'].includes(spec.travel_setting))items.push('На природе');else if(hp.breakfast)items.push('Завтрак');
    if(spec.budget)items.push('До '+new Intl.NumberFormat('ru-RU').format(spec.budget.amount_minor/100)+' ₽'+(spec.budget_period==='night'?' / ночь':''));
    return items.slice(0,3);
  }
  function update(event) {
    if(!shell||!event||event.stage==='waiting')return;
    if(event.trip_spec) {
      const scene=sceneFor(event.trip_spec);
      if(currentScene!==scene){shell.querySelector('.ow-landscape').replaceWith(art(scene));currentScene=scene;}
      shell.querySelector('.ow-mark').classList.add('opened');
      const chips=shell.querySelector('.ow-chips'),items=criteria(event.trip_spec),signature=JSON.stringify(items);
      if(chips.dataset.signature!==signature){chips.replaceChildren();items.forEach(t=>chips.append(el('span','chip',t)));chips.dataset.signature=signature;}
    }
    const labels={understanding:'Учитываем ваши пожелания',understood:'Уточняем детали поездки',searching:'Ищем подходящие отели',comparing:'Сравниваем подходящие отели',complete:'Готовим результат'};
    if(event.stage==='comparing' && event.trip_spec?.budget)labels.comparing='Сравниваем варианты в вашем бюджете';
    if(labels[event.stage])shell.querySelector('.ow-status').textContent=shell.dataset.cheaper==='true' && ['understanding','searching'].includes(event.stage) ? 'Ищем варианты дешевле' : labels[event.stage];
    shell.dataset.stage=event.stage;
  }
  function start(host, oldResults, path, message='') {
    stop();const version=++active;currentScene='road';
    shell=el('section','travel-window'+(oldResults?' compact':''));shell.setAttribute('aria-label','Поиск отеля');shell.dataset.cheaper=String(oldResults&&/дешев|подешев/i.test(message));
    const copy=el('div','ow-copy'),status=el('p','ow-status',oldResults&&/дешев|подешев/i.test(message)?'Ищем варианты дешевле':'Посмотрим, где вам будет хорошо');status.setAttribute('role','status');
    copy.append(status,el('div','ow-chips'),el('p','ow-hint',''));
    shell.append(illustration('road',false),copy);
    if(oldResults)host.prepend(shell);else host.replaceChildren(shell);
    longTimer=setTimeout(()=>{if(shell)shell.querySelector('.ow-hint').textContent='Поиск ещё идёт — можно оставаться в чате';},25000);
    async function poll(){
      try{const r=await fetch(path,{credentials:'same-origin'});if(r.ok){const event=await r.json();if(version===active)update(event);}}catch{/* Final request owns retry UX. */}
      if(version===active)timer=setTimeout(poll,700);
    }
    timer=setTimeout(poll,600);
  }
  function capture(){if(!shell)return null;return {rect:shell.querySelector('.ow-ring').getBoundingClientRect(),scene:currentScene,compact:shell.classList.contains('compact')};}
  function stop(){++active;clearTimeout(timer);clearTimeout(longTimer);shell?.remove();shell=null;}
  function finish(from,host) {
    stop();if(!from||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    const cards=[...host.querySelectorAll('.hotel-card')];if(!cards.length)return;
    if(from.compact){cards.forEach((c,i)=>c.animate([{opacity:.45},{opacity:1}],{duration:400,delay:i*70,fill:'backwards'}));return;}
    const photo=cards[0].querySelector('.card-photo'),to=photo.getBoundingClientRect();
    if(!to.width||!from.rect.width)return;
    const ghost=el('div','ow-morph');ghost.append(art(from.scene));
    const img=photo.querySelector('img');if(img){const copy=img.cloneNode();copy.loading='eager';ghost.append(copy);copy.animate([{opacity:0},{opacity:1}],{duration:260,fill:'both'});}
    document.body.append(ghost);
    const a=from.rect;
    Object.assign(ghost.style,{left:a.left+'px',top:a.top+'px',width:a.width+'px',height:a.height+'px'});
    const anim=ghost.animate([{left:a.left+'px',top:a.top+'px',width:a.width+'px',height:a.height+'px',borderRadius:'48%',borderWidth:'22px'},{left:to.left+'px',top:to.top+'px',width:to.width+'px',height:to.height+'px',borderRadius:'16px 16px 0 0',borderWidth:'0px'}],{duration:850,delay:120,easing:'cubic-bezier(.22,.8,.25,1)',fill:'both'});
    photo.style.visibility='hidden';
    cards[0].querySelector('.card-body').animate([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'none'}],{duration:350,delay:550,fill:'backwards'});
    cards.slice(1).forEach((c,i)=>c.animate([{opacity:0,transform:'translateY(14px)'},{opacity:1,transform:'none'}],{duration:400,delay:580+i*100,fill:'backwards'}));
    anim.finished.finally(()=>{photo.style.visibility='';ghost.remove();});
  }
  async function prepare(hotels) {
    if(!shell||!hotels?.length)return;
    const image=new Image();image.decoding='async';image.src=hotels[0].image_url;
    // Wait for a real photo, with a bounded CDN fallback; never hold results forever.
    await Promise.race([image.decode().catch(()=>{}),new Promise(r=>setTimeout(r,1800))]);
  }
  return {start,stop,capture,finish,art,illustration,prepare};
})();

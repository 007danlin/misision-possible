'use strict';
// Fonts and libraries are local; unavailable hotel photos fall back to the destination.
const TripPDF = (() => {
  let assets;
  function script(src, global) {
    if (window[global]) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const tag = document.createElement('script'); tag.src = src;
      tag.onload = resolve;
      tag.onerror = () => { tag.remove(); reject(new Error('PDF library unavailable')); };
      document.head.append(tag);
    });
  }
  async function bytes(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error('PDF asset unavailable');
    return response.arrayBuffer();
  }
  async function png(svg, width, height) {
    const image = new Image(), url = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
    try {
      image.src = url; await image.decode();
      const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
      canvas.getContext('2d').drawImage(image, 0, 0, width, height);
      return canvas.toDataURL('image/png');
    } finally { URL.revokeObjectURL(url); }
  }
  async function tripPhoto(hotel, destination) {
    const place = /сочи|адлер/i.test(destination) ? 'sochi' : /казан/i.test(destination) ? 'kazan' : /петербург/i.test(destination) ? 'petersburg' : null;
    const urls = [...new Set([hotel.image_url, ...(hotel.images || []).slice(0, 2), place && '/assets/idea-' + place + '.jpg'].filter(Boolean))];
    for (const value of urls) {
      let objectURL;
      try {
        const url = new URL(value, location.href);
        if (url.origin !== location.origin && url.protocol !== 'https:') continue;
        const response = await fetch(url.href, {signal: AbortSignal.timeout(3000)});
        if (!response.ok) continue;
        const blob = await response.blob();
        objectURL = URL.createObjectURL(blob);
        const image = new Image(); image.src = objectURL; await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = 600; canvas.height = 440;
        const scale = Math.max(canvas.width / image.naturalWidth, canvas.height / image.naturalHeight);
        const context = canvas.getContext('2d');
        context.beginPath();
        context.roundRect(0, 0, canvas.width, canvas.height, 40);
        context.clip();
        context.drawImage(image, (canvas.width-image.naturalWidth*scale)/2, (canvas.height-image.naturalHeight*scale)/2, image.naturalWidth*scale, image.naturalHeight*scale);
        return canvas.toDataURL('image/png');
      } catch { /* A missing photo must not prevent downloading the trip. */ }
      finally { if (objectURL) URL.revokeObjectURL(objectURL); }
    }
    return null;
  }
  function load() {
    if (!assets) assets = Promise.all([
      script('/assets/vendor/pdf-lib-1.17.1.min.js', 'PDFLib'),
      script('/assets/vendor/fontkit-1.1.1.min.js', 'fontkit'),
      bytes('/assets/root-regular.ttf'), bytes('/assets/root-bold.ttf'),
      fetch('/assets/ostrovok.svg').then(r => { if (!r.ok) throw new Error('Logo unavailable'); return r.text(); }).then(svg => png(svg, 390, 120))
    ]).catch(error => { assets = null; throw error; });
    return assets;
  }
  const clean = value => String(value ?? '').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim();
  const count = (n, one, few, many) => n + ' ' + (n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14) ? few : many);
  const price = n => new Intl.NumberFormat('ru-RU', {style:'currency',currency:'RUB',minimumFractionDigits:0,maximumFractionDigits:2}).format(n / 100);
  function date(value) {
    const parsed = new Date(value + 'T12:00:00Z');
    return Number.isNaN(parsed.getTime()) ? 'Дата не указана' : new Intl.DateTimeFormat('ru-RU', {day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(parsed);
  }
  function guests(t = {}) {
    return [t.adults && count(t.adults,'взрослый','взрослых','взрослых'), t.children?.length && count(t.children.length,'ребёнок','ребёнка','детей')].filter(Boolean).join(', ') || 'Гости не указаны';
  }
  async function create(booking, spec = {}) {
    const [, , regularBytes, boldBytes, logoData] = await load();
    const {PDFDocument, rgb, PDFString} = window.PDFLib;
    const doc = await PDFDocument.create(); doc.registerFontkit(window.fontkit);
    const regular = await doc.embedFont(regularBytes, {subset:true}), bold = await doc.embedFont(boldBytes, {subset:true});
    const logo = await doc.embedPng(logoData);
    const h = booking.hotel || {}, q = booking.quote || h.quote || {}, dates = booking.dates || {}, journey = h.journey;
    const destination = clean(spec.destination || 'Время для путешествия');
    const photoData = await tripPhoto(h, destination);
    const coverPhoto = photoData ? await doc.embedPng(photoData) : null;
    doc.setTitle('План поездки · ' + destination); doc.setAuthor('Островок · О!План'); doc.setSubject('Детали сохранённой поездки ' + clean(booking.id));
    doc.setCreator('О!План'); doc.setLanguage('ru-RU');
    const color = hex => rgb(parseInt(hex.slice(0,2),16)/255,parseInt(hex.slice(2,4),16)/255,parseInt(hex.slice(4,6),16)/255);
    const ink=color('18342D'), muted=color('65736B'), green=color('DFF4B9'), soft=color('F4F6F0'), blue=color('2458D3'), line=color('DFE5DC');
    const W=595.28, H=841.89, margin=36, width=W-margin*2, bottom=H-62;
    let page, y;
    // Unsupported glyphs fall back per character; Cyrillic remains searchable text.
    const supported = new Set(regular.getCharacterSet());
    const text = value => [...clean(value)].map(c => supported.has(c.codePointAt(0)) ? c : '?').join('');
    function rect(x, top, w, height, fill) { page.drawRectangle({x,y:H-top-height,width:w,height,color:fill}); }
    function draw(value, x, top, size=10, font=regular, fill=ink) { page.drawText(text(value),{x,y:H-top-size,font,size,color:fill}); }
    function wrap(value, maxWidth, size=10, font=regular) {
      const lines=[]; let current='';
      for(const word of text(value).split(' ')) {
        if(current && font.widthOfTextAtSize(current+' '+word,size)>maxWidth) {lines.push(current);current='';}
        // Even a long URL or an unbroken hotel name stays inside the page.
        for(const character of word) {
          if(current && font.widthOfTextAtSize(current+character,size)>maxWidth) {lines.push(current);current='';}
          current+=character;
        }
        current+=' ';
      }
      if(current.trim()) lines.push(current.trim());
      return lines.length ? lines : [''];
    }
    function newPage() {
      page=doc.addPage([W,H]); y=84;
      page.drawImage(logo,{x:margin,y:H-64,width:128,height:39.38});
      draw('О!ПЛАН / ПЛАН ПОЕЗДКИ',W-201,39,8,bold,muted);
      page.drawLine({start:{x:margin,y:H-73},end:{x:W-margin,y:H-73},thickness:.7,color:line});
    }
    function ensure(height) { if(y+height>bottom) newPage(); }
    function paragraph(value, {x=margin,w=width,size=10,font=regular,fill=ink,leading=14}={}) {
      for(const row of wrap(value,w,size,font)) {ensure(leading);draw(row,x,y,size,font,fill);y+=leading;}
    }
    function section(title, body, {fill=null}={}) {
      // Move the heading with the first paragraph when that block fits a page.
      const firstHeight=body.length?wrap(body[0],width).length*14+4:0;
      ensure(firstHeight+29<=bottom-84?firstHeight+29:47);
      y+=8;draw(title,margin,y,12,bold);y+=21;
      for(const [index,item] of body.entries()) {
        const height=wrap(item,width).length*14+4;
        if(index>0 && height<bottom-84) ensure(height);
        paragraph(item,{fill:fill||ink});y+=4;
      }
      y+=4;
    }
    newPage();
    const titleWidth = coverPhoto ? 310 : width-36;
    const heroHeight=Math.max(126,wrap(destination,titleWidth,28,bold).length*32+48);
    rect(margin,y,width,heroHeight,green);
    draw('ХОРОШЕЕ ПУТЕШЕСТВИЕ НАЧИНАЕТСЯ ЗДЕСЬ',margin+18,y+14,7,bold);
    wrap(destination,titleWidth,28,bold).forEach((row,i)=>draw(row,margin+18,y+34+i*32,28,bold));
    if (coverPhoto) page.drawImage(coverPhoto,{x:W-margin-160,y:H-y-heroHeight+(heroHeight-110)/2,width:150,height:110});
    y+=heroHeight+15;
    const col=width/3;
    const travel=[['ЗАЕЗД',date(dates.start)],['ВЫЕЗД',date(dates.end)],['ВЫ ЕДЕТЕ',guests(booking.travellers)]];
    const travelHeight=Math.max(...travel.map(([,v])=>wrap(v,col-22,11,bold).length))*15+47;
    rect(margin,y,width,travelHeight,soft);
    travel.forEach(([label,value],i)=>{draw(label,margin+14+i*col,y+12,8,bold,muted);wrap(value,col-22,11,bold).forEach((row,j)=>draw(row,margin+14+i*col,y+29+j*15,11,bold));});
    y+=travelHeight+12;
    if(childAgesText(booking.travellers)) {
      paragraph(childAgesText(booking.travellers),{size:9,leading:13,fill:muted});y+=8;
    }
    paragraph(h.name || 'Ваше размещение',{size:18,font:bold,leading:22});y+=4;
    paragraph(h.address || 'Адрес нужно уточнить у объекта размещения',{fill:muted});
    const facts=[h.stars>0 && count(h.stars,'звезда','звезды','звёзд'),h.rating>0 && 'Оценка гостей '+new Intl.NumberFormat('ru-RU').format(h.rating)+'/10',h.distance_m!=null && 'До центра: '+new Intl.NumberFormat('ru-RU',{maximumFractionDigits:1}).format(h.distance_m/1000)+' км'].filter(Boolean);
    if(facts.length) {y+=3;paragraph(facts.join(' · '),{size:9,fill:muted,leading:13});}
    y+=12;
    ensure(79); rect(margin,y,width,75,ink);
    draw(journey?(journey.total_incomplete?'ПЛАН БЕЗ СТОИМОСТИ ВАШИХ БИЛЕТОВ':'СТОИМОСТЬ ВСЕЙ ПОЕЗДКИ'):h.transfer_addon?'ПРОЖИВАНИЕ И ТРАНСФЕРЫ':'СТОИМОСТЬ ПРОЖИВАНИЯ',margin+16,y+12,8,bold,green);
    draw(Number.isFinite(tripAmount(h))?(h.source_kind==='public'?'≈ ':'')+price(tripAmount(h)):'Уточните стоимость',margin+16,y+29,25,bold,color('FFFFFF'));
    const stay=[q.nights && count(q.nights,'ночь','ночи','ночей'),q.rooms && count(q.rooms,'номер','номера','номеров')].filter(Boolean).join(' · ');
    draw(stay,W-margin-180,y+15,10,bold,color('FFFFFF'));
    if(Number.isFinite(q.nightly_minor)) draw(price(q.nightly_minor)+' / ночь',W-margin-180,y+35,10,regular,color('FFFFFF'));
    y+=87;
    const columns=[
      ['ВАШ ТАРИФ',[
        h.source_kind==='public'?(q.breakfast?'Питание учтено в стоимости':'Проживание без питания'):q.breakfast===true?'Завтрак включён':q.breakfast===false?'Без питания':'Питание: уточните у отеля',
        h.source_kind==='public'?'Категория, отмена и сборы: тариф не подтверждён':journey?.cancellation_until?'Отмена до '+tripTime(journey.cancellation_until):q.free_cancellation===true?'Точный срок отмены требует подтверждения':q.free_cancellation===false?'Тариф без возврата':'Условия отмены: уточните у отеля',
        'Основной гость: '+clean(booking.guest_name)
      ]],
      ['ПОЧЕМУ ЭТОТ ОТЕЛЬ',h.reasons?.length ? h.reasons : ['Ваш выбор сохранён в плане поездки.']]
    ];
    const cw=(width-24)/2;
    const rowHeights=columns.map(([,items])=>items.reduce((n,item)=>n+wrap(item,cw,9).length*12+5,25));
    // Break unusually long descriptions into flowing sections instead of clipping.
    if(Math.max(...rowHeights)>200) {
      columns.forEach(([title,items])=>section(title,items));
    } else {
      const height=Math.max(...rowHeights);ensure(height+8);
      columns.forEach(([title,items],i)=>{const x=margin+i*(cw+24);let top=y;draw(title,x,top,8,bold,muted);top+=22;items.forEach(item=>{wrap(item,cw,9).forEach(row=>{draw(row,x,top,9);top+=12;});top+=5;});});
      y+=height+8;
    }
    if(h.amenities?.length) {paragraph('Удобства: '+h.amenities.join(' · '),{size:9,leading:12,fill:muted});y+=6;}
    if(h.unverified?.length) {paragraph('Нужно уточнить у отеля: '+h.unverified.join('; '),{size:9,leading:12});y+=6;}
    if(journey){
      section('Состав стоимости',Object.entries(journey.breakdown).map(([key,value])=>(journeyNames[key]||key)+': '+price(value)).concat(journey.reserve_minor?['Отдельный резерв: '+price(journey.reserve_minor)]:[]));
      section('Дорога и трансферы · время МСК',journey.segments.map(s=>s.label+': '+s.origin+' → '+s.destination+'. '+(s.time_partial==='arrival'?'Прибытие '+tripTime(s.arrival):s.time_partial==='departure'?'Отправление '+tripTime(s.departure):tripTime(s.departure)+' — '+tripTime(s.arrival))));
      section('Проверка плана',journey.checks.map(c=>((journey.budget_override_accepted&&['budget','hotel_budget'].includes(c.code)&&c.status!=='pass')?'Согласовано: ':c.status==='pass'?'Проверено: ':'Требует внимания: ')+c.message));
    }
    if(h.transfer_addon){section('Дополнительно: оба трансфера',[price(h.transfer_addon.total_minor),...h.transfer_addon.segments.map(s=>s.origin+' → '+s.destination+'. '+tripTime(s.departure)+' — '+tripTime(s.arrival)),h.transfer_addon.notice]);}
    if(booking.early_checkin_request){section('Пожелание раннего заезда',[booking.early_checkin_request.time+' · сохранено в плане; в отель не отправлено и не подтверждено.']);}
    const preparation=[
      '01  Возьмите документы для всех гостей, включая детей, если они едут с вами.',
      '02  Уточните время заезда и выезда, питание и особые пожелания у отеля.',
      journey?(journey.transport?.kind==='car'?'03  Сохраните маршрут на автомобиле. Отдельные трансферы не нужны.':'03  Сохраните расписание дороги и обоих трансферов из этого плана.'):h.transfer_addon?'03  Оба трансфера добавлены в план. Дорога до города оплачивается отдельно.':'03  Сохраните адрес и продумайте дорогу. Проезд и трансферы в этот расчёт не включены.'
    ];
    const isDemo=booking.is_demo===true || q.source_kind==='demo';
    const note=journey?'Демонстрационный режим: без оплаты и реального бронирования. Стоимость предварительная; номера, билеты и трансферы нужно подтвердить перед поездкой.':isDemo?'Демонстрационный режим: без оплаты и реального бронирования. Стоимость и наличие номеров на выбранные даты нужно уточнить.':'Это сохранённый план поездки. Актуальные условия и статус бронирования проверьте у поставщика.';
    const noteHeight=4+wrap(note,width,8).length*11+(safeURL(h.url)?22:0);
    const endingHeight=29+preparation.reduce((sum,item)=>sum+wrap(item,width).length*14+4,0)+4+noteHeight;
    // Keep the short closing checklist, notice and link together.
    if(endingHeight<=bottom-84)ensure(endingHeight);
    section('Перед поездкой',preparation);
    ensure(noteHeight);y+=4;paragraph(note,{size:8,leading:11,fill:muted});
    if(h.url && safeURL(h.url)) {
      y+=6;ensure(14);const top=y;
      draw('Открыть отель на Островке',margin,top,9,bold,blue);
      const link=doc.context.obj({Type:'Annot',Subtype:'Link',Rect:[margin,H-top-13,margin+180,H-top+1],Border:[0,0,0],A:{Type:'Action',S:'URI',URI:PDFString.of(safeURL(h.url))}});
      page.node.addAnnot(doc.context.register(link));y+=16;
    }
    const pages=doc.getPages();
    pages.forEach((p,i)=>{
      page=p;
      page.drawLine({start:{x:margin,y:47},end:{x:W-margin,y:47},thickness:.7,color:line});
      draw('План '+clean(booking.id),margin,H-35,8,regular,muted);
      draw((i+1)+' / '+pages.length,W-margin-26,H-35,8,regular,muted);
    });
    return doc.save();
  }
  function safeURL(value) {
    try {const u=new URL(value);return u.protocol==='https:' && (u.hostname==='ostrovok.ru'||u.hostname.endsWith('.ostrovok.ru'))?u.href:null;}catch{return null;}
  }
  return {create};
})();

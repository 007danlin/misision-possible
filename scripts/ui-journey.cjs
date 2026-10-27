const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..');const{chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const p=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});p.setDefaultTimeout(190000);
 const out=path.join(root,'.runtime/screenshots/journey');fs.mkdirSync(out,{recursive:true});const report={steps:[],errors:[]};p.on('pageerror',e=>report.errors.push(e.message));
 async function state(){return p.evaluate(async()=>await(await fetch('/api/sessions/'+localStorage.getItem('oplan-hotels-session'))).json())}
 async function shot(name,fullPage=false){await p.evaluate(async()=>{await document.fonts.ready;await Promise.all(document.getAnimations().filter(a=>a.effect?.getComputedTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})));});await p.screenshot({path:out+'/'+name,fullPage});}
 async function turn(message){await p.locator('#message').fill(message);const pending=p.waitForResponse(r=>r.url().endsWith('/turns')&&r.request().method()==='POST');const start=Date.now();await p.locator('#send').click();const r=await pending,s=await r.json();await p.waitForFunction(()=>!document.querySelector('#send').disabled);report.steps.push({message,status:s.status,answer:s.assistant_message,elapsed_ms:Date.now()-start,telemetry:s.telemetry});console.log(JSON.stringify(report.steps.at(-1)));return s;}
 async function action(label){const pending=p.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST');await p.getByRole('button',{name:label,exact:true}).first().click();const r=await pending,s=await r.json();assert.equal(r.status(),200,JSON.stringify(s));await p.waitForFunction(()=>document.querySelector('#progress').hidden);return s;}
 try{
  await p.goto('http://127.0.0.1:18080/plan.html');await p.locator('.bubble.assistant').waitFor();
  let s=await turn('Из Москвы в Сочи, 10–15 ноября 2026, двое взрослых. 120 тысяч рублей на дорогу, отель и оба трансфера. Без ночных рейсов, нужен бассейн.');
  if(s.status==='needs_input'&&s.trip_spec.budget_scope==='whole_trip')s=await turn('Резерв на личные расходы 0 рублей.');
  assert.equal(s.status,'choosing',JSON.stringify(s));assert.ok(s.hotel_options.every(h=>h.journey?.can_book));assert.ok(s.hotel_options.every(h=>h.journey.total_minor<=12000000));report.first_total=s.hotel_options[0].journey.total_minor;
  await p.locator('.hotel-card').first().waitFor();await shot('01-options.png');
  await p.locator('.hotel-name-button').first().click();await p.getByText(/^Отзывы · /).click();await p.getByRole('combobox',{name:'Тема отзывов'}).selectOption('Тишина');assert.equal(await p.locator('.review-item').count(),1);await p.getByText('Дорога и трансферы',{exact:true}).click();await shot('02-details.png',true);
  s=await action('Перейти к оформлению');assert.equal(s.status,'hotel_checkout');
  await p.getByRole('button',{name:'Изменить выезд',exact:true}).click();await p.locator('#stay-out').fill('2026-11-17');s=await action('Сохранить и пересчитать');assert.ok(s.journey_preview);assert.equal(s.selected_hotel,null);await shot('03-preview.png');
  s=await action('Оставить прежний план');assert.equal(s.trip_spec.dates.end,'2026-11-15');assert.equal(s.selected_hotel.journey.total_minor,report.first_total);
  await p.getByRole('button',{name:'Изменить выезд',exact:true}).click();await p.locator('#stay-out').fill('2026-11-17');s=await action('Сохранить и пересчитать');s=await action('Принять изменения');assert.equal(s.trip_spec.dates.end,'2026-11-17');assert.ok(s.selected_hotel.journey.segments.at(-1).departure.startsWith('2026-11-17'));
  await p.locator('#guest-name').fill('Тестовый Гость');await p.locator('#booking-consent').check();await shot('04-checkout.png');s=await action('Подтвердить поездку');assert.equal(s.status,'hotel_booked');report.booking_total=s.hotel_booking.hotel.journey.total_minor;report.booking_id=s.hotel_booking.id;
  await p.reload();await p.getByRole('heading',{name:'Поездка оформлена',exact:true}).waitFor();s=await state();assert.equal(s.hotel_booking.id,report.booking_id);assert.equal(s.hotel_booking.hotel.journey.total_minor,report.booking_total);
  const downloaded=p.waitForEvent('download');await p.getByRole('button',{name:'Скачать план поездки · PDF',exact:true}).click();const download=await downloaded;await download.saveAs(out+'/journey.pdf');
  await p.setViewportSize({width:390,height:844});await p.getByRole('button',{name:/^Варианты/}).click();await p.locator('h1').last().scrollIntoViewIfNeeded();assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await shot('05-mobile.png',true);assert.deepEqual(report.errors,[]);console.log('PASS complete journey, reviews, reprice, rollback, confirmation, reload, PDF, mobile');
 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1;}finally{fs.writeFileSync(out+'/report.json',JSON.stringify(report,null,2));await browser.close();}
})();

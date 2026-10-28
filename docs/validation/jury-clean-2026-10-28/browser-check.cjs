const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=process.cwd(), out=path.join(root,'docs/validation/jury-clean-2026-10-28');
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const p=await browser.newPage({viewport:{width:1280,height:900},acceptDownloads:true});
 p.setDefaultTimeout(190000); const report={steps:[],errors:[],no_api_keys:true};p.on('pageerror',e=>report.errors.push(e.message));
 async function turn(message){await p.locator('#message').fill(message);const pending=p.waitForResponse(r=>r.url().endsWith('/turns')&&r.request().method()==='POST');const started=Date.now();await p.locator('#send').click();const r=await pending,s=await r.json();assert.equal(r.status(),200);await p.waitForFunction(()=>!document.querySelector('#send').disabled);report.steps.push({message,status:s.status,elapsed_seconds:(Date.now()-started)/1000,telemetry:s.telemetry});return s;}
 async function action(label){const pending=p.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST');await p.getByRole('button',{name:label,exact:true}).first().click();const r=await pending,s=await r.json();assert.equal(r.status(),200,JSON.stringify(s));await p.waitForFunction(()=>document.querySelector('#progress').hidden);return s;}
 try{
  await p.goto('http://127.0.0.1:8080/plan.html');
  if(await p.getByRole('heading',{name:'Готовим помощника к работе'}).count()){
   report.startup_page_seen=true;
   await p.locator('#numbers').filter({hasText:/ГБ/}).waitFor({timeout:10000});
   const first=await p.locator('#numbers').innerText();
   await p.waitForFunction(previous=>document.querySelector('#numbers')?.textContent!==previous,first,{timeout:12000});
   report.download_counter_updates=true;
   await p.screenshot({path:path.join(out,'01-downloading.png')});
  }
  await p.locator('#send').waitFor({timeout:1200000}); report.automatic_entry=true;
  let s=await turn('Из Москвы в Сочи, 10–15 ноября 2026, двое взрослых. 120 тысяч рублей на дорогу, отель и оба трансфера. Без ночных рейсов, нужен бассейн.');
  if(s.status==='needs_input')s=await turn('Резерв на личные расходы 0 рублей.');
  assert.equal(s.status,'choosing',JSON.stringify(s));assert.ok(s.hotel_options.length>0);
  assert.ok(s.hotel_options.every(h=>h.source_kind==='public'));
  report.hotels=s.hotel_options.map(h=>({name:h.name,total_minor:h.journey.total_minor,source_kind:h.source_kind}));
  await p.locator('.hotel-card').first().waitFor();await p.screenshot({path:path.join(out,'02-options.png')});
  await p.locator('.hotel-name-button').first().click();s=await action('Перейти к оформлению');assert.equal(s.status,'hotel_checkout');
  await p.locator('#guest-name').fill('Тестовый Гость');await p.locator('#booking-consent').check();s=await action('Подтвердить поездку');assert.equal(s.status,'hotel_booked');report.booking_id=s.hotel_booking.id;
  await p.reload();await p.getByRole('heading',{name:'Поездка оформлена',exact:true}).waitFor();
  const downloadPromise=p.waitForEvent('download');await p.getByRole('button',{name:'Скачать план поездки · PDF',exact:true}).click();const download=await downloadPromise;await download.saveAs(path.join(out,'trip.pdf'));report.pdf_bytes=fs.statSync(path.join(out,'trip.pdf')).size;assert.ok(report.pdf_bytes>10000);
  await p.screenshot({path:path.join(out,'03-booked.png')});assert.deepEqual(report.errors,[]);report.success=true;
 }catch(e){report.failure=String(e);console.error(e);process.exitCode=1;}finally{fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));await browser.close();}
})();

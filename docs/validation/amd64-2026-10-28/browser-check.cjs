const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=process.cwd();
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const out=path.join(root,'.runtime/amd64-check');fs.mkdirSync(out,{recursive:true});
 const report={base_url:'http://127.0.0.1:18084',passed:false,errors:[],steps:[]};
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const p=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});p.setDefaultTimeout(350000);
 p.on('pageerror',e=>report.errors.push(e.message));
 async function turn(message){const t=Date.now();await p.locator('#message').fill(message);const pending=p.waitForResponse(r=>r.url().endsWith('/turns')&&r.request().method()==='POST');await p.locator('#send').click();const r=await pending,s=await r.json();assert.equal(r.status(),200);await p.waitForFunction(()=>!document.querySelector('#send').disabled);report.steps.push({action:'message',seconds:(Date.now()-t)/1000,status:s.status,answer:s.assistant_message,telemetry:s.telemetry});console.log(JSON.stringify(report.steps.at(-1)));return s;}
 async function action(label){const pending=p.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST');await p.getByRole('button',{name:label,exact:true}).first().click();const r=await pending,s=await r.json();assert.equal(r.status(),200);await p.waitForFunction(()=>document.querySelector('#progress').hidden);report.steps.push({action:label,status:s.status});console.log(JSON.stringify(report.steps.at(-1)));return s;}
 try{
  await p.goto(report.base_url+'/plan.html');await p.locator('.bubble.assistant').waitFor();
  let s=await turn('Из Москвы в Сочи с 10 по 15 ноября 2026 года, двое взрослых. 150 тысяч рублей на отель, дорогу туда-обратно и оба трансфера. Нужен бассейн. Резерв на личные расходы 0 рублей.');
  if(s.status==='needs_input'&&s.trip_spec.budget_scope==='whole_trip')s=await turn('Резерв на личные расходы 0 рублей.');
  assert.equal(s.status,'choosing',s.assistant_message);assert.ok(s.hotel_options.length>0);report.options=s.hotel_options.length;
  await p.locator('.hotel-name-button').first().click();s=await action('Перейти к оформлению');assert.equal(s.status,'hotel_checkout');
  await p.locator('#guest-name').fill('Тестовый Гость');await p.locator('#booking-consent').check();s=await action('Подтвердить поездку');assert.equal(s.status,'hotel_booked');const id=s.hotel_booking.id;
  await p.reload();await p.getByRole('heading',{name:'Поездка оформлена',exact:true}).waitFor();
  const restored=await p.evaluate(async()=>await(await fetch('/api/sessions/'+localStorage.getItem('oplan-hotels-session'))).json());assert.equal(restored.hotel_booking.id,id);report.reload=true;
  const dl=p.waitForEvent('download');await p.getByRole('button',{name:'Скачать план поездки · PDF',exact:true}).click();await(await dl).saveAs(out+'/trip.pdf');report.pdf_bytes=fs.statSync(out+'/trip.pdf').size;assert.ok(report.pdf_bytes>1000);
  assert.deepEqual(report.errors,[]);report.passed=true;await p.screenshot({path:out+'/booked.png',fullPage:true});
 }catch(e){report.failure=String(e);console.error(e);await p.screenshot({path:out+'/failure.png',fullPage:true}).catch(()=>{});process.exitCode=1;}
 finally{fs.writeFileSync(out+'/smoke.json',JSON.stringify(report,null,2));await browser.close();}
})();

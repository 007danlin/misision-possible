// Live frontend and API regression check against port 18080; creates its own demo trip.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),{chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{const b=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});const p=await b.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});p.setDefaultTimeout(45000);const errors=[];p.on('pageerror',e=>{errors.push(e.message);console.log('JS ERROR',e.message)});const out=path.join(root,'.runtime/screenshots/live-front-audit');fs.mkdirSync(out,{recursive:true});
try{
await p.goto('http://127.0.0.1:18080/plan.html');await p.locator('.bubble.assistant').waitFor();console.log('Loaded real plan.html',await p.locator('.topnav').innerText());
await p.locator('#about').click();assert.ok(await p.locator('#about-dialog').isVisible());await p.locator('#close-about').click();
await p.locator('#message').fill('Сочи, с 10 по 15 ноября 2026, двое взрослых, бюджет 80 тысяч рублей на отель за всю поездку. Только отель, без дороги.');const response=p.waitForResponse(r=>r.url().endsWith('/turns')&&r.request().method()==='POST',{timeout:190000});await p.locator('#send').click();const r=await response;const s=await r.json();fs.writeFileSync(out+'/state.json',JSON.stringify(s,null,2));console.log('Real search',r.status(),s.status,s.hotel_options?.length,s.assistant_message);assert.equal(r.status(),200);await p.locator('.hotel-card').first().waitFor();
await p.locator('.ow-morph').waitFor({state:'detached'});await p.screenshot({path:out+'/01-cards.png'});
const cards=p.locator('.hotel-card');const count=await cards.count();for(let i=0;i<count;i++){const name=await cards.nth(i).locator('h3').innerText();await cards.nth(i).locator('.card-photo').click();await p.locator('.detail-heading h1').waitFor();assert.equal(await p.locator('.detail-heading h1').innerText(),name);await p.getByRole('button',{name:'← К подборке',exact:true}).click();await cards.nth(i).locator('h3 button').click();await p.locator('.detail-heading h1').waitFor();assert.equal(await p.locator('.detail-heading h1').innerText(),name);await p.getByRole('button',{name:'← К подборке',exact:true}).click();}console.log('PASS photo/name for all',count,'hotels');
for(const selector of ['.hotel-facts','.card-subtitle','.hotel-amenities','.hotel-price','.match-reasons','.card-actions']){
const card=cards.first(),target=card.locator(selector);await target.click({position:{x:2,y:2}});await p.locator('.detail-heading h1').waitFor();await p.getByRole('button',{name:'← К подборке',exact:true}).click();
}
await cards.first().click({position:{x:2,y:250}});await p.locator('.detail-heading h1').waitFor();await p.getByRole('button',{name:'← К подборке',exact:true}).click();
console.log('PASS full card: facts, address, amenities, price, reasons, padding and border');
await p.locator('.hotel-name-button').first().focus();await p.keyboard.press('Enter');await p.locator('.booking-panel').waitFor();await p.screenshot({path:out+'/02-details.png'});await p.getByRole('button',{name:'← К подборке',exact:true}).click();
await p.reload();await cards.first().waitFor();console.log('PASS reload restores cards');
await p.locator('#edit').click();await p.locator('.region-dialog').waitFor();await p.locator('.region-dialog .icon-button').click();
await p.locator('#history').click();await p.locator('.history-item').first().waitFor();console.log('History visible');await p.keyboard.press('Escape');
for(const width of [900,390]){await p.setViewportSize({width,height:844});if(width===390)await p.locator('#mobile-results').click();assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await cards.first().locator('.card-photo').click();await p.locator('.booking-panel').waitFor();await p.getByRole('button',{name:'← К подборке',exact:true}).click();await p.screenshot({path:out+'/03-cards-'+width+'.png'});}console.log('PASS tablet/mobile, photo and overflow');
await p.setViewportSize({width:1440,height:1000});
const actionResponse=p.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST',{timeout:190000});await p.getByRole('button',{name:'Выбрать отель',exact:true}).first().click();const ar=await actionResponse,as=await ar.json();console.log('Selection',ar.status(),as.status);assert.equal(ar.status(),200);await p.locator('.checkout-form').waitFor();assert.equal(await p.locator('.detail-heading').count(),0);
await p.locator('#guest-name').fill('Анна Проверка');
await p.getByRole('button',{name:'Изменить заезд',exact:true}).click();await p.locator('.stay-dialog').waitFor();
await p.locator('#stay-in-text').fill('31.02.2026');assert.equal(await p.locator('#stay-in-text').evaluate(e=>e.checkValidity()),false);
await p.locator('#stay-in-text').fill('11.11.2026');await p.locator('#stay-out-text').fill('17.11.2026');
assert.equal(await p.locator('#stay-in').inputValue(),'2026-11-11');assert.equal(await p.locator('#stay-out').inputValue(),'2026-11-17');
await p.locator('#stay-adults').fill('3');await p.locator('#stay-children').fill('2');await p.locator('.child-ages select').nth(0).selectOption('5');await p.locator('.child-ages select').nth(1).selectOption('9');
await p.screenshot({path:out+'/04-date-editor.png'});
let actionResponse2=p.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST',{timeout:190000});
await p.getByRole('button',{name:'Сохранить и пересчитать',exact:true}).click();let action2=await actionResponse2;let updated=await action2.json();assert.equal(action2.status(),200);await p.locator('.stay-dialog').waitFor({state:'detached'});
assert.equal(updated.trip_spec.dates.end,'2026-11-17');assert.equal(updated.trip_spec.travellers.adults,3);assert.deepEqual(updated.trip_spec.travellers.children,[5,9]);assert.equal(updated.selected_hotel.quote.nights,6);assert.equal(await p.locator('#guest-name').inputValue(),'Анна Проверка');
console.log('PASS date input validation, date/guest update via actual API, recalculation, guest name preserved');
if(await p.locator('#budget-accept').count())await p.locator('#budget-accept').check();await p.locator('#booking-consent').check();
actionResponse2=p.waitForResponse(r=>r.url().endsWith('/actions')&&r.request().method()==='POST',{timeout:190000});await p.getByRole('button',{name:'Подтвердить поездку',exact:true}).click();action2=await actionResponse2;updated=await action2.json();assert.equal(action2.status(),200);assert.equal(updated.status,'hotel_booked');await p.getByRole('heading',{name:'Поездка оформлена',exact:true}).waitFor();
const downloadPromise=p.waitForEvent('download');await p.getByRole('button',{name:'Скачать план поездки · PDF',exact:true}).click();const download=await downloadPromise;await download.saveAs(out+'/trip.pdf');assert.ok(fs.statSync(out+'/trip.pdf').size>1000);
await p.screenshot({path:out+'/05-booked.png'});await p.reload();await p.getByRole('heading',{name:'Поездка оформлена',exact:true}).waitFor();
await p.locator('#new').click();await p.locator('.inspiration').waitFor();await p.locator('#history').click();await p.locator('.history-item').filter({hasText:updated.hotel_booking.hotel.name}).first().click();await p.getByRole('heading',{name:'Поездка оформлена',exact:true}).waitFor();
await p.setViewportSize({width:390,height:844});await p.locator('#mobile-results').click();assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
console.log('PASS demo confirmation, PDF download, reload, new search, history restore, mobile confirmation');
assert.deepEqual(errors,[]);console.log('PASS REAL FRONT AUDIT');
}catch(e){await p.screenshot({path:out+'/failure.png',fullPage:true});console.error(e);process.exitCode=1;}finally{await b.close()}
})().catch(e=>{console.error(e);process.exit(1)});

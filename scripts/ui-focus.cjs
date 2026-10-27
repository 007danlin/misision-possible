// UI focus regression checks; fixtures isolate browser behavior from model latency.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),web=path.join(root,'backend/core/web');
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const b=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const p=await b.newPage({viewport:{width:1440,height:1000},locale:'ru-RU'}),errors=[];
 p.setDefaultTimeout(10000);p.on('pageerror',e=>errors.push(e.message));
 const out=path.join(root,'.runtime/screenshots/focus');fs.mkdirSync(out,{recursive:true});
 const fixture=JSON.parse(fs.readFileSync(path.join(root,'.runtime/nature-fixture.json')));
 await p.route('**/api/sessions/**',r=>r.fulfill({json:r.request().url().includes('?mode=')?[]:{schema_version:'0.2',session_id:'a'.repeat(32),revision:0,search_mode:'hotels',status:'needs_input',trip_spec:{},hotel_options:[],destination_options:[],assistant_message:'Расскажите о поездке.'}}));
 if(process.env.FOCUS_SOURCE==='1')await p.route('http://127.0.0.1:18080/**',r=>{const u=new URL(r.request().url()),f=path.join(web,u.pathname==='/'?'index.html':u.pathname);return fs.existsSync(f)&&fs.statSync(f).isFile()?r.fulfill({path:f}):r.fallback()});
 async function ring(loc){const s=await loc.evaluate(e=>{const s=getComputedStyle(e);return {style:s.outlineStyle,width:s.outlineWidth}});assert.equal(s.style,'solid');assert.equal(s.width,'2px');}
 async function noRing(loc){assert.equal(await loc.evaluate(e=>getComputedStyle(e).outlineStyle),'none');}
 async function shot(name){await p.screenshot({path:path.join(out,name+'.png')});}
 try{
  await p.goto('http://127.0.0.1:18080/plan.html');await p.locator('.inspiration').waitFor();
  await p.locator('#about').click();await noRing(p.locator('#close-about'));await p.keyboard.press('Tab');await ring(p.locator('#about-dialog :focus'));await shot('01-about-keyboard');await p.keyboard.press('Escape');
  await p.getByRole('button',{name:'Мои предпочтения',exact:true}).click();const text=p.locator('.stay-dialog textarea');await ring(text);assert.equal(await text.evaluate(e=>getComputedStyle(e).borderStyle),'solid');await shot('02-preferences');await p.keyboard.press('Escape');
  await p.evaluate(()=>editRegion());await p.locator('.region-dialog select').first().selectOption('Россия');await p.locator('.region-dialog select').first().focus();await ring(p.locator('.region-dialog select').first());await shot('03-region');await p.keyboard.press('Escape');
  await p.locator('#history').click();await p.locator('.history-list').waitFor();await noRing(p.getByRole('button',{name:'Закрыть историю'}));await p.keyboard.press('Escape');
  await p.locator('#message').click();await noRing(p.locator('#message'));assert.notEqual(await p.locator('#form').evaluate(e=>getComputedStyle(e).boxShadow),'none');
  await p.evaluate(f=>{Object.assign(state,f,{status:'choosing'});state.hotel_options[0].images=['/assets/ostrovok.svg','/assets/ostrovok.svg'];state.trip_spec.dates={start:'2026-12-23',end:'2026-12-28'};render();},fixture);
  await p.locator('.hotel-name-button').first().click();await noRing(p.locator('#results'));await shot('04-detail-no-container-ring');
  await p.locator('.hotel-gallery button').first().click();await noRing(p.locator('.hotel-gallery button').first());assert.equal(await p.locator('.hotel-gallery button').first().evaluate(e=>getComputedStyle(e).borderTopColor),'rgba(0, 0, 0, 0)');await p.keyboard.press('Tab');const photo=p.locator('.hotel-gallery button').nth(1);await ring(photo);assert.equal(await photo.evaluate(e=>getComputedStyle(e).outlineOffset),'-4px');assert.equal(await photo.evaluate(e=>getComputedStyle(e).borderTopColor),'rgba(0, 0, 0, 0)');await shot('05-gallery-keyboard');
  const summary=p.locator('.trip-fold>summary').first();await summary.click();await noRing(summary);await p.keyboard.press('Shift+Tab');await p.keyboard.press('Tab');await ring(summary);
  await p.evaluate(()=>{state.selected_hotel=state.hotel_options[0];state.status='hotel_checkout';render()});await p.locator('#guest-name').click();await ring(p.locator('#guest-name'));await shot('06-checkout');
  await p.locator('#booking-consent').focus();await p.keyboard.press('Shift+Tab');await p.keyboard.press('Tab');await ring(p.locator('#booking-consent'));
  await p.getByRole('button',{name:'Изменить выезд',exact:true}).click();await ring(p.locator('#stay-out-text'));await p.locator('#stay-children').fill('2');await ring(p.locator('#stay-children'));await p.locator('.child-ages select').first().selectOption('5');await p.locator('.child-ages select').first().focus();await ring(p.locator('.child-ages select').first());await shot('07-stay');
  await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await p.locator('.stay-dialog').evaluate(e=>e.scrollWidth>e.clientWidth),false);await shot('08-mobile-stay');await p.keyboard.press('Escape');
  await p.getByRole('button',{name:/^Варианты/}).click();await noRing(p.locator('#mobile-results'));await p.keyboard.press('Shift+Tab');await p.keyboard.press('Tab');await ring(p.locator('#mobile-results'));await shot('09-mobile-tabs');
  await p.evaluate(()=>{$('results').replaceChildren(bookingExtras({hotel:{},id:'test',dates:{start:'2026-12-23',end:'2026-12-28'}}));$('results').querySelector('details').open=true});
  await p.getByRole('button',{name:'Запланировать ранний заезд',exact:true}).click();await ring(p.locator('.stay-dialog input[type=time]'));await shot('10-time');await p.keyboard.press('Escape');
  await p.goto('http://127.0.0.1:18080/');await p.locator('#checkin').waitFor();
  for(const id of ['destination','checkin-text','checkout-text','guests']){await p.locator('#'+id).focus();await ring(p.locator('#'+id));}
  await p.setViewportSize({width:1440,height:1000});await p.getByRole('button',{name:'Войти',exact:true}).click();await p.getByRole('textbox',{name:'Имя',exact:true}).click();await ring(p.getByRole('textbox',{name:'Имя',exact:true}));assert.equal(await p.getByRole('textbox',{name:'Имя',exact:true}).evaluate(e=>e.getBoundingClientRect().right<=e.closest('dialog').getBoundingClientRect().right-20),true);await shot('11-home-profile');await p.keyboard.press('Escape');
  await p.goto('http://127.0.0.1:18080/shared.html');await p.evaluate(()=>{const b=document.createElement('button');b.textContent='Выбрать';document.querySelector('#shared-options').append(b)});await p.getByRole('button',{name:'Выбрать',exact:true}).click();await noRing(p.getByRole('button',{name:'Выбрать',exact:true}));await p.keyboard.press('Tab');await p.keyboard.press('Shift+Tab');await ring(p.getByRole('button',{name:'Выбрать',exact:true}));
  assert.deepEqual(errors,[]);console.log('PASS pointer/keyboard focus, about/history/region/preferences dialogs, composer, detail pane, gallery, summaries, checkout, checkbox, dates/guests/time, mobile tabs, homepage/profile, shared page; no JS errors');
 }catch(e){await shot('failure').catch(()=>{});throw e;}finally{await b.close()}
})().catch(e=>{console.error(e);process.exit(1)});

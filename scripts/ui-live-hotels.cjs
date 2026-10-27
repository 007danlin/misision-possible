// Real Qwen + HTTP public Ostrovok catalogue; no mocked AI/hotel response.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const out=path.join(root,'.runtime/screenshots/home-live');fs.mkdirSync(out,{recursive:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(190000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18080/');await page.evaluate(()=>document.fonts.ready);await page.locator('#cities option').first().waitFor({state:'attached'});
  assert.equal(await page.locator('main>section').count(),10);assert.equal(await page.locator('.workspace').count(),0);
  await page.screenshot({path:out+'/01-home.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:out+'/02-mobile-home.png',fullPage:true});await page.setViewportSize({width:1440,height:1000});
  // Intercept only outbound navigation, not catalogue fetches from the backend.
  let outbound='';await page.route('https://ostrovok.ru/**',route=>{outbound=route.request().url();return route.fulfill({contentType:'text/html',body:'Search navigation verified'});});
  await page.locator('#destination').fill('Сочи');await page.locator('#checkin').fill('2026-11-10');await page.locator('#checkout').fill('2026-11-15');await page.getByRole('button',{name:'Найти',exact:true}).click();await page.waitForURL('https://ostrovok.ru/**');
  const url=new URL(outbound);assert.equal(url.pathname,'/hotel/russia/sochi/');assert.equal(url.searchParams.get('dates'),'10.11.2026-15.11.2026');assert.equal(url.searchParams.get('guests'),'2');
  await page.goto('http://127.0.0.1:18080/');await page.locator('#ai-entry').click();await page.locator('.bubble.assistant').waitFor();assert.ok(page.url().endsWith('/plan.html'));
  await page.locator('#message').fill('Найди отели в Сочи, с 10 по 15 ноября 2026, двое взрослых, до 40 тысяч рублей на отель.');await page.locator('#send').click();
  await page.locator('.hotel-card').first().waitFor();const data=await page.evaluate(async()=>await(await fetch('/api/sessions/'+localStorage.getItem('oplan-hotels-session'))).json());
  assert.equal(data.hotel_options.length,3);assert.equal(data.data_mode,'public_catalogue_demo_rates');assert.equal(data.checkout_allowed,false);assert.ok(data.telemetry.model_calls>0);assert.ok(data.telemetry.tool_calls.includes('ostrovok_public_search'));assert.equal(data.trip_spec.destination,'Сочи');
  assert.ok(data.hotel_options.every(h=>h.url.startsWith('https://ostrovok.ru/')&&!('total'in h)));assert.equal(data.options.length,0);
  await page.waitForFunction(()=>[...document.querySelectorAll('.hotel-card img')].length===3&&[...document.querySelectorAll('.hotel-card img')].every(i=>i.complete&&i.naturalWidth>0),{},{timeout:30000});
  await page.screenshot({path:out+'/03-live-results.png'});await page.locator('.hotel-name-button').first().click();await page.locator('.booking-panel').waitFor();assert.ok(await page.getByRole('link',{name:'Проверить цены ↗',exact:true}).isVisible());await page.screenshot({path:out+'/04-detail.png'});
  await page.reload();await page.locator('.hotel-card').first().waitFor();assert.equal(await page.locator('.hotel-card').count(),3);
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:/^Варианты/}).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:out+'/05-mobile-results.png',fullPage:true});
  assert.deepEqual(errors,[]);fs.writeFileSync(out+'/report.json',JSON.stringify({model:data.telemetry.model,latency_ms:data.telemetry.total_ms,hotels:data.hotel_options.map(h=>({name:h.name,url:h.url})),passed:['homepage','mobile','normal-search-params','AI-entry','real-model','public-catalogue','three-photos','detail','reload','no-fake-prices']},null,2));console.log('PASS live hotel flow',data.telemetry.model,data.telemetry.total_ms+'ms',data.hotel_options.map(h=>h.name));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

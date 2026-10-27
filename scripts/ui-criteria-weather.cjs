// End-to-end regression: real search, proximity, weather, copy and mobile layout.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.setDefaultTimeout(45000);
 const out=path.join(root,'.runtime/screenshots/criteria-weather');fs.mkdirSync(out,{recursive:true});
 const report={steps:[],errors:[]};page.on('pageerror',e=>report.errors.push(e.message));
 async function turn(message){
  await page.locator('#message').fill(message);
  const pending=page.waitForResponse(r=>r.url().endsWith('/turns')&&r.request().method()==='POST');
  await page.locator('#send').click();const response=await pending,s=await response.json();
  await page.waitForFunction(()=>!document.querySelector('#send').disabled);
  assert.equal(response.status(),200);assert.notEqual(s.status,'error',s.assistant_message);
  report.steps.push({message,status:s.status,hotel_count:s.hotel_options?.length,preferences:s.trip_spec.hotel_preferences,model_calls:s.telemetry?.model_calls});
  return s;
 }
 try{
  await page.goto('http://127.0.0.1:18080/plan.html');await page.locator('.bubble.assistant').waitFor();
  await turn('Только отель, без дороги');
  let s=await turn('В Казань на 3 ночи, двое взрослых, до 25 тысяч рублей на отель, не дальше 2 км от центра');
  assert.ok(s.hotel_options.length>0,s.assistant_message);
  s=await turn('Около центра');
  assert.equal(s.trip_spec.hotel_preferences.max_center_m,2000);
  assert.equal(s.trip_spec.travellers.adults,2);assert.equal(s.trip_spec.stay_nights,3);
  assert.ok(s.hotel_options.length>0);assert.equal(s.telemetry.model_calls,0);
  assert.ok(s.hotel_options.every(h=>h.distance_m<=2000));
  assert.ok((await page.locator('#spec').innerText()).includes('До центра ≤ 2 км'));
  const copy=await page.locator('#results').innerText();
  for(const text of ['Оценка поездки · источники и условия','Повторяющиеся замечания','выборке','разобрано'])assert.ok(!copy.toLowerCase().includes(text.toLowerCase()),text);
  await page.screenshot({path:path.join(out,'results-desktop.png')});
  await page.locator('.hotel-name-button').first().click();
  await page.getByText('Расположение и погода',{exact:true}).click();
  await page.locator('.weather-summary').waitFor();
  const before=await page.locator('.weather-panel').innerText();assert.ok(before.includes('°C'));assert.ok(await page.locator('.weather-day').count()>0);assert.ok(!before.includes('Ссылка недоступна'));
  const source=page.locator('.weather-panel a');assert.ok((await source.getAttribute('href')).startsWith('https://api.met.no/')||(await source.getAttribute('href')).startsWith('https://open-meteo.com/'));
  report.weather=before;
  await page.getByRole('button',{name:'Обновить прогноз',exact:true}).click();
  await page.getByRole('button',{name:'Обновить прогноз',exact:true}).waitFor();
  assert.ok((await page.locator('.weather-panel').innerText()).includes('°C'));
  await page.locator('.weather-panel').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'weather-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:/^Варианты/}).click();await page.locator('.weather-panel').scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(out,'weather-mobile.png')});
  await page.getByRole('button',{name:'Диалог',exact:true}).click();
  const composer=await page.locator('#message').boundingBox();assert.ok(composer.height>0&&composer.y+composer.height<=844);
  assert.deepEqual(report.errors,[]);console.log('PASS real proximity search, live weather, refresh, copy and mobile');
 }finally{fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});

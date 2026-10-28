const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let snapshot={session_id:'b'.repeat(32),revision:1,status:'needs_input',search_mode:'hotels',trip_spec:{destination:'Сочи',dates:{start:'2026-11-10',end:'2026-11-15'},travellers:{adults:2,children:[]},budget:{amount_minor:12000000},budget_scope:'whole_trip',include_transport:true},hotel_options:[],destination_options:[],questions:['Из какого города отправляетесь?'],assistant_message:'Учёл ваши пожелания. Из какого города отправляетесь?'};
  await page.route('**/api/runtime/status',route=>route.fulfill({json:{ready:true}}));
  await page.route('**/api/sessions/**',async route=>{
   if(route.request().url().endsWith('/turns')){
    assert.equal(route.request().postDataJSON().message,'питер');
    snapshot={...snapshot,revision:2,trip_spec:{...snapshot.trip_spec,origin:'Санкт-Петербург'},questions:['Сколько из общего бюджета оставить на питание и личные расходы? Можно написать «резерв 0 рублей».'],assistant_message:'Учёл ваши пожелания. Сколько из общего бюджета оставить на питание и личные расходы? Можно написать «резерв 0 рублей».'};
   }
   await route.fulfill({json:snapshot});
  });
  await page.route('http://127.0.0.1:18080/**',route=>{
   const file=path.join(root,'backend/core/web',new URL(route.request().url()).pathname);
   return fs.existsSync(file)&&fs.statSync(file).isFile()?route.fulfill({path:file}):route.fallback();
  });
  await page.goto('http://127.0.0.1:18080/plan.html');
  await page.locator('#suggestions').getByRole('button',{name:'Санкт-Петербург',exact:true}).waitFor();
  assert.doesNotMatch(await page.locator('#suggestions').innerText(),/резерв|10 000/);
  assert.equal((await page.locator('#chat').innerText()).match(/Из какого города/g).length,1);
  // Old saved snapshots have the question only in assistant_message.
  await page.evaluate(()=>{state.questions=[];render();});
  assert.match(await page.locator('#suggestions').innerText(),/Санкт-Петербург/);
  await page.locator('#message').fill('питер');
  await page.locator('#send').click();
  await page.waitForFunction(()=>state.trip_spec.origin==='Санкт-Петербург'&&!working);
  assert.equal(await page.getByRole('button',{name:'Изменить город отправления'}).innerText(),'Санкт-Петербург');
  assert.match(await page.locator('#suggestions').innerText(),/Без отдельного резерва/);
  const last=await page.locator('#chat .assistant').last().innerText();
  assert.doesNotMatch(last,/Из какого города/);
  assert.equal((last.match(/Сколько из общего бюджета/g)||[]).length,1);
  await page.reload();
  await page.locator('#suggestions').getByRole('button',{name:'Без отдельного резерва'}).waitFor();
  // Exact journey dates come before reserve even if a stay length is known.
  await page.evaluate(()=>{delete state.trip_spec.dates;state.trip_spec.stay_nights=5;state.questions=['На какие точные даты собрать дорогу, отель и трансферы?'];render();});
  assert.match(await page.locator('#suggestions').innerText(),/Указать даты/);
  assert.doesNotMatch(await page.locator('#suggestions').innerText(),/резерв|10 000/);
  // An unrelated clarification must not trigger the reserve shortcuts.
  await page.evaluate(()=>{state.trip_spec.dates={start:'2026-11-10',end:'2026-11-15'};state.questions=['Выберите способ добраться.'];render();});
  assert.doesNotMatch(await page.locator('#suggestions').innerText(),/резерв|10 000/);
  assert.deepEqual(errors,[]);
  console.log('PASS: departure question → питер → reserve, legacy state, reload, exact dates, no duplicate questions or JS errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});

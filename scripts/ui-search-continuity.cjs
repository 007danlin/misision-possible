const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),{chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
  const fixtures=JSON.parse(fs.readFileSync(path.join(root,'backend/core/testdata/journey-quotes.json')));
  const old=fixtures.original,changed=fixtures.changed;
  changed.hotel.journey.checks.push({code:'children',status:'unknown',blocking:true,message:'Нужно подтвердить детские кресла.'});
  changed.hotel.journey.can_book=false;
  let snapshot={session_id:'b'.repeat(32),search_mode:'hotels',revision:1,status:'hotel_checkout',trip_spec:old.spec,selected_hotel:old.hotel,hotel_options:[old.hotel],assistant_message:'Выбрали отель.'};
  const recovery={hotel:old.hotel,spec:old.spec,previous_options:[old.hotel]};
  const preview={previous_hotel:old.hotel,previous_spec:old.spec,previous_options:[old.hotel],proposed_hotel:changed.hotel,proposed_spec:changed.spec,proposed_options:[changed.hotel],price_delta:changed.hotel.journey.total_minor-old.hotel.journey.total_minor};
  await page.route('**/api/sessions/**',async route=>{
   const url=route.request().url();
   if(url.endsWith('/turns')){
    const message=route.request().postDataJSON().message;
    if(message==='Добавь ребёнка')snapshot={...snapshot,revision:2,status:'needs_input',trip_spec:{...old.spec,travellers:{...old.spec.travellers,children:[null]}},journey_recovery:recovery,assistant_message:'Сколько лет ребёнку?'};
    else snapshot={...snapshot,revision:3,status:'choosing',trip_spec:changed.spec,selected_hotel:null,hotel_options:[changed.hotel],journey_recovery:null,journey_preview:preview,assistant_message:'Пересчитал поездку.'};
   }else if(url.endsWith('/actions'))snapshot={...snapshot,revision:4,status:'hotel_checkout',trip_spec:changed.spec,selected_hotel:changed.hotel,journey_preview:null};
   await route.fulfill({json:snapshot});
  });
  await page.route('http://127.0.0.1:18080/**',route=>{
   const file=path.join(root,'backend/core/web',new URL(route.request().url()).pathname);
   return fs.existsSync(file)&&fs.statSync(file).isFile()?route.fulfill({path:file}):route.fallback();
  });
  await page.goto('http://127.0.0.1:18080/plan.html');await page.locator('#guest-name').waitFor();
  async function send(message){await page.locator('#message').fill(message);await page.locator('#send').click();await page.waitForFunction(()=>!working);}
  await send('Добавь ребёнка');
  await page.locator('.saved-hotel-options').waitFor();
  assert.match(await page.locator('#results').innerText(),/ваш выбор сохранён/);
  assert.match(await page.locator('.saved-hotel-options').innerText(),new RegExp(old.hotel.name));
  assert.equal(await page.getByRole('button',{name:'Подтвердить поездку',exact:true}).count(),0);
  await page.reload();await page.locator('.saved-hotel-options').waitFor();
  await send('Ему 5 лет');await page.locator('.trip-preview').waitFor();
  const table=await page.locator('.trip-preview table').innerText();assert.match(table,/Гости/);assert.match(table,/Оба трансфера/);assert.match(table,/Сборы/);
  await page.getByRole('button',{name:'Принять изменения',exact:true}).click();
  await page.locator('#guest-name').waitFor();
  assert.equal(await page.getByRole('button',{name:'Подтвердить поездку',exact:true}).isDisabled(),true);
  const out=path.join(root,'.runtime/screenshots/continuity');fs.mkdirSync(out,{recursive:true});
  await page.screenshot({path:path.join(out,'family-repriced.png')});
  for(const status of ['no_solution','error']){
   await page.evaluate(({recovery,status})=>{state={...state,status,journey_recovery:recovery,journey_preview:null,assistant_message:'Уточните новые условия.'};render();},{recovery,status});
   assert.equal(await page.locator('.saved-hotel-options .card').count(),1);
  }
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:path.join(out,'saved-mobile.png')});
  await page.evaluate(preview=>{delete preview.previous_hotel.journey;delete preview.proposed_hotel.journey;state.journey_recovery=null;state.journey_preview=preview;render();},structuredClone(preview));
  assert.match(await page.locator('.trip-preview').innerText(),/Не включено/);
  assert.deepEqual(errors,[]);
  console.log('PASS: selected hotel survives clarification and reload; family and all cost items show in preview; unknown conditions stay blocked at checkout; hotel-only preview and mobile recovery render.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});

const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
const catalogue=JSON.parse(fs.readFileSync(path.join(root,'agent/travel_agent/direction_catalogue.json'),'utf8'));
const cards = ids => ids.map(id => {const d=catalogue.find(d=>d.id===id);return {...d,reason:d.facts.join(' '),caveat:d.limits};});
(async()=>{
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],turns=[];
  page.on('pageerror',e=>errors.push(e.message));
  const snapshot={session_id:'d'.repeat(32),revision:1,status:'needs_input',search_mode:'hotels',search_title:'Хочу на природу',trip_spec:{origin:'Москва',travel_setting:'forest',include_transport:true,preferences:['уединение']},hotel_options:[],destination_options:cards(['karelia','altai','seliger']),assistant_message:'Выберите направление.'};
  await page.route('**/api/sessions/**',async route=>{if(route.request().url().endsWith('/turns'))turns.push(route.request().postDataJSON());await route.fulfill({json:snapshot});});
  await page.route('http://127.0.0.1:18080/**',route=>{const file=path.join(root,'backend/core/web',new URL(route.request().url()).pathname);return fs.existsSync(file)&&fs.statSync(file).isFile()?route.fulfill({path:file}):route.fallback();});
  await page.goto('http://127.0.0.1:18080/plan.html');
  await page.locator('.direction-card').first().waitFor();
  const verifyPhotos=async()=>{
   await page.waitForFunction(()=>[...document.querySelectorAll('.direction-visual img')].every(i=>i.complete&&i.naturalWidth>0));
   const photos=await page.locator('.direction-visual img').evaluateAll(imgs=>imgs.map(i=>i.src));
   assert.equal(photos.length,3);assert.equal(new Set(photos).size,3);
   assert.ok(photos.every(p=>!p.includes('stay-')&&!p.includes('cdn.ostrovok')));
  };
  await verifyPhotos();
  assert.deepEqual(await page.locator('.direction-card h3').allTextContents(),['Карелия','Алтай','Селигер']);
  fs.mkdirSync(path.join(root,'.runtime/screenshots'),{recursive:true});
  await page.screenshot({path:path.join(root,'.runtime/screenshots/directions-general.png'),fullPage:true});
  await page.getByRole('button',{name:'Выбрать Алтай',exact:true}).click();
  await page.waitForFunction(()=>!working);
  assert.equal(turns.at(-1).message,'Выбираю Алтай, ищем в районе Чемал. Остальные пожелания сохрани.');
  await page.evaluate(options=>{state.destination_options=options;state.trip_spec.travel_setting='city';render();},cards(['petersburg','kazan','sochi']));
  await verifyPhotos();
  // Every catalogue destination must have a real local photo, including
  // previously saved cards with a null photo_key.
  for(let i=0;i<catalogue.length;i+=3){
   const batch=cards(catalogue.slice(i,i+3).map(d=>d.id));
   await page.evaluate(options=>{state.destination_options=options;render();},batch);
   await verifyPhotos();
  }
  await page.evaluate(options=>{state.destination_options=options.map(d=>({...d,photo_key:null}));render();},cards(['sochi_nature','gelendzhik','anapa']));
  await verifyPhotos();
  await page.screenshot({path:path.join(root,'.runtime/screenshots/directions-sea.png'),fullPage:true});
  await page.evaluate(options=>{state.destination_options=options;render();},cards(catalogue.map(d=>d.id)));
  await page.waitForFunction(()=>[...document.querySelectorAll('.direction-visual img')].every(i=>i.complete&&i.naturalWidth>0));
  await page.screenshot({path:path.join(root,'.runtime/screenshots/directions-all.png'),fullPage:true});
  // Broken landscape asset also has a truthful fallback.
  await page.route('**/assets/directions/missing.jpg',r=>r.abort());
  await page.evaluate(()=>{directionPhotos['Сортавала'].image_url='/assets/directions/missing.jpg';});
  await page.evaluate(options=>{state.destination_options=options;state.trip_spec.travel_setting='forest';render();},cards(['karelia']));
  await page.waitForFunction(()=>document.querySelector('.direction-visual')?.getAttribute('role')==='img');
  assert.equal(await page.locator('.direction-visual img').count(),0);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log('PASS: distinct landscapes, city photographs, attribution, choice command, all 21 catalogue photos, legacy cards, broken-photo fallback and mobile layout.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});

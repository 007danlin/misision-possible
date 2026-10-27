// Layout fixtures exercise real renderers without model/network timing.
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'..'),web=path.join(root,'backend/core/web');
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
const fixture=JSON.parse(fs.readFileSync(path.join(root,'.runtime/nature-fixture.json')));
const desktop=process.env.LAYOUT_PROFILE==='desktop';
const sizes=desktop?[[761,600],[900,600],[1000,700],[1001,700],[1100,700],[1101,700],[1200,700],[1280,720],[1366,768],[1440,900],[1600,900],[1920,1080],[2560,1440],[1024,450],[1280,500],[1440,400]]:[[320,568],[360,640],[390,844],[430,932],[768,1024],[844,390],[390,400],[1440,1000]];
const out=path.join(root,'.runtime/screenshots',desktop?'desktop-layout':'mobile-layout');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const b=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true}),report=[],errors=[];
 try{for(const [width,height] of sizes){
  const p=await b.newPage({viewport:{width,height},locale:'ru-RU'});p.setDefaultTimeout(10000);p.on('pageerror',e=>errors.push(e.message));
  await p.route('**/api/sessions/**',r=>r.fulfill({json:r.request().url().includes('?mode=')?[]:{session_id:'a'.repeat(32),revision:0,search_mode:'hotels',status:'needs_input',trip_spec:{},hotel_options:[],destination_options:[],assistant_message:'Расскажите о поездке.'}}));
  if(process.env.FOCUS_SOURCE==='1')await p.route('http://127.0.0.1:18080/**',r=>{const u=new URL(r.request().url()),file=path.join(web,u.pathname==='/'?'index.html':u.pathname);return fs.existsSync(file)&&fs.statSync(file).isFile()?r.fulfill({path:file}):r.fallback()});
  async function scan(name){await p.evaluate(()=>document.fonts.ready);const issues=await p.evaluate(()=>{
   const root=document.querySelector('dialog[open]')||document.body,issues=[];
   if(document.documentElement.scrollWidth>innerWidth+1)issues.push('page wider than viewport');
   const describe=e=>e.tagName.toLowerCase()+(e.id?'#'+e.id:'.'+String(e.className).slice(0,55));
   for(const e of [root,...root.querySelectorAll('*')]){
    if(!e.getClientRects().length||getComputedStyle(e).visibility==='hidden'||e.closest('svg')||e.matches('img,canvas,script,style,option,.sr-only,.skip')||e.closest('.sr-only'))continue;
    const r=e.getBoundingClientRect(),s=getComputedStyle(e);if(r.width<1)continue;
    // A visually hidden native checkbox backs the visible switch in the archive.
    if(r.left< -1000&&e.matches('input[type=checkbox]'))continue;
    // Decorative art can bleed at the edge; interactive content cannot.
    if(e.matches('[class^="USPSection_image__"]'))continue;
    let scroller=false;for(let a=e.parentElement;a&&a!==document.body;a=a.parentElement){if(['auto','scroll'].includes(getComputedStyle(a).overflowX)&&a.scrollWidth>a.clientWidth+2){scroller=true;break;}}
    if(!scroller&&(r.left< -2||r.right>innerWidth+2))issues.push(describe(e)+' outside viewport');
    if(e.matches('button,select,label,h1,h2,h3,.card,.detail-content,.checkout-form,.stay-fields,.child-ages,.trip-fold,.dialog-heading')&&e.scrollWidth>e.clientWidth+2&&!['auto','scroll'].includes(s.overflowX))issues.push(describe(e)+' clips content');
   }
   for(const pane of document.querySelectorAll('.plans,.assistant,.top,.searchbar,.checkout-grid,.detail-grid,.cards,.trip-comparison')){if(pane.getClientRects().length&&pane.scrollWidth>pane.clientWidth+2)issues.push(describe(pane)+' overflows internally');}
   if(!document.querySelector('dialog[open]')&&document.querySelector('.smart-mode .assistant')?.getClientRects().length){const send=document.querySelector('#send').getBoundingClientRect();if(send.bottom>innerHeight+1)issues.push('send button below viewport');}
   const brand=document.querySelector('.brand'),actions=document.querySelector('.topright');if(brand&&actions){const x=brand.getBoundingClientRect(),y=actions.getBoundingClientRect();if(x.right>y.left&&x.bottom>y.top)issues.push('header overlap');}
   const d=document.querySelector('dialog[open]');if(d){const r=d.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight+1)issues.push('dialog outside viewport vertically');}
   return issues;
  });report.push({width,height,name,issues});if((desktop&&[761,1001,1280,1440,1920].includes(width))||(!desktop&&(width===320||width===390)))await p.screenshot({path:path.join(out,width+'x'+height+'-'+name+'.png')});if(!process.env.LAYOUT_AUDIT)assert.deepEqual(issues,[],width+'x'+height+' '+name);else if(issues.length)console.log(width,height,name,JSON.stringify(issues));}
  async function goto(url){await p.goto('http://127.0.0.1:18080'+url,{waitUntil:'domcontentloaded'});}
  await goto('/');await p.locator('#checkin').waitFor();await scan('home');
  await p.locator('[data-testid="sing-in-control"]').click();await scan('profile');await p.locator('.archive-dialog .close').click();
  await goto('/plan.html');await p.locator('.bubble.assistant').waitFor();await scan('chat');
  if(width<=760){const r=await p.locator('#send').boundingBox();assert.ok(r.y+r.height<=height+1,'send button below viewport');}
  await p.evaluate(()=>fillPrompt('Семейная поездка с детьми, бассейном и завтраками. '.repeat(40)));await scan('chat-long-message');await p.evaluate(()=>{$('message').value='';resizeComposer();mobileView('results')});await scan('empty');await p.evaluate(()=>TravelWindow.start($('results'),false,'/api/sessions/layout/progress'));await p.locator('.ow-mark').evaluate(e=>Promise.all(e.getAnimations().map(a=>a.finished.catch(()=>{}))));await scan('searching');await p.evaluate(()=>TravelWindow.stop());
  await p.evaluate(f=>{Object.assign(state,f,{status:'choosing'});state.trip_spec.dates={start:'2026-12-23',end:'2026-12-28'};render();mobileView('results');},fixture);await scan('cards');await p.evaluate(()=>TravelWindow.start($('results'),true,'/api/sessions/layout/progress','Найди дешевле'));await scan('searching-compact');await p.evaluate(()=>TravelWindow.stop());
  await p.locator('.hotel-name-button').first().click();await p.evaluate(()=>document.querySelectorAll('#results details').forEach(d=>d.open=true));await scan('details');
  await p.evaluate(()=>{state.selected_hotel=state.hotel_options[0];state.status='hotel_checkout';render();});await scan('checkout');
  await p.getByRole('button',{name:'Изменить выезд',exact:true}).click();await p.locator('#stay-children').fill('10');await scan('stay-10-children');
  const save=p.getByRole('button',{name:'Сохранить и пересчитать',exact:true});await save.scrollIntoViewIfNeeded();const rect=await save.boundingBox();assert.ok(rect.y>=0&&rect.y+rect.height<=height,'dialog save unreachable');await p.keyboard.press('Escape');
  await p.getByRole('button',{name:'Мои предпочтения',exact:true}).click();await scan('preferences');await p.keyboard.press('Escape');
  await p.evaluate(()=>editRegion());await scan('region');await p.keyboard.press('Escape');
  await p.locator('#history').click();await p.locator('.history-list').waitFor();await scan('history');await p.keyboard.press('Escape');
  await p.evaluate(()=>{state.hotel_booking={id:'OPlan-'+('1234567890abcdef'.repeat(4)),hotel:state.selected_hotel,dates:state.trip_spec.dates,travellers:{adults:2},guest_name:'Александр Константинопольский'};render();document.querySelectorAll('#results details').forEach(d=>d.open=true)});await scan('booked-long-id');
  await p.evaluate(()=>{state.hotel_booking=null;state.selected_hotel=null;state.hotel_options.forEach(h=>h.journey={total_minor:12345678,breakdown:{hotel:3450000,transport:6800000,transfers:2095678},segments:[{label:'Самолёт туда',kind:'flight',origin:'Москва — аэропорт Шереметьево',destination:'Санкт-Петербург — аэропорт Пулково',departure:'2026-12-23T10:00:00+03:00',arrival:'2026-12-23T11:30:00+03:00',duration_minutes:90},{label:'Трансфер до отеля',kind:'transfer',origin:'Аэропорт',destination:h.name,departure:'2026-12-23T12:00:00+03:00',arrival:'2026-12-23T13:00:00+03:00',duration_minutes:60}],checks:[],can_book:true,vehicles:1,baggage:'2 чемодана',checkin_from:'2026-12-23T14:00:00+03:00',checkout_until:'2026-12-28T12:00:00+03:00'});state.journey_preview={previous_hotel:state.hotel_options[0],proposed_hotel:state.hotel_options[1],previous_spec:state.trip_spec,proposed_spec:state.trip_spec,price_delta:120000};render();document.querySelectorAll('#results details').forEach(d=>d.open=true);});await scan('journey-preview');
  await p.evaluate(()=>{state.journey_preview=null;state.share={token:'a'.repeat(64),expires_at:'2026-12-23',options:state.hotel_options,votes:{}};render();document.querySelectorAll('#results details').forEach(d=>d.open=true)});await scan('comparison-share');
  await p.evaluate(()=>{state.status='error';state.assistant_message='Поиск временно недоступен. Попробуйте ещё раз.';render();});await scan('error');
  await goto('/shared.html');await p.evaluate(()=>{const card=document.createElement('article');card.innerHTML='<h3>Частный дом рядом с историческим центром Санкт-Петербурга</h3><p>Даты: 23–28 декабря, 20 взрослых и 10 детей</p><button>Выбрать этот вариант</button>';document.querySelector('#shared-options').append(card)});await scan('shared');
  console.log('PASS '+width+'x'+height+' all states');await p.close();
 }assert.deepEqual(errors,[]);}finally{fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({report,errors},null,2));await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});

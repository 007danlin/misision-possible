// Browser contract for decorative flights. Model responses are deliberately held.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const {chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
const base=process.env.TRIP_SMOKE_URL||'http://127.0.0.1:18080/plan.html';
const out=path.join(root,'.runtime/screenshots/travel-cards');
fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}}), errors=[], external=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   if(new URL(route.request().url()).origin!==new URL(base).origin){external.push(route.request().url());return route.abort();}
   return route.continue();
  });
  await page.route('**/api/sessions/**',route=>route.fulfill({json:route.request().url().includes('/progress')?{stage:'waiting'}:{schema_version:'0.2',session_id:'a'.repeat(32),revision:0,search_mode:'hotels',status:'needs_input',trip_spec:{},hotel_options:[],destination_options:[],assistant_message:'Расскажите о поездке.'}}));
  await page.goto(base);await page.locator('.inspiration').waitFor();
  await page.waitForFunction(()=>performance.getEntriesByType('resource').filter(r=>r.name.includes('/travel-cards/')&&r.responseEnd>0).length===24);
  await page.evaluate(async()=>{await document.fonts.ready;});
  const start=compact=>page.evaluate(compact=>{
   TravelWindow.start(document.getElementById('results'),compact,'/api/sessions/test/progress');
   window.births=[];window.maxCards=0;
   new MutationObserver(records=>{
    for(const record of records)for(const n of record.addedNodes)if(n.matches?.('.ow-photo-card'))births.push({src:n.src,at:performance.now(),decoded:n.complete&&n.naturalWidth===320});
    maxCards=Math.max(maxCards,document.querySelectorAll('.ow-photo-card').length);
   }).observe(document.querySelector('.ow-photo-layer'),{childList:true});
  },compact);
  await start(false);
  await page.waitForTimeout(1100);
  await page.screenshot({path:out+'/desktop.png'});
  // Freeze O's animations, leaving flight scheduling unaffected by screenshots.
  const sameO=await page.evaluate(async()=>{
   const animations=document.getAnimations().filter(a=>!a.effect.target.matches?.('.ow-photo-card'));animations.forEach(a=>a.pause());
   await Promise.all(animations.map(a=>a.ready));
   const mark=document.querySelector('.ow-mark'),ring=document.querySelector('.ow-ring');
   const dimensions=()=>JSON.stringify([mark.getBoundingClientRect().toJSON(),ring.getBoundingClientRect().toJSON(),getComputedStyle(ring).border,getComputedStyle(ring).boxShadow]);
   const before=dimensions();document.querySelector('.ow-photo-layer').style.display='none';return before===dimensions();
  });
  const ringBox=await page.locator('.ow-ring').boundingBox();
  const opening={x:ringBox.x+50,y:ringBox.y+50,width:ringBox.width-100,height:ringBox.height-100};
  const original=await page.screenshot({clip:opening});
  await page.locator('.ow-photo-layer').evaluate(e=>e.style.display='');
  const withCards=await page.screenshot({clip:opening});
  assert.ok(sameO,'Cards must not change O geometry or styles');
  assert.ok(original.equals(withCards),'Cards must not alter any visible pixels inside O');
  assert.deepEqual(await page.evaluate(async()=>{
   const url=document.querySelector('.ow-photo-layer').style.maskImage.slice(5,-2);
   const img=new Image();img.src=url;await img.decode();
   const canvas=document.createElement('canvas');canvas.width=860;canvas.height=430;
   const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
   return [ctx.getImageData(410,215,1,1).data[3],ctx.getImageData(10,10,1,1).data[3]];
  }),[0,255],'The actual mask must remove the entire O opening');
  await page.evaluate(()=>document.getAnimations().forEach(a=>a.play()));
  await page.waitForFunction(()=>births.length>=26,{},{timeout:40000});
  const run=await page.evaluate(()=>({births,maxCards}));
  assert.ok(run.maxCards<=3,'At most three simultaneous cards');
  // Observer starts after the first card; the next full shuffled bag is still unique.
  assert.equal(new Set(run.births.slice(0,24).map(b=>b.src)).size,24);
  assert.ok(run.births.every(b=>b.decoded),'Only decoded local photos may fly');
  assert.ok(run.births.every((b,i)=>!i||b.src!==run.births[i-1].src),'No adjacent repeats at shuffle boundary');
  const gaps=run.births.slice(1).map((b,i)=>b.at-run.births[i].at);
  assert.ok(gaps.every(ms=>ms>=680&&ms<1450),'Birth interval stays near 0.7–1.2 s');
  const finish=await page.evaluate(async()=>{
   const count=births.length,start=performance.now();const done=TravelWindow.prepare([]);
   await new Promise(r=>setTimeout(r,100));const layer=document.querySelector('.ow-photo-layer');
   const opacity=layer?Number(getComputedStyle(layer).opacity):0;
   await done;return {elapsed:performance.now()-start,opacity,births:births.length-count,cards:document.querySelectorAll('.ow-photo-card').length};
  });
  assert.ok(finish.elapsed>=200&&finish.elapsed<400);assert.ok(finish.opacity>0&&finish.opacity<1);assert.equal(finish.births,0);assert.equal(finish.cards,0);
  await page.evaluate(()=>TravelWindow.stop());
  for(const width of [390,320]) {
   await page.setViewportSize({width,height:844});
   await page.evaluate(()=>document.querySelector('.workspace').dataset.mobileView='results');
   await start(false);await page.waitForTimeout(1000);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   assert.equal(await page.locator('.ow-photo-card').first().evaluate(e=>getComputedStyle(e).width),'96px');
   await page.screenshot({path:out+'/mobile-'+width+'.png'});
   await start(true);await page.waitForTimeout(1000);
   await page.screenshot({path:out+'/compact-'+width+'.png'});
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForTimeout(1300);assert.equal(await page.locator('.ow-photo-card').count(),0);
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.locator('.ow-photo-card').first().waitFor({state:'attached'});
  // An error uses stop(), which should drain without leaving timers or nodes.
  await page.evaluate(()=>TravelWindow.stop());
  await page.waitForTimeout(300);assert.equal(await page.locator('.travel-window').count(),0);
  await page.waitForTimeout(1300);assert.equal(await page.locator('.ow-photo-card').count(),0);
  await page.emulateMedia({reducedMotion:'reduce'});await start(false);
  await page.waitForTimeout(1300);assert.equal(await page.locator('.ow-photo-card').count(),0);
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  console.log('PASS: 24-photo shuffle, long wait, <=3 flights, cadence, decoded local assets, unchanged O pixels, 250 ms drain, error cleanup, 320/390 mobile, compact, reduced-motion toggle, no external requests');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

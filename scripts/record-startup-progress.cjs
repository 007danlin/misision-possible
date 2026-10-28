// Observe the real Compose startup; no health, model, or download responses are mocked.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');const{chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
const base=process.env.STARTUP_TEST_URL||'http://127.0.0.1:8080';
const out=process.env.STARTUP_TEST_OUTPUT||path.join(root,'.runtime/screenshots/cold-start');fs.mkdirSync(out,{recursive:true});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});const report={base_url:base,mocked:false,phases:[],errors:[],download_samples:[]};const started=Date.now();
 try{const page=await browser.newPage({viewport:{width:1440,height:960}});page.on('pageerror',e=>report.errors.push(e.message));let connected=false;const seen=new Set();
 while(Date.now()-started<1800000){
  if(!connected){try{await page.goto(base+'/plan.html',{timeout:5000});connected=true}catch{await sleep(1000);continue}}
  try{const s=await page.evaluate(async()=>{const r=await fetch('/api/runtime/status',{cache:'no-store'});if(!r.ok)throw Error('not ready');return await r.json()});
   if(s.phase==='downloading'&&s.downloaded_bytes>0){if(report.download_samples.at(-1)!==s.downloaded_bytes)report.download_samples.push(s.downloaded_bytes)}
   if(!seen.has(s.phase)&&(!['downloading'].includes(s.phase)||s.downloaded_bytes>0)){
    if(s.phase==='downloading')await page.waitForFunction(()=>document.getElementById('bar')?.value>0,{},{timeout:8000});
    seen.add(s.phase);report.phases.push({seconds:(Date.now()-started)/1000,...s});
    if(!s.ready){await page.screenshot({path:path.join(out,s.phase+'-desktop.png')});if(s.phase==='downloading'){await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'downloading-mobile.png')});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)){report.errors.push('mobile overflow');throw Error('mobile overflow')};await page.setViewportSize({width:1440,height:960})}}
   }
   if(s.ready){await page.locator('#send').waitFor({timeout:15000});report.redirected_to_application=true;report.title=await page.title();report.seconds=(Date.now()-started)/1000;report.passed=report.errors.length===0&&report.download_samples.length>1;await page.screenshot({path:path.join(out,'ready.png')});break}
  }catch(e){if(!String(e).includes('Execution context was destroyed')){report.last_observer_error=String(e);if(seen.has('ready')){report.errors.push(String(e));break}}}
  await sleep(1000)
 }
 if(!report.passed)throw Error('Startup observation incomplete: '+JSON.stringify(report));console.log('PASS real startup progress, changing byte counts, mobile, automatic application entry');
 }finally{fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

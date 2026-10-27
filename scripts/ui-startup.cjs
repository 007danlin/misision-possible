// UI test with service-health fixtures; the real empty-volume test is separate.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict');
const{spawn,execFile}=require('child_process');const{promisify}=require('util');
const root=path.resolve(__dirname,'..');const{chromium}=require(path.join(root,'.runtime/browser/node_modules/playwright-core'));
const run=promisify(execFile),sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const out=path.join(root,'.runtime/screenshots/startup');fs.mkdirSync(out,{recursive:true});
 const tmp=fs.mkdtempSync(path.join(root,'.runtime/bootstrap-ui-'));const binary=path.join(tmp,'core');
 await run('go',['build','-o',binary],{cwd:path.join(root,'backend/core'),env:{...process.env,GOMAXPROCS:'2'}});
 const python=spawn(path.join(root,'agent/.venv/bin/python'),['-u','-c',`import sys\nfrom concurrent import futures\nsys.path.insert(0,${JSON.stringify(path.join(root,'agent'))})\nimport grpc\nfrom proto import predict_pb2 as pb,predict_pb2_grpc as rpc\nclass Health(rpc.PredictorServicer):\n def Predict(self,req,ctx): return pb.PredictReply(caller=req.caller)\ns=grpc.server(futures.ThreadPoolExecutor(1));rpc.add_PredictorServicer_to_server(Health(),s);p=s.add_insecure_port('127.0.0.1:0');s.start();print(p,flush=True);s.wait_for_termination()`],{cwd:root});
 let browser,core,model,healthy=false;
 try{
  const agentPort=await new Promise((resolve,reject)=>{python.stdout.once('data',d=>resolve(Number(d.toString().trim())));python.once('error',reject);python.once('exit',code=>reject(Error('health fixture exited '+code)))});
  model=http.createServer((req,res)=>{res.writeHead(healthy?200:503);res.end('{}')});await new Promise(r=>model.listen(0,'127.0.0.1',r));
  const free=http.createServer();await new Promise(r=>free.listen(0,'127.0.0.1',r));const port=free.address().port;await new Promise(r=>free.close(r));
  const status=path.join(tmp,'status.json');fs.writeFileSync(status,JSON.stringify({phase:'downloading',message:'Скачиваем модель',downloaded_bytes:1234567890,total_bytes:5680522464,percent:21.73,bytes_per_second:13500000}));
  core=spawn(binary,[],{cwd:root,env:{...process.env,PORT:String(port),BIND_HOST:'127.0.0.1',LOCAL_DEMO_MODE:'true',TRIP_DATA_DIR:path.join(tmp,'trips'),MODEL_STATUS_FILE:status,MODEL_HEALTH_URL:'http://127.0.0.1:'+model.address().port,AGENT_HOST:'127.0.0.1',AGENT_PORT:String(agentPort)}});
  for(let i=0;i<50;i++){try{await fetch('http://127.0.0.1:'+port+'/health');break}catch{await sleep(100)}}
  browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const p=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
  await p.goto('http://127.0.0.1:'+port+'/plan.html');await p.getByText(/21.7%/).waitFor();assert.equal(await p.locator('progress').getAttribute('value'),'21.73');
  assert.equal((await p.request.post('http://127.0.0.1:'+port+'/api/sessions/',{data:{}})).status(),503);
  await p.screenshot({path:path.join(out,'download-desktop.png')});await p.setViewportSize({width:390,height:844});await p.screenshot({path:path.join(out,'download-mobile.png')});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  fs.writeFileSync(status,JSON.stringify({phase:'loading',message:'Загружаем модель в память'}));await p.getByText('Загружаем модель в память').waitFor();assert.equal(await p.locator('progress').getAttribute('value'),null);
  healthy=true;await p.locator('#send').waitFor();assert.equal(await p.title(),'О!План — ваша поездка с Островком');assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({passed:true,fixture:true,checks:['download bytes and percent','mobile layout','trip API blocked before readiness','loading phase indeterminate','automatic navigation after model and agent readiness','no JS errors']},null,2));
  console.log('PASS startup UI: real Core, health fixtures, live progress, API guard, mobile, automatic navigation');
 }finally{if(browser)await browser.close();if(core)core.kill('SIGTERM');python.kill('SIGTERM');if(model)await new Promise(r=>model.close(r));fs.rmSync(tmp,{recursive:true,force:true})}
})().catch(e=>{console.error(e);process.exitCode=1});

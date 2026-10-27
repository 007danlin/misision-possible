// Records real browser interactions. Requires playwright-core, Chrome and Playwright ffmpeg.
const path = require('node:path');
const fs = require('node:fs');
const root = path.resolve(__dirname, '..');
process.chdir(root);
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
const output = path.join(root, '.runtime/submission-video');
fs.mkdirSync(output, {recursive:true});
(async()=>{
  const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1280,height:900},recordVideo:{dir:output,size:{width:1280,height:900}}});
  const page=await context.newPage();page.setDefaultTimeout(315000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  async function waitForResult(button){
    await page.waitForFunction(() => !document.getElementById('send').disabled);
    await button.waitFor({timeout:5000});
  }
  const times={};let success=false;
  try{
    await page.goto(process.env.TRIP_SMOKE_URL || 'http://127.0.0.1:8080');
    await page.locator('.bubble.assistant').waitFor();
    await page.screenshot({path:path.join(output,'intro.png'),fullPage:true});
    await page.getByRole('button',{name:'Море на двоих'}).click();
    await page.locator('#send').scrollIntoViewIfNeeded();
    let started=Date.now();await page.locator('#send').click();
    await waitForResult(page.getByRole('button',{name:'Выбрать поездку'}).first());
    times.first_turn_ms=Date.now()-started;
    const first=page.locator('.card').filter({has:page.getByRole('heading',{name:'Вариант A',exact:true})});
    await first.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,'options.png'),fullPage:true});
    await first.getByRole('button',{name:'Выбрать поездку'}).click();
    await page.getByRole('button',{name:'Подтвердить поездку'}).waitFor();
    await page.locator('#message').fill('Теперь максимум 100 тысяч, остальное оставь');
    await page.locator('#send').scrollIntoViewIfNeeded();
    started=Date.now();await page.locator('#send').click();
    await waitForResult(page.getByRole('button',{name:'Принять изменение'}));
    times.change_turn_ms=Date.now()-started;
    if(await page.getByRole('button',{name:'Подтвердить поездку'}).count())throw Error('Checkout allowed before preview acceptance');
    if(!(await page.locator('.delta').textContent()).includes('12'))throw Error('Missing expected price delta');
    await page.locator('.change-details').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,'changes.png'),fullPage:true});
    await page.getByRole('button',{name:'Принять изменение'}).click();
    await page.getByRole('button',{name:'Подтвердить поездку'}).click();
    await page.getByRole('heading',{name:'Поездка оформлена — в демо'}).waitFor();
    await page.locator('.booking').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,'booked.png'),fullPage:true});
    await page.reload();await page.getByRole('heading',{name:'Поездка оформлена — в демо'}).waitFor();
    await page.locator('.booking').scrollIntoViewIfNeeded();
    if(errors.length)throw Error(errors.join('; '));
    success=true;
  }finally{
    const video=page.video();await context.close();
    if(video)await video.saveAs(path.join(output,success?'demo.webm':'failed-run.webm'));
    await browser.close();
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({success,times,errors,url:process.env.TRIP_SMOKE_URL || 'http://127.0.0.1:8080'},null,2));
    console.log(JSON.stringify({success,times,output}));
  }
})().catch(e=>{console.error(e);process.exit(1)});

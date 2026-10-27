const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
(async () => {
  const browser = await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    let snapshot = {session_id:'a'.repeat(32),revision:0,status:'needs_input',search_mode:'hotels',trip_spec:{include_transport:true},hotel_options:[],destination_options:[],assistant_message:'Расскажите о поездке.'};
    let releaseTurn;
    await page.route('**/api/sessions/**', async route => {
      if (route.request().url().endsWith('/turns')) {
        const body = route.request().postDataJSON();
        assert.equal(body.message, 'Отправляемся из Казань');
        await new Promise(resolve => {releaseTurn = resolve;});
        snapshot = {...snapshot,revision:snapshot.revision+1,trip_spec:{origin:'Казань',include_transport:true,transfer_provider:'estimate',transport_mode:'auto',travel_setting:'any',budget_period:'stay',travellers:{adults:null,children:[]},hard_constraints:{no_connections:false,other:[]},hotel_preferences:{pool:null}},assistant_message:'Куда хотите поехать?'};
      }
      await route.fulfill({json:snapshot});
    });
    await page.route('http://127.0.0.1:18080/**', route => {
      const file = path.join(root,'backend/core/web',new URL(route.request().url()).pathname);
      return fs.existsSync(file) && fs.statSync(file).isFile() ? route.fulfill({path:file}) : route.fallback();
    });
    const checkIdeas = async () => {
      assert.match(await page.locator('#results').innerText(),/Хорошая поездка начинается с идеи/);
      assert.equal(await page.locator('.inspiration .card').count(),3);
      if (!await page.evaluate(() => working)) assert.match(await page.locator('#suggestions').innerText(),/К морю/);
    };
    await page.goto('http://127.0.0.1:18080/plan.html');
    await page.locator('.inspiration').waitFor();
    await checkIdeas();
    for(let i=0;i<2;i++) {
      await page.getByRole('button',{name:'Изменить город отправления'}).click();
      await page.locator('#origin-city').fill('Казань');
      const request = page.waitForRequest(r => r.url().endsWith('/turns'));
      await page.getByRole('button',{name:'Подтвердить город'}).click();
      await request;
      await checkIdeas();
      await page.waitForFunction(() => working);
      while (!releaseTurn) await new Promise(resolve => setTimeout(resolve,10));
      releaseTurn(); releaseTurn = null;
      await page.waitForFunction(() => !working);
      await checkIdeas();
      assert.equal(await page.getByRole('button',{name:'Изменить город отправления'}).innerText(),'Казань');
    }
    await page.reload(); await page.locator('.inspiration').waitFor(); await checkIdeas();
    // Every idea uses the current origin, including edits after the cards rendered.
    for (const origin of ['Казань', 'Санкт-Петербург', '']) {
      await page.evaluate(origin => {state.trip_spec.origin=origin;}, origin);
      for (const selector of ['.inspiration .card button', '#suggestions button']) {
        const buttons = page.locator(selector);
        assert.equal(await buttons.count(),3);
        for (let i=0;i<await buttons.count();i++) {
          await buttons.nth(i).click();
          const message = await page.locator('#message').inputValue();
          assert.equal(message.includes('Город отправления:'),Boolean(origin));
          if (origin) assert.ok(message.startsWith('Город отправления: '+origin+'. '));
          assert.ok(!message.includes('Москв'));
          if (selector.startsWith('.inspiration')) assert.ok(message.includes(['В Сочи,','В Казань','В Санкт-Петербург'][i]));
        }
      }
    }
    await page.evaluate(() => {state.trip_spec.destination='Сочи';state.revision++;render();});
    assert.equal(await page.locator('.inspiration').count(),0);
    assert.match(await page.locator('#results').innerText(),/Уточним одну деталь/);
    await page.evaluate(() => {state.trip_spec={origin:'Казань',travel_setting:'nature'};render();});
    assert.equal(await page.locator('.inspiration').count(),0);
    assert.deepEqual(errors,[]);
    console.log('PASS: inspiration stays during origin save, repeated edits and reload; destination and nature requests still show search details.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});

// Uses the real provider response saved by the destination-coverage smoke run.
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
(async () => {
  const browser = await chromium.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}}), errors = [], messages = [];
    page.on('pageerror', e => errors.push(e.message));
    let snapshot = JSON.parse(fs.readFileSync(path.join(root, '.runtime/destination-coverage/live-turn.json')));
    await page.route('**/api/runtime/status', route => route.fulfill({json: {ready: true}}));
    await page.route('**/api/sessions/**', async route => {
      if (route.request().url().endsWith('/turns')) {
        messages.push(route.request().postDataJSON().message);
        snapshot = {...snapshot, revision: snapshot.revision + 1, status: 'needs_input', hotel_options: [],
          trip_spec: {...snapshot.trip_spec, include_transport: false, budget_scope: 'hotel', budget: null},
          questions: ['Какой бюджет на проживание за весь отдых?'], assistant_message: 'Какой бюджет на проживание за весь отдых?'};
      }
      await route.fulfill({json: snapshot});
    });
    await page.route('http://127.0.0.1:18080/**', route => {
      const file = path.join(root, 'backend/core/web', new URL(route.request().url()).pathname);
      return fs.existsSync(file) && fs.statSync(file).isFile() ? route.fulfill({path: file}) : route.fallback();
    });
    await page.goto('http://127.0.0.1:18080/plan.html');
    await page.locator('.hotel-card').first().waitFor();
    assert.equal(await page.locator('.hotel-card').count(), 3);
    assert.match(await page.locator('.hotel-card').first().innerText(), /только проживание/i);
    assert.doesNotMatch(await page.locator('.hotel-card').first().innerText(), /за всю поездку/);
    await page.getByText('Сравнить варианты', {exact: true}).click();
    assert.match(await page.locator('.trip-comparison').innerText(), /Дорога и трансферы не рассчитаны/);
    await page.getByRole('button', {name: 'Посмотреть отель', exact: true}).first().click();
    await page.getByRole('button', {name: 'Подобрать только отель', exact: true}).waitFor();
    assert.equal(await page.getByRole('button', {name: 'Перейти к оформлению', exact: true}).count(), 0);
    await page.screenshot({path: path.join(root, '.runtime/destination-coverage/hotel-desktop.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.getByRole('button', {name: 'Подобрать только отель', exact: true}).click();
    await page.waitForFunction(() => !working && state.trip_spec.budget_scope === 'hotel');
    assert.equal(messages[0], 'только отель, без дороги');
    await page.evaluate(() => editRegion());
    await page.getByRole('textbox', {name: 'Город или регион', exact: true}).fill('Крым');
    await page.getByRole('textbox', {name: 'Страна', exact: true}).fill('Россия');
    await page.screenshot({path: path.join(root, '.runtime/destination-coverage/region-mobile.png')});
    await page.getByRole('button', {name: 'Обновить направление', exact: true}).click();
    await page.waitForFunction(() => !working);
    assert.equal(messages[1], 'Ищем отель: Крым, страна Россия. Остальные условия сохрани.');
    await page.evaluate(() => {
      state.selection = {destination_suggestions: [{name: 'Казань', country: 'Россия'}]};
      state.questions = ['Какое направление выбрать?']; render();
    });
    await page.getByRole('button', {name: 'Диалог', exact: true}).click();
    await page.locator('#suggestions').getByRole('button', {name: 'Казань', exact: true}).click();
    assert.match(await page.locator('#message').inputValue(), /Ищем отель: Казань, страна Россия/);
    assert.deepEqual(errors, []);
    console.log('PASS: real Yalta hotels, partial cost, no checkout, mobile layout, unrestricted region input, provider alternatives');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exit(1);});

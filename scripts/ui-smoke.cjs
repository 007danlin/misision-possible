// Real HTTP Core → Python agent → configured model. No mocked model responses.
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
process.chdir(root);
const { chromium } = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
const output = '.runtime/screenshots/ostrovok';
fs.mkdirSync(output, {recursive: true});
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 960}});
    page.setDefaultTimeout(Number(process.env.TRIP_SMOKE_TIMEOUT_MS || 180000));
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const base = process.env.TRIP_SMOKE_URL || 'http://127.0.0.1:18080/plan.html?mode=demo';
    const snapshot = () => page.evaluate(async () => (await fetch('/api/sessions/' + localStorage.getItem('odin-session'))).json());
    await page.goto(base); await page.locator('.bubble.assistant').waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({path: output + '/01-start.png'});
    await page.getByRole('button', {name: 'Море на двоих', exact: true}).click();
    await page.locator('#send').click();
    await page.getByRole('button', {name: 'Выбрать поездку', exact: true}).first().waitFor();
    const initial = await snapshot();
    assert.equal(initial.status, 'choosing'); assert.equal(initial.options.length, 3);
    assert.ok(initial.telemetry.model_calls > 0, 'The request must call the configured model');
    assert.ok(initial.telemetry.model, 'Missing model identity');
    assert.equal(await page.locator('.card[data-plan-id]').count(), 3);
    assert.ok(await page.locator('.card img').evaluateAll(imgs => imgs.every(x => x.complete && x.naturalWidth > 0)));
    await page.screenshot({path: output + '/02-options.png'});
    const first = page.locator('.card').filter({has: page.getByRole('heading', {name: 'Вариант A', exact: true})});
    await first.getByRole('button', {name: 'Подробнее о поездке'}).click();
    assert.equal((await snapshot()).revision, initial.revision, 'Opening details must not select or mutate a plan');
    await page.getByRole('button', {name: 'Выбрать поездку', exact: true}).click();
    await page.getByRole('button', {name: 'Подтвердить поездку'}).waitFor();
    assert.equal((await snapshot()).selected_plan.total.amount_minor, 10900000);
    await page.screenshot({path: output + '/03-selected.png'});
    await page.locator('#message').fill('Теперь максимум 100 тысяч, остальное оставь');
    await page.locator('#send').click();
    await page.getByRole('button', {name: 'Принять изменение'}).waitFor();
    const preview = await snapshot();
    assert.equal(preview.change_preview.price_delta, -1200000);
    assert.deepEqual(preview.trip_spec.dates, initial.trip_spec.dates);
    assert.equal(await page.getByRole('button', {name: 'Подтвердить поездку'}).count(), 0);
    assert.ok((await page.locator('.delta').innerText()).includes('12'));
    assert.ok((await page.locator('.terms-note').innerText()).includes('Невозвратный'));
    await page.screenshot({path: output + '/04-budget-change.png'});
    // Lose the response AFTER Core commits; retry must replay the same operation once.
    let dropped = false; const attempts = [];
    await page.route('**/api/sessions/*/actions', async route => {
      const data = route.request().postDataJSON();
      if (data.type === 'accept_change') {
        attempts.push(data.idempotency_key);
        if (!dropped) { dropped = true; await route.fetch(); await route.abort('failed'); return; }
      }
      await route.continue();
    });
    await page.getByRole('button', {name: 'Принять изменение'}).click();
    await page.locator('#retry').waitFor();
    const committed = await snapshot();
    assert.equal(committed.revision, preview.revision + 1);
    await page.locator('#retry').click();
    await page.getByRole('button', {name: 'Подтвердить поездку'}).waitFor();
    const accepted = await snapshot();
    assert.equal(accepted.revision, committed.revision, 'Retry must not create another revision');
    assert.equal(attempts.length, 2); assert.equal(attempts[0], attempts[1]);
    assert.equal(accepted.selected_plan.total.amount_minor, 9700000);
    await page.getByRole('button', {name: 'Подтвердить поездку'}).click();
    await page.getByRole('heading', {name: 'Поездка оформлена — в демо'}).waitFor();
    const booked = await snapshot();
    await page.reload(); await page.getByRole('heading', {name: 'Поездка оформлена — в демо'}).waitFor();
    assert.equal((await snapshot()).booking.demo_booking_id, booked.booking.demo_booking_id);
    assert.ok((await page.locator('#chat').innerText()).includes('Теперь максимум 100 тысяч'));
    await page.screenshot({path: output + '/05-booked.png'});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.getByRole('button', {name: 'Диалог', exact: true}).click();
    assert.ok(await page.locator('#message').isVisible());
    await page.getByRole('button', {name: /^Варианты/}).click();
    assert.ok(await page.getByRole('heading', {name: 'Поездка оформлена — в демо'}).isVisible());
    await page.screenshot({path: output + '/06-mobile.png'});
    assert.deepEqual(errors, []);
    const report = {passed: true, model: initial.telemetry.model, provider: initial.telemetry.provider, first_turn_ms: initial.telemetry.total_ms, change_turn_ms: preview.telemetry.total_ms, cards: initial.options.length, price_before_minor: 10900000, price_after_minor: 9700000, idempotency_recovery: true, restored_booking: booked.booking.demo_booking_id, mobile_width: 390};
    fs.writeFileSync(output + '/report.json', JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exit(1);});

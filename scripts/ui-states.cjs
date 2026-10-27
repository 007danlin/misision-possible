// Presentation/contract checks using saved snapshots. This does NOT evaluate Qwen.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
const fixtures = name => JSON.parse(fs.readFileSync(path.join(root, 'docs/examples/session-' + name + '.json')));
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
  const passed = [];
  const screenshots = path.join(root, '.runtime/screenshots/ostrovok/states');
  fs.mkdirSync(screenshots, {recursive: true});
  try {
    for (const name of ['needs-input', 'choosing-destinations', 'choosing-plans', 'ready', 'change-preview', 'no-solution', 'error', 'booked-demo']) {
      const snapshot = fixtures(name), page = await browser.newPage({viewport: {width: 1440, height: 960}});
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.route('**/api/sessions/**', route => route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(snapshot)}));
      await page.goto(process.env.TRIP_SMOKE_URL || 'http://127.0.0.1:18080/plan.html?mode=demo');
      await page.locator('.bubble.assistant').waitFor();
      await page.evaluate(() => document.fonts.ready);
      assert.ok((await page.locator('#results').innerText()).length > 0, name + ' is blank');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, name + ' desktop overflow');
      if (name === 'choosing-plans') {
        assert.equal(await page.locator('.card[data-plan-id]').count(), 3);
        await page.getByRole('button', {name: 'Подробнее о поездке'}).first().click();
        assert.ok((await page.locator('.breakdown').innerText()).replace(/\s/g, ' ').includes('52 000'));
        await page.getByText('Проверки и источники', {exact: true}).click();
        assert.ok((await page.locator('.checks').innerText()).includes('Учебный каталог'));
        await page.getByRole('button', {name: '← К подборке'}).click();
      }
      if (name === 'no-solution' || name === 'error' || name === 'change-preview') assert.equal(await page.getByRole('button', {name: 'Подтвердить поездку'}).count(), 0, name + ' must not allow checkout');
      if (name === 'no-solution') {
        assert.ok((await page.locator('#results').innerText()).includes('Подходящий вариант пока не найден'));
        assert.equal(await page.getByRole('button', {name: 'Выбрать поездку', exact: true}).count(), 0);
      }
      if (name === 'change-preview') assert.ok(await page.getByRole('button', {name: 'Принять изменение'}).isVisible());
      if (['choosing-plans', 'ready', 'change-preview'].includes(name)) await page.screenshot({path: path.join(screenshots, name + '.png')});
      await page.setViewportSize({width: 390, height: 844});
      await page.getByRole('button', {name: /^Варианты/}).click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, name + ' mobile overflow');
      await page.getByRole('button', {name: 'Диалог', exact: true}).click();
      await page.locator('#message').waitFor({state:'visible'});
      const bounds = await page.locator('#message').boundingBox();
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 844, name + ' composer off-screen');
      assert.deepEqual(errors, [], name + ' JS errors');
      passed.push(name); await page.close();
    }
    console.log('PASS mocked UI contract states: ' + passed.join(', '));
  } finally { await browser.close(); }
})().catch(e => {console.error(e);process.exit(1)});

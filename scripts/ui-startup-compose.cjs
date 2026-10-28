// Opt-in real restart of the root Compose stack. Keeps all volumes and user trips.
// Build app/model first. Optional STARTUP_BROWSER_STATE checks an existing booked trip.
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const {execFile} = require('child_process'), {promisify} = require('util');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
const run = promisify(execFile), sleep = ms => new Promise(r => setTimeout(r, ms));
const base = 'http://127.0.0.1:8080';
const out = process.env.STARTUP_TEST_OUTPUT || path.join(root, '.runtime/screenshots/startup-compose');
fs.mkdirSync(out, {recursive: true});
(async () => {
  const browser = await chromium.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
  const context = await browser.newContext({viewport: {width: 390, height: 844}, storageState: process.env.STARTUP_BROWSER_STATE || undefined, acceptDownloads: true});
  const page = await context.newPage(), report = {mocked: false, phases: [], errors: [], checks: []};
  page.on('pageerror', e => report.errors.push(e.message));
  async function snapshot() {
    return page.evaluate(async () => {
      const id = localStorage.getItem('oplan-hotels-session');
      if (!id) return null;
      const response = await fetch('/api/sessions/' + id);
      if (!response.ok) throw Error('Saved session unavailable: ' + response.status);
      return response.json();
    });
  }
  try {
    await page.goto(base + '/plan.html');
    await page.locator('#send').waitFor({state: 'attached'});
    const before = await snapshot();
    if (process.env.STARTUP_BROWSER_STATE) assert.ok(before?.hotel_booking, 'supply a booked test session');
    const started = Date.now();
    await run('docker', ['compose', 'up', '-d', '--no-build', '--force-recreate', 'model', 'agent', 'app'], {cwd: root, timeout: 120000});
    for (let i = 0; i < 60; i++) {
      try { await page.goto(base + '/plan.html', {timeout: 5000}); break; }
      catch (e) { if (i === 59) throw e; await sleep(500); }
    }
    await page.getByRole('heading', {name: 'Готовим помощника к работе'}).waitFor();
    await page.getByText(/Модель скачана: 100% · .* ГБ/).waitFor();
    assert.equal(await page.locator('progress').getAttribute('value'), null, 'loading is not a fabricated percent');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({path: path.join(out, 'loading-mobile.png')});
    await page.reload();
    await page.getByText(/Модель скачана: 100% · .* ГБ/).waitFor();
    report.checks.push('real cached model size in GB', 'mobile has no overflow', 'reload during startup');
    const seen = new Set();
    while (Date.now() - started < 360000) {
      const response = await context.request.get(base + '/api/runtime/status');
      const status = await response.json();
      if (!seen.has(status.phase)) {
        seen.add(status.phase);
        report.phases.push({seconds: (Date.now() - started) / 1000, ...status});
      }
      if (status.ready) break;
      await sleep(1000);
    }
    assert.ok(seen.has('ready'), 'real model and agent became ready');
    await page.locator('#send').waitFor({state: 'attached', timeout: 15000});
    assert.equal(await page.title(), 'О!План — ваша поездка с Островком');
    report.ready_seconds = (Date.now() - started) / 1000;
    report.checks.push('automatic entry into real application');
    for (let i = 0; i < 2; i++) {
      await page.reload();
      await page.locator('#send').waitFor({state: 'attached'});
      assert.equal(await page.getByRole('heading', {name: 'Готовим помощника к работе'}).count(), 0);
      if (before?.hotel_booking) {
        await page.getByRole('heading', {name: 'Поездка оформлена', exact: true}).waitFor();
        const after = await snapshot();
        assert.equal(after.hotel_booking.id, before.hotel_booking.id);
        assert.deepEqual(after.hotel_booking.hotel.journey, before.hotel_booking.hotel.journey);
      }
    }
    report.checks.push('two reloads after readiness');
    if (before?.hotel_booking) {
      report.checks.push('saved booking, route and total survive container restart and reload');
      const download = page.waitForEvent('download');
      await page.getByRole('button', {name: 'Скачать план поездки · PDF', exact: true}).click();
      const pdf = path.join(out, 'saved-trip.pdf');
      await (await download).saveAs(pdf);
      assert.equal(fs.readFileSync(pdf).subarray(0, 5).toString(), '%PDF-');
      report.checks.push('PDF after restart');
    }
    const fresh = await context.newPage();
    await fresh.goto(base + '/plan.html');
    await fresh.locator('#send').waitFor({state: 'attached'});
    report.checks.push('direct entry in another tab');
    await page.screenshot({path: path.join(out, 'ready-mobile.png')});
    assert.deepEqual(report.errors, []);
    report.passed = true;
    console.log(JSON.stringify(report, null, 2));
  } catch (e) {
    report.failure = String(e);
    throw e;
  } finally {
    fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });

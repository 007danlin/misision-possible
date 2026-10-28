// Real browser -> Core -> agent -> Qwen -> public sources. No routed responses.
// RANDOM_SEED reproduces wording/order; CASES selects comma-separated scenarios.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const {chromium} = require(path.join(root, '.runtime/browser/node_modules/playwright-core'));
const base = process.env.TRIP_SMOKE_URL || 'http://127.0.0.1:8080';
const seed = Number(process.env.RANDOM_SEED || Date.now()) >>> 0;
let randomState = seed;
const random = () => ((randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0) / 4294967296);
const pick = xs => xs[Math.floor(random() * xs.length)];
const out = path.join(root, '.runtime/random-journeys', String(seed));
fs.mkdirSync(out, {recursive: true});
const report = {seed, base, started: new Date().toISOString(), cases: []};
const save = () => fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
const cases = [
  {id: 'omsk', run: async t => {
    let s = await t.turn('Хочу на природу, в лес. Дикая природа.');
    assert.match(s.assistant_message, /Из какого города/);
    s = await t.turn('Отправляемся из Омска');
    assert.equal(s.trip_spec.origin, 'Омск');
    assert.equal(s.trip_spec.travel_setting, 'forest');
    assert.ok(s.destination_options.length, 'Forest directions must arrive without a retry');
    assert.ok(s.destination_options.every(d => ['karelia','altai','seliger','sochi_nature'].includes(d.id)));
    await t.reload(s);
    const choice = s.destination_options[0];
    s = await t.clickTurn('Выбрать ' + choice.name);
    assert.equal(s.trip_spec.destination, choice.destination);
    assert.equal(s.trip_spec.origin, 'Омск');
    assert.equal(s.trip_spec.travel_setting, 'forest');
  }},
  {id: 'forest_exclusion', run: async t => {
    let s = await t.turn(pick([
      'Хочу в лес, к озеру, подальше от города. Только не Сочи.',
      'Мечтаю отдохнуть среди лесов и озёр, подальше от города. Сочи не предлагай.',
    ]));
    if (!s.trip_spec.origin) s = await t.turn(pick(['Из Москвы', 'Отправляемся из Москвы']));
    assert.equal(s.trip_spec.origin, 'Москва');
    assert.ok(s.destination_options.length, 'Expected nature options');
    assert.ok(s.destination_options.every(d => !['sochi','sochi_nature'].includes(d.id)), 'Explicit exclusion lost');
    assert.ok(s.destination_options.every(d => ['karelia','altai','seliger'].includes(d.id)), 'Urban option for wilderness');
    await t.reload(s);
  }},
  {id: 'sea', run: async t => {
    let s = await t.turn(pick(['Хочу к морю', 'Хочу на море', 'к морю']));
    assert.match(s.assistant_message, /Из какого города/);
    s = await t.turn(pick(['Из Казани', 'Отправляемся из Казани']));
    assert.equal(s.trip_spec.origin, 'Казань');
    assert.equal(s.trip_spec.travel_setting, 'sea');
    assert.ok(s.destination_options.length, 'Expected sea options');
    assert.ok(s.destination_options.every(d => ['sochi','gelendzhik','anapa'].includes(d.id)));
    const choice = s.destination_options.at(-1);
    s = await t.turn(choice.name);
    assert.equal(s.trip_spec.destination, choice.destination);
    s = await t.turn(pick(['трое взрослых', '3 взрослых']));
    assert.equal(s.trip_spec.travellers.adults, 3);
    assert.equal(s.trip_spec.destination, choice.destination);
    await t.reload(s);
  }},
  {id: 'nearby', run: async t => {
    const s = await t.turn(pick([
      'Из Москвы хочу в лес к озеру, недалеко, на машине на выходные.',
      'Мы из Москвы. Хочется леса и озера поблизости на выходные, поедем на своей машине.',
    ]));
    assert.equal(s.trip_spec.origin, 'Москва');
    assert.ok(s.destination_options.length || s.questions.length);
    if (s.destination_options.length) {
      assert.ok(s.destination_options.every(d => ['seliger','karelia'].includes(d.id)), 'Distant wilderness offered for a nearby weekend');
      assert.match(s.assistant_message + ' ' + s.destination_options.map(d=>d.caveat).join(' '), /времени|по прямой|дорог/);
    }
    await t.reload(s);
  }},
  {id: 'culture', run: async t => {
    let s = await t.turn(pick([
      'Хочу посмотреть дворцы и погулять вдоль каналов. Море и пляжи не нужны.',
      'Интересуют музеи, дворцы и каналы, пляжный отдых не нужен.',
    ]));
    if (!s.trip_spec.origin) s = await t.turn('Из Казани');
    assert.equal(s.trip_spec.origin, 'Казань');
    assert.ok(s.destination_options.some(d=>d.id==='petersburg'), 'Palaces and canals should include Petersburg');
    assert.ok(s.destination_options.every(d=>!['sochi','gelendzhik','anapa'].includes(d.id)));
    await t.reload(s);
  }},
  {id: 'hotel_edits', run: async t => {
    let s = await t.turn(pick([
      'Нужен только отель в Казани с 10 по 15 ноября 2026, двое взрослых, 60000 рублей за всё проживание, с завтраком.',
      'Ищем только отель в Казани: 10–15 ноября 2026, два взрослых, до 60 тысяч рублей за проживание. Нужен завтрак.',
    ]));
    assert.equal(s.trip_spec.destination, 'Казань');
    assert.equal(s.trip_spec.include_transport, false);
    assert.equal(s.trip_spec.hotel_preferences.breakfast, true);
    assert.equal(s.trip_spec.travellers.adults, 2);
    assert.equal(s.trip_spec.dates.start, '2026-11-10');
    assert.equal(s.trip_spec.dates.end, '2026-11-15');
    assert.equal(s.status, 'choosing', s.assistant_message);
    assert.ok(s.hotel_options.length);
    s = await t.turn('Бюджет на отель 80000 рублей');
    assert.equal(s.trip_spec.budget.amount_minor, 8000000);
    assert.equal(s.trip_spec.hotel_preferences.breakfast, true);
    assert.equal(s.trip_spec.destination, 'Казань');
    s = await t.turn('Добавь ребёнка 7 лет');
    assert.deepEqual(s.trip_spec.travellers.children, [7]);
    assert.equal(s.trip_spec.travellers.adults, 2);
    s = await t.turn(pick(['Завтрак больше не обязателен', 'Завтрак не важен']));
    assert.equal(s.trip_spec.hotel_preferences.breakfast, null);
    assert.deepEqual(s.trip_spec.travellers.children, [7]);
    assert.equal(s.trip_spec.budget.amount_minor, 8000000);
    assert.equal(s.trip_spec.dates.end, '2026-11-15');
    assert.equal(s.status, 'choosing', s.assistant_message);
    s = await t.turn('Почему второй отель?');
    assert.equal(s.trip_spec.destination, 'Казань');
    assert.ok(s.hotel_options.length);
    await t.reload(s);
    await t.page.locator('.hotel-name-button').first().click();
    const button = t.page.getByRole('button', {name: 'Перейти к оформлению', exact: true});
    await button.waitFor();
    s = await t.action('Перейти к оформлению');
    assert.equal(s.status, 'hotel_checkout');
    await t.page.locator('#guest-name').fill('Проверочный Гость');
    await t.page.locator('#booking-consent').check();
    s = await t.action('Подтвердить поездку');
    assert.equal(s.status, 'hotel_booked');
    await t.reload(s);
    const pending = t.page.waitForEvent('download');
    await t.page.getByRole('button', {name: 'Скачать план поездки · PDF', exact: true}).click();
    const download = await pending;
    await download.saveAs(path.join(out, 'hotel-plan.pdf'));
    assert.ok(fs.statSync(path.join(out, 'hotel-plan.pdf')).size > 1000);
  }},
  {id: 'unknown_place', run: async t => {
    let s = await t.turn('Нужен только отель: Несуществующийгород Зюзю, 5 ночей для двоих, бюджет 50000 рублей на проживание.');
    assert.equal(s.hotel_options.length, 0);
    assert.ok(s.questions.length || /не удалось|не наш|уточн|провер/i.test(s.assistant_message));
    assert.ok(!s.trip_spec.destination || /несуществующийгород|зюзю/i.test(s.trip_spec.destination), 'Unknown destination replaced silently');
    await t.reload(s);
  }},
  {id: 'clarification', run: async t => {
    let s = await t.turn(pick(['Привет!', 'Здравствуйте']));
    assert.equal(s.hotel_options.length, 0);
    s = await t.turn('Хочу только отель в Сочи, двое взрослых, бюджет 50000 рублей на проживание.');
    assert.equal(s.trip_spec.destination, 'Сочи');
    assert.equal(s.trip_spec.include_transport, false);
    assert.ok(s.questions.length);
    s = await t.turn('10–15 ноября 2026');
    assert.equal(s.trip_spec.dates.start, '2026-11-10');
    assert.equal(s.trip_spec.dates.end, '2026-11-15');
    s = await t.turn('3 взрослых');
    assert.equal(s.trip_spec.travellers.adults, 3);
    assert.equal(s.trip_spec.destination, 'Сочи');
    assert.equal(s.trip_spec.budget.amount_minor, 5000000);
    await t.reload(s);
  }},
];

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
  try {
    const selected = process.env.CASES?.split(',');
    for (const scenario of cases.filter(c => !selected || selected.includes(c.id))) {
      const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
      const page = await context.newPage(); page.setDefaultTimeout(100000);
      const row = {id: scenario.id, steps: [], errors: [], passed: false}; report.cases.push(row); save();
      page.on('pageerror', e => row.errors.push(e.message));
      const capture = async (message, trigger, suffix) => {
        const pending = page.waitForResponse(r => r.url().endsWith(suffix) && r.request().method() === 'POST');
        const start = Date.now(); await trigger(); const response = await pending, s = await response.json();
        const step = {message, seconds: (Date.now()-start)/1000, http: response.status(), snapshot: s};
        row.steps.push(step); save();
        console.log(JSON.stringify({case: scenario.id, message, seconds: step.seconds, status: s.status, answer: s.assistant_message, calls: s.telemetry?.model_calls}));
        assert.equal(response.status(), 200, JSON.stringify(s));
        assert.notEqual(s.status, 'error', s.assistant_message);
        assert.doesNotMatch(s.assistant_message || '', /подбор направлений не завершился/);
        await page.waitForFunction(() => !working);
        return s;
      };
      const t = {page,
        turn: message => capture(message, async () => {await page.locator('#message').fill(message); await page.locator('#send').click();}, '/turns'),
        clickTurn: label => capture(label, () => page.getByRole('button', {name: label, exact: true}).first().click(), '/turns'),
        action: label => capture(label, () => page.getByRole('button', {name: label, exact: true}).first().click(), '/actions'),
        reload: async expected => {
          await page.reload(); await page.locator('#chat .assistant').first().waitFor();
          const actual = await page.evaluate(async () => (await fetch('/api/sessions/' + localStorage.getItem('oplan-hotels-session'))).json());
          assert.deepEqual(actual.trip_spec, expected.trip_spec);
          assert.equal(actual.status, expected.status);
        },
      };
      try {
        await page.goto(base.replace(/\/$/, '') + '/plan.html');
        await page.locator('#chat .assistant').first().waitFor();
        await scenario.run(t);
        await page.screenshot({path: path.join(out, scenario.id+'-desktop.png'), fullPage: true});
        await page.setViewportSize({width:390,height:844});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Mobile overflow');
        await page.screenshot({path: path.join(out, scenario.id+'-mobile.png'), fullPage: true});
        assert.deepEqual(row.errors, []);
        row.passed = true;
      } catch (error) {
        row.failure = String(error); console.error(scenario.id, error);
        await page.screenshot({path:path.join(out, scenario.id+'-failure.png'),fullPage:true}).catch(()=>{});
      } finally {save(); await context.close();}
    }
  } finally {await browser.close();}
  report.finished = new Date().toISOString(); save();
  console.log(JSON.stringify({seed, passed:report.cases.filter(c=>c.passed).length, total:report.cases.length, report:path.join(out,'report.json')}));
  if(report.cases.some(c=>!c.passed)) process.exitCode = 1;
})().catch(e=>{console.error(e);process.exitCode=1;});

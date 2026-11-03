// Run against a local production build; all API responses are mocked.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { performance } = require('node:perf_hooks');
const origin = process.env.VPO_QA_UI_URL || 'http://127.0.0.1:3103';
assert(['127.0.0.1', 'localhost'].includes(new URL(origin).hostname));
const output = path.join(require('node:os').tmpdir(), 'royalty-rankings-qa');
fs.mkdirSync(output, { recursive: true });
const rank = (name, count) => Array.from({ length: count }, (_, i) => ({
  name: `${name} ${i + 1}`, identity_key: `ISRC:TEST${i}`,
  amount_usd: count - i, units: 1000, rows: 1, percentage: 1,
}));
const frame = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));

async function check(browser, viewport, cpu) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: cpu > 1 ? 2 : 1, hasTouch: viewport.width < 500 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
  const errors = [], queries = [], metrics = { width: viewport.width, cpu };
  page.on('pageerror', error => errors.push(error.message));
  let count = 2410, servedAt, detailQuery;
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    let body = {};
    if (url.pathname === '/api/session') body = { authenticated: true, user: { username: 'qa', role: 'admin', canEdit: true } };
    if (url.pathname === '/api/royalties-dashboard/track') { detailQuery = url; body = { tracks: [], restricted: false }; }
    if (url.pathname === '/api/royalties-dashboard') {
      queries.push(url);
      const totals = { amount_usd: 1000, units: 1000, titles: count, artists: Math.min(count, 1470), sources: 1, accounts: 1, first_month: '2026-09', last_month: '2026-09' };
      body = { totals, period_months: ['2026-09'],
        report_personalization: { enabled: false }, catalog_refresh: { status: 'ready' },
        monthly: Array.from({ length: 6 }, (_, i) => ({ month: `2026-0${i + 4}`, amount_usd: 1000, units: 1000 })),
        matrix: [{ source: 'fuga', account: 'QA', months: { '2026-09': 1000 }, amount_usd: 1000, titles: count }],
        rankings: { title: rank('Tema', count), artist: rank('Artista', Math.min(count, 1470)), dsp: rank('Plataforma', 10), monetization: [], content_origin: [], territory: rank('Territorio', 10), label: rank('Sello', 10) },
        youtube: { totals, title: [], monetization: [], content_origin: [], territory: [] },
        options: { sources: ['fuga'], accounts: ['QA'], source_accounts: [{ source: 'fuga', account: 'QA' }], first_month: '2026-01', last_month: '2026-09' } };
      servedAt = performance.now();
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.goto(origin);
  const navigation = page.getByRole('button', { name: 'Dashboard Regalías', exact: true }).first();
  await navigation.waitFor({ state: 'attached' });
  const menu = page.getByRole('button', { name: 'Abrir menú', exact: true });
  if (await menu.isVisible()) await menu.click();
  await navigation.click();
  const title = page.getByRole('region', { name: 'Ingresos por tema', exact: true });
  const artist = page.getByRole('region', { name: 'Ingresos por artista', exact: true });
  await title.getByRole('button', { name: 'Tema 1', exact: true }).waitFor();
  await frame(page);
  metrics.mount_ms = Math.round(performance.now() - servedAt);
  assert.equal(queries.at(-1).searchParams.get('full_catalog_rankings'), 'true');
  for (const list of [title, artist]) assert(await list.getByRole('listitem').count() <= 15);
  metrics.dom_nodes = await page.evaluate(() => document.getElementsByTagName('*').length);
  assert(metrics.dom_nodes < 2000, 'Offscreen rankings must not populate the document');
  for (const [list, last] of [[title, 2410], [artist, 1470]]) {
    await list.scrollIntoViewIfNeeded();
    const heading = list.locator('..').getByRole('heading');
    const before = (await heading.boundingBox()).y;
    await list.press('End');
    await list.locator(`[aria-posinset="${last}"]`).waitFor();
    await frame(page);
    assert(Math.abs((await heading.boundingBox()).y - before) < 2);
    assert.equal(await list.locator(`[aria-posinset="${last}"]`).getAttribute('aria-setsize'), String(last));
    assert(await list.getByRole('listitem').count() <= 15);
    if (list === title) {
      const detailResponse = page.waitForResponse(response => response.url().includes('/api/royalties-dashboard/track?') && response.status() === 200);
      await list.getByRole('button', { name: `Tema ${last}`, exact: true }).click();
      const close = page.getByRole('dialog').getByRole('button', { name: 'Cerrar detalle', exact: true });
      await close.waitFor();
      await detailResponse;
      assert.equal(detailQuery.searchParams.get('track_key'), 'ISRC:TEST2409');
      assert.equal(detailQuery.searchParams.get('track_title'), 'Tema 2410');
      await close.click();
    }
    await list.press('Home');
    await list.locator('[aria-posinset="1"]').waitFor();
  }
  // Native focus scrolling must mount following rows rather than skipping them.
  await title.focus();
  for (let i = 1; i <= 20; i++) {
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.textContent), `Tema ${i}`);
  }
  await artist.press('End');
  await artist.locator('[aria-posinset="1470"]').waitFor();
  await title.press('Home');
  await title.locator('[aria-posinset="1"]').waitFor();
  assert(await artist.evaluate(el => el.scrollTop > 0), 'Each list scrolls independently');
  await artist.press('Home');
  await title.scrollIntoViewIfNeeded();
  const listBox = await title.boundingBox();
  if (viewport.width < 500) {
    const x = listBox.x + listBox.width / 2, y = listBox.y + listBox.height - 30;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
    for (let step = 1; step <= 12; step++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - step * 15 }] });
      await page.waitForTimeout(16);
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  } else {
    await cdp.send('Input.synthesizeScrollGesture', { x: listBox.x + listBox.width / 2, y: listBox.y + listBox.height / 2,
      yDistance: -200, speed: 500, gestureSourceType: 'mouse' });
  }
  await page.waitForFunction(() => document.querySelector('[role="region"][aria-label="Ingresos por tema"]').scrollTop > 0);
  assert.equal(await artist.evaluate(el => el.scrollTop), 0);
  await title.press('Home');
  await title.locator('[aria-posinset="1"]').waitFor();
  await page.evaluate(() => {
    const section = document.querySelector('[role="region"][aria-label="Ingresos por tema"]').parentElement;
    const header = document.querySelector('.vpo-app-header').getBoundingClientRect();
    scrollTo(0, Math.max(0, section.getBoundingClientRect().top + scrollY - header.height - 40));
  });
  await title.locator('..').screenshot({ path: path.join(output, `rankings-${viewport.width}.png`) });

  await page.evaluate(() => scrollTo(0, 0)); await frame(page);
  await page.evaluate(() => {
    window.__frames = []; window.__watch = true; let last;
    function tick(t) { if (last) window.__frames.push(t - last); last = t; if (window.__watch) requestAnimationFrame(tick); }
    requestAnimationFrame(tick);
  });
  const x = viewport.width < 500 ? 12 : 285;
  const distance = Math.min(900, await page.evaluate(() => document.documentElement.scrollHeight - innerHeight - 5));
  assert(distance > 100);
  await cdp.send('Input.synthesizeScrollGesture', { x, y: 500, yDistance: -distance, speed: 500, gestureSourceType: 'mouse' });
  assert(await page.evaluate(() => scrollY > 100), 'The whole page must move outside ranking panels');
  await cdp.send('Input.synthesizeScrollGesture', { x, y: 500, yDistance: distance, speed: 500, gestureSourceType: 'mouse' });
  const frames = await page.evaluate(() => { window.__watch = false; return window.__frames; });
  frames.sort((a, b) => a - b);
  metrics.page_scroll_p95_ms = Math.round(frames[Math.floor(frames.length * .95)]);
  metrics.page_scroll_max_ms = Math.round(Math.max(...frames));
  assert(metrics.page_scroll_p95_ms < 35, 'Whole-page scrolling must retain a regular frame cadence');
  assert(metrics.page_scroll_max_ms < 150, 'Whole-page scrolling must not freeze');
  assert.equal(await title.evaluate(el => el.scrollTop), 0);
  assert.equal(await artist.evaluate(el => el.scrollTop), 0);

  const start = performance.now();
  await page.locator('#royalties_dashboard_keyword').pressSequentially('analisis');
  await frame(page);
  metrics.typing_8_chars_ms = Math.round(performance.now() - start);
  assert(metrics.typing_8_chars_ms < (cpu > 1 ? 2500 : 1000));
  // Data replacement after reaching the end must reset the virtual window.
  await title.press('End'); await title.locator('[aria-posinset="2410"]').waitFor();
  count = 2;
  await page.getByRole('button', { name: 'Actualizar dashboard', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[role="region"][aria-label="Ingresos por tema"] [role="listitem"]')?.getAttribute('aria-setsize') === '2');
  assert.equal(await title.getByRole('listitem').count(), 2);
  assert.equal(await title.evaluate(el => el.scrollTop), 0);
  assert(await title.evaluate(el => el.clientHeight === el.scrollHeight));
  count = 0;
  await page.getByRole('button', { name: 'Actualizar dashboard', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('[role="region"][aria-label="Ingresos por tema"] [role="listitem"]'));
  assert.equal(await title.getAttribute('tabindex'), null);
  assert.equal(await title.evaluate(el => el.clientHeight), 0);
  assert.deepEqual(errors, []);
  await page.close();
  console.log(JSON.stringify(metrics));
  return metrics;
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const metrics = [];
    for (const [viewport, cpu] of [[{ width: 1440, height: 1000 }, 1], [{ width: 1440, height: 1000 }, 4], [{ width: 390, height: 844 }, 4]]) {
      metrics.push(await check(browser, viewport, cpu));
    }
    fs.writeFileSync(path.join(output, 'metrics.json'), JSON.stringify(metrics, null, 2));
    console.log('OK: whole-page scroll, complete virtual lists, keyboard traversal, filters, empty lists and performance.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

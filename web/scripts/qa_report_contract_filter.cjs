// Local UI only; every API response is intercepted.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { chromium } = require(process.argv[2]);
const output = process.argv[3];
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
    const errors = [], jobs = [], counts = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      let body = {};
      if (path === '/api/session') body = { authenticated: true, user: { username: 'fixture', role: 'admin', canEdit: true } };
      else if (path === '/api/wml') body = { enabled: false };
      else if (path === '/api/report-options') body = { sources: [], source_accounts: [], excel_contracts_supported: true };
      else if (path === '/api/report-distribution-contracts') body = { items: [
        { number: 10010, label: 'El Caserio', sublabel: 'Los Anormales' },
        { number: 10011, label: 'El Caserio', sublabel: 'Activos' },
        { number: 10012, label: 'El Caserio', sublabel: 'Contrato Terminado' },
      ] };
      else if (path === '/api/report-detail-count') { counts.push(request.postDataJSON()); body = { rows: 2, excel_max_data_rows: 1048575, exceeds_excel_limit: false }; }
      else if (path === '/api/report' && request.method() === 'POST') {
        const params = request.postDataJSON(); jobs.push(params);
        body = { item: { id: jobs.length, status: 'failed', error_message: 'Fixture terminada', output_format: params.output, params } };
      } else if (path === '/api/report') body = { items: [] };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto('http://127.0.0.1:3117', { waitUntil: 'networkidle', timeout: 180000 });
    await page.getByRole('button', { name: /Reporte de regalías/ }).first().click();
    const numbers = page.locator('#royalty_contract_numbers');
    await numbers.waitFor();
    await page.getByRole('button', { name: 'Buscar contratos', exact: true }).click();
    await page.getByLabel('Buscar por número, sello o subsello', { exact: true }).fill('caserio');
    await page.getByRole('button', { name: '10011 El Caserio / Activos', exact: true }).click();
    await page.getByRole('button', { name: '10012 El Caserio / Contrato Terminado', exact: true }).click();
    assert.equal(await numbers.inputValue(), '10011, 10012');
    await page.getByRole('button', { name: 'Quitar contrato 10011', exact: true }).click();
    assert.equal(await numbers.inputValue(), '10012');
    await page.getByRole('button', { name: '10011 El Caserio / Activos', exact: true }).click();
    await page.screenshot({ path: output + '/contracts-desktop.png', fullPage: true });
    await page.getByRole('button', { name: 'Generar Excel', exact: true }).click();
    await page.waitForFunction(() => document.body.innerText.includes('Fixture terminada'));
    assert.deepEqual(jobs[0].distribution_contract_numbers, [10012, 10011]);
    assert.deepEqual(jobs[0].keywords, []);
    await numbers.fill('10011, 10011, 10012,');
    await page.locator('#royalty_keywords').fill('Tomi');
    await page.getByLabel('Incluir todas las filas del detalle').check();
    await page.getByRole('button', { name: 'Generar Excel', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    assert.deepEqual(counts[0].distribution_contract_numbers, [10011, 10012]);
    assert.deepEqual(counts[0].keywords, ['Tomi']);
    await page.getByRole('button', { name: /Cancelar/ }).click();
    await numbers.fill('El Caserio');
    await page.getByRole('button', { name: 'Generar Excel', exact: true }).click();
    assert.equal(jobs.length, 1);
    await page.getByText('Ingresá solo números de contrato, separados por comas.').first().waitFor();
    await numbers.fill('10012');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: output + '/contracts-mobile.png', fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    assert.deepEqual(errors, []);
    console.log('PASS: selector, manual entry, deduplication, contract-only report, keyword intersection, full-count payload, invalid text and mobile layout');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });

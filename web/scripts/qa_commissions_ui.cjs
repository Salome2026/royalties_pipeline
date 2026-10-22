const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.argv[2] || "playwright");

const url = process.argv[3];
const output = process.argv[4];
const legacy = process.argv[5] === "control";
assert.ok(url && output, "Provide Playwright module, URL and isolated evidence directory");
const permission = (access = true) => ({ module_key: "booking_commissions", can_access: access,
  can_edit: true, can_create: true, can_approve: true, can_view_history: true, scope: [], notes: null });
const artists = ["Candu Dominguez", "Gusty DJ", "G Sony"];
const employees = [
  { id: 1, display_name: "Marcelo Kessel", active: true, functions: [], permissions: [permission()] },
  { id: 2, display_name: "Empleado sin acceso", active: true, functions: [], permissions: [permission(false)] },
  { id: 3, display_name: "Empleado inactivo", active: false, functions: [], permissions: [permission()] },
];
const initialRules = artists.map((artist, index) => ({ artist, employee_id: 1, employee_name: "Marcelo Kessel",
  percent: index === 1 ? 5 : 10, base: "commissionable", include_booking_fee_paid_shows: false,
  priority_order: 1, start_month: "2026-07", end_month: null, active: true, notes: "Regla de prueba" }));
const specifications = [
  ["Candu Dominguez", "2026-08", 2, 1000000, 900000, 90000],
  ["Candu Dominguez", "2026-09", 3, 1500000, 1200000, 120000],
  ["Gusty DJ", "2026-09", 2, 2000000, 2000000, 100000],
  ["Gusty DJ", "2026-07", 1, 600000, 600000, 30000],
  ["G Sony", "2026-08", 2, 800000, 700000, 70000],
];
const summary = { generated_at: "2026-10-22T12:00:00Z", months: ["2026-07", "2026-08", "2026-09"],
  items: artists.map(artist => ({ artist, shows: 0, indyana_total: 0, commissionable_total: 0,
    non_commissionable_total: 0, commission_total: 0, indyana_net_total: 0, commission_details: [], notes: [],
    months: Object.fromEntries(specifications.filter(row => row[0] === artist).map(([_, month, shows, total, base, commission]) => [month,
      { shows, indyana_total: total, commissionable_total: base, non_commissionable_total: total - base,
        commission_total: commission, indyana_net_total: total - commission,
        commission_details: [{ employee_id: 1, employee_name: "Marcelo Kessel", artist, month, priority_order: 1,
          percent: artist === "Gusty DJ" ? 5 : 10, base_amount: base, commission_amount: commission,
          show_excludes_general: false, include_booking_fee_paid_shows: false }] }])) })),
  totals: { shows: 10, indyana_total: 5900000, commissionable_total: 5400000, non_commissionable_total: 500000,
    commission_total: 410000, indyana_net_total: 5490000 }, commission_rules: initialRules };

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const results = [];
  try {
    for (const readonly of [false, true]) {
      let rules = structuredClone(initialRules);
      const writes = [], unexpected = [], errors = [];
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const page = await context.newPage();
      page.setDefaultTimeout(30000);
      page.on("pageerror", error => errors.push(String(error)));
      await page.route("**/api/**", async route => {
        const request = route.request(), pathname = new URL(request.url()).pathname;
        const respond = body => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
        if (pathname === "/api/session") return respond({ authenticated: true,
          user: { username: "commission-fixture", role: readonly ? "viewer" : "admin", canEdit: !readonly } });
        if (pathname === "/api/me/permissions") return respond({ permissions: [{ ...permission(), can_edit: !readonly }], modules: [] });
        if (pathname === "/api/employees/commission-options") return respond({ items: employees });
        if (pathname === "/api/booking/artists") return respond({ items: artists });
        if (pathname === "/api/booking/commissions-summary") return respond(summary);
        if (pathname === "/api/booking/commission-rules") {
          if (request.method() === "PUT") {
            assert.equal(readonly, false);
            const payload = request.postDataJSON();
            writes.push(payload);
            rules = payload.rules;
          }
          return respond({ rules });
        }
        unexpected.push({ pathname, method: request.method() });
        return route.fulfill({ status: 403, contentType: "application/json", body: '{"error":"Unconfigured fixture; real request blocked"}' });
      });
      await page.goto(url, { waitUntil: "networkidle", timeout: 180000 });
      await page.getByRole("button", { name: "Comisiones", exact: true }).first().click();
      await page.waitForLoadState("networkidle");
      const save = page.getByRole("button", { name: "Guardar configuracion", exact: true });
      assert.equal(await save.isDisabled(), true);
      assert.equal(await page.locator('#commission_employee option[value="3"]').count(), 0);
      await page.screenshot({ path: path.join(output, `${readonly ? "reader" : "editor"}_empty.png`), fullPage: true });
      await page.locator("#commission_employee").selectOption("1");
      await page.waitForLoadState("networkidle");
      const table = page.locator("table.summary-table");
      assert.equal(await table.locator("tbody tr").count(), 5);
      const financial = await page.locator(".control-dashboard > div").evaluateAll(items => items.map(item => ({
        label: item.querySelector("span").textContent, value: item.querySelector("strong").textContent })));
      const originalRows = await table.locator("tbody tr").allTextContents();
      assert.ok(financial.some(item => item.label === "Comision calculada" && item.value.replace(/\D/g, "") === "410000"));
      await page.screenshot({ path: path.join(output, `${readonly ? "reader" : "editor"}_settlement_desktop.png`), fullPage: true });
      await page.evaluate(() => { window.__qaPrintHtml = ""; window.open = () => ({ document: {
        write: html => { window.__qaPrintHtml = html; }, close: () => {} } }); });
      await page.getByRole("button", { name: "Imprimir PDF", exact: true }).click();
      const print = (await page.evaluate(() => window.__qaPrintHtml)).replace(/<div>Generado:.*?<\/div>/, "<div>Generado: [QA]</div>");
      assert.ok(print.includes("Marcelo Kessel") && print.includes("410.000"));
      if (!readonly) await fs.writeFile(path.join(output, "print.html"), print);
      await page.locator("#commission_settlement_search").fill("Gusty");
      assert.equal(await table.locator("tbody tr").count(), 2);
      await page.locator("#commission_settlement_search").fill("sin resultados fixture");
      await page.getByText("Sin movimientos para los artistas asignados.", { exact: true }).waitFor();
      if (!legacy) assert.equal(await table.locator("tbody td").getAttribute("colspan"), "10");
      await page.locator("#commission_settlement_search").fill("");
      await page.locator("#commission_period_trigger").click();
      await page.locator("#commission_period_year").selectOption("2026");
      await page.screenshot({ path: path.join(output, `${readonly ? "reader" : "editor"}_period.png`), fullPage: true });
      await page.locator(".period-month-grid button").nth(8).click();
      assert.equal(await table.locator("tbody tr").count(), 2);
      await page.locator("#commission_period_trigger").click();
      await page.locator(".period-quick-row button").filter({ hasText: "Todo" }).click();
      assert.equal(await table.locator("tbody tr").count(), 5);
      const config = () => legacy ? page.locator(".finance-tabs button").filter({ hasText: "Configuracion" }).click()
        : page.getByRole("tab", { name: "Configuracion", exact: true }).click();
      const settle = () => legacy ? page.locator(".finance-tabs button").filter({ hasText: "Liquidacion" }).click()
        : page.getByRole("tab", { name: "Liquidacion", exact: true }).click();
      await config();
      const percent = page.locator('.commission-config-table tbody input[type="number"]').first();
      assert.equal(await percent.inputValue(), "10");
      assert.equal(await percent.isDisabled(), readonly);
      await page.screenshot({ path: path.join(output, `${readonly ? "reader" : "editor"}_config_desktop.png`), fullPage: true });
      if (!readonly) {
        await percent.fill("12.5");
        assert.equal(await save.isEnabled(), true);
        await save.click();
        await page.waitForLoadState("networkidle");
        assert.equal(writes.length, 1);
        assert.equal(writes[0].rules[0].percent, 12.5);
        assert.equal(writes[0].employee_id, 1);
        assert.equal(await save.isDisabled(), true);
      }
      const responsive = [];
      for (const width of [1440, 1024, 820, 390, 360]) {
        await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 });
        await settle();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
        if (!legacy) assert.equal(overflow, false, `Overflow at ${width}`);
        const clipped = await page.locator(".control-dashboard strong").evaluateAll(elements => elements.some(element => element.scrollWidth > element.clientWidth + 1));
        if (!legacy) assert.equal(clipped, false, `Metric text clipping at ${width}`);
        if (!legacy) {
          const opaqueMetrics = await page.locator(".commission-metrics > div").evaluateAll(elements =>
            elements.some(element => getComputedStyle(element).backgroundColor !== "rgba(0, 0, 0, 0)"));
          assert.equal(opaqueMetrics, false, `Opaque settlement metrics at ${width}`);
        }
        if (width === 390) await page.screenshot({ path: path.join(output, `${readonly ? "reader" : "editor"}_settlement_mobile.png`), fullPage: true });
        await config();
        if (!legacy) assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
        if (width === 390) await page.screenshot({ path: path.join(output, `${readonly ? "reader" : "editor"}_config_mobile.png`), fullPage: true });
        responsive.push({ width, overflow, metric_text_clipped: clipped });
      }
      if (!legacy) {
        await page.getByRole("tab", { name: "Configuracion", exact: true }).focus();
        await page.keyboard.press("ArrowLeft");
        assert.equal(await page.getByRole("tab", { name: "Liquidacion", exact: true }).getAttribute("aria-selected"), "true");
        await page.keyboard.press("End");
        assert.equal(await page.getByRole("tab", { name: "Configuracion", exact: true }).getAttribute("aria-selected"), "true");
        const backgrounds = await page.locator(".commissions-page, .summary-table-wrap, .commission-metrics > div, .inline-check").evaluateAll(elements =>
          elements.map(element => getComputedStyle(element).backgroundColor));
        assert.ok(backgrounds.every(color => color === "rgba(0, 0, 0, 0)"), "Opaque work surface");
      }
      await page.locator("#commission_employee").selectOption("2");
      await settle();
      await page.getByText("Este empleado no tiene acceso al modulo Comisiones. Configuralo primero en ABM Empleados.").waitFor();
      assert.equal(await save.isDisabled(), true);
      assert.deepEqual(errors, []);
      assert.deepEqual(unexpected, []);
      results.push({ readonly, financial, rows: originalRows, print, responsive, unexpected, errors,
        fixture_writes: writes, real_api_requests: 0, permission_checks: "passed", keyboard_tabs: !legacy });
      await context.close();
    }
    await fs.writeFile(path.join(output, "results.json"), JSON.stringify({ status: "passed", url, legacy, results }, null, 2));
    console.log(JSON.stringify({ status: "passed", readonly_and_editor: true, viewports: 5, real_api_requests: 0, output }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

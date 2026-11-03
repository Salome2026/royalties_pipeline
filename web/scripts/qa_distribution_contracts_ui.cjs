// Isolated browser fixtures: every API request is intercepted; no live data is read or changed.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(process.argv[2] || "playwright");
const url = process.argv[3], output = process.argv[4];
assert.ok(url && output, "Provide Playwright module, local app URL and evidence directory");

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [], unexpected = [], writes = [];
    page.on("pageerror", error => errors.push(String(error)));
    let templates = [];
    const allocation = { principal: "Artista de prueba", principal_percent: 70, indyana_percent: null,
      apply_guest_contracts: false, principal_rule: { treatment: "direct" }, participants: [] };
    const agreement = { id: "principal", label: "Contrato principal", commercialization: "pending", allocation_model: "pools",
      master_pool_percent: null, company_name: "Indyana", contract_kind: "simple", owners: [],
      effective_from: "2026-01-01", effective_until: null, allocation };
    const item = { isrc: "ARDL12600041", title: "Tema de prueba", artists_informed: "Artista de prueba",
      amount_usd: 100, isrc_amount_usd: 100, associated_amount_usd: 0, sources: "fuga", closed: false, version: 0,
      first_month: "2026-01", last_month: "2026-07" };
    let detail = { ...item, split: { ...allocation, agreements: [agreement], master_type: "pending", has_contract: null,
      agreement_confirmed: false, effective_from: "2026-01-01", notes: "" },
      artist_suggestions: { artists: ["Artista de prueba"], evidence: [], warnings: [] }, artist_contracts: [],
      first_statement_date: "2026-01-01", statement_income: [], pool_contracts_supported: true, distribution_recipients_supported: true };
    await page.route("**/api/**", async route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      const respond = body => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
      if (pathname === "/api/wml") return respond({ enabled: false });
      if (pathname === "/api/session") return respond({ authenticated: true, user: { username: "fixture", role: "admin", canEdit: true } });
      if (pathname === "/api/master-contracts") return respond({ items: [item], total: 1, offset: 0, source_accounts: [], summary: { open: 1, closed: 0 } });
      if (pathname === "/api/master-contract-distribution") {
        if (request.method() === "PUT") {
          const payload = request.postDataJSON(); writes.push(payload);
          const saved = { ...payload, number: payload.number ?? 10010 + templates.length, version: payload.expected_version + 1,
            updated_by: "fixture", updated_at: "2026-11-03" };
          templates = [...templates.filter(row => row.number !== saved.number), saved];
          return respond(saved);
        }
        return respond({ items: templates, total: templates.length });
      }
      if (pathname.endsWith("/associations")) return respond({ items: [], summary: {}, version: detail.version });
      if (pathname === "/api/master-contracts/ARDL12600041") {
        if (request.method() === "PUT") {
          const payload = request.postDataJSON(); writes.push(payload);
          assert.equal("future_reports_selected" in payload, false);
          detail = { ...detail, ...payload, version: detail.version + 1, updated_by: "fixture", updated_at: "2026-11-03" };
        }
        return respond({ ...detail, distribution_contracts: templates });
      }
      unexpected.push(pathname);
      return route.fulfill({ status: 403, contentType: "application/json", body: '{"error":"Unconfigured fixture; live request blocked"}' });
    });
    await page.goto(url, { waitUntil: "networkidle", timeout: 180000 });
    await page.getByRole("button", { name: "Contratos", exact: true }).first().click();
    await page.getByRole("button", { name: "Contratos de distribución", exact: true }).click();
    await page.getByRole("textbox", { name: "Sello", exact: true }).fill("Sello de prueba");
    await page.getByRole("spinbutton", { name: "Bolsa master porcentaje" }).fill("30");
    await page.getByRole("button", { name: "Agregar destinatario", exact: true }).click();
    await page.getByLabel("Destinatario 2", { exact: true }).fill("Socio");
    await page.getByRole("spinbutton", { name: "Porcentaje destinatario 1", exact: true }).fill("20");
    await page.getByRole("spinbutton", { name: "Porcentaje destinatario 2", exact: true }).fill("10");
    await page.getByRole("button", { name: "Guardar contrato", exact: true }).click();
    await page.getByRole("heading", { name: "Contrato nro. 10010", exact: true }).waitFor();
    assert.equal(templates[0].master_pool_percent, 30);
    assert.deepEqual(templates[0].distribution_recipients, [{ name: "Indyana", percent: 20 }, { name: "Socio", percent: 10 }]);
    await page.screenshot({ path: path.join(output, "distribution-template-desktop.png"), fullPage: true, animations: "disabled" });
    // The same label needs a different sublabel; the number is assigned by the server.
    await page.getByRole("button", { name: "Nuevo contrato de distribución", exact: true }).click();
    await page.getByRole("textbox", { name: "Sello", exact: true }).fill("Sello de prueba");
    await page.getByRole("spinbutton", { name: "Bolsa master porcentaje" }).fill("25");
    assert.equal(await page.getByRole("button", { name: "Guardar contrato", exact: true }).isDisabled(), true);
    await page.getByRole("textbox", { name: "Subsello (opcional)", exact: true }).fill("Pop");
    await page.getByRole("button", { name: "Guardar contrato", exact: true }).click();
    await page.getByRole("heading", { name: "Contrato nro. 10011", exact: true }).waitFor();
    await page.getByRole("button", { name: "Volver a contratos", exact: true }).click();
    await page.getByRole("button", { name: "Tema de prueba", exact: true }).click();
    await page.getByRole("button", { name: /Contrato principal.*Por definir/ }).click();
    await page.getByRole("combobox", { name: "Comercialización", exact: true }).selectOption("distribution");
    await page.getByRole("combobox", { name: "Contrato existente", exact: true }).selectOption("10010");
    await page.getByRole("button", { name: "Aplicar contrato", exact: true }).click();
    assert.equal(await page.getByRole("spinbutton", { name: "Bolsa master porcentaje" }).inputValue(), "30");
    assert.equal(await page.getByRole("spinbutton", { name: "Bolsa participaciones porcentaje" }).inputValue(), "70");
    assert.equal(await page.getByLabel("Destinatario 2", { exact: true }).inputValue(), "Socio");
    assert.equal(await page.getByText("Seleccionado para futura aplicación a reportes", { exact: true }).count(), 0);
    await page.getByRole("button", { name: "Guardar", exact: true }).click();
    await page.getByText("Borrador guardado.", { exact: true }).waitFor();
    assert.deepEqual(detail.split.agreements[0].allocation, allocation);
    assert.equal(detail.split.agreements[0].distribution_contract_number, 10010);
    assert.equal(detail.split.agreements[0].effective_from, "2026-01-01");
    await page.screenshot({ path: path.join(output, "applied-distribution-desktop.png"), fullPage: true, animations: "disabled" });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, "applied-distribution-mobile.png"), fullPage: true, animations: "disabled" });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), "Mobile page must not overflow horizontally");
    assert.deepEqual(unexpected, []); assert.deepEqual(errors, []);
    assert.equal(writes.length, 3);
    console.log("UI: create two numbered templates, reject duplicate label/sub-label, add recipients, apply and save a song, preserve participants/dates, no report checkbox, desktop and mobile: PASS");
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

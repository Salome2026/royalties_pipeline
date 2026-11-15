const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { setTimeout: delay } = require("node:timers/promises");

const dependencies = path.resolve(process.cwd(), "tmp/app_integration");
const scenarioDirectory = {
  ingest: "statement_ingest_preview", fuga: "fuga_ingest_preview", operational: "report_operational_preview",
  cloud: "report_cloud_preview",
}[process.env.ROYALTY_PREVIEW_SCENARIO];
const root = scenarioDirectory ? path.resolve(process.cwd(), "tmp", scenarioDirectory) : dependencies;
const { chromium } = require(path.join(dependencies, "node_modules/playwright"));
const config = JSON.parse(fs.readFileSync(path.join(root, "local_config.json"), "utf8"));
const address = "http://127.0.0.1:" + config.web_port;
const output = path.join(root, "browser");
const months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const report146 = { numbers: "10012", basis: "statement_period", month: "2026-09", source: "orchard", account: "mawzrecords" };
const pilotFuga = { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" };
const cases = {
  "pilot-off": { ...pilotFuga, keywords: "655857944443", month: "2024-12", fullDetail: true, initialEngine: "parquet" },
  "pilot-on": { ...pilotFuga, initialEngine: "bigquery" },
  "pilot-rollback": { ...pilotFuga, initialEngine: "bigquery", waitForRollback: true },
  "pilot-on-final": { ...pilotFuga, initialEngine: "bigquery" },
  "pilot-rollback-final": { ...pilotFuga, initialEngine: "bigquery", waitForRollback: true },
  "pilot-excluded": { ...pilotFuga, username: "otro-usuario-prueba", initialEngine: "parquet" },
  "pilot-wml": { keywords: "USWL12100382", scope: "wml", basis: "statement_period", month: "2025-06", initialEngine: "parquet" },
  "146-before": report146,
  "146-cloud-before": report146,
  "146-after": report146,
  "146-enriched": { ...report146, columns: "all" },
  "146-sheet": { ...report146, format: "google_sheet" },
  "146-sheet-regular-close": { ...report146, format: "google_sheet" },
  "la-juntada": { keywords: "la juntada", basis: "statement_period", count: 2 },
  "la-juntada-cloud-automatic": { keywords: "la juntada", basis: "statement_period", count: 2 },
  "la-juntada-retry": { keywords: "la juntada", basis: "statement_period", count: 2 },
  "la-juntada-sheet": { keywords: "la juntada", basis: "statement_period", format: "google_sheet",
    expectedError: /celdas.+Elegí Excel/ },
  "la-juntada-sheet-regular-close": { keywords: "la juntada", basis: "statement_period", format: "google_sheet",
    expectedError: /celdas.+Elegí Excel/, waitMs: 3600000 },
  "income-pdf": { ...report146, keywords: "Amanece, Eze Greco", numbers: "10010, 10011, 10012", format: "executive_pdf",
    basis: "transaction_month", month: null, range: ["2026-01", "2026-08"] },
  "all-contracts": { ...report146, keywords: "Amanece, Eze Greco", numbers: "10010, 10011, 10012",
    match: "all", basis: "transaction_month", month: null, range: ["2026-01", "2026-08"] },
  "no-results": { keywords: "zz-unmatched-report-validation-20261105", basis: "transaction_month" },
  "contract-pdf": { format: "executive_pdf", mode: "contractual", artist: "G Sony" },
  "settlement": { format: "executive_pdf", mode: "artist_settlement", artist: "Meli Gimenez", month: "2026-09" },
  "enriched-consumption": { keywords: "mamiyosoyelth", basis: "transaction_month", range: ["2026-07", "2026-09"], columns: "matching" },
  "wml-consumption": { keywords: "5054197144011, 5054197423383", scope: "wml", basis: "transaction_month", month: "2024-10" },
  "wml-statement": { keywords: "5054197144011, 5054197423383", scope: "wml", basis: "statement_period", month: "2024-12" },
  "wml-before-publication": { keywords: "USWL12100382", scope: "wml", basis: "transaction_month", month: "2024-12" },
  "wml-after-publication": { keywords: "USWL12100382", scope: "wml", basis: "transaction_month", month: "2024-12" },
  "wml-new-statement": { keywords: "USWL12100382", scope: "wml", basis: "statement_period", month: "2026-06" },
  "wml-first-arrival": { keywords: "USWL12100382", scope: "wml", basis: "statement_period" },
  "wml-second-arrival": { keywords: "USWL12100382", scope: "wml", basis: "statement_period" },
  "wml-regular-rollback": { keywords: "USWL12100382", scope: "wml", basis: "statement_period", month: "2025-06" },
  "fuga-statement-upc": { keywords: "655857944443", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-12" },
  "fuga-statement-isrc": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-12" },
  "fuga-cloud-before": { keywords: "789556228853", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2026-04" },
  "fuga-cloud-upc": { keywords: "789556228853", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2026-04" },
  "fuga-cloud-upc-after": { keywords: "789556228853", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2026-04" },
  "fuga-cloud-isrc": { keywords: "ARL2P2500320", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2026-04" },
  "fuga-cloud-complete": { keywords: "fuga", source: "fuga", account: "indyana_records", basis: "statement_period", count: 2,
    waitMs: 5400000 },
  "fuga-recurring-nov-before": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" },
  "fuga-recurring-nov": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" },
  "fuga-recurring-dec-before": { keywords: "655857944443", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-12" },
  "fuga-recurring-dec": { keywords: "655857944443", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-12" },
  "fuga-recurring-nov-after": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" },
  "fuga-raw-drop-august": { keywords: "ARDL12400029", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-08" },
  "fuga-raw-drop-september": { keywords: "ARDL12400029", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-09" },
  "fuga-recurring-top-countries": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11", topCountries: true },
  "fuga-rollback-legacy": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" },
  "fuga-rollback-restored": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" },
  "fuga-rollback-during-bigquery": { keywords: "ES71G1921229", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2024-11" },
  "text-numbered-preview-statement": { source: "dashgo", account: "mawzrecords", basis: "statement_period", numbers: "990001", columns: "all" },
  "text-numbered-preview-consumption": { source: "dashgo", account: "mawzrecords", basis: "transaction_month", numbers: "990001", columns: "all" },
  "catalog-close-orchard": { keywords: "QMBZ92608916", source: "orchard", account: "mawzrecords", basis: "statement_period", month: "2026-09", numbers: "10011", columns: "all" },
  "catalog-close-soundon": { keywords: "QT5M22692699", source: "soundon", account: "soundon", basis: "statement_period", month: "2026-09" },
  "catalog-close-fuga-before": { keywords: "QMDA62568121", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2025-12", columns: "all" },
  "catalog-close-fuga-after-unfiltered": { keywords: "QMDA62568121", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2025-12", columns: "all" },
  "catalog-close-fuga-after": { keywords: "QMDA62568121", source: "fuga", account: "indyana_records", basis: "statement_period", month: "2025-12", numbers: "10012", columns: "all" },
  "catalog-close-fuga-consumption": { keywords: "QMDA62568121", source: "fuga", account: "indyana_records", basis: "transaction_month", range: ["2025-01", "2026-01"], columns: "all" },
  "catalog-close-contract-pdf": { format: "executive_pdf", mode: "contractual", artist: "El Caserio", month: "2025-12", numbers: "10012" },
};

function json(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + "\n");
}

async function until(callback, failure, milliseconds = 600000) {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    const value = callback();
    if (value) return value;
    await delay(250);
  }
  throw new Error(failure);
}

async function openReport(browser, username = "reportes-prueba", historyLimit = 8) {
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  await page.goto(address, { timeout: 120000 });
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(config.user_password);
  for (let attempt = 0; attempt < 3; attempt++) {
    const login = page.waitForResponse(r => r.url().endsWith("/api/login") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Ingresar" }).click();
    const response = await login;
    if (response.ok()) break;
    assert(attempt < 2 && response.status() === 503, "El acceso local de prueba falló");
  }
  if (historyLimit !== 8) {
    await page.route(/\/api\/report\?limit=8$/, route => route.continue({ url: address + `/api/report?limit=${historyLimit}` }));
  }
  await page.getByRole("button", { name: "Reporte de regalías", exact: true }).click({ timeout: 45000 });
  await page.locator("#royalty_keywords").waitFor();
  return { context, page };
}

async function selectPeriod(page, options) {
  if (!options.month && !options.range) return;
  await page.locator("#royalty_period_trigger").click();
  const dialog = page.getByRole("dialog", { name: "Período" });
  if (options.range) await dialog.getByRole("button", { name: "Rango", exact: true }).click();
  for (const month of options.range || [options.month]) {
    await page.locator("#royalty_period_year").selectOption(month.slice(0, 4));
    const label = options.scope === "wml" && options.basis === "statement_period"
      ? (month.endsWith("-06") ? "Enero–junio" : "Julio–diciembre") : months[Number(month.slice(-2)) - 1];
    await dialog.getByRole("button", { name: label, exact: true }).click();
  }
}

async function chooseReport(page, options) {
  if (options.scope === "wml") {
    await page.getByLabel("Ámbito de regalías").selectOption("wml");
    await page.waitForLoadState("domcontentloaded");
    if (!(await page.locator("#royalty_keywords").isVisible())) {
      await page.getByRole("button", { name: "Reporte de regalías", exact: true }).click();
    }
    await page.waitForFunction(() => document.cookie.includes("vpo_royalty_scope=wml"));
    await page.locator("#royalty_contract_numbers").waitFor({ state: "hidden" });
  }
  if (options.format === "executive_pdf") {
    await page.getByRole("button", { name: "PDF ejecutivo", exact: true }).click();
    if (options.mode) {
      await page.locator("#royalty_pdf_type").selectOption(options.mode);
      await page.locator("#royalty_contract_artist").fill(options.artist);
      await page.getByRole("button", { name: "Agregar artista" }).click();
    }
  }
  if (options.basis) await page.locator("#royalty_period_basis").selectOption(options.basis);
  if (options.match) await page.locator("#royalty_match_mode").selectOption(options.match);
  if (options.keywords) await page.locator("#royalty_keywords").fill(options.keywords);
  if (options.topCountries) await page.getByRole("checkbox", { name: "Priorizar los 5 países con mayores ingresos" }).check();
  if (options.numbers) await page.locator("#royalty_contract_numbers").fill(options.numbers);
  if (options.source) {
    await page.locator("#royalty_source").selectOption(options.source);
    await page.locator("#royalty_account").selectOption(options.account);
  }
  if (options.columns) {
    await page.locator("#royalty_include_contracts").selectOption("yes");
    await page.locator("#royalty_contract_columns").selectOption(options.columns);
  }
  await selectPeriod(page, options);
}

async function runCase(browser, name, options = cases[name]) {
  assert(options, "Caso desconocido: " + name);
  const folder = path.join(output, name);
  assert(!fs.existsSync(path.join(folder, "submission.json")), "Ya existe una solicitud. Recuperá el trabajo desde el historial.");
  const { context, page } = await openReport(browser, options.username);
  const downloads = [];
  const observations = [];
  page.on("download", item => downloads.push(item));
  page.on("response", async response => {
    const url = new URL(response.url());
    if (url.pathname === "/api/report" && url.searchParams.has("job_id") && !url.searchParams.has("download")) {
      try { observations.push((await response.json()).item); } catch {}
    }
  });
  try {
    await chooseReport(page, options);
    if (options.initialEngine === "bigquery") {
      await page.getByText("Si el detalle completo supera la capacidad de Excel", { exact: false }).waitFor();
      assert.equal(await page.locator("#royalty_raw_limit").count(), 0);
    } else if (options.initialEngine === "parquet") {
      assert.equal(await page.locator("#royalty_raw_limit").inputValue(), "5000");
    }
    if (options.fullDetail) await page.getByRole("checkbox", { name: /Incluir todas las filas del detalle/ }).check();
    if (options.waitForRollback) {
      json(path.join(folder, "screen-before-switch.json"), { bigquery_excel_options: true });
      await until(() => fs.existsSync(path.join(root, "pilot-release", "rollback.json")), "La reversión no quedó registrada", 180000);
    }
    const label = options.format === "google_sheet" ? "Crear Google Sheet"
      : options.format === "executive_pdf" ? "Generar PDF" : "Generar Excel";
    let submit = page.getByRole("button", { name: label, exact: true });
    if (options.fullDetail) {
      const [counted] = await Promise.all([
        page.waitForResponse(r => new URL(r.url()).pathname === "/api/report-detail-count", { timeout: 120000 }),
        submit.click(),
      ]);
      const preflight = await counted.json();
      assert.equal(counted.status(), 200, JSON.stringify(preflight));
      assert.equal(preflight.exceeds_excel_limit, false);
      json(path.join(folder, "preflight.json"), preflight);
      await page.getByRole("dialog", { name: "Generar detalle completo" }).waitFor({ timeout: 120000 });
      submit = page.getByRole("button", { name: "Generar igualmente" });
    }
    const [response] = await Promise.all([
      page.waitForResponse(r => new URL(r.url()).pathname === "/api/report" && r.request().method() === "POST"),
      submit.click(),
    ]);
    const data = await response.json();
    assert.equal(response.status(), 202, JSON.stringify(data));
    const job = data.item;
    json(path.join(folder, "submission.json"), { request: response.request().postDataJSON(), job, reused: data.reused });
    console.log(name, "solicitud", job.id);
    const terminal = ["completed", "failed"].includes(job.status) ? job
      : await until(() => observations.find(item => item?.id === job.id && ["completed", "failed"].includes(item.status)),
        "La pantalla no mostró el resultado del trabajo " + job.id, options.waitMs ?? 1200000);
    json(path.join(folder, "terminal.json"), terminal);
    if (options.expectedError) {
      assert.equal(terminal.status, "failed");
      assert.match(terminal.error_message, options.expectedError);
      assert.equal(terminal.result_url, null);
      assert.equal(downloads.length, 0);
      await page.getByText(options.expectedError).first().waitFor({ state: "visible" });
      json(path.join(folder, "acceptance.json"), { job: terminal.id, visible_error: terminal.error_message, no_download: true });
      console.log(name, "límite visible desde la pantalla");
      return;
    }
    assert.equal(terminal.status, "completed", terminal.error_message);
    if (options.format === "google_sheet") {
      const link = page.getByRole("link", { name: "Abrir Google Sheet", exact: false });
      const href = await link.getAttribute("href");
      assert.match(href, /^https:\/\/docs\.google\.com\/spreadsheets\/d\/[A-Za-z0-9_-]+\/edit/);
      assert.equal(href, terminal.result_url);
      json(path.join(folder, "acceptance.json"), { job: terminal.id, sheet_url: href, screen_link: true });
    } else {
      const count = options.count || 1;
      await until(() => downloads.length >= count, "La pantalla no inició todas las descargas", 120000);
      assert.equal(downloads.length, count);
      const saved = [];
      for (const item of downloads) {
        const file = item.suggestedFilename();
        assert.equal(file, path.basename(file));
        const target = path.join(folder, file);
        await item.saveAs(target);
        assert.equal(await item.failure(), null);
        saved.push({ name: file, path: target, bytes: fs.statSync(target).size });
      }
      if (count === 2) {
        const excel = saved.find(item => item.name.endsWith(".xlsx"));
        assert(excel);
        assert(saved.some(item => item.name === excel.name.replace(/\.xlsx$/, "_detalle.csv")));
      }
      json(path.join(folder, "acceptance.json"), { job: terminal.id, automatic_downloads: saved });
    }
    if (["146-after", "la-juntada", "wml-consumption", "146-sheet-regular-close"].includes(name)) {
      await page.screenshot({ path: path.join(folder, "pantalla.png") });
    }
    console.log(name, "listo desde la pantalla");
  } catch (error) {
    fs.mkdirSync(folder, { recursive: true });
    await page.screenshot({ path: path.join(folder, "failure.png") }).catch(() => {});
    throw error;
  } finally {
    await context.close();
  }
}

async function recoverSingle(browser, name, targetCase = name) {
  const folder = path.join(output, name);
  const targetFolder = path.join(output, targetCase);
  const { job } = JSON.parse(fs.readFileSync(path.join(folder, "submission.json"), "utf8"));
  const { context, page } = await openReport(browser);
  try {
    const response = await context.request.get(address + "/api/report?job_id=" + job.id);
    assert(response.ok());
    const terminal = (await response.json()).item;
    assert.equal(terminal.status, "completed", terminal.error_message);
    const row = page.locator('[class*="recentRow"]').filter({ hasText: new RegExp("#" + terminal.id + "(?![0-9])") });
    const waiting = page.waitForEvent("download");
    await row.getByRole("link", { name: "Excel", exact: true }).click();
    const item = await waiting;
    fs.mkdirSync(targetFolder, { recursive: true });
    const target = path.join(targetFolder, item.suggestedFilename());
    assert.equal(item.suggestedFilename(), terminal.result_filename);
    await item.saveAs(target);
    assert.equal(await sha256(target), terminal.result_sha256);
    json(path.join(targetFolder, "terminal.json"), terminal);
    json(path.join(targetFolder, "acceptance.json"), { job: terminal.id,
      history_downloads: [{ name: item.suggestedFilename(), path: target, bytes: fs.statSync(target).size }] });
  } finally {
    await context.close();
  }
}

async function history(browser, wml = false, recurring = false) {
  const caseName = recurring === "rollback" ? "fuga-rollback-restored"
    : recurring ? "fuga-recurring-nov" : wml ? "wml-first-arrival"
    : process.env.ROYALTY_PREVIEW_SCENARIO === "cloud" ? "146-cloud-before" : "146-before";
  const historyFolder = recurring === "rollback" ? "fuga-rollback-history"
    : recurring ? "fuga-recurring-history" : wml ? "wml-arrival-history" : "history";
  const before = JSON.parse(fs.readFileSync(path.join(output, caseName, "acceptance.json"), "utf8"));
  const { context, page } = await openReport(browser);
  try {
    if (wml) await chooseReport(page, { scope: "wml" });
    const row = page.locator('[class*="recentRow"]').filter({ hasText: new RegExp("#" + before.job + "(?![0-9])") });
    await row.getByRole("link", { name: "Excel" }).waitFor();
    const waiting = page.waitForEvent("download");
    await row.getByRole("link", { name: "Excel" }).click();
    const item = await waiting;
    const folder = path.join(output, historyFolder);
    fs.mkdirSync(folder, { recursive: true });
    const target = path.join(folder, item.suggestedFilename());
    await item.saveAs(target);
    const original = (before.automatic_downloads || before.history_downloads)[0];
    assert.equal(item.suggestedFilename(), original.name);
    assert.equal(await sha256(target), await sha256(original.path));
    json(path.join(folder, "acceptance.json"), { job: before.job, name: item.suggestedFilename(), path: target,
      sha256: await sha256(target) });
  } finally {
    await context.close();
  }
  const other = await openReport(browser, "otro-usuario-prueba");
  try {
    if (wml) await chooseReport(other.page, { scope: "wml" });
    const denied = await other.context.request.get(address + "/api/report?job_id=" + before.job + "&download=1");
    assert.equal(denied.status(), 403, "Otro usuario no debe poder descargar el reporte");
    const receipt = path.join(output, historyFolder, "acceptance.json");
    json(receipt, { ...JSON.parse(fs.readFileSync(receipt, "utf8")), other_user_status: denied.status() });
  } finally {
    await other.context.close();
  }
}

async function sha256(file) {
  const hash = createHash("sha256");
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function heavyHistory(browser) {
  const retry = path.join(output, "la-juntada-retry", "acceptance.json");
  const original = JSON.parse(fs.readFileSync(fs.existsSync(retry) ? retry : path.join(output, "la-juntada", "acceptance.json"), "utf8"));
  const { context, page } = await openReport(browser);
  try {
    const row = page.locator('[class*="recentRow"]').filter({ hasText: new RegExp("#" + original.job + "(?![0-9])") });
    const result = [];
    for (const [label, extension] of [["Excel", ".xlsx"], ["CSV de detalle", ".csv"]]) {
      const link = row.getByRole("link", { name: label, exact: true });
      await link.waitFor();
      const waiting = page.waitForEvent("download");
      await link.click();
      const item = await waiting;
      const expected = original.automatic_downloads.find(file => file.name.endsWith(extension));
      assert.equal(item.suggestedFilename(), expected.name);
      const saved = await item.path();
      assert.equal(fs.statSync(saved).size, expected.bytes);
      const hash = await sha256(saved);
      assert.equal(hash, await sha256(expected.path));
      result.push({ name: expected.name, sha256: hash, bytes: expected.bytes });
      await item.delete();
    }
    json(path.join(output, "history-heavy", "acceptance.json"), { job: original.job, downloads_equal: result });
    console.log("history-heavy", "ambas descargas recuperadas");
  } finally {
    await context.close();
  }
}

async function recoverHeavyDownloads(browser, name = "la-juntada") {
  const original = path.join(output, name);
  const completed = JSON.parse(fs.readFileSync(path.join(original, "terminal.json"), "utf8"));
  assert.equal(completed.status, "completed");
  assert.equal(completed.download_files.length, 2);
  const folder = path.join(output, name + "-recovered");
  fs.mkdirSync(folder, { recursive: true });
  for (const receipt of ["submission.json", "terminal.json"]) {
    const source = path.join(original, receipt);
    if (fs.existsSync(source)) fs.copyFileSync(source, path.join(folder, receipt));
  }
  const { context, page } = await openReport(browser);
  try {
    const row = page.locator('[class*="recentRow"]').filter({ hasText: new RegExp("#" + completed.id + "(?![0-9])") });
    const saved = [];
    for (const [index, label] of ["Excel", "CSV de detalle"].entries()) {
      const link = row.getByRole("link", { name: label, exact: true });
      await link.waitFor();
      const waiting = page.waitForEvent("download");
      await link.click();
      const item = await waiting;
      const name = item.suggestedFilename();
      assert.equal(name, completed.download_files[index].name);
      assert.equal(name, path.basename(name));
      const target = path.join(folder, name);
      await item.saveAs(target);
      assert.equal(await item.failure(), null);
      saved.push({ name, path: target, bytes: fs.statSync(target).size, sha256: await sha256(target) });
    }
    assert.equal(saved[0].sha256, completed.result_sha256);
    assert.equal(saved[1].name, saved[0].name.replace(/\.xlsx$/, "_detalle.csv"));
    json(path.join(folder, "acceptance.json"), { job: completed.id, history_downloads: saved });
    console.log(name, "ambos archivos recuperados desde el historial");
  } finally {
    await context.close();
  }
}

async function pilotSignedHistory(browser) {
  const original = path.join(output, "la-juntada-cloud-automatic");
  const completed = JSON.parse(fs.readFileSync(path.join(original, "terminal.json"), "utf8"));
  const baseline = JSON.parse(fs.readFileSync(path.join(original, "acceptance.json"), "utf8"));
  const { context, page } = await openReport(browser, "reportes-prueba", 50);
  try {
    const row = page.locator('[class*="recentRow"]').filter({ hasText: new RegExp("#" + completed.id + "(?![0-9])") });
    const result = [];
    for (const [index, label] of ["Excel", "CSV de detalle"].entries()) {
      const link = row.getByRole("link", { name: label, exact: true });
      const endpoint = await link.getAttribute("href", { timeout: 30000 });
      const response = await context.request.get(address + endpoint, { maxRedirects: 0 });
      assert.equal(response.status(), 307);
      const target = new URL(response.headers().location);
      assert.equal(target.protocol, "https:");
      assert.equal(target.hostname, "storage.googleapis.com");
      assert(target.searchParams.has("generation"));
      assert(target.searchParams.has("X-Goog-Signature"));
      const expected = baseline.automatic_downloads[index];
      const waiting = page.waitForEvent("download");
      await link.click();
      const download = await waiting;
      const downloaded = await download.path();
      assert.equal(download.suggestedFilename(), expected.name);
      assert.equal(fs.statSync(downloaded).size, expected.bytes);
      const hash = await sha256(downloaded);
      assert.equal(hash, await sha256(expected.path));
      result.push({ part: label, name: expected.name, bytes: expected.bytes, sha256: hash,
        generation: target.searchParams.get("generation"), direct_storage: true });
      await download.delete();
    }
    const other = await openReport(browser, "otro-usuario-prueba");
    try {
      const url = address + `/api/report?job_id=${completed.id}&download=1&file=detail`;
      const denied = await other.context.request.get(url, { maxRedirects: 0 });
      assert.equal(denied.status(), 403);
    } finally {
      await other.context.close();
    }
    json(path.join(output, "pilot-signed-history", "acceptance.json"), { job: completed.id, downloads: result, other_user: 403 });
  } finally {
    await context.close();
  }
}

async function pilotLargeSignedRanges(browser) {
  const original = path.join(output, "fuga-cloud-complete-automatic");
  const baseline = JSON.parse(fs.readFileSync(path.join(original, "acceptance.json"), "utf8"));
  const file = baseline.automatic_downloads.find(item => item.name.endsWith("_detalle.csv"));
  assert(file && file.bytes > 1024 ** 3);
  const { context } = await openReport(browser);
  try {
    const route = address + `/api/report?job_id=${baseline.job}&download=1&file=detail`;
    const redirect = await context.request.get(route, { maxRedirects: 0 });
    assert.equal(redirect.status(), 307);
    const target = new URL(redirect.headers().location);
    assert.equal(target.hostname, "storage.googleapis.com");
    assert(target.searchParams.has("generation"));
    const ranges = [];
    const local = fs.openSync(file.path, "r");
    try {
      for (const start of [0, file.bytes - 1024]) {
        const end = start + 1023;
        const response = await context.request.get(target.href, { headers: { Range: `bytes=${start}-${end}` } });
        assert.equal(response.status(), 206);
        assert.equal(response.headers()["content-range"], `bytes ${start}-${end}/${file.bytes}`);
        const expected = Buffer.alloc(1024);
        assert.equal(fs.readSync(local, expected, 0, 1024, start), 1024);
        assert.deepEqual(await response.body(), expected);
        ranges.push({ start, end, bytes: 1024, matches_original: true });
      }
    } finally {
      fs.closeSync(local);
    }
    json(path.join(output, "pilot-signed-large", "acceptance.json"), {
      job: baseline.job, name: file.name, bytes: file.bytes, generation: target.searchParams.get("generation"),
      direct_storage: true, ranges,
    });
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.ROYALTY_PREVIEW_BROWSER_CHANNEL });
  try {
    for (const name of process.argv.slice(2)) {
      if (name === "history") await history(browser);
      else if (name === "wml-arrival-history") await history(browser, true);
      else if (name === "fuga-recurring-history") await history(browser, false, true);
      else if (name === "fuga-rollback-history") await history(browser, false, "rollback");
      else if (name === "pilot-signed-history") await pilotSignedHistory(browser);
      else if (name === "pilot-signed-large") await pilotLargeSignedRanges(browser);
      else if (name === "pilot-on-final-history") await recoverSingle(browser, "pilot-on-final", name);
      else if (name === "catalog-close-before-history") await recoverSingle(browser, "catalog-close-fuga-before", name);
      else if (name === "fuga-recurring-nov-recover") await recoverSingle(browser, "fuga-recurring-nov");
      else if (name === "fuga-recurring-top-recover") await recoverSingle(browser, "fuga-recurring-top-countries");
      else if (name === "history-heavy") await heavyHistory(browser);
      else if (name === "recover-heavy") await recoverHeavyDownloads(browser);
      else if (name === "recover-fuga") await recoverHeavyDownloads(browser, "fuga-cloud-complete");
      else if (name === "fuga-cloud-complete-automatic") await runCase(browser, name, cases["fuga-cloud-complete"]);
      else await runCase(browser, name);
    }
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

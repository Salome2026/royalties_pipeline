const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.argv[2] || "playwright");
const { PDFDocument } = require("pdf-lib");

const months = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"];
const accountRows = [
  { source: "fuga", account: "Motorcito", values: [21043, 18200, 24350, 22780, 30520, 28160], artists: 44, share: false },
  { source: "ada", account: "Mawz Records", values: [8700, 9200, 7500, 11200, 10800, 12400], artists: 27, share: true },
  { source: "onerpm", account: "Catalogo general", values: [4200, 5700, 3900, 6100, 7200, 8100], artists: 18, share: false },
];

const matrix = accountRows.map((row) => ({
  source: row.source,
  account: row.account,
  months: Object.fromEntries(months.map((month, index) => [month, row.values[index]])),
  total_usd: row.values.reduce((sum, amount) => sum + amount, 0),
  total_eur: 0,
  rows: 500,
  artists: row.artists,
  has_share_in_out: row.share,
}));
const monthly = months.map((month, index) => ({
  statement_period: month,
  total_usd: accountRows.reduce((sum, row) => sum + row.values[index], 0),
  total_eur: 0,
  rows: 1500,
}));
const totalUsd = monthly.reduce((sum, row) => sum + row.total_usd, 0);
const items = Array.from({ length: 120 }, (_, index) => ({
  statement_period: months[index % months.length],
  source: accountRows[index % accountRows.length].source,
  account: accountRows[index % accountRows.length].account,
  artist: index % 2 ? "Flor Alvarez" : "La Juntada de los Artistas",
  title: index % 2 ? "Una cancion para revisar el detalle" : "Tema de respaldo con nombre extenso",
  total_usd: 45.25 + index,
  total_eur: index % 3 ? 0 : 18.50,
  has_share_in_out: index % 3 === 1,
  raw_rows: 10,
}));

const fixture = {
  items,
  monthly,
  by_source: [],
  matrix,
  matrix_months: months,
  total: 1360,
  limit: 500,
  offset: 0,
  keyword: "",
  totals: {
    total_usd: totalUsd,
    total_eur: 1230.45,
    rows: 9000,
    months: months.length,
    sources: 3,
    accounts: 3,
    first_month: months[0],
    last_month: months[months.length - 1],
  },
  options: {
    sources: ["ada", "fuga", "onerpm"],
    accounts: accountRows.map((row) => row.account),
    source_accounts: accountRows.map((row) => ({ source: row.source, account: row.account })),
    artists: ["Flor Alvarez", "La Juntada de los Artistas"],
    first_month: "2023-11",
    last_month: "2026-08",
  },
};

const allMonths = [];
for (let year = 2023, month = 11; year < 2026 || month <= 8; month += 1) {
  allMonths.push(`${year}-${String(month).padStart(2, "0")}`);
  if (month === 12) { year += 1; month = 0; }
}

function fixtureForMonths(selectedMonths) {
  const expandedMatrix = accountRows.map((row) => {
    const amounts = selectedMonths.map((_, index) => row.values[index % row.values.length]);
    return {
      source: row.source,
      account: row.account,
      months: Object.fromEntries(selectedMonths.map((month, index) => [month, amounts[index]])),
      total_usd: amounts.reduce((sum, amount) => sum + amount, 0),
      artists: row.artists,
      has_share_in_out: row.share,
    };
  });
  const expandedMonthly = selectedMonths.map((month) => ({
    statement_period: month,
    total_usd: expandedMatrix.reduce((sum, row) => sum + row.months[month], 0),
  }));
  return {
    ...fixture,
    monthly: expandedMonthly,
    matrix: expandedMatrix,
    matrix_months: selectedMonths,
    totals: {
      ...fixture.totals,
      total_usd: expandedMonthly.reduce((sum, row) => sum + row.total_usd, 0),
      months: selectedMonths.length,
      first_month: selectedMonths[0],
      last_month: selectedMonths[selectedMonths.length - 1],
    },
  };
}

function fixtureForManyAccounts() {
  const manyMatrix = Array.from({ length: 31 }, (_, index) => {
    const amounts = months.map((_, monthIndex) => 1000 + index * 137 + monthIndex * 83);
    return {
      source: index % 2 ? "fuga" : "ada",
      account: `Cuenta de catalogo numero ${String(index + 1).padStart(2, "0")}`,
      months: Object.fromEntries(months.map((month, monthIndex) => [month, amounts[monthIndex]])),
      total_usd: amounts.reduce((sum, amount) => sum + amount, 0),
      artists: 10 + index,
      has_share_in_out: index % 4 === 0,
    };
  });
  const manyMonthly = months.map((month) => ({ statement_period: month, total_usd: manyMatrix.reduce((sum, row) => sum + row.months[month], 0) }));
  return {
    ...fixture,
    monthly: manyMonthly,
    matrix: manyMatrix,
    totals: {
      ...fixture.totals,
      total_usd: manyMonthly.reduce((sum, row) => sum + row.total_usd, 0),
      sources: 2,
      accounts: manyMatrix.length,
    },
  };
}

async function downloadPdf(page, outputPath) {
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF ejecutivo" }).click();
  const download = await pending;
  assert(download.suggestedFilename().startsWith("ingresos_digitales_"));
  await download.saveAs(outputPath);
  const pdf = await PDFDocument.load(fs.readFileSync(outputPath));
  return pdf.getPageCount();
}

async function setupPage(browser, viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1, acceptDownloads: true });
  const queries = [];
  await page.route("**/api/session", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ authenticated: true, user: { username: "qa", role: "admin", canEdit: true } }) }));
  await page.route("**/api/digital-income**", (route) => {
    queries.push(route.request().url());
    const search = new URL(route.request().url()).searchParams;
    const period = search.get("period_mode");
    const data = search.get("artist_keyword") === "__qa_many_accounts__" ? fixtureForManyAccounts() : period === "all" ? fixtureForMonths(allMonths) : period === "last_12_months" ? fixtureForMonths(allMonths.slice(-12)) : fixture;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
  });
  await page.goto("http://localhost:3000", { waitUntil: "domcontentloaded" });
  if (await page.getByRole("button", { name: "Abrir menú" }).isVisible()) {
    await page.getByRole("button", { name: "Abrir menú" }).click();
  }
  const incomeNav = page.getByRole("button", { name: /Ingresos digitales/i }).first();
  if (viewport.width <= 820) {
    await incomeNav.evaluate((button) => button.click());
  } else {
    await incomeNav.click();
  }
  await page.getByRole("main").getByRole("heading", { name: "Ingresos digitales" }).waitFor();
  const formattedTotal = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 }).format(totalUsd);
  await page.getByText(formattedTotal, { exact: true }).first().waitFor();
  assert.equal(await page.getByRole("main").getByText("Ingreso EUR", { exact: true }).count(), 0);
  return { page, queries };
}

async function main() {
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const outDir = path.resolve(__dirname, "../../tmp");
  fs.mkdirSync(outDir, { recursive: true });
  try {
    const desktop = await setupPage(browser, { width: 1440, height: 900 });
    await desktop.page.screenshot({ path: path.join(outDir, "digital-income-desktop.png"), fullPage: true });
    const queriesBeforePdf = desktop.queries.length;
    const shortPages = await downloadPdf(desktop.page, path.join(outDir, "digital-income-6m.pdf"));
    assert.equal(desktop.queries.length, queriesBeforePdf, "PDF generation should not refetch digital income");
    assert.equal(shortPages, 2, `unexpected six-month PDF pages: ${shortPages}`);
    assert.equal(await desktop.page.getByRole("tab", { name: /Por cuenta/i }).getAttribute("aria-selected"), "true");
    await desktop.page.getByRole("tab", { name: /Detalle/i }).click();
    assert.equal(await desktop.page.getByRole("columnheader", { name: "Ingreso EUR" }).count(), 0);
    assert.equal(await desktop.page.locator("tbody tr").count(), 50);
    await desktop.page.getByRole("button", { name: "Página siguiente" }).click();
    assert.equal(await desktop.page.locator("tbody tr").count(), 50);
    await desktop.page.locator("#digital_income_artist").fill("Flor Alvarez");
    await desktop.page.getByRole("button", { name: "Aplicar" }).click();
    assert(desktop.queries.at(-1).includes("artist_keyword=Flor+Alvarez"));
    await desktop.page.getByRole("button", { name: "Limpiar filtros" }).click();
    assert(!desktop.queries.at(-1).includes("artist_keyword="));
    await desktop.page.screenshot({ path: path.join(outDir, "digital-income-detail.png"), fullPage: true });
    await desktop.page.getByRole("tab", { name: /Por cuenta/i }).click();
    await desktop.page.locator("#digital_income_period_trigger").click();
    await desktop.page.getByRole("dialog", { name: "Periodo" }).getByRole("button", { name: "Todo" }).click();
    const allResponse = desktop.page.waitForResponse((response) => response.url().includes("period_mode=all") && response.status() === 200);
    await desktop.page.getByRole("button", { name: "Aplicar" }).click();
    await allResponse;
    const longPages = await downloadPdf(desktop.page, path.join(outDir, "digital-income-all.pdf"));
    assert(longPages > shortPages, `all-period PDF should grow: ${longPages} <= ${shortPages}`);
    await desktop.page.getByRole("button", { name: "Limpiar filtros" }).click();
    await desktop.page.locator("#digital_income_artist").fill("__qa_many_accounts__");
    const manyResponse = desktop.page.waitForResponse((response) => response.url().includes("artist_keyword=__qa_many_accounts__") && response.status() === 200);
    await desktop.page.getByRole("button", { name: "Aplicar" }).click();
    await manyResponse;
    const manyPages = await downloadPdf(desktop.page, path.join(outDir, "digital-income-many-accounts.pdf"));
    assert(manyPages > shortPages, `account row pagination should grow the PDF: ${manyPages}`);

    const mobile = await setupPage(browser, { width: 390, height: 844 });
    await mobile.page.screenshot({ path: path.join(outDir, "digital-income-mobile.png"), fullPage: true });
    const workspace = mobile.page.locator("main.digital-income-main > section").first();
    const width = await workspace.evaluate((element) => element.getBoundingClientRect().width);
    assert(width <= 390, `mobile workspace overflow: ${width}`);
    const matrixScroll = await mobile.page.locator("main.digital-income-main table").first().evaluate((table) => ({
      width: table.parentElement.clientWidth,
      scrollWidth: table.parentElement.scrollWidth,
    }));
    assert(matrixScroll.scrollWidth > matrixScroll.width, "mobile matrix should scroll horizontally");
    await mobile.page.locator("#digital_income_period_trigger").click();
    const periodDialog = await mobile.page.getByRole("dialog", { name: "Periodo" }).boundingBox();
    assert(periodDialog && periodDialog.x >= 0 && periodDialog.x + periodDialog.width <= 390, "mobile period popover overflow");
    await mobile.page.getByRole("dialog", { name: "Periodo" }).getByRole("button", { name: "Últimos 12" }).click();
    await mobile.page.getByRole("button", { name: "Aplicar" }).click();
    assert(mobile.queries.at(-1).includes("period_mode=last_12_months"));
    const mediumPages = await downloadPdf(mobile.page, path.join(outDir, "digital-income-12m.pdf"));
    assert(mediumPages > shortPages && mediumPages < longPages, `twelve-month PDF pages should be intermediate: ${mediumPages}`);
    await mobile.page.getByRole("tab", { name: /Detalle/i }).click();
    assert.equal(await mobile.page.getByRole("columnheader", { name: "Ingreso EUR" }).count(), 0);
    assert.equal(await mobile.page.locator("main.digital-income-main tbody tr").count(), 50);
    await mobile.page.screenshot({ path: path.join(outDir, "digital-income-mobile-detail.png"), fullPage: true });

    const narrow = await setupPage(browser, { width: 320, height: 720 });
    const pdfButton = await narrow.page.getByRole("button", { name: "PDF ejecutivo" }).boundingBox();
    assert(pdfButton && pdfButton.x >= 0 && pdfButton.x + pdfButton.width <= 320, "narrow mobile PDF button overflow");
    const narrowWorkspaceWidth = await narrow.page.locator("main.digital-income-main > section").first().evaluate((element) => element.getBoundingClientRect().width);
    assert(narrowWorkspaceWidth <= 320, `narrow mobile workspace overflow: ${narrowWorkspaceWidth}`);
    await narrow.page.screenshot({ path: path.join(outDir, "digital-income-mobile-narrow.png"), fullPage: true });
    console.log(`OK: desktop/mobile layout, filters, detail paging, dynamic PDFs (${shortPages}/${mediumPages}/${longPages} pages; ${manyPages} with 31 accounts)`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });

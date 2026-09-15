import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from "pdf-lib";

export type DigitalIncomeReportScope = {
  artistKeyword: string;
  source: string;
  account: string;
  periodLabel: string;
};

export type DigitalIncomeReportData = {
  total: number;
  monthly: { statement_period: string; total_usd: number }[];
  matrix_months: string[];
  matrix: {
    source: string;
    account: string;
    months: Record<string, number>;
    total_usd: number;
    artists: number;
    has_share_in_out: boolean;
  }[];
  totals: {
    total_usd: number;
    months: number;
    sources: number;
    accounts: number;
    first_month: string | null;
    last_month: string | null;
  };
};

const portrait: [number, number] = [595.28, 841.89];
const landscape: [number, number] = [841.89, 595.28];
const ink = rgb(0.13, 0.18, 0.16);
const muted = rgb(0.39, 0.46, 0.42);
const line = rgb(0.82, 0.86, 0.83);
const pale = rgb(0.95, 0.97, 0.95);
const green = rgb(0.16, 0.52, 0.42);
const coral = rgb(0.73, 0.31, 0.28);

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function safeText(value: unknown, font: PDFFont) {
  return Array.from(String(value ?? "").replace(/\s+/g, " ").replace(/[\u2010-\u2015\u2212]/g, "-").replace(/[\u2018\u2019]/g, "'")).map((character) => {
    try {
      font.encodeText(character);
      return character;
    } catch {
      return "?";
    }
  }).join("");
}

function fit(value: unknown, font: PDFFont, size: number, maxWidth: number) {
  const text = safeText(value, font);
  if (font.widthOfTextAtSize(text, size) <= maxWidth) return text;
  let end = text.length;
  while (end > 0 && font.widthOfTextAtSize(`${text.slice(0, end)}...`, size) > maxWidth) end -= 1;
  return end ? `${text.slice(0, end)}...` : "...";
}

function drawText(page: PDFPage, value: unknown, x: number, y: number, font: PDFFont, size: number, color = ink, maxWidth?: number) {
  const content = maxWidth ? fit(value, font, size, maxWidth) : safeText(value, font);
  page.drawText(content, { x, y, size, font, color });
}

function drawRight(page: PDFPage, value: unknown, right: number, y: number, font: PDFFont, size: number, color = ink, maxWidth?: number) {
  const content = maxWidth ? fit(value, font, size, maxWidth) : safeText(value, font);
  page.drawText(content, { x: right - font.widthOfTextAtSize(content, size), y, size, font, color });
}

function rule(page: PDFPage, x: number, y: number, width: number) {
  page.drawRectangle({ x, y, width, height: 0.6, color: line });
}

function sectionHeading(page: PDFPage, title: string, y: number, bold: PDFFont, width: number) {
  drawText(page, title, 40, y, bold, 14);
  rule(page, 40, y - 9, width - 80);
}

function monthlyHeader(page: PDFPage, y: number, bold: PDFFont) {
  page.drawRectangle({ x: 40, y: y - 5, width: portrait[0] - 80, height: 20, color: pale });
  drawText(page, "MES", 48, y + 1, bold, 8, muted);
  drawText(page, "EVOLUCION USD", 130, y + 1, bold, 8, muted);
  drawRight(page, "INGRESO USD", portrait[0] - 48, y + 1, bold, 8, muted);
}

function monthlyRow(page: PDFPage, month: DigitalIncomeReportData["monthly"][number], y: number, index: number, max: number, regular: PDFFont, bold: PDFFont) {
  if (index % 2 === 1) page.drawRectangle({ x: 40, y: y - 7, width: portrait[0] - 80, height: 20, color: pale });
  drawText(page, month.statement_period, 48, y, regular, 9);
  page.drawRectangle({ x: 130, y: y + 2, width: 250, height: 5, color: line });
  if (month.total_usd) page.drawRectangle({ x: 130, y: y + 2, width: Math.max(2, 250 * Math.abs(month.total_usd) / max), height: 5, color: month.total_usd < 0 ? coral : green });
  drawRight(page, usd.format(month.total_usd), portrait[0] - 48, y, bold, 9, month.total_usd < 0 ? coral : ink);
  rule(page, 40, y - 7, portrait[0] - 80);
}

function topAccounts(page: PDFPage, rows: DigitalIncomeReportData["matrix"], y: number, regular: PDFFont, bold: PDFFont) {
  sectionHeading(page, "Cuentas principales", y, bold, portrait[0]);
  drawText(page, "Ordenadas por ingreso USD del periodo completo", 40, y - 28, regular, 8, muted);
  let rowY = y - 54;
  for (const row of rows.slice(0, 5)) {
    drawText(page, `${row.source} / ${row.account}`, 48, rowY, regular, 9, ink, 345);
    drawRight(page, usd.format(row.total_usd), portrait[0] - 48, rowY, bold, 9, row.total_usd < 0 ? coral : ink);
    rule(page, 40, rowY - 8, portrait[0] - 80);
    rowY -= 23;
  }
}

function matrixPageHeader(doc: PDFDocument, bold: PDFFont) {
  const page = doc.addPage(landscape);
  drawText(page, "VPO CORP / DIGITAL", 40, 564, bold, 9, green);
  drawText(page, "Ingresos por distribuidora y cuenta", 40, 538, bold, 18);
  rule(page, 40, 528, landscape[0] - 80);
  return page;
}

function matrixBlock(page: PDFPage, months: string[], rows: DigitalIncomeReportData["matrix"], scope: { block: number; blocks: number; start: number; totalRows: number }, top: number, regular: PDFFont, bold: PDFFont) {
  const accountWidth = 212;
  const monthWidth = 86;
  const totalWidth = 120;
  const tableWidth = accountWidth + monthWidth * months.length + totalWidth;
  const right = 40 + tableWidth;
  drawText(page, months.length === 1 ? months[0] : `${months[0]} a ${months[months.length - 1]}`, 40, top, bold, 13);
  drawText(page, `Bloque ${scope.block} de ${scope.blocks}  |  Cuentas ${scope.start + 1}-${scope.start + rows.length} de ${scope.totalRows}`, 40, top - 17, regular, 8, muted);
  drawRight(page, "Total USD: periodo completo", right, top - 17, regular, 8, muted);

  const headerBottom = top - 49;
  page.drawRectangle({ x: 40, y: headerBottom, width: tableWidth, height: 24, color: pale });
  drawText(page, "DISTRIBUIDORA / CUENTA", 46, headerBottom + 9, bold, 8, muted);
  months.forEach((month, index) => drawRight(page, month, 40 + accountWidth + (index + 1) * monthWidth - 7, headerBottom + 9, bold, 8, muted));
  drawRight(page, "TOTAL USD", right - 7, headerBottom + 9, bold, 8, muted);

  rows.forEach((row, index) => {
    const bottom = headerBottom - (index + 1) * 24;
    if (index % 2 === 1) page.drawRectangle({ x: 40, y: bottom, width: tableWidth, height: 24, color: pale });
    drawText(page, row.source, 46, bottom + 13, bold, 9, ink, accountWidth - 12);
    drawText(page, `${row.account}  |  ${row.artists} artistas${row.has_share_in_out ? "  |  Share In/Out" : ""}`, 46, bottom + 3, regular, 7, muted, accountWidth - 12);
    months.forEach((month, monthIndex) => {
      const amount = row.months[month] || 0;
      drawRight(page, usd.format(amount), 40 + accountWidth + (monthIndex + 1) * monthWidth - 7, bottom + 8, regular, 8, amount < 0 ? coral : ink, monthWidth - 10);
    });
    drawRight(page, usd.format(row.total_usd), right - 7, bottom + 8, bold, 8, row.total_usd < 0 ? coral : green, totalWidth - 10);
    rule(page, 40, bottom, tableWidth);
  });

  const subtotalY = headerBottom - rows.length * 24 - 27;
  page.drawRectangle({ x: 40, y: subtotalY - 5, width: tableWidth, height: 24, color: rgb(0.88, 0.92, 0.89) });
  drawText(page, "Subtotal de estas cuentas", 46, subtotalY + 4, bold, 9);
  months.forEach((month, index) => drawRight(page, usd.format(rows.reduce((sum, row) => sum + (row.months[month] || 0), 0)), 40 + accountWidth + (index + 1) * monthWidth - 7, subtotalY + 4, bold, 8, ink, monthWidth - 10));
  drawRight(page, usd.format(rows.reduce((sum, row) => sum + row.total_usd, 0)), right - 7, subtotalY + 4, bold, 8, green, totalWidth - 10);
  return subtotalY - 24;
}

export async function buildDigitalIncomeExecutivePdf(data: DigitalIncomeReportData, scope: DigitalIncomeReportScope) {
  const doc = await PDFDocument.create();
  const regular = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);
  const page = doc.addPage(portrait);
  const width = portrait[0];
  const created = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date());
  const months = [...data.monthly].sort((a, b) => a.statement_period.localeCompare(b.statement_period));
  const matrix = [...data.matrix].sort((a, b) => b.total_usd - a.total_usd);
  const max = Math.max(1, ...months.map((month) => Math.abs(month.total_usd)));

  page.drawRectangle({ x: 40, y: 796, width: 34, height: 3, color: green });
  drawText(page, "VPO CORP / DIGITAL", 82, 793, bold, 9, green);
  drawRight(page, `Emitido: ${created}`, width - 40, 793, regular, 9, muted);
  drawText(page, "Ingresos digitales", 40, 755, bold, 28);
  drawText(page, "Informe ejecutivo - ingresos informados por distribuidoras", 40, 735, regular, 10, muted);
  rule(page, 40, 715, width - 80);

  drawText(page, "PERIODO APLICADO", 40, 691, bold, 8, muted);
  drawText(page, scope.periodLabel, 40, 676, bold, 11, ink, 245);
  drawText(page, "MESES CON DATOS", 315, 691, bold, 8, muted);
  drawText(page, `${data.totals.first_month || "-"} a ${data.totals.last_month || "-"}`, 315, 676, bold, 11);
  drawText(page, "BUSQUEDA", 40, 649, bold, 8, muted);
  drawText(page, scope.artistKeyword || "Sin filtro", 40, 634, regular, 10, ink, 245);
  drawText(page, "DISTRIBUIDORA / CUENTA", 315, 649, bold, 8, muted);
  drawText(page, `${scope.source || "Todas"} / ${scope.account || "Todas"}`, 315, 634, regular, 10, ink, 240);
  rule(page, 40, 618, width - 80);

  drawText(page, "INGRESO USD", 40, 594, bold, 8, muted);
  drawText(page, usd.format(data.totals.total_usd), 40, 568, bold, 21, green, 300);
  drawText(page, "GRUPOS", 368, 594, bold, 8, muted);
  drawText(page, data.total.toLocaleString("es-AR"), 368, 574, bold, 12);
  drawText(page, `${data.totals.months} meses  |  ${data.totals.sources} distribuidoras  |  ${data.totals.accounts} cuentas`, 40, 543, regular, 9, muted);
  drawText(page, "Base: statements sin splits, comisiones ni ajustes internos.", 40, 521, regular, 9, muted, width - 80);

  sectionHeading(page, "Evolucion mensual", 490, bold, width);
  monthlyHeader(page, 463, bold);
  let rowY = 439;
  if (!months.length) drawText(page, "Sin ingresos para el filtro aplicado.", 48, rowY, regular, 10, muted);
  for (let index = 0; index < months.length; index += 1) {
    if (rowY < 91) {
      const next = doc.addPage(portrait);
      drawText(next, "VPO CORP / DIGITAL", 40, 793, bold, 9, green);
      sectionHeading(next, "Evolucion mensual (continuacion)", 755, bold, width);
      monthlyHeader(next, 728, bold);
      rowY = 704;
    }
    const current = doc.getPages().at(-1)!;
    monthlyRow(current, months[index], rowY, index, max, regular, bold);
    rowY -= 20;
  }

  if (matrix.length && rowY > 236) topAccounts(doc.getPages().at(-1)!, matrix, rowY - 12, regular, bold);

  const monthBlocks = Array.from({ length: Math.ceil(data.matrix_months.length / 5) }, (_, index) => data.matrix_months.slice(index * 5, index * 5 + 5));
  let currentMatrixPage: PDFPage | null = null;
  let nextMatrixTop = 510;
  let blocksOnPage = 0;
  for (let block = 0; block < monthBlocks.length; block += 1) {
    for (let start = 0; start < matrix.length; start += 15) {
      const rows = matrix.slice(start, start + 15);
      const requiredHeight = 49 + rows.length * 24 + 27 + 24;
      if (!currentMatrixPage || blocksOnPage >= 2 || nextMatrixTop - requiredHeight < 62) {
        currentMatrixPage = matrixPageHeader(doc, bold);
        nextMatrixTop = 510;
        blocksOnPage = 0;
      }
      nextMatrixTop = matrixBlock(currentMatrixPage, monthBlocks[block], rows, { block: block + 1, blocks: monthBlocks.length, start, totalRows: matrix.length }, nextMatrixTop, regular, bold);
      blocksOnPage += 1;
    }
  }

  const pages = doc.getPages();
  pages.forEach((current, index) => {
    const pageWidth = current.getWidth();
    rule(current, 40, 49, pageWidth - 80);
    drawText(current, "VPO CORP  |  Ingresos digitales  |  Fuente: statements", 40, 31, regular, 8, muted);
    drawRight(current, `Pagina ${index + 1} de ${pages.length}`, pageWidth - 40, 31, regular, 8, muted);
  });

  return doc.save();
}

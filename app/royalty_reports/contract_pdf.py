"""Versioned rendering of the approved VPO contractual executive report."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from scripts import build_executive_royalty_pdf as style


TEMPLATE_VERSION = "contractual-v1"
W, H, M = style.PAGE_W, style.PAGE_H, 28


class ContractPdf:
    def __init__(self, data: dict, snapshot: dict, manifest: dict, request):
        self.data, self.snapshot, self.manifest, self.request = data, snapshot, manifest, request
        self.title = ", ".join(snapshot["artists"])
        months = [month for month, _ in data["monthly"]]
        self.period = style._period_label(request.start_month or min(months), request.end_month or max(months))
        self.partners = sorted([row for row in data["recipients"] if row["partner"]], key=lambda r: (r["artist"] != "Indyana", r["artist"].casefold()))
        self.artists = sorted([row for row in data["recipients"] if not row["partner"]], key=lambda r: (-r["amount"], r["artist"].casefold()))
        self.artist_total = sum(round(row["amount"] * 100) for row in self.artists) / 100
        self.partner_total = sum(round(row["amount"] * 100) for row in self.partners) / 100
        self.artist_chunks = [self.artists[i:i + 44] for i in range(0, len(self.artists), 44)] or [[]]
        self.partner_chunks = [self.partners[i:i + 44] for i in range(0, len(self.partners), 44)] if len(self.partners) > 3 else []
        extras = data["extra_codes"]
        self.pending_chunks = [extras[i:i + 12] for i in range(0, len(extras), 12)] or [[]]
        self.pages = 1 + len(self.partner_chunks) + len(self.artist_chunks) + len(self.pending_chunks)
        self.page = 0

    def text(self, value, x, y, size=9, bold=False, color=None, align="left", width=None):
        font = "VpoSans-Bold" if bold else "VpoSans"
        value = str(value).replace("\ufffd", "").encode("cp1252", "ignore").decode("cp1252")
        if width:
            value = style._ellipsize(self.c, value, width, font, size)
        self.c.setFont(font, size)
        self.c.setFillColor(color or style.INK)
        {"left": self.c.drawString, "right": self.c.drawRightString, "center": self.c.drawCentredString}[align](x, y, value)

    def paragraph(self, value, x, top, width, size=9):
        p = Paragraph(escape(value), ParagraphStyle("contract", fontName="VpoSans", fontSize=size, leading=size * 1.3, textColor=style.MUTED))
        _, height = p.wrap(width, H)
        p.drawOn(self.c, x, top - height)

    def line(self, x1, y, x2):
        self.c.setStrokeColor(style.LINE)
        self.c.setLineWidth(0.6)
        self.c.line(x1, y, x2, y)

    def header(self, subtitle, label, amount, compact=False):
        self.c.setFillColor(style.PAPER)
        self.c.rect(0, 0, W, H, fill=1, stroke=0)
        height = 98 if compact else 118
        self.c.setFillColor(style.NAVY)
        self.c.rect(0, H - height, W, height, fill=1, stroke=0)
        self.c.setFillColor(style.TEAL)
        self.c.rect(0, H - height, 8, height, fill=1, stroke=0)
        logo = Path(__file__).resolve().parents[2] / "web/public/vpo-logo.png"
        if not logo.is_file():
            raise RuntimeError("Falta el logo oficial del informe contractual.")
        self.c.drawImage(str(logo), 36, H - 45, width=66, height=34, preserveAspectRatio=True, mask="auto")
        self.text("VPO CORP  |  ROYALTIES", 115, H - 31, 9, True, style.TEAL_LIGHT)
        # Keep multi-artist headings away from the total; metadata retains the full selection.
        self.text(self.title, 36, H - 66, 23, True, style.WHITE, width=W - 320)
        self.text(subtitle, 36, H - 85, 9.3, color=style.TEAL_LIGHT, width=W - 80)
        if not compact:
            self.text(f"{self.period} | Fecha de statement", 36, H - 103, 9, color=style.TEAL_LIGHT)
        self.text(label, W - 38, H - 34, 9, color=style.TEAL_LIGHT, align="right")
        self.text(style._money(amount), W - 38, H - 70, 28 if not compact else 24, True, style.WHITE, "right")

    def finish(self):
        self.page += 1
        self.text("USD devengados según contratos guardados. No se descuentan pagos anteriores.", M, 24, 7, color=style.MUTED)
        date = datetime.fromisoformat(self.snapshot["captured_at"]).strftime("%d/%m/%Y")
        self.text(f"{date}  |  {self.page} / {self.pages}", W - M, 24, 7, color=style.MUTED, align="right")
        self.c.showPage()

    def overview(self):
        d = self.data
        self.header("Informe ejecutivo de regalías y distribución contractual", "NETO TOTAL", d["total"])
        cards = [(row["artist"].upper(), row["amount"]) for row in self.partners[:3]] + [("ARTISTAS", self.artist_total)]
        width = (W - 2 * M - (len(cards) - 1) * 10) / len(cards)
        for index, (label, amount) in enumerate(cards):
            x = M + index * (width + 10)
            style._rounded_box(self.c, x, 400, width, 66, style.WHITE)
            self.text(label, x + 14, 448, 8, True, style.TEAL, width=width - 28)
            self.text(style._money(amount), x + 14, 424, 18, True)
            self.text("Detalle individual" if label == "ARTISTAS" else "Master + participaciones y retenciones", x + 14, 405, 7.5, color=style.MUTED, width=width - 28)
        self.text(f"{d['catalog_count']} ISRC en catálogo | {d['income_isrc_count']} con ingresos | "
                  f"{len(d['extra_codes'])} ingresos sin asignar | {style._compact_number(d['units'])} unidades | {d['sources']} distribuidoras", M, 388, 8, color=style.MUTED)
        for x, width in [(28, 230), (268, 250), (528, W - 556)]:
            style._rounded_box(self.c, x, 100, width, 278, style.WHITE)
        self.text("Evolución mensual", 44, 350, 12.5, True)
        self.text("Neto reportable por statement", 44, 334, 8, color=style.MUTED)
        style._draw_monthly_chart(self.c, d["monthly"], 44, 151, 198, 159)
        self.text(self.period, 44, 122, 8, color=style.MUTED, width=198)
        self.text("Origen del reparto a socios", 284, 350, 12, True)
        self.text("Incluye contratos internos aplicables", 284, 334, 8, color=style.MUTED)
        names = self.partners[:3]
        xs = [381, 441, 502] if len(names) == 3 else [502 - (len(names) - index - 1) * 75 for index in range(len(names))]
        self.text("Concepto", 284, 306, 7.8, True, style.TEAL)
        for row, x in zip(names, xs):
            self.text(row["artist"], x, 306, 7.8, True, style.TEAL, "right", 58)
        self.line(284, 298, 502)
        project_label = "La Juntada" if self.title == "La Juntada de los Artistas" else "Proyecto"
        for i, label in enumerate(["Master", project_label, "Contratos artistas"]):
            y = 279 - i * 24
            self.text(label, 284, y, 7.6)
            for row, x in zip(names, xs):
                self.text(style._money(row["components"][i]).replace("USD ", ""), x, y, 7.6, align="right")
        self.line(284, 221, 502)
        self.text("Total socios", 284, 200, 9, True)
        self.text(style._money(self.partner_total), 502, 200, 10, True, align="right")
        for y, label, amount in [(176, "Artistas individuales", self.artist_total), (155, "Ingresos sin contrato", d["pending"]), (134, "Total general", d["total"])]:
            self.text(label, 284, y, 8, color=style.MUTED)
            self.text(style._money(amount), 502, y, 8, align="right")
        self.text("Principales temas", 544, 350, 12.5, True)
        self.text("Ingresos antes del reparto contractual", 544, 334, 8, color=style.MUTED)
        for index, row in enumerate(d["tracks"][:5]):
            y = 307 - index * 39
            self.text(row["title"], 544, y, 9, True, width=W - 588)
            self.text(row["isrc"], 544, y - 15, 8, color=style.MUTED)
            self.text(style._money(row["amount_usd"]), W - 44, y - 15, 9, True, align="right")
            if index < 4:
                self.line(544, y - 25, W - 44)
        self.c.setFillColor(style.NAVY_2)
        self.c.roundRect(M, 47, W - 2 * M, 39, 7, fill=1, stroke=0)
        self.text(f"Contratos ISRC: {style._money(d['covered'])}  +  Sin asignar: {style._money(d['pending'])}"
                  f"  =  Neto total: {style._money(d['total'])}", W / 2, 70, 9, True, style.WHITE, "center")
        self.text("Contratos y datos congelados al solicitar el informe. Ingresos sin contrato separados en la conciliación.", W / 2, 55, 8, color=style.TEAL_LIGHT, align="center")
        self.finish()

    def beneficiaries_page(self, rows: list[dict], partners=False):
        self.header(f"Detalle individual de {'socios' if partners else 'artistas'} | {self.period}", "TOTAL SOCIOS" if partners else "TOTAL ARTISTAS", self.partner_total if partners else self.artist_total, True)
        all_rows = self.partners if partners else self.artists
        self.text(f"{len(all_rows)} {'socios' if partners else 'artistas o grupos'} en los contratos.", M, 476, 9, color=style.MUTED)
        self.text("Importes finales tras aplicar el contrato interno del artista cuando está indicado en el ISRC.", M, 460, 9, color=style.MUTED)
        half = math.ceil(len(rows) / 2)
        width = (W - 2 * M - 18) / 2
        for col, group in enumerate([rows[:half], rows[half:]]):
            x = M + col * (width + 18)
            self.c.setFillColor(style.NAVY_2)
            self.c.rect(x, 426, width, 24, fill=1, stroke=0)
            self.text("SOCIO" if partners else "ARTISTA / GRUPO", x + 12, 434, 8.5, True, style.WHITE)
            self.text("REGALÍAS USD", x + width - 12, 434, 8.5, True, style.WHITE, "right")
            for index, row in enumerate(group):
                top = 426 - index * 17
                self.c.setFillColor(style.WHITE if index % 2 == 0 else style.SOFT)
                self.c.rect(x, top - 17, width, 17, fill=1, stroke=0)
                self.text(row["artist"], x + 12, top - 12, 9.2, width=width - 112)
                self.text(style._money(row["amount"]).replace("USD ", ""), x + width - 12, top - 12, 9.2, True, align="right")
        self.text("Los ingresos sin contrato se presentan separados y no integran los importes de socios o artistas.", M, 40, 8, color=style.MUTED)
        self.finish()

    def pending_page(self, rows: list[dict]):
        self.header(f"Observaciones y conciliación | {self.period}", "SIN ASIGNAR", self.data["pending"], True)
        self.text("Ingresos sin reparto contractual asociado", M, 476, 13, True)
        self.text(f"{len(self.data['extra_codes'])} identidades o vigencias pendientes: incluidas en el neto total, no asignadas a beneficiarios.", M, 460, 9, color=style.MUTED)
        self.c.setFillColor(style.NAVY_2)
        self.c.rect(M, 421, W - 2 * M, 24, fill=1, stroke=0)
        for label, x, align in [("IDENTIFICADOR", M + 10, "left"), ("LANZAMIENTO / OBSERVACIÓN", 162, "left"), ("STATEMENT", 637, "left"), ("IMPORTE USD", W - M - 10, "right")]:
            self.text(label, x, 429, 8, True, style.WHITE, align)
        for index, row in enumerate(rows):
            top = 421 - index * 22
            self.c.setFillColor(style.WHITE if index % 2 == 0 else style.SOFT)
            self.c.rect(M, top - 22, W - 2 * M, 22, fill=1, stroke=0)
            self.text("Sin ISRC / UPC" if row["code"].startswith("TEXT:") else row["code"], M + 10, top - 14, 8, width=114)
            title = row["title"].split("#", 1)[0].strip()
            if " / " in title:
                title = title.split(" / ")[0] + " / Enganchado en vivo"
            if row["reason"] != "Sin contrato de ISRC asociado":
                title += " - " + row["reason"]
            self.text(title, 162, top - 14, 8, width=458)
            self.text(", ".join(style._month_label(month, True) for month in row["months"]), 637, top - 14, 7.5, width=90)
            self.text(style._money(row["display_amount"]).replace("USD ", ""), W - M - 10, top - 14, 8, True, align="right")
        self.paragraph("Estos ingresos se conservan separados. No se asignan a una canción por similitud de nombre. Las vigencias sin contrato cerrado no se descartan ni se redistribuyen.", M, 150, W - 2 * M, 9)
        self.text("Base y cálculo", M, 112, 12, True)
        self.paragraph("Misma base neta y descuentos del dashboard; fecha de statement y vigencia del contrato guardado. Un mes se asigna por su primer día. Se consolidan beneficiarios antes de redondear, conservando el total. Los importes son devengados, no saldos después de pagos.", M, 99, W - 2 * M, 8.5)
        self.text(f"Datos publicados: {self.manifest['release_id']} | Plantilla: {TEMPLATE_VERSION}", M, 51, 7, color=style.MUTED)
        self.text("Informe independiente. No modifica los reportes actuales ni es un saldo pendiente de pago.", M, 39, 7.5, color=style.MUTED)
        self.finish()

    def build(self, output: Path) -> Path:
        style._register_fonts()
        pdfmetrics.registerFontFamily("VpoSans", normal="VpoSans", bold="VpoSans-Bold", italic="VpoSans", boldItalic="VpoSans-Bold")
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"Regalias ejecutivas - {style._slug(self.title)} - {self.period} - {self.request.job_id}.pdf"
        self.c = canvas.Canvas(str(path), pagesize=(W, H))
        self.c.setTitle(f"{self.title} - Regalías y reparto contractual - {self.period}")
        self.c.setAuthor("VPO Corp")
        self.overview()
        for rows in self.partner_chunks:
            self.beneficiaries_page(rows, True)
        for rows in self.artist_chunks:
            self.beneficiaries_page(rows)
        for rows in self.pending_chunks:
            self.pending_page(rows)
        self.c.save()
        return path


def build_contractual_pdf(request, job: dict, output_dir: Path):
    from app.royalty_reports.contract_query import query_contract_income
    from app.royalty_reports.contractual import analyze_contractual_income
    from app.royalty_reports.contracts import BuiltReport
    manifest = job["input_manifest"]
    snapshot = manifest["contract_snapshot"]
    income = query_contract_income(request, manifest, job["policy_snapshot"])
    data = analyze_contractual_income(snapshot, income)
    path = ContractPdf(data, snapshot, manifest, request).build(output_dir)
    return BuiltReport(output_path=path, content_type="application/pdf")

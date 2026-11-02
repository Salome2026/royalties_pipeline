"""Individual artist statement using the supplied Indyana layout and frozen contracts."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.royalty_reports.contracts import BuiltReport
from app.royalty_reports.contractual import analyze_contractual_income, beneficiary_key, settle_amounts


TEMPLATE_VERSION = "artist-settlement-v1"
HEADER = Path(__file__).with_name("assets") / "artist_settlement_header.pdf"
WIDTH, HEIGHT = 842, 595
LEFT, RIGHT = 109.375, 732.625
COLS = (LEFT, 429.625, 505.375, 581.125, 656.875, RIGHT)
ROW_HEIGHT = 15.75
MONTHS = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def individual_statement(snapshot: dict, income: list[dict]) -> dict:
    if len(snapshot.get("artists") or []) != 1:
        raise ValueError("La liquidación individual requiere exactamente un artista.")
    artist = snapshot["artists"][0]
    key = beneficiary_key(artist)
    data = analyze_contractual_income(snapshot, income)
    if data["extra_codes"]:
        raise ValueError("Hay ingresos sin contrato cerrado o sin vigencia aplicable. Revisalos antes de emitir la liquidación individual.")
    recipient = next((row for row in data["recipients"] if beneficiary_key(row["artist"]) == key), None)
    if recipient is None:
        raise ValueError("El artista seleccionado no tiene una participación individual en los contratos aplicables.")
    tracks = {row["isrc"]: row for row in data["tracks"]}
    amounts: dict[str, dict] = defaultdict(lambda: {"raw_amount": 0.0, "rates": set(), "all_rates": set(), "participant": False})
    active_isrcs = {row.get("isrc") for row in income}
    for allocation in data["allocations"]:
        shares = [row for row in allocation["shares"] if beneficiary_key(row["artist"]) == key]
        if allocation["isrc"] not in active_isrcs:
            continue
        rate = sum(row["percent"] for row in shares)
        row = amounts[allocation["isrc"]]
        row["participant"] |= bool(shares)
        row["all_rates"].add(round(rate, 10))
        row["raw_amount"] += allocation["amount_usd"] * rate / 100
        # Agreements with no income do not make a fixed contractual rate variable.
        if abs(allocation["amount_usd"]) > 1e-10:
            row["rates"].add(round(rate, 10))
    rows = [{"isrc": isrc, "title": tracks[isrc]["title"], "net": tracks[isrc]["amount_usd"], **values}
            for isrc, values in amounts.items() if values["participant"]]
    rows.sort(key=lambda row: (beneficiary_key(row["title"]), row["isrc"]))
    for row, amount in zip(rows, settle_amounts([row["raw_amount"] for row in rows], recipient["amount"])):
        row["amount"] = amount
        row["effective_percent"] = row["raw_amount"] / row["net"] * 100 if abs(row["net"]) > 1e-10 else None
        rates = row["rates"] or row["all_rates"]
        row["contract_percent"] = next(iter(rates)) if len(rates) == 1 else None
    if not rows:
        raise ValueError("No hay temas con participación individual para el período seleccionado.")
    return {"artist": artist, "rows": rows, "total": recipient["amount"]}


def localized(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def period_label(start: str | None, end: str | None, as_of: str) -> str:
    def month(value: str) -> str:
        return f"{MONTHS[int(value[5:7]) - 1]} {value[:4]}"
    until = end or as_of[:7]
    if start == until:
        return month(until)
    return f"{month(start) if start else 'Fecha de lanzamiento'} - {month(until)}"


class IndividualPdf:
    def __init__(self, data: dict, snapshot: dict, request):
        self.data, self.snapshot, self.request = data, snapshot, request
        self.style = ParagraphStyle("statement-track", fontName="Times-Roman", fontSize=9.75, leading=11.25, textColor=HexColor("#1F2937"))

    def text(self, text: str, x: float, top: float, font="Times-Roman", size=9.75, align="left", color=black, max_width=None):
        if max_width:
            size = min(size, max_width / max(self.c.stringWidth(text, font, 1), 1))
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        draw = {"left": self.c.drawString, "right": self.c.drawRightString, "center": self.c.drawCentredString}[align]
        draw(x, HEIGHT - top, text)

    def line(self, top: float, left=LEFT, right=RIGHT):
        self.c.setStrokeColor(HexColor("#E5EAEA"))
        self.c.setLineWidth(.75)
        self.c.line(left, HEIGHT - top, right, HEIGHT - top)

    def box(self, top: float, height: float, color: str, left=LEFT, right=RIGHT):
        self.c.setFillColor(HexColor(color))
        self.c.rect(left, HEIGHT - top - height, right - left, height, fill=1, stroke=0)

    def field(self, name: str, label: str, left: float, top: float, width: float, maxlen=120):
        self.c.acroForm.textfield(name=name, tooltip=label, value="", x=left, y=HEIGHT-top-14,
            width=width, height=14, fontName="Helvetica", fontSize=9.75, textColor=black,
            borderStyle="underlined", borderWidth=.5, borderColor=HexColor("#BFCFCA"),
            fillColor=white, forceBorder=True, fieldFlags="", annotationFlags="print", maxlen=maxlen)

    def build(self, output_dir: Path) -> Path:
        from scripts.build_executive_royalty_pdf import _slug
        overlay = BytesIO()
        self.c = canvas.Canvas(overlay, pagesize=(WIDTH, HEIGHT))
        chunks, chunk, used = [], [], 0.0
        for row in self.data["rows"]:
            paragraph = Paragraph(escape(row["title"]), self.style)
            _, height = paragraph.wrap(COLS[1]-COLS[0]-6, 500)
            height = max(ROW_HEIGHT, height + 4.5)
            if height > 280:
                raise ValueError("El título de un tema es demasiado largo para la liquidación.")
            if chunk and used + height > 280:
                chunks.append(chunk); chunk, used = [], 0.0
            chunk.append((row, paragraph, height)); used += height
        if chunk:
            chunks.append(chunk)
        for page_index, rows in enumerate(chunks):
            label = f"Período : {period_label(self.request.start_month, self.request.end_month, self.snapshot['as_of'])}"
            self.text(label, 112.375, 160.82, "Helvetica", 10)
            artist_label = "Artista : " + self.data["artist"]
            artist_size = min(10, 198 / max(self.c.stringWidth(artist_label, "Helvetica", 1), 1))
            self.text(artist_label, 532.375, 160.82, "Helvetica", artist_size)
            top = 207.75
            for index, (row, paragraph, height) in enumerate(rows):
                self.box(top, height, "#F6FAF9" if index % 2 == 0 else "#FFFFFF")
                paragraph.drawOn(self.c, 112.375, HEIGHT-top-2.25-paragraph.height)
                self.text("$" + localized(row["net"]), 502.375, top+11.39, color=HexColor("#1F2937"), align="right", max_width=70)
                self.text("$" + localized(row["amount"]), 578.125, top+11.39, color=HexColor("#1F2937"), align="right", max_width=70)
                effective = localized(row["effective_percent"])+"%" if row["effective_percent"] is not None else "-"
                contractual = localized(row["contract_percent"])+"%" if row["contract_percent"] is not None else "Variable"
                self.text(effective, 618.75, top+11.39, align="center")
                self.text(contractual, 694.5, top+11.39, align="center")
                top += height
                self.line(top-.375)
            # The supplied one-track form keeps three empty rows before its total.
            for index in range(max(0, 4-len(rows))):
                self.box(top, ROW_HEIGHT, "#F6FAF9" if (len(rows)+index)%2 == 0 else "#FFFFFF")
                top += ROW_HEIGHT
                self.line(top-.375)
            last = page_index == len(chunks)-1
            if last:
                self.box(top, 16.5, "#D0E0E3", right=581.125)
                self.box(top, 16.5, "#F6FAF9", left=581.125)
                self.text("Total del artista en el período", 502.375, top+12.18, "Helvetica-Bold", 9.75, "right", HexColor("#315D5A"))
                self.text("$"+localized(self.data["total"]), 578.125, top+11.93, "Times-Bold", 10.725, "right", HexColor("#173B3A"), max_width=70)
                self.line(top); self.line(top+16.125)
                top += 16.5
                self.line(top+15.375); self.line(top+31.875)
                self.text("ORDEN DE PAGO A NOMBRE DE :", 227, top+27.32, "Helvetica", 10)
                self.field("nombre_cobro", "Nombre completo para el cobro", 394, top+15, 172)
                self.text(", DNI", 570, top+27.32, "Helvetica", 10)
                self.field("dni_cobro", "DNI para el cobro", 601, top+15, 105, 30)
                self.text("Correo electrónico :", 335, top+43.82, "Helvetica", 10)
                self.field("correo_cobro", "Correo electrónico para el cobro", 429, top+31.5, 277, 160)
            captured = datetime.fromisoformat(self.snapshot["captured_at"]).astimezone(ZoneInfo("America/New_York"))
            self.text(captured.strftime("%d/%m/%Y"), 21.6, 572.8, "Helvetica", 9.75)
            self.text(str(page_index+1), 820.35, 572.8, "Helvetica", 9.75, "right")
            self.c.showPage()
        self.c.save()
        overlay.seek(0)
        writer = PdfWriter()
        writer.append(PdfReader(overlay), import_outline=False)
        background = PdfReader(HEADER).pages[0]
        for page in writer.pages:
            page.merge_page(background, over=False)
        writer.add_metadata({"/Title": f"Liquidación de regalías - {self.data['artist']}",
            "/Author": "INDYANA RECORDS LLC", "/Subject": TEMPLATE_VERSION})
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"Liquidacion - {_slug(self.data['artist'])} - {self.request.end_month or self.snapshot['as_of'][:7]} - {self.request.job_id}.pdf"
        with path.open("wb") as stream:
            writer.write(stream)
        return path


def build_individual_pdf(request, job: dict, output_dir: Path) -> BuiltReport:
    from app.royalty_reports.contract_query import query_contract_income
    manifest = job["input_manifest"]
    snapshot = manifest["contract_snapshot"]
    income = query_contract_income(request, manifest, job["policy_snapshot"])
    data = individual_statement(snapshot, income)
    return BuiltReport(output_path=IndividualPdf(data, snapshot, request).build(output_dir), content_type="application/pdf")

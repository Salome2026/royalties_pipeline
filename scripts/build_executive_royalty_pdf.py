from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


PAGE_W, PAGE_H = landscape(A4)

NAVY = HexColor("#102733")
NAVY_2 = HexColor("#173B48")
TEAL = HexColor("#2F8A84")
TEAL_LIGHT = HexColor("#DDEDEA")
INK = HexColor("#17313B")
MUTED = HexColor("#63777F")
LINE = HexColor("#D7E0E3")
PAPER = HexColor("#F3F6F6")
WHITE = HexColor("#FFFFFF")
SOFT = HexColor("#E8EEEF")
ACCENT = HexColor("#E0A458")

MONTHS = {
    "01": "ENE",
    "02": "FEB",
    "03": "MAR",
    "04": "ABR",
    "05": "MAY",
    "06": "JUN",
    "07": "JUL",
    "08": "AGO",
    "09": "SEP",
    "10": "OCT",
    "11": "NOV",
    "12": "DIC",
}


def _register_fonts() -> None:
    # Standard PDF fonts keep this renderer portable between Windows and Cloud Run.
    pdfmetrics.registerFont(pdfmetrics.Font("VpoSans", "Helvetica", "WinAnsiEncoding"))
    pdfmetrics.registerFont(pdfmetrics.Font("VpoSans-Bold", "Helvetica-Bold", "WinAnsiEncoding"))


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    text = f"{abs(value):,.2f}"
    localized = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}USD {localized}"


def _compact_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f} M".replace(".", ",")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f} K".replace(".", ",")
    return f"{value:,.0f}".replace(",", ".")


def _percentage(value: float) -> str:
    return f"{value:.1f}%".replace(".", ",")


def _safe_text(value: object, fallback: str = "-") -> str:
    text = str(value or "").replace("\ufffd", "").strip()
    return text or fallback


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")[:70] or "todas"


def _month_label(value: str, include_year: bool = False) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", value or ""):
        return value or "-"
    month = MONTHS.get(value[-2:], value[-2:])
    return f"{month} {value[:4]}" if include_year else month


def _period_label(start_month: str | None, end_month: str | None) -> str:
    if not start_month and not end_month:
        return "Todo el historico"
    start = start_month or end_month or ""
    end = end_month or start_month or ""
    if start == end:
        return _month_label(start, include_year=True)
    return f"{_month_label(start, include_year=True)} - {_month_label(end, include_year=True)}"


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _number(frame: pd.DataFrame, row: int, *names: str) -> float:
    column = _column(frame, *names)
    if column is None or frame.empty:
        return 0.0
    value = pd.to_numeric(pd.Series([frame.iloc[row][column]]), errors="coerce").iloc[0]
    return float(value) if pd.notna(value) else 0.0


def _rounded_box(c: canvas.Canvas, x: float, y: float, w: float, h: float, fill, radius: float = 8) -> None:
    c.setFillColor(fill)
    c.roundRect(x, y, w, h, radius, stroke=0, fill=1)


def _label(c: canvas.Canvas, text: str, x: float, y: float, size: float = 8.5, color=MUTED) -> None:
    c.setFont("VpoSans", size)
    c.setFillColor(color)
    c.drawString(x, y, text)


def _value(c: canvas.Canvas, text: str, x: float, y: float, size: float = 17, color=INK) -> None:
    c.setFont("VpoSans-Bold", size)
    c.setFillColor(color)
    c.drawString(x, y, text)


def _ellipsize(c: canvas.Canvas, text: str, max_width: float, font: str, size: float) -> str:
    if c.stringWidth(text, font, size) <= max_width:
        return text
    candidate = text
    while candidate and c.stringWidth(candidate + "...", font, size) > max_width:
        candidate = candidate[:-1]
    return candidate.rstrip() + "..."


def _monthly_rows(frame: pd.DataFrame) -> list[tuple[str, float]]:
    if frame.empty:
        return []
    month_col = _column(frame, "Mes", "period_month", "month")
    amount_col = _column(frame, "Ingresos USD", "amount_usd")
    if not month_col or not amount_col:
        return []
    grouped = frame[[month_col, amount_col]].copy()
    grouped[amount_col] = pd.to_numeric(grouped[amount_col], errors="coerce").fillna(0.0)
    grouped = grouped.groupby(month_col, as_index=False)[amount_col].sum().sort_values(month_col)
    return [(_safe_text(row[month_col]), float(row[amount_col])) for _, row in grouped.iterrows()]


def _dsp_rows(frame: pd.DataFrame, total: float) -> list[tuple[str, float, float]]:
    if frame.empty:
        return []
    dsp_col = _column(frame, "DSP / Store", "dsp_normalized", "Store normalizado")
    amount_col = _column(frame, "Ingresos USD", "amount_usd")
    if not dsp_col or not amount_col:
        return []
    grouped = frame[[dsp_col, amount_col]].copy()
    grouped[dsp_col] = grouped[dsp_col].fillna("Otros").astype(str)
    grouped[amount_col] = pd.to_numeric(grouped[amount_col], errors="coerce").fillna(0.0)
    grouped = grouped.groupby(dsp_col, as_index=False)[amount_col].sum().sort_values(amount_col, ascending=False)
    top = [(_safe_text(row[dsp_col], "Otros"), float(row[amount_col])) for _, row in grouped.head(5).iterrows()]
    remainder = float(grouped.iloc[5:][amount_col].sum()) if len(grouped) > 5 else 0.0
    if abs(remainder) > 0.000001:
        top.append(("Otros", remainder))
    return [(name, amount, (amount / total * 100) if total else 0.0) for name, amount in top]


def _track_rows(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    title_col = _column(frame, "Tema", "track_statement_style")
    artist_col = _column(frame, "Artista", "artist_statement_style")
    code_col = _column(frame, "Codigo", "report_code")
    amount_col = _column(frame, "Ingresos USD", "amount_usd")
    if not title_col or not amount_col:
        return []
    ranked = frame.copy()
    ranked[amount_col] = pd.to_numeric(ranked[amount_col], errors="coerce").fillna(0.0)
    ranked = ranked.sort_values(amount_col, ascending=False).head(5)
    return [
        {
            "title": _safe_text(row[title_col], "Sin titulo"),
            "artist": _safe_text(row[artist_col], "") if artist_col else "",
            "code": _safe_text(row[code_col], "") if code_col else "",
            "amount": float(row[amount_col]),
        }
        for _, row in ranked.iterrows()
    ]


def _draw_monthly_chart(c: canvas.Canvas, rows: list[tuple[str, float]], x: float, y: float, w: float, h: float) -> None:
    if not rows:
        _label(c, "Sin datos mensuales", x + 8, y + h / 2, 9)
        return

    plot_x = x + 8
    plot_y = y + 25
    plot_w = w - 16
    plot_h = h - 40
    amounts = [amount for _, amount in rows]
    min_value = min(0.0, min(amounts))
    max_value = max(0.0, max(amounts))
    if math.isclose(min_value, max_value):
        max_value = min_value + 1.0

    def value_y(amount: float) -> float:
        return plot_y + (amount - min_value) / (max_value - min_value) * plot_h

    zero_y = value_y(0.0)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(plot_x, zero_y, plot_x + plot_w, zero_y)

    if len(rows) == 1:
        amount = rows[0][1]
        target_y = value_y(amount)
        bottom = min(zero_y, target_y)
        height = max(5, abs(target_y - zero_y))
        c.setFillColor(TEAL if amount >= 0 else ACCENT)
        c.roundRect(plot_x + plot_w * 0.34, bottom, plot_w * 0.32, height, 5, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont("VpoSans-Bold", 8)
        c.drawCentredString(plot_x + plot_w / 2, min(y + h - 4, max(zero_y, target_y) + 10), _money(amount))
        c.setFont("VpoSans", 7.5)
        c.setFillColor(MUTED)
        c.drawCentredString(plot_x + plot_w / 2, y + 5, _month_label(rows[0][0], include_year=True))
        return

    step = plot_w / max(1, len(rows) - 1)
    points = [(plot_x + index * step, value_y(amount)) for index, (_, amount) in enumerate(rows)]
    c.setStrokeColor(TEAL)
    c.setLineWidth(2.2)
    path = c.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    c.drawPath(path, stroke=1, fill=0)

    point_indexes = {0, len(points) - 1, max(range(len(amounts)), key=lambda idx: amounts[idx])}
    for index, (point_x, point_y) in enumerate(points):
        c.setFillColor(TEAL if amounts[index] >= 0 else ACCENT)
        c.circle(point_x, point_y, 2.6, stroke=0, fill=1)
        if index in point_indexes:
            c.setFont("VpoSans-Bold", 6.7)
            c.setFillColor(INK)
            label_y = point_y + 7 if amounts[index] >= 0 else point_y - 12
            c.drawCentredString(point_x, label_y, _money(amounts[index]))

    tick_step = max(1, math.ceil(len(rows) / 6))
    tick_indexes = list(range(0, len(rows), tick_step))
    if len(rows) - 1 not in tick_indexes:
        tick_indexes.append(len(rows) - 1)
    for index in tick_indexes:
        c.setFont("VpoSans", 6.5)
        c.setFillColor(MUTED)
        c.drawCentredString(points[index][0], y + 5, _month_label(rows[index][0], include_year=len(rows) > 12))


def build_executive_royalty_pdf(
    *,
    tables: dict[str, pd.DataFrame],
    output_dir: Path,
    scope_label: str,
    keywords: list[str],
    period_basis: str,
    start_month: str | None,
    end_month: str | None,
) -> Path:
    _register_fonts()
    general = tables.get("resumen general", pd.DataFrame())
    monthly = tables.get("resumen mensual", pd.DataFrame())
    stores = tables.get("resumen por store", pd.DataFrame())
    territories = tables.get("resumen por territorio", pd.DataFrame())
    tracks = tables.get("resumen por tema", pd.DataFrame())

    total = _number(general, 0, "Ingresos USD", "song_level_amount_usd")
    units = _number(general, 0, "Unidades", "song_level_units")
    if general.empty or abs(total) < 0.0000001:
        raise ValueError("No hay ingresos netos para los filtros seleccionados.")

    monthly_rows = _monthly_rows(monthly)
    dsp_rows = _dsp_rows(stores, total)
    track_rows = _track_rows(tracks)
    actual_start = monthly_rows[0][0] if monthly_rows else start_month
    actual_end = monthly_rows[-1][0] if monthly_rows else end_month
    effective_start = start_month or actual_start
    effective_end = end_month or actual_end

    artist_col = _column(tracks, "Artista", "artist_statement_style")
    artist_count = int(tracks[artist_col].dropna().astype(str).str.strip().replace("", pd.NA).dropna().nunique()) if artist_col else 0
    territory_count = len(territories.index)
    title_count = len(tracks.index)

    filter_label = ", ".join(keywords).strip()
    filename_scope = "_".join([scope_label, filter_label]) if filter_label else scope_label
    period_slug = f"{effective_start or 'inicio'}_a_{effective_end or 'fin'}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (
        f"regalias_ejecutivo_{_slug(filename_scope)}_{_slug(period_slug)}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    c = canvas.Canvas(str(output_path), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Regalias - {scope_label}")
    c.setAuthor("VPO Corp")

    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - 118, PAGE_W, 118, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.rect(0, PAGE_H - 118, 8, 118, stroke=0, fill=1)

    c.setFont("VpoSans-Bold", 9)
    c.setFillColor(TEAL_LIGHT)
    c.drawString(36, PAGE_H - 31, "VPO CORP  |  ROYALTIES")
    c.setFont("VpoSans-Bold", 22)
    c.setFillColor(WHITE)
    c.drawString(36, PAGE_H - 62, _ellipsize(c, scope_label.upper(), 490, "VpoSans-Bold", 22))
    c.setFont("VpoSans", 9.5)
    c.setFillColor(TEAL_LIGHT)
    c.drawString(36, PAGE_H - 82, "Resumen ejecutivo de regalias netas")
    basis_label = "Statements" if period_basis == "statement_period" else "Consumos"
    subtitle = f"{basis_label}: {_period_label(effective_start, effective_end)}"
    if filter_label:
        subtitle += f"  |  Filtro: {filter_label}"
    c.drawString(36, PAGE_H - 99, _ellipsize(c, subtitle, 540, "VpoSans", 9.5))

    c.setFont("VpoSans", 9)
    c.setFillColor(TEAL_LIGHT)
    c.drawRightString(PAGE_W - 38, PAGE_H - 34, "NETO TOTAL")
    c.setFont("VpoSans-Bold", 29)
    c.setFillColor(WHITE)
    c.drawRightString(PAGE_W - 38, PAGE_H - 70, _money(total))
    c.setFont("VpoSans", 8.5)
    c.setFillColor(TEAL_LIGHT)
    c.drawRightString(PAGE_W - 38, PAGE_H - 91, "capa de negocio vigente")

    card_y, card_h, gap = 400, 66, 10
    margin = 28
    card_w = (PAGE_W - 2 * margin - 3 * gap) / 4
    kpis = [
        ("PERIODO INFORMADO", _period_label(effective_start, effective_end), f"Base: {basis_label.lower()}"),
        ("UNIDADES", _compact_number(units), "reproducciones y usos"),
        ("CATALOGO CON INGRESOS", f"{title_count} temas", "identidades consolidadas"),
        ("ALCANCE", f"{artist_count} artistas", f"{territory_count} territorios"),
    ]
    for index, (heading, main, detail) in enumerate(kpis):
        x = margin + index * (card_w + gap)
        _rounded_box(c, x, card_y, card_w, card_h, WHITE)
        _label(c, heading, x + 14, card_y + 47, 7.4, TEAL)
        _value(c, _ellipsize(c, main, card_w - 28, "VpoSans-Bold", 15), x + 14, card_y + 25, 15)
        _label(c, detail, x + 14, card_y + 10, 8)

    panel_y, panel_h = 92, 290
    left_x, left_w = 28, 230
    middle_x, middle_w = 268, 250
    right_x, right_w = 528, PAGE_W - 528 - 28
    for x, width in [(left_x, left_w), (middle_x, middle_w), (right_x, right_w)]:
        _rounded_box(c, x, panel_y, width, panel_h, WHITE)

    _value(c, "Evolucion mensual", left_x + 16, panel_y + panel_h - 28, 12.5)
    _label(c, f"Neto por mes de {basis_label.lower()}", left_x + 16, panel_y + panel_h - 44, 8)
    _draw_monthly_chart(c, monthly_rows, left_x + 16, panel_y + 32, left_w - 32, panel_h - 96)

    _value(c, "Plataformas", middle_x + 16, panel_y + panel_h - 28, 12.5)
    _label(c, "Participacion sobre el neto", middle_x + 16, panel_y + panel_h - 44, 8)
    row_y = panel_y + panel_h - 76
    max_dsp = max([abs(amount) for _, amount, _ in dsp_rows] or [1.0])
    for name, amount, pct in dsp_rows[:6]:
        c.setFont("VpoSans-Bold", 8.2)
        c.setFillColor(INK)
        c.drawString(middle_x + 16, row_y, _ellipsize(c, name, 95, "VpoSans-Bold", 8.2))
        c.setFont("VpoSans", 8)
        c.setFillColor(MUTED)
        c.drawRightString(middle_x + middle_w - 16, row_y, f"{_money(amount)}  |  {_percentage(pct)}")
        bar_y = row_y - 11
        c.setFillColor(SOFT)
        c.roundRect(middle_x + 16, bar_y, middle_w - 32, 6, 3, stroke=0, fill=1)
        c.setFillColor(TEAL if amount >= 0 and name != "Otros" else ACCENT)
        c.roundRect(middle_x + 16, bar_y, (middle_w - 32) * abs(amount) / max_dsp, 6, 3, stroke=0, fill=1)
        row_y -= 36

    _value(c, "Principales temas", right_x + 16, panel_y + panel_h - 28, 12.5)
    _label(c, "Identidad consolidada del catalogo", right_x + 16, panel_y + panel_h - 44, 8)
    row_y = panel_y + panel_h - 77
    for index, row in enumerate(track_rows, start=1):
        c.setFillColor(TEAL_LIGHT)
        c.circle(right_x + 25, row_y + 2, 10, stroke=0, fill=1)
        c.setFillColor(TEAL)
        c.setFont("VpoSans-Bold", 8)
        c.drawCentredString(right_x + 25, row_y - 1, str(index))
        c.setFillColor(INK)
        c.setFont("VpoSans-Bold", 8.7)
        c.drawString(right_x + 43, row_y + 4, _ellipsize(c, row["title"], right_w - 126, "VpoSans-Bold", 8.7))
        detail = " | ".join(part for part in [row["artist"], row["code"]] if part)
        c.setFont("VpoSans", 7.2)
        c.setFillColor(MUTED)
        c.drawString(right_x + 43, row_y - 10, _ellipsize(c, detail, right_w - 126, "VpoSans", 7.2))
        c.setFont("VpoSans-Bold", 8.7)
        c.setFillColor(INK)
        c.drawRightString(right_x + right_w - 16, row_y + 1, _money(row["amount"]))
        if index < len(track_rows):
            c.setStrokeColor(LINE)
            c.setLineWidth(0.6)
            c.line(right_x + 16, row_y - 23, right_x + right_w - 16, row_y - 23)
        row_y -= 43

    highest_month = max(monthly_rows, key=lambda item: item[1]) if monthly_rows else ("-", 0.0)
    top_two_pct = sum(item[2] for item in dsp_rows[:2])
    insight = (
        f"Mayor mes: {_month_label(highest_month[0], include_year=True)} ({_money(highest_month[1])}). "
        f"Las dos plataformas principales representan {_percentage(top_two_pct)} del neto."
    )
    c.setFillColor(NAVY_2)
    c.roundRect(28, 48, PAGE_W - 56, 30, 7, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("VpoSans-Bold", 8.5)
    c.drawCentredString(PAGE_W / 2, 59, _ellipsize(c, insight, PAGE_W - 90, "VpoSans-Bold", 8.5))

    c.setFont("VpoSans", 6.8)
    c.setFillColor(MUTED)
    c.drawString(28, 25, "Fuente: statements de distribuidoras. Neto reportable en USD; sin bruto ni columnas tecnicas.")
    c.drawRightString(PAGE_W - 28, 25, f"Emitido: {datetime.now().strftime('%d/%m/%Y')}")

    c.showPage()
    c.save()
    return output_path

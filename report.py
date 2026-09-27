"""Render the season summary as a shareable PDF."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#14202e")
ACCENT = colors.HexColor("#1f6f4a")
MUTED = colors.HexColor("#6b7a8c")
RULE = colors.HexColor("#d7dee6")
BAND = colors.HexColor("#f2f5f8")

PAGE = landscape(A4)
CONTENT_WIDTH = PAGE[0] - 24 * mm

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], fontSize=20, textColor=INK, spaceAfter=2, alignment=0)
SUB = ParagraphStyle("SUB", parent=styles["Normal"], fontSize=9.5, textColor=MUTED, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=5)
BOARD = ParagraphStyle("BOARD", parent=styles["Normal"], fontSize=8.5, textColor=ACCENT, spaceAfter=3)
CELL = ParagraphStyle("CELL", parent=styles["Normal"], fontSize=7.6, textColor=INK, leading=9.5)
NOTE = ParagraphStyle("NOTE", parent=styles["Normal"], fontSize=7.5, textColor=MUTED)
BIGLABEL = ParagraphStyle("BIGLABEL", parent=styles["Normal"], fontSize=7, textColor=MUTED, alignment=TA_CENTER)
BIGVALUE = ParagraphStyle("BIGVALUE", parent=styles["Normal"], fontSize=16, textColor=INK, alignment=TA_CENTER, leading=19)
RECLABEL = ParagraphStyle("RECLABEL", parent=styles["Normal"], fontSize=7, textColor=MUTED)
RECVALUE = ParagraphStyle("RECVALUE", parent=styles["Normal"], fontSize=12.5, textColor=INK, leading=15)
RECDETAIL = ParagraphStyle("RECDETAIL", parent=styles["Normal"], fontSize=7.2, textColor=MUTED, leading=9)


def _grid_style(header: bool = True) -> TableStyle:
    commands = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.6),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        commands += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), BAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ]
    return TableStyle(commands)


def _data_table(df: pd.DataFrame, width: float, align_right_from: int = 1) -> Table:
    body = [[str(c) for c in df.columns]] + df.astype(str).values.tolist()
    table = Table(body, colWidths=[width / len(df.columns)] * len(df.columns), hAlign="LEFT")
    style = _grid_style()
    style.add("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT")
    table.setStyle(style)
    return table


def _headline(items: list[tuple[str, str]]) -> Table:
    cells = [
        [Paragraph(str(value), BIGVALUE), Paragraph(label.upper(), BIGLABEL)]
        for label, value in items
    ]
    stacks = [Table([[c[0]], [c[1]]], style=TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ])) for c in cells]

    table = Table([stacks], colWidths=[CONTENT_WIDTH / len(stacks)] * len(stacks), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, RULE),
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _records(items: list[tuple[str, str, str]], per_row: int = 3) -> list:
    flow = []
    for start in range(0, len(items), per_row):
        chunk = items[start:start + per_row]
        cells = []
        for label, value, detail in chunk:
            inner = Table(
                [[Paragraph(label.upper(), RECLABEL)], [Paragraph(value, RECVALUE)], [Paragraph(detail, RECDETAIL)]],
                style=TableStyle([
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ]),
            )
            cells.append(inner)
        cells += [""] * (per_row - len(cells))

        table = Table([cells], colWidths=[CONTENT_WIDTH / per_row] * per_row, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, RULE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        flow += [table, Spacer(1, 4)]
    return flow


def _boards(boards: list[tuple[str, pd.DataFrame]], per_row: int = 3) -> list:
    flow = []
    for start in range(0, len(boards), per_row):
        chunk = boards[start:start + per_row]
        column_width = CONTENT_WIDTH / per_row
        cells = []
        for title, df in chunk:
            inner = [Paragraph(title, BOARD)]
            if df is None or df.empty:
                inner.append(Paragraph("No qualifying players", NOTE))
            else:
                inner.append(_data_table(df, column_width - 10))
            cells.append(Table([[i] for i in inner], style=TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ])))
        cells += [""] * (per_row - len(cells))

        row = Table([cells], colWidths=[column_width] * per_row, hAlign="LEFT")
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        flow += [KeepTogether(row), Spacer(1, 8)]
    return flow


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(12 * mm, 8 * mm, doc.subject or "")
    canvas.drawRightString(PAGE[0] - 12 * mm, 8 * mm, f"Page {canvas.getPageNumber()}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(12 * mm, 11 * mm, PAGE[0] - 12 * mm, 11 * mm)
    canvas.restoreState()


def build_pdf(ctx: dict) -> bytes:
    """ctx: title, subtitle, headline, records, sections, results."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=14 * mm,
        title=ctx["title"], subject=ctx["subtitle"], author="Weekend Wickets",
    )

    flow = [
        Paragraph(ctx["title"], H1),
        Paragraph(ctx["subtitle"], SUB),
        _headline(ctx["headline"]),
        Spacer(1, 10),
        Paragraph("Season Records", H2),
    ]
    flow += _records(ctx["records"])

    for name, boards in ctx["sections"]:
        flow.append(Paragraph(name, H2))
        flow += _boards(boards)

    results = ctx.get("results")
    if results is not None and not results.empty:
        flow += [PageBreak(), Paragraph("Match Results", H2), _data_table(results, CONTENT_WIDTH, align_right_from=3)]

    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()

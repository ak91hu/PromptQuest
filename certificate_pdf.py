"""Vector completion certificate with an orbital illustration and embedded fonts."""

import math
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from challenges import LEVELS
from mission_pdf import text

INK = colors.HexColor("#152b3b")
MUTED = colors.HexColor("#536773")
GOLD = colors.HexColor("#956625")
MINT = colors.HexColor("#bcefe0")
PAPER = colors.HexColor("#faf9f4")


def _label(canvas, value, x, y, *, color=MUTED, size=8, tracking=1.2):
    canvas.saveState()
    canvas.setFillColor(color)
    label = canvas.beginText(x, y)
    label.setFont("NotoBold", size)
    label.setCharSpace(tracking)
    label.textOut(value)
    canvas.drawText(label)
    canvas.restoreState()


def _paragraph(canvas, value, x, top, width, *, size=12, bold=False, color=INK, max_height=None):
    while True:
        paragraph = Paragraph(
            text(value),
            ParagraphStyle(
                "certificate",
                fontName="NotoBold" if bold else "Noto",
                fontSize=size,
                leading=size * 1.25,
                textColor=color,
                splitLongWords=True,
            ),
        )
        _, height = paragraph.wrap(width, 100 * mm)
        if max_height is None or height <= max_height:
            break
        size -= 0.5
        if size < 12:
            raise ValueError("Certificate name exceeds the supported layout.")
    paragraph.drawOn(canvas, x, top - height)


def _station(canvas, x, y):
    """Draw a segmented orbital ring, command spine and docking arms."""
    canvas.saveState()
    canvas.translate(x, y)
    canvas.rotate(-24)
    canvas.setStrokeColor(colors.HexColor("#365164"))
    canvas.setLineWidth(0.65)
    for radius in (33, 37, 42):
        canvas.ellipse(-radius * mm, -radius * 0.65 * mm, radius * mm, radius * 0.65 * mm)
    canvas.setStrokeColor(MINT)
    canvas.setLineWidth(2.5)
    canvas.ellipse(-27 * mm, -18 * mm, 27 * mm, 18 * mm)
    canvas.setStrokeColor(colors.HexColor("#74a6aa"))
    canvas.setLineWidth(0.65)
    for index in range(len(LEVELS)):
        angle = index * math.tau / len(LEVELS)
        inner = (24 * math.cos(angle) * mm, 16 * math.sin(angle) * mm)
        outer = (30 * math.cos(angle) * mm, 20 * math.sin(angle) * mm)
        canvas.line(*inner, *outer)
    for angle in range(0, 360, 60):
        radians = math.radians(angle)
        canvas.line(0, 0, 27 * math.cos(radians) * mm, 18 * math.sin(radians) * mm)
    canvas.setFillColor(INK)
    canvas.setStrokeColor(MINT)
    canvas.roundRect(-4 * mm, -32 * mm, 8 * mm, 64 * mm, 2 * mm, fill=1)
    canvas.roundRect(-8 * mm, -6 * mm, 16 * mm, 12 * mm, 2 * mm, fill=1)
    canvas.circle(0, 0, 3 * mm, fill=0, stroke=1)
    canvas.setStrokeColor(colors.HexColor("#deb875"))
    canvas.setLineWidth(1.1)
    canvas.line(-2 * mm, 0, 2 * mm, 0)
    canvas.line(0, -2 * mm, 0, 2 * mm)
    canvas.restoreState()


def _seal(canvas, x, y):
    canvas.saveState()
    canvas.translate(x, y)
    canvas.setStrokeColor(colors.HexColor("#d6b67c"))
    canvas.setLineWidth(0.8)
    canvas.circle(0, 0, 18 * mm)
    canvas.circle(0, 0, 15.8 * mm)
    for index in range(len(LEVELS)):
        angle = index * math.tau / len(LEVELS)
        canvas.line(
            19.5 * math.cos(angle) * mm,
            19.5 * math.sin(angle) * mm,
            21 * math.cos(angle) * mm,
            21 * math.sin(angle) * mm,
        )
    canvas.setFillColor(MINT)
    canvas.setFont("NotoBold", 20)
    canvas.drawCentredString(0, 0, f"{len(LEVELS)} / {len(LEVELS)}")
    canvas.setFont("Noto", 6.5)
    canvas.drawCentredString(0, -6 * mm, "SYSTEMS RECOVERED")
    canvas.restoreState()


def render_certificate(report: dict, issued_at: datetime | None = None) -> bytes:
    if len(report["rooms"]) != len(LEVELS) or not all(room["solved"] for room in report["rooms"]):
        raise ValueError(f"All {len(LEVELS)} stations must be recovered for a certificate.")
    issued_at = issued_at or datetime.now(timezone.utc)
    output = BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    canvas.setTitle("HackTheAI - Asterion completion certificate")
    canvas.setAuthor("HackTheAI")
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    canvas.setFillColor(INK)
    canvas.rect(0, 0, 90 * mm, height, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#203b4b"))
    canvas.rect(0, 0, 3 * mm, height, stroke=0, fill=1)
    canvas.setStrokeColor(colors.HexColor("#d9dfd8"))
    canvas.setLineWidth(0.6)
    canvas.rect(102 * mm, 13 * mm, width - 115 * mm, height - 26 * mm)
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(2)
    canvas.line(110 * mm, 186 * mm, 132 * mm, 186 * mm)
    _label(
        canvas,
        f"FLIGHT RECORD // {len(LEVELS):03d}",
        17 * mm,
        188 * mm,
        color=MINT,
        size=7,
        tracking=1,
    )
    _paragraph(canvas, "ASTERION", 17 * mm, 174 * mm, 70 * mm, size=26, bold=True, color=PAPER)
    _label(canvas, "PROTOCOL", 18 * mm, 155 * mm, color=MINT, size=9, tracking=3)
    _station(canvas, 45 * mm, 116 * mm)
    _seal(canvas, 45 * mm, 48 * mm)
    _label(canvas, "MISSION COMPLETE", 20 * mm, 17 * mm, color=MINT, size=7, tracking=1)
    x = 112 * mm
    content_width = 165 * mm
    _label(canvas, "HACKTHEAI / ORBITAL SECURITY PUZZLE", x, 175 * mm, size=7, tracking=1)
    _paragraph(canvas, "CERTIFICATE", x, 166 * mm, content_width, size=33, bold=True)
    _label(canvas, "OF COMPLETION", x, 146 * mm, color=GOLD, size=11, tracking=2.5)
    _label(canvas, "AWARDED TO", x, 128 * mm, size=7, tracking=1.5)
    _paragraph(
        canvas, report["team"], x, 121 * mm, content_width, size=29, bold=True, max_height=22 * mm
    )
    canvas.setStrokeColor(colors.HexColor("#cfd8d2"))
    canvas.setLineWidth(0.6)
    canvas.line(x, 95 * mm, 277 * mm, 95 * mm)
    _paragraph(
        canvas,
        f"Completed all {len(LEVELS)} Asterion challenges by identifying how each guard follows instructions and where its checks fail.",
        x,
        88 * mm,
        content_width,
        size=11,
        color=MUTED,
    )
    _label(canvas, "MISSION SCORE", x, 60 * mm, size=7)
    _paragraph(
        canvas,
        f"{report['score']} / {report['max_score']}",
        x,
        55 * mm,
        70 * mm,
        size=27,
        bold=True,
        color=GOLD,
    )
    _label(canvas, "CHALLENGES", 197 * mm, 60 * mm, size=7)
    _paragraph(canvas, f"{len(LEVELS)} completed", 197 * mm, 53 * mm, 80 * mm, size=13, bold=True)
    _label(canvas, "ISSUED", 197 * mm, 39 * mm, size=7)
    _paragraph(canvas, issued_at.strftime("%d %b %Y"), 197 * mm, 34 * mm, 80 * mm, size=10)
    _label(
        canvas,
        "READ THE TASK. TEST THE IDEA. CHECK THE RESULT.",
        x,
        18 * mm,
        size=6.5,
        tracking=0.7,
    )
    canvas.showPage()
    canvas.save()
    return output.getvalue()

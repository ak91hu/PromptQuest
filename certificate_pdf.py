"""Single-page certificate for recovering all twenty stations."""

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from challenges import LEVELS
from mission_pdf import text

NAVY = colors.HexColor("#152436")
TEAL = colors.HexColor("#247582")
GOLD = colors.HexColor("#97631d")


def _centered(
    canvas, value, y, *, size=13, bold=False, color=NAVY, width=235 * mm, max_height=None
):
    while True:
        paragraph = Paragraph(
            text(value),
            ParagraphStyle(
                "certificate",
                fontName="NotoBold" if bold else "Noto",
                fontSize=size,
                leading=size * 1.35,
                alignment=TA_CENTER,
                textColor=color,
                splitLongWords=True,
            ),
        )
        _, height = paragraph.wrap(width, 100 * mm)
        if max_height is None or height <= max_height or size <= 18:
            break
        size -= 1
    paragraph.drawOn(canvas, (landscape(A4)[0] - width) / 2, y - height)
    return height


def _emblem(canvas, x, y):
    canvas.saveState()
    canvas.translate(x, y)
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(1.5)
    canvas.circle(0, 0, 22, fill=0, stroke=1)
    canvas.ellipse(-30, -10, 30, 10, fill=0, stroke=1)
    canvas.ellipse(-10, -30, 10, 30, fill=0, stroke=1)
    canvas.setFillColor(NAVY)
    canvas.roundRect(-5, -5, 10, 10, 2, fill=1, stroke=0)
    canvas.restoreState()


def render_certificate(report: dict, issued_at: datetime | None = None) -> bytes:
    if len(report["rooms"]) != len(LEVELS) or not all(room["solved"] for room in report["rooms"]):
        raise ValueError("All twenty stations must be recovered for a certificate.")
    issued_at = issued_at or datetime.now(timezone.utc)
    output = BytesIO()
    width, height = landscape(A4)
    canvas = Canvas(output, pagesize=(width, height), pageCompression=1)
    canvas.setTitle("HackTheAI - completion certificate")
    canvas.setAuthor("HackTheAI")
    canvas.setFillColor(colors.HexColor("#fffdf8"))
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(1.5)
    canvas.roundRect(14 * mm, 14 * mm, width - 28 * mm, height - 28 * mm, 4 * mm, fill=0)
    canvas.setStrokeColor(colors.HexColor("#d4dace"))
    canvas.setLineWidth(0.6)
    canvas.roundRect(17 * mm, 17 * mm, width - 34 * mm, height - 34 * mm, 3 * mm, fill=0)
    _emblem(canvas, width / 2, 176 * mm)
    _centered(canvas, "HackTheAI / ASTERION MISSION", 161 * mm, size=17, bold=True)
    _centered(canvas, "CERTIFICATE", 149 * mm, size=36, bold=True, color=TEAL)
    _centered(canvas, "Awarded to", 126 * mm, size=11, color=TEAL)
    _centered(canvas, report["team"], 117 * mm, size=27, bold=True, max_height=19 * mm)
    _centered(canvas, "For recovering all twenty protected computing systems", 94 * mm)
    _centered(canvas, "and restoring the Asterion departure sequence.", 86 * mm)
    _centered(
        canvas,
        f"{report['score']} / {report['max_score']} points",
        72 * mm,
        size=29,
        bold=True,
        color=GOLD,
    )
    _centered(canvas, "AI security simulation / Mission accomplished", 55 * mm, size=11)
    _centered(canvas, report["mode"], 44 * mm, size=9, color=TEAL)
    canvas.setStrokeColor(colors.HexColor("#d4dace"))
    canvas.line(29 * mm, 35 * mm, width - 29 * mm, 35 * mm)
    canvas.setFillColor(NAVY)
    canvas.setFont("Noto", 9)
    canvas.drawString(29 * mm, 27 * mm, "Issued: " + issued_at.strftime("%Y-%m-%d"))
    canvas.setFont("NotoBold", 9)
    canvas.drawRightString(width - 29 * mm, 27 * mm, "HACKTHEAI / ASTERION")
    canvas.showPage()
    canvas.save()
    return output.getvalue()

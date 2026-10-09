"""Paginated English mission log with embedded fonts."""

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

FONT_ROOT = Path(__file__).parent / "static" / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("Noto", str(FONT_ROOT / "NotoSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("NotoBold", str(FONT_ROOT / "NotoSans-Bold.ttf")))
pdfmetrics.registerFontFamily(
    "Noto", normal="Noto", bold="NotoBold", italic="Noto", boldItalic="NotoBold"
)
INK = colors.HexColor("#142639")
MUTED = colors.HexColor("#526477")
LINE = colors.HexColor("#d4dde8")
LOCAL_TIME = ZoneInfo("UTC")
STYLES = {
    "title": ParagraphStyle(
        "title", fontName="NotoBold", fontSize=25, leading=32, textColor=INK, spaceAfter=12
    ),
    "h1": ParagraphStyle(
        "h1",
        fontName="NotoBold",
        fontSize=19,
        leading=25,
        textColor=INK,
        spaceAfter=12,
        keepWithNext=True,
    ),
    "h2": ParagraphStyle(
        "h2",
        fontName="NotoBold",
        fontSize=10,
        leading=14,
        textColor=INK,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "body",
        fontName="Noto",
        fontSize=10,
        leading=14,
        textColor=INK,
        spaceAfter=6,
        splitLongWords=True,
        alignment=TA_LEFT,
    ),
    "small": ParagraphStyle(
        "small",
        fontName="Noto",
        fontSize=8,
        leading=12,
        textColor=MUTED,
        spaceAfter=6,
        splitLongWords=True,
    ),
}
for role, color in (("prompt", "#eaf1f8"), ("answer", "#edf4ed")):
    STYLES[role] = ParagraphStyle(
        role,
        parent=STYLES["h2"],
        fontSize=10,
        leading=15,
        backColor=colors.HexColor(color),
        borderPadding=6,
        spaceBefore=10,
        spaceAfter=6,
    )
STYLES["message"] = ParagraphStyle(
    "message",
    parent=STYLES["body"],
    fontSize=9.5,
    leading=13,
    leftIndent=8,
    rightIndent=8,
    spaceAfter=6,
)
STYLES["time"] = ParagraphStyle("time", parent=STYLES["small"], leftIndent=8, keepWithNext=True)


def text(value):

    clean = "".join(
        c
        for c in str(value)
        if c in "\n\t" or 32 <= ord(c) <= 0x10FFFF and not 0xD800 <= ord(c) <= 0xDFFF
    )
    return escape(clean).replace("\n", "<br/>")


def p(value, style="body"):
    return Paragraph(text(value), STYLES[style])


def timestamp(value):
    if value is None:
        return "Timestamp not recorded."
    local = datetime.fromtimestamp(value, timezone.utc).astimezone(LOCAL_TIME)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def duration(seconds):
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return (f"{hours} hours " if hours else "") + f"{minutes} minutes {seconds} seconds"


def status(room):
    if room["assisted"]:
        return "Recovered with assistance"
    return "Recovered" if room["solved"] else "Not recovered"


def paragraphs(value, style="body"):

    return [p(part or " ", style) for part in str(value).split("\n\n")]


class MissionDocument(SimpleDocTemplate):
    section_title = "Overview"

    def afterFlowable(self, flowable):
        if hasattr(flowable, "section_title"):
            self.section_title = flowable.section_title
            key = f"station-{flowable.station_number}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(self.section_title, key, level=0)

    def afterPage(self):
        self.page_callback(self.canv, self)


def make_report(session, mode, model) -> dict:
    from challenges import LEVELS

    exported_at = datetime.now(timezone.utc).timestamp()
    return {
        "team": session.team,
        "mode": "Training mode (deterministic simulation)" if mode == "demo" else "Mission",
        "model": model if mode == "live" else "No live language model",
        "score": sum(r.points for r in session.rooms),
        "max_score": len(LEVELS) * 10,
        "defense": session.defense_passed,
        "elapsed": int(exported_at - session.created),
        "started_at": session.created,
        "exported_at": exported_at,
        "rooms": [
            {
                "name": level["name"],
                "subject": level["subject"],
                "topic": level["topic"],
                "agent": level["agent"],
                "intro": level["intro"],
                "mission": level["mission"],
                "solved": r.solved,
                "assisted": r.assisted,
                "points": r.points,
                "attempts": r.attempts,
                "hints": r.hints,
                "restarts": r.restarts,
                "note": r.note,
                "history": [dict(m) for m in (r.transcript or r.history)],
                "traces": [dict(t) for t in (r.trace_log or r.traces)],
                "discovery": dict(r.discovery),
                "lesson": level["lesson"] if r.solved else "",
            }
            for level, r in zip(LEVELS, session.rooms)
        ],
    }


def render_pdf(report: dict) -> bytes:
    out = BytesIO()
    doc = MissionDocument(
        out,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=23 * mm,
        bottomMargin=22 * mm,
        title="HackTheAI - mission log",
        author="HackTheAI",
    )
    story = [
        p("HACKTHEAI / MISSION LOG", "small"),
        p("Mission log", "title"),
        p(report["team"], "h1"),
        p(f"{report['mode']} · {report['score']} points"),
        p(
            f"Mission started: {timestamp(report.get('started_at'))}\n"
            f"Exported: {timestamp(report.get('exported_at'))}\n"
            f"Elapsed time: {duration(report['elapsed'])}"
        ),
        p("All timestamps use UTC.", "small"),
        p("Language model (LLM): " + report["model"], "small"),
        p(
            f"{sum(room['solved'] for room in report['rooms'])} / {len(report['rooms'])} recovered stations · "
            f"{sum(m['role'] == 'user' for r in report['rooms'] for m in r['history'])} prompt · "
            f"{sum(m['role'] == 'assistant' for r in report['rooms'] for m in r['history'])} responses"
        ),
        p(
            "A fictional orbital security exercise aboard Asterion. All protected values and systems are simulated.",
            "small",
        ),
        p("Defense workshop", "h2"),
        p("Defense plan validated." if report["defense"] else "Defense plan not yet validated."),
        p(
            "Each station starts on a new page. Full transcripts include numbered prompts, responses, timestamps and complete submitted documents. Unrecovered values are excluded.",
            "small",
        ),
        p("Data must not become authority.", "h2"),
        p("Station overview", "h2"),
    ]
    rows = [[p("Station", "small"), p("Computing subject", "small"), p("Result", "small")]]
    for i, room in enumerate(report["rooms"]):
        rows.append(
            [
                p(f"{i + 1}. {room['name']}"),
                p(room["subject"]),
                p(f"{status(room)}\n{room['points']} points", "small"),
            ]
        )
    table = Table(rows, colWidths=[69 * mm, 58 * mm, 43 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf1e9")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    for i, room in enumerate(report["rooms"]):
        heading = p(room["name"], "h1")
        heading.section_title = f"{i + 1}. {room['name']}"
        heading.station_number = i + 1
        story += [
            PageBreak(),
            p(f"{i + 1:02d} / {len(report['rooms']):02d} · {room['subject']}", "small"),
            heading,
            p(f"{status(room)} · {room['points']} points"),
            p(
                f"{room['attempts']} AI attempts · {room['hints']} hints · {room['restarts']} attempt refills · {room['points']} points",
                "small",
            ),
        ]
        if room.get("mission"):
            story += [p("Station objective", "h2"), p(room["mission"])]
        if room["assisted"]:
            story.append(
                p(
                    "Assisted recovery: a guided response or training correction contributed to this result.",
                    "small",
                )
            )
        discovery = room["discovery"] if room["solved"] else {}
        story.append(p("Recovered computing value", "h2"))
        if discovery:
            story += [p(discovery["secret"]), p(discovery["question"]), p(discovery["explanation"])]
        else:
            story.append(p("Protected value not yet recovered."))
        if room["lesson"]:
            story += [p("Security finding", "h2"), p(room["lesson"])]
        story += [
            p("Operator observations", "h2"),
            p(room["note"] or "No notes recorded."),
            p("Full transcript", "h2"),
        ]
        if room.get("intro"):
            story += [
                p("Guard opening message", "small"),
                p(room["intro"]),
            ]
        if not room["history"]:
            story.append(p("No messages recorded at this station.", "small"))
        exchange = 0
        for message in room["history"]:
            if message["role"] == "user":
                exchange += 1
                label = f"{exchange:02d}. PROMPT - OPERATOR"
                style = "prompt"
            else:
                label = f"{exchange:02d}. RESPONSE - AI" if exchange else "AI RESPONSE"
                style = "answer"
            story += [p(label, style), p(timestamp(message.get("timestamp")), "time")]
            if "document" in message:
                story.extend(paragraphs(message["prompt"], "message"))
                story.append(p("Submitted document (complete text)", "time"))
                story.extend(paragraphs(message["document"], "message"))
            else:
                story.extend(paragraphs(message["content"], "message"))
        if room["traces"]:
            story.append(p("Executed simulated tool operations", "h2"))
            tool_names = {
                "get_status": "Get status",
                "open_compartment": "Open compartment",
            }
            for trace in room["traces"]:
                story += [
                    p(tool_names.get(trace["name"], trace["name"]), "h2"),
                    p(timestamp(trace.get("timestamp")), "small"),
                    p("Tool: " + trace["name"], "small"),
                    *paragraphs(trace["result"]),
                ]

    def page(canvas, document):
        canvas.saveState()
        canvas.setFont("Noto", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 283 * mm, "HACKTHEAI / MISSION LOG")
        canvas.drawRightString(190 * mm, 283 * mm, document.section_title)
        canvas.setStrokeColor(LINE)
        canvas.line(20 * mm, 280 * mm, 190 * mm, 280 * mm)
        canvas.drawString(
            20 * mm,
            13 * mm,
            "Generated: " + timestamp(report.get("exported_at")) + " UTC",
        )
        canvas.drawRightString(190 * mm, 13 * mm, f"{document.page}. page")
        canvas.restoreState()

    doc.page_callback = page
    doc.build(story)
    return out.getvalue()

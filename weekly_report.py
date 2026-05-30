"""
weekly_report.py — PDF Weekly Report Generator
================================================
Generates a polished PDF summary of the past 7 days using ReportLab.
Includes: score trend chart (drawn as SVG-style paths via ReportLab),
top issues, streak info, milestones unlocked this week, and tips.

Usage:
    from weekly_report import generate_weekly_report
    path = generate_weekly_report(user_id, profile, sessions_this_week)
"""

import io, time, os
from pathlib import Path
from datetime import date, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable)
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Circle, PolyLine
from reportlab.graphics import renderPDF
from reportlab.platypus import Flowable

DATA_DIR = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

# Colour palette
C_BG     = colors.HexColor("#060a0e")
C_ACC    = colors.HexColor("#00e5b0")
C_ACC2   = colors.HexColor("#00aaff")
C_TEXT   = colors.HexColor("#ddeeff")
C_MUTED  = colors.HexColor("#4a6a86")
C_CARD   = colors.HexColor("#0a1520")
C_BORDER = colors.HexColor("#1a2b3c")
C_GOOD   = colors.HexColor("#00e5b0")
C_WARN   = colors.HexColor("#ffb020")
C_BAD    = colors.HexColor("#ff3c5c")


def score_color(s):
    if s >= 85: return C_GOOD
    if s >= 65: return C_WARN
    return C_BAD


def _style(name, **kw):
    return ParagraphStyle(name, **kw)

S_TITLE = _style("T", fontName="Helvetica-Bold", fontSize=20, textColor=C_ACC,   spaceAfter=3,  leading=26)
S_SUB   = _style("S", fontName="Helvetica",      fontSize=9,  textColor=C_MUTED, spaceAfter=14, leading=13)
S_H1    = _style("H", fontName="Helvetica-Bold", fontSize=12, textColor=C_ACC,   spaceBefore=12, spaceAfter=5)
S_BODY  = _style("B", fontName="Helvetica",      fontSize=9,  textColor=C_TEXT,  spaceAfter=5,  leading=14)
S_MONO  = _style("M", fontName="Courier",        fontSize=8,  textColor=C_ACC2,  spaceAfter=5,  leading=12,
                 backColor=C_CARD, leftIndent=8, rightIndent=8)
S_MUT   = _style("U", fontName="Helvetica",      fontSize=8,  textColor=C_MUTED, spaceAfter=3,  leading=12)
S_CTR   = _style("C", fontName="Helvetica",      fontSize=8,  textColor=C_MUTED, spaceAfter=4,  leading=12,
                 alignment=1)


class ScoreLineChart(Flowable):
    """Inline ReportLab Drawing that plots a 7-day score sparkline."""

    def __init__(self, scores: list, width=170*mm, height=40*mm):
        super().__init__()
        self.scores = scores    # list of (label, value_or_None)
        self.width  = width
        self.height = height

    def draw(self):
        w, h = self.width, self.height
        pad  = 8

        # Grid lines at 65 and 85
        for val, col in [(65, C_BAD), (85, C_GOOD)]:
            y = pad + (val / 100) * (h - 2 * pad)
            self.canv.setStrokeColor(col)
            self.canv.setLineWidth(0.3)
            self.canv.setDash(3, 3)
            self.canv.line(pad, y, w - pad, y)
        self.canv.setDash()

        # Plot line
        valid = [(i, v) for i, (_, v) in enumerate(self.scores) if v is not None]
        if len(valid) < 2:
            return

        n  = len(self.scores)
        xs = [pad + i * (w - 2 * pad) / (n - 1) for i in range(n)]

        pts = [(xs[i], pad + (v / 100) * (h - 2 * pad)) for i, v in valid]

        # Fill
        self.canv.setFillColor(colors.Color(0, 0.9, 0.69, alpha=0.12))
        path = self.canv.beginPath()
        path.moveTo(pts[0][0], pad)
        for x, y in pts:
            path.lineTo(x, y)
        path.lineTo(pts[-1][0], pad)
        path.close()
        self.canv.drawPath(path, fill=1, stroke=0)

        # Line
        self.canv.setStrokeColor(C_ACC)
        self.canv.setLineWidth(1.2)
        p = self.canv.beginPath()
        p.moveTo(*pts[0])
        for x, y in pts[1:]:
            p.lineTo(x, y)
        self.canv.drawPath(p, fill=0, stroke=1)

        # Dots + labels
        for i, v in valid:
            x, y = xs[i], pad + (v / 100) * (h - 2 * pad)
            self.canv.setFillColor(score_color(v))
            self.canv.circle(x, y, 2.5, fill=1, stroke=0)

        # X labels
        self.canv.setFont("Helvetica", 6)
        self.canv.setFillColor(C_MUTED)
        for i, (label, _) in enumerate(self.scores):
            self.canv.drawCentredString(xs[i], 1, label[:6])


def generate_weekly_report(user_id: str, profile: dict,
                            weekly_data: list) -> str:
    """
    Generate and save a PDF weekly report.
    weekly_data: list of {week, label, avg_score, sessions} from profiles.get_weekly_scores()
    Returns: path to the generated PDF file.
    """
    name     = profile.get("name", "User")
    streak   = profile.get("streak", {})
    sessions = profile.get("sessions", [])
    best     = profile.get("best_score", 0)
    total_h  = round(profile.get("total_duration", 0) / 3600, 1)

    # This week's sessions
    today      = date.today()
    week_start = today - timedelta(days=today.weekday())
    this_week  = [s for s in sessions
                  if s.get("date", "") >= week_start.isoformat()]
    avg_this_week = (sum(s["avg_score"] for s in this_week) / len(this_week)
                     if this_week else 0)

    # Issue frequency this week
    from collections import Counter
    issue_counts = Counter()
    for s in this_week:
        for iss in s.get("issues", []):
            issue_counts[iss] += 1

    filename = f"weekly_{user_id}_{today.isoformat()}.pdf"
    filepath = REPORT_DIR / filename

    doc   = SimpleDocTemplate(str(filepath), pagesize=A4,
                              leftMargin=18*mm, rightMargin=18*mm,
                              topMargin=16*mm, bottomMargin=16*mm)
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("PostureGuard AI", S_TITLE))
    story.append(Paragraph(
        f"Weekly Report for {name}  ·  Week of {week_start.strftime('%B %d, %Y')}",
        S_SUB))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER,
                             spaceAfter=10, spaceBefore=2))

    # ── Summary stats ─────────────────────────────────────────────────────────
    story.append(Paragraph("This week", S_H1))

    stat_data = [
        [Paragraph("<b>Avg score</b>", S_MUT),
         Paragraph("<b>Sessions</b>", S_MUT),
         Paragraph("<b>Current streak</b>", S_MUT),
         Paragraph("<b>Best ever</b>", S_MUT)],
        [Paragraph(f"<b>{round(avg_this_week, 1)}</b>", _style("N", fontName="Helvetica-Bold",
                  fontSize=20, textColor=score_color(avg_this_week), leading=24)),
         Paragraph(f"<b>{len(this_week)}</b>", _style("N2", fontName="Helvetica-Bold",
                  fontSize=20, textColor=C_TEXT, leading=24)),
         Paragraph(f"<b>{streak.get('current', 0)} days</b>", _style("N3", fontName="Helvetica-Bold",
                  fontSize=20, textColor=C_ACC, leading=24)),
         Paragraph(f"<b>{best}</b>", _style("N4", fontName="Helvetica-Bold",
                  fontSize=20, textColor=C_ACC2, leading=24))],
    ]
    st = Table(stat_data, colWidths=[43*mm]*4)
    st.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), C_CARD),
        ("GRID",       (0,0), (-1,-1), 0.4, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
        ("ROUNDEDCORNERS", [6,6,6,6]),
    ]))
    story.append(st)
    story.append(Spacer(1, 8))

    # ── Score trend chart ─────────────────────────────────────────────────────
    story.append(Paragraph("Score trend (8 weeks)", S_H1))
    chart_data = [(d["label"], d["avg_score"]) for d in weekly_data]
    story.append(ScoreLineChart(chart_data))
    story.append(Spacer(1, 6))

    # ── Top issues ────────────────────────────────────────────────────────────
    if issue_counts:
        story.append(Paragraph("Top posture issues this week", S_H1))
        issue_rows = [[Paragraph("<b>Issue</b>", S_MUT),
                       Paragraph("<b>Occurrences</b>", S_MUT),
                       Paragraph("<b>Fix</b>", S_MUT)]]
        FIXES = {
            "Forward Head":   "Chin tucks 3x/day, raise monitor",
            "Slouching":      "Lumbar support or rolled towel",
            "Shoulder Tilt":  "Check armrests, equalise heights",
            "Head Tilt":      "Remove phone shoulder cradle habit",
        }
        for iss, cnt in issue_counts.most_common(4):
            issue_rows.append([
                Paragraph(iss, S_BODY),
                Paragraph(str(cnt), S_BODY),
                Paragraph(FIXES.get(iss, "See posture guide"), S_BODY),
            ])
        it = Table(issue_rows, colWidths=[50*mm, 30*mm, 92*mm])
        it.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_CARD),
            ("TEXTCOLOR",  (0,0), (-1,0), C_ACC),
            ("GRID",       (0,0), (-1,-1), 0.4, C_BORDER),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 8),
            ("TEXTCOLOR",  (0,1), (-1,-1), C_TEXT),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_BG, C_CARD]),
        ]))
        story.append(it)
        story.append(Spacer(1, 6))

    # ── Day-by-day log ────────────────────────────────────────────────────────
    if this_week:
        story.append(Paragraph("Session log", S_H1))
        log_rows = [[Paragraph("<b>Date</b>", S_MUT),
                     Paragraph("<b>Avg score</b>", S_MUT),
                     Paragraph("<b>Duration</b>", S_MUT),
                     Paragraph("<b>Bad posture</b>", S_MUT)]]
        for s in this_week:
            dur = f"{s['duration_s']//60}m {s['duration_s']%60}s"
            log_rows.append([
                Paragraph(s.get("date",""), S_BODY),
                Paragraph(str(s["avg_score"]), S_BODY),
                Paragraph(dur, S_BODY),
                Paragraph(f"{s['bad_pct']}%", S_BODY),
            ])
        lt = Table(log_rows, colWidths=[40*mm, 35*mm, 35*mm, 62*mm])
        lt.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), C_CARD),
            ("GRID",       (0,0), (-1,-1), 0.4, C_BORDER),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 8),
            ("TEXTCOLOR",  (0,0), (-1,0), C_ACC),
            ("TEXTCOLOR",  (0,1), (-1,-1), C_TEXT),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_BG, C_CARD]),
        ]))
        story.append(lt)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER,
                             spaceAfter=6, spaceBefore=4))
    story.append(Paragraph(
        f"PostureGuard AI  ·  Generated {date.today().strftime('%B %d, %Y')}  ·  Total tracked: {total_h}h",
        S_CTR))

    doc.build(story)
    return str(filepath)

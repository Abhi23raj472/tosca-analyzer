"""Excel and PDF exports of an analysis report."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

INK = "1B1D22"
BLUE = "1F3FA8"
RUST = "B8481C"
SEV_FILL = {"high": "F6DDD2", "medium": "FBEBD9", "low": "E9EEF8"}


def _autosize(ws, widths: dict[int, int] | None = None) -> None:
    for col in ws.columns:
        idx = col[0].column
        length = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[get_column_letter(idx)].width = (widths or {}).get(idx, min(max(10, length + 2), 60))


def to_xlsx(report: dict, analyzed_at: str) -> bytes:
    wb = Workbook()
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor=INK)
    head_font = Font(bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")

    ws = wb.active
    ws.title = "Summary"
    s = report["summary"]
    rows = [
        ("File", report["file_name"]), ("Rule set", report["rule_set"]["name"]),
        ("Tosca docs version", report["docs_version"]), ("Analyzed", analyzed_at),
        ("Compliance score", s["score"]), ("Score after fixing high findings", s["projected_score"]),
        ("Test cases", s["test_cases"]), ("Steps", s["steps"]), ("Findings", s["findings"]),
        ("High / Medium / Low", f"{s['by_severity']['high']} / {s['by_severity']['medium']} / {s['by_severity']['low']}"),
    ]
    ex = report.get("execution")
    if ex:
        rows += [("Runs passed", ex["passed"]), ("Runs failed", ex["failed"]), ("Runs not run", ex["not_run"]),
                 ("Failures traced to a finding", ex["failures_traced"])]
    for r in rows:
        ws.append(r)
        ws.cell(ws.max_row, 1).font = bold
    ws.append([])
    ws.append(["Category", "Score", "Findings"])
    for c in ws[ws.max_row]:
        c.font, c.fill = head_font, head_fill
    for cat in report["categories"]:
        ws.append([cat["label"], cat["score"], cat["findings"]])
    _autosize(ws, {1: 34, 2: 40})

    wf = wb.create_sheet("Findings")
    wf.append(["Severity", "Rule", "Title", "Location", "Occurrences", "Linked failed runs", "Why it matters",
               "Current", "Suggested", "Tosca docs"])
    for c in wf[1]:
        c.font, c.fill = head_font, head_fill
    for f in report["findings"]:
        wf.append([f["severity"].title(), f["rule_id"], f["title"], f["location"], len(f["occurrences"]),
                   len(f.get("linked_failures") or []), f["message"], f["current"], f["suggested"], f["docs"]["url"]])
        wf.cell(wf.max_row, 1).fill = PatternFill("solid", fgColor=SEV_FILL.get(f["severity"], "FFFFFF"))
        wf.cell(wf.max_row, 10).hyperlink = f["docs"]["url"]
        for c in wf[wf.max_row]:
            c.alignment = wrap
    _autosize(wf, {3: 42, 4: 44, 7: 50, 8: 36, 9: 36, 10: 40})
    wf.freeze_panes = "A2"
    wf.auto_filter.ref = wf.dimensions

    wo = wb.create_sheet("Occurrences")
    wo.append(["Rule", "Severity", "Test case", "Location", "Detail"])
    for c in wo[1]:
        c.font, c.fill = head_font, head_fill
    for f in report["findings"]:
        for o in f["occurrences"]:
            wo.append([f["rule_id"], f["severity"].title(), o["test_case"], o["location"], o.get("detail", "")])
    _autosize(wo)
    wo.freeze_panes = "A2"
    wo.auto_filter.ref = wo.dimensions

    if report.get("results"):
        wr = wb.create_sheet("Execution")
        wr.append(["Test case", "Result", "Message", "Linked findings"])
        for c in wr[1]:
            c.font, c.fill = head_font, head_fill
        for r in report["results"]:
            linked = [f["rule_id"] for f in report["findings"] if r.get("test_case_id") in (f.get("linked_failures") or [])]
            wr.append([r["name"], r["status"].replace("_", " ").title(), r.get("message", ""), ", ".join(linked)])
        _autosize(wr, {3: 60})

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(report: dict, analyzed_at: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Tosca Analyzer – {report['file_name']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=24,
                        textColor=colors.HexColor("#" + INK))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_LEFT)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#5b5f68"))
    mono = ParagraphStyle("m", parent=body, fontName="Courier", fontSize=8, leading=10)

    s = report["summary"]
    story = [
        Paragraph(escape(report["file_name"]), h1),
        Paragraph(escape(f"{report['rule_set']['name']} · Tosca docs {report['docs_version']} · Analyzed {analyzed_at}"), small),
        Spacer(1, 8),
    ]
    tiles = [[Paragraph(f"<font size=26><b>{s['score']}</b></font> / 100", body),
              Paragraph(f"<b>{s['test_cases']}</b> test cases<br/><b>{s['steps']}</b> steps<br/><b>{s['findings']}</b> findings", body),
              Paragraph((f"Fixing the {s['high_findings']} high-severity findings would raise the score to about "
                         f"<b>{s['projected_score']}</b>.") if s["high_findings"] else "No high-severity findings.", body)]]
    t = Table(tiles, colWidths=[45 * mm, 40 * mm, 89 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d4cc")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    story += [t, Spacer(1, 8), Paragraph("By category", h2)]
    cat_rows = [["Category", "Score", "Findings"]] + [[c["label"], str(c["score"]), str(c["findings"])] for c in report["categories"]]
    ct = Table(cat_rows, colWidths=[110 * mm, 30 * mm, 34 * mm])
    ct.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + INK)),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d8d4cc"))]))
    story.append(ct)

    ex = report.get("execution")
    if ex:
        story += [Paragraph("Execution results", h2),
                  Paragraph(f"Passed {ex['passed']} · Failed {ex['failed']} · Not run {ex['not_run']}. "
                            f"{ex['failures_traced']} of {ex['failed']} failures trace back to a finding.", body)]

    story.append(Paragraph("Findings and suggested fixes", h2))
    sev_color = {"high": "#" + RUST, "medium": "#C07A1E", "low": "#" + BLUE}
    for f in report["findings"]:
        linked = len(f.get("linked_failures") or [])
        head = (f"<font color='{sev_color.get(f['severity'])}'><b>{f['severity'].upper()}</b></font> "
                f"<font color='#5b5f68'>{f['rule_id']}</font>" + (f" · linked to {linked} failed run(s)" if linked else ""))
        code = Table([[Paragraph("<b>CURRENT</b><br/>" + escape(f["current"]).replace("\n", "<br/>"), mono),
                       Paragraph("<b>SUGGESTED</b><br/>" + escape(f["suggested"]).replace("\n", "<br/>"), mono)]],
                     colWidths=[87 * mm, 87 * mm])
        code.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FBF1EB")),
                                  ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#EDF1FA")),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
        story.append(KeepTogether([
            Spacer(1, 6), Paragraph(head, small), Paragraph(f"<b>{escape(f['title'])}</b>", body),
            Paragraph(escape(f["location"]), small), Paragraph(escape(f["message"]), body), Spacer(1, 3), code,
            Paragraph(f"Tosca docs: <link href='{f['docs']['url']}' color='#{BLUE}'>{escape(f['docs']['label'])}</link>", small),
        ]))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5b5f68"))
        canvas.drawString(18 * mm, 10 * mm, f"Tosca Analyzer · {report['file_name']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def stamp(dt: datetime) -> str:
    return dt.strftime("%d %b %Y, %H:%M UTC")

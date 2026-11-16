"""Reusable styles, doc template and helper flowables for the NetQuest interview-prep PDF."""
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle, XPreformatted,
)

# ---------------------------------------------------------------- fonts ----
FONT_DIR = "/usr/share/fonts/liberation-sans-fonts"
MONO_DIR = "/usr/share/fonts/liberation-mono-fonts"

pdfmetrics.registerFont(TTFont("LibSans", f"{FONT_DIR}/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("LibSans-Bold", f"{FONT_DIR}/LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("LibSans-Italic", f"{FONT_DIR}/LiberationSans-Italic.ttf"))
pdfmetrics.registerFont(TTFont("LibSans-BoldItalic", f"{FONT_DIR}/LiberationSans-BoldItalic.ttf"))
pdfmetrics.registerFont(TTFont("LibMono", f"{MONO_DIR}/LiberationMono-Regular.ttf"))
pdfmetrics.registerFont(TTFont("LibMono-Bold", f"{MONO_DIR}/LiberationMono-Bold.ttf"))
pdfmetrics.registerFontFamily("LibSans", normal="LibSans", bold="LibSans-Bold",
                              italic="LibSans-Italic", boldItalic="LibSans-BoldItalic")
pdfmetrics.registerFontFamily("LibMono", normal="LibMono", bold="LibMono-Bold",
                              italic="LibMono", boldItalic="LibMono-Bold")

# --------------------------------------------------------------- colours ----
NAVY = colors.HexColor("#1f3a5f")
STEEL = colors.HexColor("#3d5a80")
ACCENT = colors.HexColor("#e07a5f")
INK = colors.HexColor("#1c2430")
MUTED = colors.HexColor("#66707d")
CODE_BG = colors.HexColor("#f2f4f7")
CODE_BD = colors.HexColor("#d4dae2")
ANSWER_BG = colors.HexColor("#eff6ee")
ANSWER_BD = colors.HexColor("#bcd7b4")
GOOD = colors.HexColor("#1a7f37")
BAD = colors.HexColor("#c0483f")
RULE = colors.HexColor("#c9d2dd")

PAGE_W, PAGE_H = A4
M = 18 * mm
CONTENT_W = PAGE_W - 2 * M

# --------------------------------------------------------------- styles ----
def _st(name, **kw):
    base = dict(fontName="LibSans", fontSize=9.8, leading=13.4, textColor=INK,
                alignment=TA_LEFT, spaceBefore=0, spaceAfter=4)
    base.update(kw)
    return ParagraphStyle(name, **base)

STY = {
    "Kicker":     _st("Kicker", fontName="LibSans-Bold", fontSize=12, leading=16, textColor=ACCENT, spaceAfter=10),
    "Title":      _st("Title", fontName="LibSans-Bold", fontSize=27, leading=33, textColor=NAVY, spaceAfter=8),
    "SubTitle":   _st("SubTitle", fontSize=13.5, leading=19, textColor=STEEL, spaceAfter=14),
    "CoverBody":  _st("CoverBody", fontSize=10.5, leading=15.5, spaceAfter=8, textColor=INK),
    "CoverMeta":  _st("CoverMeta", fontSize=9.5, leading=14, textColor=MUTED),
    "Part":       _st("Part", fontName="LibSans-Bold", fontSize=20, leading=25,
                      textColor=colors.white, backColor=NAVY, borderPadding=(7, 10, 7, 10),
                      spaceBefore=0, spaceAfter=14),
    "Chapter":    _st("Chapter", fontName="LibSans-Bold", fontSize=14.5, leading=19,
                      textColor=NAVY, spaceBefore=12, spaceAfter=7),
    "Section":    _st("Section", fontName="LibSans-Bold", fontSize=11.5, leading=15,
                      textColor=STEEL, spaceBefore=11, spaceAfter=5),
    "SubSection": _st("SubSection", fontName="LibSans-BoldItalic", fontSize=10, leading=13.5,
                      textColor=INK, spaceBefore=9, spaceAfter=3),
    "Body":       _st("Body"),
    "Small":      _st("Small", fontSize=8.6, leading=11.6, textColor=MUTED),
    "Lead":       _st("Lead", fontSize=10.2, leading=14.4, spaceAfter=8),
    "Bullet":     _st("Bullet", leftIndent=16, firstLineIndent=-10, spaceAfter=2.5),
    "Option":     _st("Option", leftIndent=14, firstLineIndent=-11, spaceAfter=2, fontSize=9.6, leading=13),
    "Answer":     _st("Answer", backColor=ANSWER_BG, borderColor=ANSWER_BD, borderWidth=0.7,
                      borderPadding=6, leftIndent=4, rightIndent=4, spaceBefore=5, spaceAfter=7,
                      fontSize=9.4, leading=13.2),
    "Code":       _st("Code", fontName="LibMono", fontSize=8.1, leading=10.4, textColor=INK,
                      backColor=CODE_BG, borderColor=CODE_BD, borderWidth=0.6,
                      borderPadding=5, leftIndent=4, rightIndent=4, spaceBefore=3, spaceAfter=7),
    "CodeTitle":  _st("CodeTitle", fontName="LibMono-Bold", fontSize=8.4, leading=11.2,
                      textColor=STEEL, spaceBefore=6, spaceAfter=1.5),
    "Verbatim":   _st("Verbatim", fontName="LibMono", fontSize=8, leading=10.8,
                      backColor=CODE_BG, borderColor=CODE_BD, borderWidth=0.6,
                      borderPadding=4, leftIndent=4, rightIndent=4),
    "TableHead":  _st("TableHead", fontName="LibSans-Bold", fontSize=8.6, leading=11,
                      textColor=colors.white, spaceAfter=0),
    "TableCell":  _st("TableCell", fontSize=8.7, leading=11.6, spaceAfter=0),
    "TOC":        _st("TOC", fontSize=10, leading=17),
    "TOC2":       _st("TOC2", fontSize=9.2, leading=15, leftIndent=14),
}

# ------------------------------------------------------------ doc template ----
class NetQuestDoc(BaseDocTemplate):
    def __init__(self, filename, dist=0.28 * mm, **kw):
        super().__init__(filename, pagesize=A4, leftMargin=M, rightMargin=M,
                         topMargin=20 * mm, bottomMargin=20 * mm,
                         title="NetQuest — Interview Question Bank & Practical Scenarios",
                         author="NetQuest", **kw)
        self._bm = 0
        cover_frame = Frame(M, 22 * mm, CONTENT_W, PAGE_H - 86 * mm, id="cover")
        later_frame = Frame(M, 20 * mm, CONTENT_W, PAGE_H - 40 * mm, id="later")
        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover_frame], onPage=self._cover_page),
            PageTemplate(id="Later", frames=[later_frame], onPage=self._later_page),
        ])

    def _cover_page(self, canv, doc):
        canv.saveState()
        canv.setFillColor(NAVY)
        canv.rect(0, PAGE_H - 58 * mm, PAGE_W, 58 * mm, fill=1, stroke=0)
        canv.setFillColor(ACCENT)
        canv.rect(0, PAGE_H - 61 * mm, PAGE_W, 3 * mm, fill=1, stroke=0)
        canv.setFillColor(colors.white)
        canv.setFont("LibSans-Bold", 12)
        canv.drawString(M, PAGE_H - 24 * mm, "NETQUEST")
        canv.setFont("LibSans", 9)
        canv.setFillColor(colors.HexColor("#c9d6e6"))
        canv.drawRightString(PAGE_W - M, PAGE_H - 24 * mm, "Networking · Linux · Troubleshooting")
        canv.restoreState()

    def _later_page(self, canv, doc):
        canv.saveState()
        y = PAGE_H - 11 * mm
        canv.setFont("LibSans", 7.4)
        canv.setFillColor(MUTED)
        canv.drawString(M, y, "NetQuest — Interview Question Bank & Practical Scenarios")
        canv.drawRightString(PAGE_W - M, y, "Questions · model answers · practical scenarios")
        canv.setStrokeColor(RULE)
        canv.setLineWidth(0.6)
        canv.line(M, y - 3, PAGE_W - M, y - 3)
        canv.drawCentredString(PAGE_W / 2, 10 * mm, f"Page {doc.page}")
        canv.restoreState()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name not in ("Part", "Chapter"):
            return
        text = flowable.getPlainText()
        level = 0 if name == "Part" else 1
        key = f"bm-{self._bm}"
        self._bm += 1
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page))


# ------------------------------------------------------------- html -> para ----
_HTML_RE = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)>")

def html_to_markup(html):
    """Convert simple content HTML (<p>, <b>/<strong>, <i>/<em>, <code>, lists,
    <br>) into reportlab markup with monospace/italic inline styling."""
    if not html:
        return ""
    out = []
    for token in re.split(r"(<[^>]+>)", html):
        if token.startswith("<") and token.endswith(">"):
            m = _HTML_RE.match(token)
            out.append(_tag_repl(m) if m else "")
        else:
            out.append(escape(token))
    text = "".join(out).replace("\n", " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()

def _tag_repl(m):
    closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
    if tag in ("p", "div", "li", "tr", "br", "ol", "ul", "table", "pre"):
        t = "<br/>" if (closing and tag in ("p", "div", "li", "tr")) else ""
        return t
    if closing:
        return {"b": "</b>", "strong": "</b>", "i": "</i>", "em": "</i>",
                "code": "</font>", "font": "</font>"}.get(tag, "")
    if tag in ("b", "strong"):
        return "<b>"
    if tag in ("i", "em"):
        return "<i>"
    if tag == "code":
        return '<font name="LibMono" size="8">'
    return ""


# ------------------------------------------------------------- flowables ----
def P(text, style="Body"):
    return Paragraph(text, STY[style])

def part(story, number, title, intro=None):
    story.append(NextPageTemplate("Later"))
    story.append(PageBreak())
    story.append(Paragraph(f"Part {number} — {title}", STY["Part"]))
    if intro:
        story.append(Paragraph(intro, STY["Lead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=RULE, spaceAfter=10))

def chapter(story, text):
    story.append(Paragraph(f"<b>{text}</b>", STY["Chapter"]))

def section(story, text):
    story.append(Paragraph(text, STY["Section"]))

def sub(story, text):
    story.append(Paragraph(text, STY["SubSection"]))

def body(story, text, style="Body"):
    story.append(Paragraph(text, STY[style]))

def bullets(story, items):
    for it in items:
        story.append(Paragraph(escape(it), STY["Bullet"], bulletText="•"))

def wrap_code(text, width=92):
    """Wrap long terminal lines at spaces, hard-fallback after `width` chars."""
    out = []
    for line in text.replace("\t", "    ").splitlines():
        while len(line) > width:
            cut = line.rfind(" ", 0, width + 1)
            if cut < int(width * 0.55):
                cut = width
            out.append(line[:cut])
            line = "    " + line[cut:].lstrip()
        out.append(line)
    return "\n".join(out)

def code(story, text, title=None, keep=True):
    block = []
    if title:
        block.append(Paragraph(escape(title), STY["CodeTitle"]))
    block.append(XPreformatted(escape(wrap_code(text)), STY["Code"]))
    if keep and len(text.splitlines()) <= 45:
        story.append(KeepTogether(block))
    else:
        story.extend(block)

def para_block(story, label, text):
    if label:
        story.append(Paragraph(f"<b>{escape(label)}</b>", STY["Small"]))
    story.append(Paragraph(text or "", STY["Body"]))

# ------------------------------------------------------------------ MCQ ----
def option_letters(n):
    return [chr(65 + i) for i in range(n)]

def add_mcq(story, q, tag=None, show_answer=True):
    block = []
    tag = f"<b>{escape(tag)}</b>  " if tag else ""
    block.append(Paragraph(tag + escape(q["prompt"]), STY["Option"]))
    opts = q.get("options", [])
    letters = option_letters(len(opts))
    for i, opt in enumerate(opts):
        block.append(Paragraph(f"<b>{letters[i]}.</b>  {escape(opt)}", STY["Option"]))
    if not show_answer:
        story.append(KeepTogether(block))
        return
    ans_i = int(q["answer"])
    lines = [f"<b>Answer: {letters[ans_i]}.</b>  {escape(opts[ans_i])}"]
    exp = q.get("explanation")
    if exp:
        lines.append(f"<b>Explanation:</b>  {escape(exp)}")
    why = q.get("why_wrong", {})
    if why:
        extra = []
        for i, letter in enumerate(letters):
            if i == ans_i:
                continue
            w = why.get(str(i)) or why.get(i)
            if w:
                extra.append(f"<b>{letter}</b> — {escape(w)}")
        if extra:
            lines.append("<b>Why the others are wrong:</b>")
            lines.extend(extra)
    block.append(Paragraph("<br/>".join(lines), STY["Answer"]))
    story.append(KeepTogether(block))

def add_self(story, q, tag=None):
    tag = f"<b>{escape(tag)}</b>  " if tag else ""
    story.append(Paragraph(tag + escape(q["prompt"]), STY["Option"]))
    story.append(Paragraph("<b>What a strong answer covers:</b>", STY["Small"]))
    for c in q.get("checklist", []):
        story.append(Paragraph(escape(c["text"]), STY["Bullet"], bulletText="•"))
    ref = q.get("reference")
    if ref:
        story.append(Paragraph("<b>Model answer:</b>", STY["Small"]))
        story.append(Paragraph(html_to_markup(ref), STY["Body"]))

def interview_q(story, q, number):
    """A main interview question plus its weak/strong follow-ups."""
    style_effort = {"conceptual": "Conceptual", "scenario": "Scenario", "command": "Command"}
    label = f"Q{number} · {style_effort.get(q.get('kind', ''), 'Question')}"
    section(story, f"{label} — {q['prompt']}")
    if q.get("checklist"):
        story.append(Paragraph("<b>What a strong answer covers:</b>", STY["Small"]))
        for c in q["checklist"]:
            story.append(Paragraph(escape(c["text"]), STY["Bullet"], bulletText="•"))
    if q.get("reference"):
        story.append(Paragraph("<b>Model answer:</b>", STY["Small"]))
        story.append(Paragraph(html_to_markup(q["reference"]), STY["Body"]))
    for fu in q.get("followups", []):
        after = "if your answer was weak" if fu.get("after") == "weak" else "if your answer was strong"
        sub(story, f"Follow-up ({after})")
        story.append(Paragraph(escape(fu["prompt"]), STY["Option"]))
        if fu.get("checklist"):
            story.append(Paragraph("<b>What a strong answer covers:</b>", STY["Small"]))
            for c in fu["checklist"]:
                story.append(Paragraph(escape(c["text"]), STY["Bullet"], bulletText="•"))
        if fu.get("reference"):
            story.append(Paragraph("<b>Model answer:</b>", STY["Small"]))
            story.append(Paragraph(html_to_markup(fu["reference"]), STY["Body"]))

def answer_block(story, correct, explanation=None, why=None):
    lines = [f"<b>Answer:</b>  {escape(correct)}"]
    if explanation:
        lines.append(f"<b>Explanation:</b>  {escape(explanation)}")
    if why:
        lines.extend(f"<b>{k}.</b> — {escape(v)}" for k, v in why)
    story.append(Paragraph("<br/>".join(lines), STY["Answer"]))

def rule(story):
    story.append(Spacer(1, 2))
    story.append(HRFlowable(width="100%", thickness=0.7, color=RULE, spaceBefore=4, spaceAfter=8))

def spacer(story, h=6):
    story.append(Spacer(1, h))
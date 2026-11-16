"""Builds the actual PDF story from the NetQuest JSON content."""
import datetime
import json
import os
from glob import glob

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak, HRFlowable, KeepTogether, NextPageTemplate, PageBreak, Paragraph,
    Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from pdf_style import (
    BAD, CODE_BD, CONTENT_W, GOOD, MUTED, NAVY, RULE, STEEL, STY,
    add_mcq, add_self, answer_block, body, bullets, chapter, code, html_to_markup,
    interview_q, option_letters, part, rule, section, spacer, sub,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")


def load(name):
    with open(os.path.join(CONTENT, name), encoding="utf-8") as fh:
        return json.load(fh)


def load_many(pattern):
    out = []
    for path in sorted(glob(os.path.join(CONTENT, pattern))):
        with open(path, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


MODULES = load_many("modules/*.json")
LESSONS = {x["id"]: x for x in load_many("lessons/*.json")}
LABS = [lab for f in load_many("command_labs/*.json") for lab in f["labs"]]
CASES = sorted(load_many("case_studies/*.json"), key=lambda x: x.get("order", 0))
DIAG = load("diagnostic.json")
INTERVIEW = load("interview.json")
REVISION = load("revision.json")


def esc(t):
    from xml.sax.saxutils import escape
    return escape(str(t))


def count_items():
    n_interview = sum(1 + len(q.get("followups", [])) for q in INTERVIEW["questions"])
    n_curric = sum(len(l["checks"]) for l in LESSONS.values()) + sum(
        len(m.get("assessment", [])) for m in MODULES)
    n_labs = sum(1 + len(l["simulate"]["questions"]) + (1 if l.get("apply") else 0) for l in LABS)
    n_cases = len(CASES) + sum(len(c.get("interview_questions", [])) for c in CASES)
    return {
        "interview": n_interview,
        "curriculum": n_curric,
        "diagnostic": len(DIAG["questions"]),
        "revision": sum(len(q["questions"]) for q in REVISION["quizzes"]),
        "labs": n_labs,
        "cases": n_cases,
    }


# ------------------------------------------------------------------ cover ----
def cover(story):
    counts = count_items()
    story.append(Paragraph("Interview Question Bank<br/>&amp; Practical Scenarios", STY["Title"]))
    story.append(Paragraph(
        "Every question, model answer, command exercise and troubleshooting scenario "
        "from NetQuest, in one printable study document.", STY["SubTitle"]))
    story.append(HRFlowable(width="42%", thickness=2.2, color=colors.HexColor("#e07a5f"),
                            hAlign="LEFT", spaceAfter=16))
    story.append(Paragraph(
        "This document deliberately leaves out the lesson theory, packet-flow walkthroughs "
        "and simulator narratives. It keeps what you can be asked and what you can practise: "
        "mock-interview questions with answer checklists, topic quizzes, command-line labs, "
        "and full troubleshooting cases with evidence and root causes.", STY["CoverBody"]))
    story.append(Spacer(1, 12))
    data = [
        ["Mock-interview questions", f"{counts['interview']} prompts + follow-ups"],
        ["Curriculum & module assessments", f"{counts['curriculum']} questions"],
        ["Rapid revision drills", f"{counts['revision']} questions"],
        ["Diagnostic test", f"{counts['diagnostic']} questions"],
        ["Command-line labs", f"{len(LABS)} labs · {counts['labs']} exercises/questions"],
        ["Troubleshooting case studies", f"{len(CASES)} missions · {counts['cases']} case items"],
    ]
    t = Table([[Paragraph(f"<b>{esc(a)}</b>", STY["CoverMeta"]),
                Paragraph(esc(b), STY["CoverMeta"])] for a, b in data],
              colWidths=[CONTENT_W * 0.58, CONTENT_W * 0.42])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Generated from the NetQuest content files on "
        f"{datetime.date.today().strftime('%d %B %Y')}. Source: {ROOT}.", STY["CoverMeta"]))


# -------------------------------------------------------------------- toc ----
def toc(story):
    story.append(NextPageTemplate("Later"))
    story.append(PageBreak())
    story.append(Paragraph("Contents", STY["Title"]))
    story.append(HRFlowable(width="100%", thickness=1, color=RULE, spaceAfter=12))
    toc_obj = TableOfContents()
    toc_obj.levelStyles = [STY["TOC"], STY["TOC2"]]
    toc_obj.dotsMinLevel = 0
    story.append(toc_obj)
    return toc_obj


# --------------------------------------------------------------- interview ----
def interview_bank(story):
    counts = count_items()
    part(story, "I", "Mock Interview Question Bank",
         "Fourteen question banks across seven topics, with the curated checklist an "
         "interviewer is mentally ticking off, a model spoken answer, and the probing "
         f"follow-up you get when an answer is weak or strong. {counts['interview']} "
         "prompts and follow-ups in total.")
    topic_labels = {t["id"]: t["label"] for t in INTERVIEW["topics"]}
    for topic in INTERVIEW["topics"]:
        chapter(story, topic["label"])
        qs = [q for q in INTERVIEW["questions"] if q["topic"] == topic["id"]]
        body(story, f"<i>{len(qs)} question banks. Answer out loud before reading the checklist.</i>", "Small")
        spacer(story, 3)
        n = 0
        for q in qs:
            n += 1
            interview_q(story, q, n)
            rule(story)


# ---------------------------------------------------------------- revision ----
def revision_drills(story):
    count = count_items()["revision"]
    part(story, "II", "Rapid Revision Drills",
         f"{count} fast recall questions across four drill sets. Ten seconds each, "
         "no notes: anything you miss is what you re-read tonight.")
    body(story, html_to_markup(REVISION.get("intro", "")), "Small")
    for quiz in REVISION["quizzes"]:
        chapter(story, quiz["title"])
        for i, q in enumerate(quiz["questions"], 1):
            add_mcq(story, q, tag=f"Q{i}.")
            spacer(story, 4)


# --------------------------------------------------------------- diagnostic ----
def diagnostic_test(story):
    count = count_items()["diagnostic"]
    part(story, "III", "Diagnostic Test",
         f"{count} questions used to decide which modules you can skip. Treat the answer "
         "key as a scoring reference, not as a lesson.")
    body(story, html_to_markup(DIAG.get("intro", "")), "Small")
    body(story, f"<b>Scoring:</b> {html_to_markup(DIAG.get('scoring', ''))}", "Small")
    mods = {m["id"]: m for m in MODULES}
    current = None
    for i, q in enumerate(DIAG["questions"], 1):
        if q["module_id"] != current:
            current = q["module_id"]
            m = mods.get(current, {"number": current, "title": current})
            section(story, f"Module {m['number']} — {m['title']}")
        add_mcq(story, q, tag=f"Q{i}.")
        spacer(story, 4)


# --------------------------------------------------------------- curriculum ----
def curriculum_bank(story):
    count = count_items()["curriculum"]
    part(story, "IV", "Topic Question Bank",
         f"Every check from the learn pages and every module assessment, grouped by module "
         f"and lesson. The explanatory lesson text is intentionally not included. "
         f"{count} questions.")
    for module in MODULES:
        chapter(story, f"Module {module['number']} — {module['title']}")
        if module.get("key_questions"):
            section(story, "Key interview questions for this module")
            bullets(story, module["key_questions"])
        for lesson_id in module.get("lesson_ids", []):
            lesson = LESSONS.get(lesson_id)
            if not lesson:
                continue
            section(story, f"{lesson_id.upper()} — {lesson['title']}")
            for i, q in enumerate(lesson.get("checks", []), 1):
                if q["type"] == "mcq":
                    add_mcq(story, q, tag=f"Check {i}.")
                else:
                    add_self(story, q, tag=f"Check {i}.")
                spacer(story, 4)
        assessment = module.get("assessment", [])
        if assessment:
            section(story, "Module assessment")
            for i, q in enumerate(assessment, 1):
                if q["type"] == "mcq":
                    add_mcq(story, q, tag=f"A{i}.")
                else:
                    add_self(story, q, tag=f"A{i}.")
                spacer(story, 4)


# --------------------------------------------------------------------- labs ----
def lab_exercise(story, lab, number):
    section(story, f"Lab {number} — {lab['command']}: {lab.get('tagline', '')}")
    tr = lab.get("try", {})
    if tr:
        sub(story, "Practical scenario")
        body(story, f"<i>{esc(tr.get('scenario', ''))}</i>")
        if tr.get("task"):
            body(story, f"<b>Task:</b> {esc(tr['task'])}")
        if tr.get("command"):
            code(story, tr["command"], title="Command")
        labels = [p["label"] for p in tr.get("expected_patterns", []) if p.get("label")]
        if labels:
            sub(story, "Evidence to capture")
            bullets(story, labels)
    sim = lab.get("simulate", {})
    if sim:
        sub(story, "Interpret the sample output")
        if sim.get("intro"):
            body(story, esc(sim["intro"]))
        code(story, sim.get("terminal", ""), title="Terminal")
        for i, q in enumerate(sim.get("questions", []), 1):
            add_mcq(story, q, tag=f"Q{i}.")
            spacer(story, 3)
    apply_q = lab.get("apply")
    if apply_q:
        sub(story, "Applied scenario")
        body(story, f"<i>{esc(apply_q.get('scenario', ''))}</i>")
        q = dict(apply_q)
        q["prompt"] = apply_q.get("question", "")
        add_mcq(story, q)
    rule(story)


def command_labs(story):
    part(story, "V", "Command-Line Practical Labs",
         "A practical task, the command that produces the evidence, the sample output to "
         "interpret, and applied questions for each command. Command theory, flag tables "
         "and reading notes are omitted.")
    groups = []
    for lab in LABS:
        if lab.get("group") not in groups:
            groups.append(lab.get("group"))
    n = 0
    for group in groups:
        chapter(story, group)
        for lab in [l for l in LABS if l.get("group") == group]:
            n += 1
            lab_exercise(story, lab, n)


# -------------------------------------------------------------- case studies ----
def verdict_cell(verdict):
    v = (verdict or "").lower()
    if v == "accepted":
        return f'<font color="#1a7f37"><b>ACCEPTED</b></font>'
    if v == "rejected":
        return f'<font color="#c0483f"><b>REJECTED</b></font>'
    return esc(verdict or "")


def hypothesis_table(story, hypotheses):
    rows = [[Paragraph("Hypothesis", STY["TableHead"]),
             Paragraph("Verdict", STY["TableHead"]),
             Paragraph("Why", STY["TableHead"])]]
    for h in hypotheses:
        rows.append([
            Paragraph(esc(h.get("text", "")), STY["TableCell"]),
            Paragraph(verdict_cell(h.get("verdict")), STY["TableCell"]),
            Paragraph(esc(h.get("why", "")), STY["TableCell"]),
        ])
    t = Table(rows, colWidths=[CONTENT_W * 0.40, CONTENT_W * 0.14, CONTENT_W * 0.46], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fb")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))


def case_study(story, case):
    story.append(CondPageBreak(70 * mm))
    chapter(story, f"Case {case['order']} — {case['title']}")
    mods = {m["id"]: m["title"] for m in MODULES}
    body(story, f"<i>{esc(case.get('tagline', ''))}</i>")
    body(story, f"<b>Difficulty:</b> {esc(case.get('difficulty', 'core'))} &nbsp;·&nbsp; "
                f"<b>Module:</b> {esc(mods.get(case['module_id'], case['module_id']))}",
         "Small")

    section(story, "Scenario")
    body(story, "<b>Environment</b>", "Small")
    bullets(story, case.get("environment", []))
    if case.get("topology"):
        code(story, case["topology"], title="Topology")
    body(story, "<b>Symptoms</b>", "Small")
    bullets(story, case.get("symptoms", []))
    body(story, "<b>Objectives</b>", "Small")
    bullets(story, case.get("objectives", []))

    section(story, "Evidence to collect")
    for i, ev in enumerate(case.get("evidence", []), 1):
        block = []
        sub(block, f"Evidence {i} — {ev.get('label', '')}")
        if ev.get("command"):
            code(block, ev["command"], title="Command", keep=False)
        if ev.get("output"):
            code(block, ev["output"], title="Observed output", keep=False)
        if ev.get("insight"):
            body(block, f"<i>Interpretation:</i> {esc(ev['insight'])}")
        story.append(KeepTogether(block))

    section(story, "Hypothesis testing")
    hypothesis_table(story, case.get("hypotheses", []))

    section(story, "Root cause and fix")
    sol = case.get("solution", {})
    body(story, f"<b>Root cause:</b> {esc(sol.get('root_cause', ''))}")
    body(story, f"<b>Resolution:</b> {esc(sol.get('resolution', ''))}")
    body(story, f"<b>Verification:</b> {esc(sol.get('verification', ''))}")

    options = case.get("resolution_options", [])
    if options:
        section(story, "Which fix is correct?")
        for opt in options:
            mark = ('<font color="#1a7f37"><b>CORRECT</b></font>'
                    if opt.get("correct") else
                    '<font color="#c0483f"><b>WRONG</b></font>')
            story.append(Paragraph(f"{mark} — {esc(opt.get('text', ''))}",
                                   STY["Bullet"], bulletText="•"))
            story.append(Paragraph(esc(opt.get("why", "")),
                                   STY["Small"], bulletText=""))

    iqs = case.get("interview_questions", [])
    if iqs:
        section(story, "Interview questions on this case")
        for i, qa in enumerate(iqs, 1):
            body(story, f"<b>Q{i}. {esc(qa.get('q', ''))}</b>", "Option")
            body(story, html_to_markup(qa.get("a", "")))

    followups = case.get("solution", {}).get("interview_followups", [])
    if followups:
        sub(story, "Likely follow-up probes")
        bullets(story, followups)
    story.append(Spacer(1, 8))


def case_studies(story):
    part(story, "VI", "Troubleshooting Case Studies",
         "Twelve realistic incidents. Each one gives you the symptom set, the evidence "
         "commands and their output, a hypothesis table, the root cause, the correct fix "
         "and the interview questions the case invites. Work the case before reading the "
         "root cause.")
    for case in CASES:
        case_study(story, case)
    visual_walkthroughs(story)
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.8, color=RULE, spaceAfter=6))
    story.append(Paragraph(
        "<i>End of document — NetQuest question bank and practical scenarios.</i>",
        STY["Small"]))


# --------------------------------------------------------------------- build ----
def make_story():
    story = []
    cover(story)
    toc_obj = toc(story)
    interview_bank(story)
    revision_drills(story)
    diagnostic_test(story)
    curriculum_bank(story)
    command_labs(story)
    case_studies(story)
    return story, toc_obj


def build(output_path):
    from pdf_style import NetQuestDoc
    story, _toc = make_story()
    doc = NetQuestDoc(output_path)
    doc.multiBuild(story)
    return output_path


# ------------------------------------------------------------ visual section ----
VISUALS = [
    dict(
        file="visual-01-ip-addressing-429dfd.jpg",
        title="IP Addressing & Basic Subnetting",
        text="An IPv4 address is 32 bits; the mask decides which bits are network and which are host. "
             "The host ANDs its own address and the destination with its mask. Equal results mean the "
             "destination is on-link and the host ARPs for it directly; different results mean the packet "
             "goes to the default gateway. A /26 has blocks of 64, so one /24 becomes four blocks (.0, .64, "
             ".128, .192), each with a network address, usable range and broadcast address. The gateway must "
             "sit inside the host's own block.",
    ),
    dict(
        file="visual-02-switching-7bd461.jpg",
        title="Switching Basics",
        text="A switch learns a source MAC address and the port it arrived on. Known unicast is forwarded only "
             "to the learned port; unknown unicast and broadcasts are flooded inside the VLAN; a frame going back "
             "out of its ingress port is filtered. Access ports carry one VLAN, while trunk ports carry many "
             "VLANs with 802.1Q tags. Redundant links create loops and broadcast storms, which is why Spanning "
             "Tree blocks one of the paths.",
    ),
    dict(
        file="visual-03-dhcp-dns-aa4eb8.jpg",
        title="DHCP & DNS",
        text="DHCP uses the broadcast DORA exchange: DISCOVER, OFFER, REQUEST, ACK. When client and server are "
             "separated by a router, the client VLAN's relay sets giaddr so the server knows which scope to use. "
             "The lease supplies the address, mask, default gateway and DNS servers. DNS resolution then runs from "
             "the application and stub resolver to a recursive resolver, which queries the root, TLD and "
             "authoritative servers and returns an A or AAAA record with a TTL.",
    ),
    dict(
        file="visual-04-troubleshooting-8c93fd.jpg",
        title="Connectivity & Troubleshooting Commands",
        text="Work outward from the host. ip addr and ip route show whether the host has an address, mask and "
             "path. ping proves basic reachability. traceroute and mtr show where the path stops and whether loss "
             "or jitter is real. dig and nslookup separate name resolution from connectivity. ss shows whether "
             "the service is listening. tcpdump proves whether packets arrive, and curl proves the application "
             "responds. Each command answers a different question, so the order matters.",
    ),
    dict(
        file="visual-05-routing-67ef8d.jpg",
        title="Static & Dynamic Routing",
        text="A router chooses the most specific matching prefix first; only routes of the same prefix length are "
             "compared by metric. The default route 0.0.0.0/0 is the fallback when nothing more specific matches. "
             "Static routes are configured by hand, while OSPF and BGP learn routes dynamically. Every hop "
             "decrements TTL, and a packet trapped in a loop is discarded when TTL reaches zero.",
    ),
    dict(
        file="visual-06-address-switch-89c372.jpg",
        title="How Addressing and Switching Connect",
        text="Two hosts in the same subnet and VLAN resolve each other's MAC with ARP: the request is broadcast, "
             "the reply is unicast, and the switch learns both MAC addresses. If the destination is off-link, the "
             "sender does not ARP for the destination. It ARPs for the default gateway and sends the frame to the "
             "gateway's MAC while the destination IP stays unchanged. That is the hand-off between Layer 3 "
             "addressing and Layer 2 switching.",
    ),
    dict(
        file="visual-07-switch-dhcp-49099c.jpg",
        title="How Switching Connects to DHCP and DNS",
        text="A VLAN is a broadcast domain. DHCP DISCOVERs cannot cross the router between the client VLAN and the "
             "DHCP server, so the VLAN's Layer 3 SVI needs ip helper-address. The relay turns the broadcast into a "
             "unicast packet and sets giaddr to the SVI address; the server uses giaddr to select the correct scope "
             "and replies through the relay. DNS is a separate routed flow that starts after the client has a lease "
             "and a resolver address.",
    ),
    dict(
        file="visual-08-dns-troubleshooting-3afac0.jpg",
        title="How DNS Connects to Troubleshooting",
        text="Name resolution is a chain: application, /etc/hosts, nsswitch.conf, the stub resolver (often "
             "127.0.0.53), the upstream recursive resolver, then authoritative servers. Each failure looks "
             "different: no lease gives 169.254, a wrong DHCP DNS option sends queries nowhere, NXDOMAIN means the "
             "name does not exist, SERVFAIL means the resolver failed, and a timeout means no answer arrived. Use "
             "getent, resolvectl, dig and nslookup to find the broken link.",
    ),
    dict(
        file="visual-09-routing-troubleshooting-02349d.jpg",
        title="How Routing Connects to Troubleshooting",
        text="traceroute and mtr reveal the path hop by hop. The last answering hop shows where forwarding stops. "
             "Loss that appears at one hop and disappears later is usually ICMP rate limiting; loss that continues "
             "to the destination is real. A path MTU drop from 1500 to 1400 with DF set can create a PMTUD black "
             "hole, where large packets vanish and small ones work. Asymmetric routing explains one-way failures "
             "when the return path is missing or different.",
    ),
    dict(
        file="visual-10-full-workflow-193ced.jpg",
        title="The Complete Networking Workflow",
        text="Bring the whole path together: link up, DHCP DORA (address, gateway, DNS), ARP for the first hop, DNS "
             "lookup, TCP handshake, then TLS and HTTP. Each stage depends on the previous one and has its own "
             "diagnostic command. When a user says the network is down, find the first stage that fails; everything "
             "downstream of it is a symptom, not a separate fault.",
    ),
]


def visual_walkthroughs(story):
    from reportlab.platypus import Image
    from reportlab.lib.utils import ImageReader

    part(story, "VII", "Visual Walkthroughs",
         "Ten full-page diagrams: five topic explainers, four connection diagrams, and one end-to-end "
         "workflow. The captions carry the precise sequence; the diagrams are visual summaries.")
    body(story, "<b>In this part</b>", "Small")
    bullets(story, [f"Visual {i} — {v['title']}" for i, v in enumerate(VISUALS, 1)])
    for i, item in enumerate(VISUALS, 1):
        path = os.path.join(ROOT, "images", item["file"])
        if not os.path.exists(path):
            continue
        story.append(PageBreak())
        chapter(story, f"Visual {i} — {item['title']}")
        body(story, item["text"])
        iw, ih = ImageReader(path).getSize()
        max_h = 548
        max_w = CONTENT_W
        scale = min(max_w / iw, max_h / ih)
        w, h = iw * scale, ih * scale
        img = Image(path, width=w, height=h)
        img.hAlign = "CENTER"
        story.append(Spacer(1, 4))
        story.append(img)
        story.append(Paragraph(
            f"<i>Diagram {i} of {len(VISUALS)} — {esc(item['title'])}</i>",
            STY["Small"]))

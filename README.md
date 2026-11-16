# NetQuest

A local, single-user web app for networking and Linux interview preparation.
Networking is primary, Linux secondary. Everything runs on your machine:
content lives in JSON files, progress lives in SQLite, and the app binds to
`127.0.0.1` only.

Built for a DevOps engineer with roughly a year of experience who already knows
IP addressing and subnetting — it does not start from "what is an IP address".
A diagnostic produces a plan that lets you skip what you already know.

---

## What is in it

| Area | What it does |
| --- | --- |
| **Curriculum** | 7 modules, 26 lessons (IP addressing, switching/VLANs/STP, DHCP & DNS, connectivity troubleshooting, routing, Linux permissions, processes). Each lesson ends with multiple-choice and weighted self-assessment checks. |
| **Diagnostic** | 14 questions across all modules. Scores per module; anything at or above 75% is marked "strong — skip or skim" and deprioritised in the path. |
| **Command labs** | 26 labs across 6 groups (networking, connectivity, DNS, sockets, Linux, processes). Each has flags, worked examples, reading notes, common mistakes, a simulated question set, and a *real* half where you run the command on your own machine and paste the output. |
| **Simulators** | 4 interactive JavaScript simulators: L2 switching (MAC learning, flooding, VLAN isolation), DHCP DORA (step-through plus fault injection), DNS resolution (hosts → cache → hierarchy → faults), and routing (hop-by-hop trace, longest prefix match, loops). |
| **Case studies** | 12 troubleshooting missions with gated evidence collection, hypothesis testing, a written diagnosis, a root-cause reveal, and a multi-correct fix selection. |
| **Mock interview** | 14 question banks across 7 topics (2 per topic) with curated checklists and 18 follow-ups. Weak answers earn a probing follow-up, strong answers earn a harder one; the session ends with a per-topic report. |
| **Revision** | 4 drill sets plus an automatic list of your weakest recorded answers. |
| **Progress** | Weighted mastery per module, XP, ranks, streaks, attempt history, and a "what to do next" recommendation. |

Weighting for mastery: lessons 15%, checks 25%, labs 25%, missions 20%,
assessment 15%. Lessons alone cannot make a module "mastered" — that is
deliberate.

## Design constraints (on purpose)

- **The backend never executes a command.** You run commands in your own
  terminal; NetQuest grades the *pasted output* against curated regex rubrics.
  That keeps the app safe and makes you read real output from your own machine.
- **No outbound network calls.** No CDNs, no telemetry, no external fonts.
- **Deterministic grading only.** Multiple-choice answer keys, weighted
  self-assessment checklists, and regex rubrics. No LLM in the loop, so the
  same answer always scores the same.
- **Pasted output is never stored.** Only the rubric result is kept.

---

## Dependencies

Runtime:

- Python **3.10+** (developed on 3.15)
- `Flask` **3.1.3** — the only runtime dependency. Its own dependencies
  (`Werkzeug`, `Jinja2`, `MarkupSafe`, `itsdangerous`, `click`, `blinker`) are
  installed automatically.
- Python standard library: `sqlite3`, `json`, `pathlib`, `re`, `datetime`.

Development / tests:

- `pytest` **9.2.0**

Nothing else. There is no JavaScript build step, no npm, no database server, no
Docker. The front end is plain HTML/CSS/JS served by Flask.

---

## How to run

```bash
cd /home/sriharsham/netquest

# one-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# start
.venv/bin/python run.py
```

Then open <http://127.0.0.1:5000>.

The database is created automatically at `instance/netquest.db` on first run.

### Configuration (environment variables, all optional)

| Variable | Default | Purpose |
| --- | --- | --- |
| `NETQUEST_HOST` | `127.0.0.1` | Bind address. Leave it local. |
| `NETQUEST_PORT` | `5000` | Port. |
| `NETQUEST_SECRET` | dev key | Flask session secret. |
| `NETQUEST_DEBUG` | `0` | Set to `1` for Flask debug mode (auto-reload + tracebacks in the browser). |

The interview date, daily target, and accelerated mode are set in the app
under **Settings** (default interview date: 2026-11-17).

### Run the tests

```bash
cd /home/sriharsham/netquest
.venv/bin/python -m pytest tests -q
```

44 tests: content integrity (every id resolves, every MCQ key is valid, every
rubric regex compiles, every mission evidence prerequisite exists and is
acyclic), plus end-to-end route and API behaviour (grading, evidence gating,
interview branching, settings, reset, XP).

### Reset your progress

Settings → **Erase all progress** (type `RESET`), or delete
`instance/netquest.db`. Content files are never touched.

---

## Project layout

```
netquest/
├── run.py                  # entry point, binds 127.0.0.1
├── app.py                  # application factory, blueprints, error pages
├── config.py               # config, XP table, ranks, defaults
├── database.py             # SQLite schema + query helpers
├── routes/
│   ├── dashboard.py        # /
│   ├── learning.py         # /learn, /lesson, /diagnostic, /connections
│   ├── labs.py             # /labs
│   ├── simulations.py      # /simulations (+ /api/simulation/<id>/data)
│   ├── case_studies.py     # /missions
│   ├── interview.py        # /interview
│   ├── progress.py         # /progress, /revision
│   ├── settings.py         # /settings
│   └── api.py              # grading + progress write endpoints
├── services/
│   ├── content_service.py  # JSON loaders (cached)
│   ├── evaluation_service.py  # mcq / checklist / output-rubric grading
│   ├── progress_service.py # mastery, XP, streaks, recommendations
│   └── interview_service.py# session state and branching
├── content/
│   ├── modules/            # 7 module files (curriculum structure)
│   ├── lessons/            # 26 lesson files
│   ├── command_labs/       # 6 files, 26 labs
│   ├── simulations/        # metadata + per-simulator seed data
│   ├── case_studies/       # 12 case files
│   ├── journeys.json       # 5 packet/flow walkthroughs
│   ├── diagnostic.json     # 14-question assessment + plan rules
│   ├── interview.json      # topics and question banks
│   └── revision.json       # 4 drill sets
├── templates/              # Jinja2 pages
├── static/css/style.css    # single stylesheet, dark monochrome theme
├── static/js/              # app.js, quiz.js, sim-common.js, 4 simulator scripts
└── tests/                  # pytest suite
```

### Adding or editing content

Content is data, not code. To add a lesson, create
`content/lessons/mXlY.json` and add its id to the module's `lesson_ids`. To add
a lab, add it to the relevant file in `content/command_labs/`. Restart the app
(content is cached per process) and run the tests — they check that every id
resolves and every rubric pattern compiles.

Question types used throughout:

- `mcq` — `options`, `answer` (index), `explanation`, `why_wrong` (keys are
  *string* indices so JSON stays unambiguous).
- `self` — `checklist[{text, weight}]`, `min_to_pass` (fraction), `reference`.
- `output` — `expected_patterns[{pattern, label}]`, graded against pasted text.

---

## Suggested first session

1. **Settings** → confirm your interview date and daily target.
2. **Diagnostic** → answer honestly; skip the modules marked "strong".
3. Follow the dashboard's "Do this next" card, which advances you through
   lesson → lab → case study for the module you are weakest in.
4. Once a module's checks are green, do a mock interview on that topic — it is
   the closest thing here to the real conversation.

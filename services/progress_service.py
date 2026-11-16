"""Progress, mastery, XP and recommendation logic.

Mastery is *demonstrated performance*, never page views:

    lessons completed      15%
    knowledge-check results 25%
    command labs           25%
    case studies           20%
    module assessment      15%

Weights live in config so they are easy to audit and tune.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import current_app

from database import execute, query
from services import content_service

WEIGHTS = {
    "lessons": 15,
    "checks": 25,
    "labs": 25,
    "missions": 20,
    "assessment": 15,
}

STATUS_ORDER = ["not_started", "learning", "practised", "assessed", "mastered"]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def get_setting(key: str, default=None):
    row = query("SELECT value FROM user_settings WHERE key = ?", (key,), one=True)
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO user_settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def interview_date() -> date:
    raw = get_setting("interview_date", current_app.config["DEFAULT_INTERVIEW_DATE"])
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return date.fromisoformat(current_app.config["DEFAULT_INTERVIEW_DATE"])


def days_remaining() -> int:
    return (interview_date() - date.today()).days


def accelerated_mode() -> bool:
    return get_setting("accelerated_mode", "0") == "1"


# --------------------------------------------------------------------------
# XP and rank
# --------------------------------------------------------------------------
def award_xp(kind: str, reference: str, xp: int | None = None) -> int:
    """Award XP at most once per (kind, reference). Returns XP actually added."""
    if xp is None:
        xp = current_app.config["XP_TABLE"].get(kind, 0)
    if xp <= 0:
        return 0
    try:
        execute(
            "INSERT INTO activity(activity_type, activity_reference, xp_earned, timestamp) "
            "VALUES(?, ?, ?, ?)",
            (kind, reference, xp, now()),
        )
    except Exception:
        return 0  # unique index already contains this award
    return xp


def total_xp() -> int:
    row = query("SELECT COALESCE(SUM(xp_earned), 0) AS xp FROM activity", one=True)
    return int(row["xp"]) if row else 0


def rank_for(xp: int) -> tuple[str, int, int | None]:
    ranks = current_app.config["RANKS"]
    name, floor = ranks[0][1], ranks[0][0]
    nxt = None
    for threshold, label in ranks:
        if xp >= threshold:
            name, floor = label, threshold
        elif nxt is None:
            nxt = threshold
    return name, floor, nxt


def rank_progress() -> dict:
    xp = total_xp()
    name, floor, nxt = rank_for(xp)
    if nxt is None:
        pct = 100
    else:
        span = max(1, nxt - floor)
        pct = int(100 * (xp - floor) / span)
    return {"xp": xp, "rank": name, "next_threshold": nxt, "percent": max(0, min(100, pct))}


def recent_activity(limit: int = 8) -> list[dict]:
    return query(
        "SELECT activity_type, activity_reference, xp_earned, timestamp "
        "FROM activity ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def streak_days() -> int:
    rows = query("SELECT DISTINCT substr(timestamp, 1, 10) AS d FROM activity ORDER BY d DESC")
    if not rows:
        return 0
    days = {r["d"] for r in rows}
    streak = 0
    cursor = date.today()
    if cursor.isoformat() not in days:
        cursor = cursor - timedelta(days=1)
        if cursor.isoformat() not in days:
            return 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# --------------------------------------------------------------------------
# Attempts
# --------------------------------------------------------------------------
def record_attempt(question_id: str, module_id: str | None, context: str,
                   answer: str, result: dict) -> None:
    execute(
        "INSERT INTO attempts(question_id, module_id, context, submitted_answer, "
        "score, max_score, feedback, self_assessed, timestamp) "
        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            question_id,
            module_id,
            context,
            str(answer or "")[:4000],
            result["score"],
            result["max_score"],
            result.get("feedback", "")[:2000],
            1 if result.get("self_assessed") else 0,
            now(),
        ),
    )


def best_scores(question_ids: list[str]) -> dict[str, float]:
    """Best fraction (0..1) achieved per question id."""
    if not question_ids:
        return {}
    placeholders = ",".join("?" for _ in question_ids)
    rows = query(
        f"SELECT question_id, MAX(CAST(score AS REAL) / NULLIF(max_score, 0)) AS best "
        f"FROM attempts WHERE question_id IN ({placeholders}) GROUP BY question_id",
        tuple(question_ids),
    )
    return {r["question_id"]: float(r["best"] or 0) for r in rows}


def attempt_counts() -> int:
    row = query("SELECT COUNT(*) AS c FROM attempts", one=True)
    return int(row["c"]) if row else 0


# --------------------------------------------------------------------------
# Lesson progress
# --------------------------------------------------------------------------
def touch_lesson(lesson_id: str, module_id: str) -> None:
    execute(
        "INSERT INTO lesson_progress(lesson_id, module_id, last_accessed) VALUES(?, ?, ?) "
        "ON CONFLICT(lesson_id) DO UPDATE SET last_accessed = excluded.last_accessed",
        (lesson_id, module_id, now()),
    )


def lesson_state(lesson_id: str) -> dict:
    row = query("SELECT * FROM lesson_progress WHERE lesson_id = ?", (lesson_id,), one=True)
    if not row:
        return {"completed": 0, "assessment_score": 0, "attempts": 0}
    return dict(row)


def set_lesson_completed(lesson_id: str, module_id: str, score: int | None = None) -> None:
    execute(
        "INSERT INTO lesson_progress(lesson_id, module_id, completed, assessment_score, "
        "last_accessed) VALUES(?, ?, 1, ?, ?) "
        "ON CONFLICT(lesson_id) DO UPDATE SET completed = 1, "
        "assessment_score = MAX(COALESCE(?, lesson_progress.assessment_score), "
        "COALESCE(lesson_progress.assessment_score, 0)), last_accessed = excluded.last_accessed",
        (lesson_id, module_id, score or 0, now(), score),
    )


def lessons_completed_map() -> dict[str, int]:
    rows = query("SELECT lesson_id, completed FROM lesson_progress")
    return {r["lesson_id"]: r["completed"] for r in rows}


# --------------------------------------------------------------------------
# Labs / simulations / missions
# --------------------------------------------------------------------------
def touch_lab(lab_id: str, module_id: str | None, sim_percent: int | None = None,
              real_percent: int | None = None) -> dict:
    row = query("SELECT * FROM lab_progress WHERE lab_id = ?", (lab_id,), one=True)
    sim_score = row["sim_score"] if row else 0
    sim_done = row["sim_done"] if row else 0
    real_done = row["real_done"] if row else 0
    notes = row["real_notes"] if row else None

    if sim_percent is not None:
        sim_score = max(sim_score, sim_percent)
        sim_done = 1 if sim_score >= 80 else sim_done
    if real_percent is not None:
        real_done = 1 if real_percent >= 80 else real_done
    status = "practised" if (sim_done and real_done) else "learning"

    execute(
        "INSERT INTO lab_progress(lab_id, module_id, sim_score, sim_done, real_done, "
        "status, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(lab_id) DO UPDATE SET sim_score = excluded.sim_score, "
        "sim_done = excluded.sim_done, real_done = excluded.real_done, "
        "status = excluded.status, updated_at = excluded.updated_at",
        (lab_id, module_id, sim_score, sim_done, real_done, status, now()),
    )
    return {"sim_score": sim_score, "sim_done": sim_done, "real_done": real_done,
            "status": status}


def lab_states() -> dict[str, dict]:
    rows = query("SELECT * FROM lab_progress")
    return {r["lab_id"]: dict(r) for r in rows}


def set_simulation_complete(sim_id: str, score: int) -> dict:
    execute(
        "INSERT INTO simulation_progress(simulation_id, completed, score, updated_at) "
        "VALUES(?, ?, ?, ?) ON CONFLICT(simulation_id) DO UPDATE SET "
        "completed = MAX(completed, excluded.completed), "
        "score = MAX(score, excluded.score), updated_at = excluded.updated_at",
        (sim_id, 1 if score >= 60 else 0, score, now()),
    )
    row = query("SELECT * FROM simulation_progress WHERE simulation_id = ?",
                (sim_id,), one=True)
    return dict(row) if row else {}


def simulation_states() -> dict[str, dict]:
    rows = query("SELECT * FROM simulation_progress")
    return {r["simulation_id"]: dict(r) for r in rows}


def mission_state(mission_id: str) -> dict:
    row = query("SELECT * FROM mission_progress WHERE mission_id = ?",
                (mission_id,), one=True)
    return dict(row) if row else {"status": "open", "score": 0, "attempts": 0}


def mission_states() -> dict[str, dict]:
    rows = query("SELECT * FROM mission_progress")
    return {r["mission_id"]: dict(r) for r in rows}


def set_mission_progress(mission_id: str, solved: bool, score: int = 0) -> None:
    state = mission_state(mission_id)
    status = "solved" if solved else "investigating"
    best = max(state.get("score", 0), score)
    execute(
        "INSERT INTO mission_progress(mission_id, status, score, attempts, completed_at) "
        "VALUES(?, ?, ?, 1, ?) ON CONFLICT(mission_id) DO UPDATE SET "
        "status = excluded.status, score = MAX(mission_progress.score, excluded.score), "
        "attempts = mission_progress.attempts + 1, "
        "completed_at = CASE WHEN excluded.status = 'solved' "
        "THEN excluded.completed_at ELSE mission_progress.completed_at END",
        (mission_id, status, best, now() if solved else None),
    )


# --------------------------------------------------------------------------
# Mastery
# --------------------------------------------------------------------------
def _fraction(rows: list[dict], key: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.get(key)) / len(rows)


def module_stats(module: dict) -> dict:
    """Compute mastery components for one module."""
    m = module
    lp = {r["lesson_id"]: dict(r) for r in query("SELECT * FROM lesson_progress")}
    lessons = m["lessons"]
    completed = sum(1 for lesson in lessons if lp.get(lesson["id"], {}).get("completed"))

    q_ids = [q["id"] for lesson in lessons for q in lesson.get("checks", [])]
    q_ids += [q["id"] for q in m.get("assessment", [])]
    best = best_scores(q_ids)
    check_ids = [q["id"] for lesson in lessons for q in lesson.get("checks", [])]
    check_frac = (
        sum(best.get(qid, 0) for qid in check_ids) / len(check_ids) if check_ids else 0.0
    )
    assessment_ids = [q["id"] for q in m.get("assessment", [])]
    assessment_frac = (
        sum(best.get(qid, 0) for qid in assessment_ids) / len(assessment_ids)
        if assessment_ids else 0.0
    )

    labs_state = lab_states()
    lab_ids = m.get("lab_ids", [])
    lab_frac = 0.0
    if lab_ids:
        parts = []
        for lid in lab_ids:
            st = labs_state.get(lid, {})
            # each lab counts half for the simulated challenge, half for real practice
            parts.append(0.5 * (st.get("sim_score", 0) / 100) + 0.5 * (1 if st.get("real_done") else 0))
        lab_frac = sum(parts) / len(parts)

    missions_state = mission_states()
    mission_ids = m.get("mission_ids", [])
    mission_frac = 0.0
    if mission_ids:
        mission_frac = sum(
            1 for mid in mission_ids if missions_state.get(mid, {}).get("status") == "solved"
        ) / len(mission_ids)

    lesson_frac = completed / len(lessons) if lessons else 0.0
    mastery = round(
        WEIGHTS["lessons"] * lesson_frac
        + WEIGHTS["checks"] * check_frac
        + WEIGHTS["labs"] * lab_frac
        + WEIGHTS["missions"] * mission_frac
        + WEIGHTS["assessment"] * assessment_frac
    )

    if mastery == 0 and completed == 0 and attempt_counts() == 0:
        status = "not_started"
    elif mastery >= 85 and assessment_frac >= 0.8 and (not mission_ids or mission_frac == 1):
        status = "mastered"
    elif mastery >= 55:
        status = "assessed"
    elif mastery >= 25:
        status = "practised"
    elif mastery > 0 or completed:
        status = "learning"
    else:
        status = "not_started"

    return {
        "module_id": m["id"],
        "title": m["title"],
        "number": m["number"],
        "priority": m.get("priority", "core"),
        "mastery": mastery,
        "status": status,
        "lessons_total": len(lessons),
        "lessons_completed": completed,
        "checks_percent": round(check_frac * 100),
        "labs_total": len(lab_ids),
        "labs_done": sum(1 for lid in lab_ids if labs_state.get(lid, {}).get("sim_done")),
        "labs_real_done": sum(1 for lid in lab_ids if labs_state.get(lid, {}).get("real_done")),
        "missions_total": len(mission_ids),
        "missions_solved": sum(
            1 for mid in mission_ids if missions_state.get(mid, {}).get("status") == "solved"
        ),
        "assessment_percent": round(assessment_frac * 100),
        "assessment_attempted": any(best.get(qid, 0) > 0 for qid in assessment_ids),
    }


def all_module_stats() -> list[dict]:
    return [module_stats(m) for m in content_service.modules()]


def overall() -> dict:
    stats = all_module_stats()
    total_weight = sum(m.get("weight", 1) for m in content_service.modules()) or 1
    weighted = 0.0
    for m, s in zip(content_service.modules(), stats):
        weighted += s["mastery"] * m.get("weight", 1)
    overall_mastery = round(weighted / total_weight)
    rp = rank_progress()
    return {
        "mastery": overall_mastery,
        "modules": stats,
        "xp": rp["xp"],
        "rank": rp["rank"],
        "rank_next": rp["next_threshold"],
        "rank_percent": rp["percent"],
        "lessons_completed": sum(s["lessons_completed"] for s in stats),
        "lessons_total": sum(s["lessons_total"] for s in stats),
        "labs_done": sum(s["labs_done"] for s in stats),
        "labs_total": sum(s["labs_total"] for s in stats),
        "missions_solved": sum(s["missions_solved"] for s in stats),
        "missions_total": sum(s["missions_total"] for s in stats),
        "weak": sorted(
            [s for s in stats if s["mastery"] < 70], key=lambda s: s["mastery"]
        ),
        "days_remaining": days_remaining(),
        "streak": streak_days(),
        "attempts": attempt_counts(),
    }


# --------------------------------------------------------------------------
# Recommendations
# --------------------------------------------------------------------------
def recommend_next() -> dict:
    """Pick the next activity: weakest module, priority-aware."""
    stats = all_module_stats()
    accelerated = accelerated_mode()
    modules = {m["id"]: m for m in content_service.modules()}

    def score(s: dict) -> float:
        # lower mastery first; priority modules pulled forward in accelerated mode
        priority_bonus = 0
        if accelerated:
            priority_bonus = {"core": 25, "revision": 15, "secondary": 0}.get(s["priority"], 0)
        return s["mastery"] - priority_bonus

    pending = [s for s in stats if s["mastery"] < 90]
    if not pending:
        return {
            "kind": "revision",
            "title": "Keep it sharp",
            "detail": "Everything is above 90% mastery. Run a mock interview or a timed mission.",
            "href": "/interview",
            "label": "Start mock interview",
        }

    target = min(pending, key=score)
    module = modules[target["module_id"]]
    if target["lessons_completed"] < target["lessons_total"]:
        nxt = next(
            (l for l in module["lessons"]
             if not lesson_state(l["id"]).get("completed")),
            module["lessons"][0],
        )
        return {
            "kind": "lesson",
            "title": f"Continue {module['title']}",
            "detail": f"Next lesson: {nxt['title']} \u2014 {target['mastery']}% mastery so far.",
            "href": f"/lesson/{nxt['id']}",
            "label": "Continue learning",
        }
    if target["labs_total"] and target["labs_done"] < target["labs_total"]:
        lab_id = next(
            (lid for lid in module.get("lab_ids", [])
             if not lab_states().get(lid, {}).get("sim_done")),
            module["lab_ids"][0],
        )
        lab = content_service.lab(lab_id)
        return {
            "kind": "lab",
            "title": f"Practise {lab['command'] if lab else lab_id}",
            "detail": f"Command lab in {module['title']} \u2014 practical work drives mastery.",
            "href": f"/labs/{lab_id}",
            "label": "Open command lab",
        }
    if target["missions_total"] and target["missions_solved"] < target["missions_total"]:
        mid = next(
            (m for m in module.get("mission_ids", [])
             if mission_state(m).get("status") != "solved"),
            module["mission_ids"][0],
        )
        return {
            "kind": "mission",
            "title": f"Diagnose mission {mid}",
            "detail": "Case studies carry the most weight towards mastery.",
            "href": f"/missions/{mid}",
            "label": "Open the mission",
        }
    return {
        "kind": "assessment",
        "title": f"Take the {module['title']} assessment",
        "detail": f"Current assessment score: {target['assessment_percent']}%.",
        "href": f"/learn/{module['id']}#assessment",
        "label": "Start assessment",
    }


def revision_items(limit: int = 12) -> list[dict]:
    """Questions answered below 75%, weakest first, joined with content."""
    rows = query(
        "SELECT question_id, MAX(CAST(score AS REAL) / NULLIF(max_score,0)) AS best, "
        "COUNT(*) AS tries, MAX(timestamp) AS last "
        "FROM attempts GROUP BY question_id HAVING best < 0.75 "
        "ORDER BY best ASC, last DESC LIMIT ?",
        (limit,),
    )
    index = content_service.lesson_question_index()
    items = []
    for r in rows:
        entry = index.get(r["question_id"])
        if not entry:
            continue
        q = entry["question"]
        module = content_service.module(entry["module_id"]) if entry["module_id"] else None
        items.append({
            "question_id": r["question_id"],
            "prompt": q["prompt"],
            "best": round((r["best"] or 0) * 100),
            "tries": r["tries"],
            "module_id": entry["module_id"],
            "module_title": module["title"] if module else "",
            "lesson_id": entry["lesson_id"],
            "context": entry["context"],
            "href": f"/lesson/{entry['lesson_id']}" if entry["lesson_id"] else
                    (f"/learn/{entry['module_id']}" if entry["module_id"] else "/revision"),
        })
    return items

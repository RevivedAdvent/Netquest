"""Mock interview engine.

One question at a time, curated follow-ups, structured self-assessment and a
final report. Entirely local and deterministic: branching depends on the
learner's checklist score, not on any language model.
"""
from __future__ import annotations

import json
from datetime import datetime

from services import content_service, evaluation_service, progress_service


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def bank() -> dict:
    return content_service.interview_bank()


def question_map() -> dict[str, dict]:
    return {q["id"]: q for q in bank()["questions"]} | {
        f["id"]: f for q in bank()["questions"] for f in q.get("followups", [])
    }


def build_queue(length: int, focus: str | None = None) -> list[str]:
    """Pick questions: weak topics first, then breadth across topics."""
    questions = bank()["questions"]
    if focus:
        questions = [q for q in questions if q.get("topic") == focus] or questions

    # Weakness weighting from recorded attempts per topic.
    stats = {s["module_id"]: s["mastery"] for s in progress_service.all_module_stats()}
    links = bank().get("topic_modules", {})
    scored = []
    for q in questions:
        module_id = links.get(q.get("topic"), "")
        mastery = stats.get(module_id, 50)
        scored.append((mastery, q["priority"] if "priority" in q else 0, q["id"]))
    scored.sort(key=lambda row: (row[0], -row[1]))

    queue: list[str] = []
    seen_topics: dict[str, int] = {}
    for _mastery, _prio, qid in scored:
        q = next(x for x in questions if x["id"] == qid)
        topic = q.get("topic", "general")
        # at most 3 questions per topic, breadth is more useful than depth here
        if seen_topics.get(topic, 0) >= 3:
            continue
        queue.append(qid)
        seen_topics[topic] = seen_topics.get(topic, 0) + 1
        if len(queue) >= length:
            break
    return queue


def start_session(length: int = 8, focus: str | None = None) -> dict:
    queue = build_queue(length, focus)
    if not queue:
        return {"error": "no questions available"}
    from database import execute
    state = {"target": len(queue), "queue": queue, "asked": [], "scores": [],
             "followup_used": {}, "focus": focus or "all"}
    sid = execute(
        "INSERT INTO interview_sessions(started_at, score, report) VALUES(?, 0, ?)",
        (_now(), json.dumps(state)),
    )
    return {"session_id": sid, "question": public_question(queue[0]),
            "remaining": len(queue)}


def public_question(qid: str) -> dict:
    q = question_map().get(qid)
    if not q:
        return {"id": qid, "prompt": "Question unavailable.", "checklist": []}
    return {
        "id": q["id"],
        "prompt": q["prompt"],
        "topic": q.get("topic", "general"),
        "kind": q.get("kind", "conceptual"),
        "checklist": [{"text": item["text"], "weight": item.get("weight", 1)}
                      for item in q.get("checklist", [])],
        "min_to_pass": q.get("min_to_pass", 0.7),
    }


def _load_state(sid: int) -> dict | None:
    from database import query
    row = query("SELECT * FROM interview_sessions WHERE id = ?", (sid,), one=True)
    if not row:
        return None
    state = json.loads(row["report"] or "{}")
    state["_row"] = dict(row)
    return state


def _save_state(sid: int, state: dict, finished: bool = False) -> None:
    from database import execute
    payload = {k: v for k, v in state.items() if not k.startswith("_")}
    execute(
        "UPDATE interview_sessions SET report = ?, finished_at = ?, score = ? WHERE id = ?",
        (json.dumps(payload), _now() if finished else None,
         int(sum(payload.get("scores", [])) / max(1, len(payload.get("scores", [])))),
         sid),
    )


def answer(sid: int, qid: str, text: str, covered: list[str]) -> dict:
    state = _load_state(sid)
    if not state:
        return {"error": "unknown session"}
    if state.get("_row", {}).get("finished_at"):
        return {"error": "session already finished"}

    q = question_map().get(qid)
    if not q:
        return {"error": "unknown question"}

    result = evaluation_service.grade_checklist(q, covered)
    from database import execute
    execute(
        "INSERT INTO interview_answers(session_id, question_id, answer, covered, score, timestamp) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (sid, qid, (text or "")[:6000], json.dumps(covered or []), result["percent"], _now()),
    )
    progress_service.record_attempt(
        f"interview:{qid}", bank().get("topic_modules", {}).get(q.get("topic")),
        f"interview:{sid}", text or "", {
            "score": result["score"], "max_score": result["max_score"],
            "feedback": result["feedback"], "self_assessed": True})
    progress_service.award_xp("interview_question", f"{sid}:{qid}")

    state.setdefault("asked", []).append(qid)
    state.setdefault("scores", []).append(result["percent"])
    state.setdefault("followup_used", {})

    # --- branching -------------------------------------------------------
    nxt = None
    followups = q.get("followups", [])
    used = state["followup_used"].get(qid, 0)
    if followed := [f for f in followups if f.get("after", "weak") == "weak"]:
        if result["percent"] < 65 and used == 0 and followed:
            nxt = followed[0]
    if nxt is None and result["percent"] >= 80 and used == 0:
        strong = [f for f in followups if f.get("after") == "strong"]
        if strong:
            nxt = strong[0]
    if nxt is not None:
        state["followup_used"][qid] = used + 1
        _save_state(sid, state)
        return {
            "result": result,
            "reference": q.get("reference", ""),
            "next": public_question(nxt["id"]),
            "followup": True,
            "progress": {"asked": len(state["asked"]), "target": state["target"]},
            "average": round(sum(state["scores"]) / len(state["scores"])),
        }

    # --- advance the main queue -----------------------------------------
    queue = state.get("queue", [])
    asked = set(state["asked"])
    remaining_queue = [x for x in queue if x not in asked]
    if not remaining_queue:
        report = finish(sid, state)
        return {
            "result": result,
            "reference": q.get("reference", ""),
            "next": None,
            "report": report,
            "progress": {"asked": len(state["asked"]), "target": state["target"]},
            "average": round(sum(state["scores"]) / len(state["scores"])),
        }

    _save_state(sid, state)
    return {
        "result": result,
        "reference": q.get("reference", ""),
        "next": public_question(remaining_queue[0]),
        "followup": False,
        "progress": {"asked": len(state["asked"]), "target": state["target"]},
        "average": round(sum(state["scores"]) / len(state["scores"])),
    }


def finish(sid: int, state: dict | None = None) -> dict:
    from database import query
    if state is None:
        state = _load_state(sid) or {}
    rows = query("SELECT * FROM interview_answers WHERE session_id = ?", (sid,))
    qmap = question_map()
    per_topic: dict[str, list[int]] = {}
    for row in rows:
        topic = qmap.get(row["question_id"], {}).get("topic", "general")
        per_topic.setdefault(topic, []).append(row["score"])
    topics = {t: round(sum(v) / len(v)) for t, v in per_topic.items()}
    overall = round(sum(topics.values()) / len(topics)) if topics else 0

    strengths = [t for t, v in sorted(topics.items(), key=lambda kv: -kv[1]) if v >= 70]
    weaknesses = [t for t, v in sorted(topics.items(), key=lambda kv: kv[1]) if v < 60]

    report = {
        "overall": overall,
        "questions": len(rows),
        "topics": topics,
        "strengths": strengths[:4],
        "weaknesses": weaknesses[:6],
        "topic_modules": bank().get("topic_modules", {}),
        "advice": _advice(overall, weaknesses, topics),
        "finished_at": _now(),
    }
    state["report"] = report
    _save_state(sid, state, finished=True)
    if rows:
        progress_service.award_xp("interview_complete", f"{sid}")
    return report


def _advice(overall: int, weaknesses: list[str], topics: dict[str, int]) -> list[str]:
    advice = []
    if overall >= 85:
        advice.append("Interview ready on explanation depth. Keep drilling timed case studies.")
    elif overall >= 70:
        advice.append("Solid. Tighten the weak topics below and re-run this interview in a week.")
    elif overall >= 50:
        advice.append("Half-way. Re-read the linked lessons, then redo the weak questions.")
    else:
        advice.append("Start with the lessons for your weakest topics before another interview.")
    for topic in weaknesses[:3]:
        module = bank().get("topic_modules", {}).get(topic)
        if module:
            advice.append(f"Revise {topic} \u2014 open the related module and its command labs.")
    if not weaknesses:
        advice.append("No topic scored below 60%. Move to full end-to-end journeys and missions.")
    return advice


def sessions(limit: int = 6) -> list[dict]:
    from database import query
    rows = query("SELECT * FROM interview_sessions ORDER BY id DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        rep = json.loads(r["report"] or "{}")
        out.append({
            "id": r["id"], "started_at": r["started_at"],
            "finished_at": r["finished_at"], "score": r["score"],
            "overall": rep.get("report", {}).get("overall") if rep.get("report") else None,
            "questions": len(rep.get("asked", [])),
        })
    return out

"""JSON endpoints used by the frontend (fetch API).

All evaluation is deterministic and local. Nothing here executes shell
commands or contacts the network.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from database import execute, query
from services import content_service, evaluation_service, progress_service

bp = Blueprint("api", __name__, url_prefix="/api")


def _error(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _mastery(module_id: str | None) -> dict | None:
    module = content_service.module(module_id) if module_id else None
    if not module:
        return None
    stats = progress_service.module_stats(module)
    return {"module_id": stats["module_id"], "mastery": stats["mastery"],
            "status": stats["status"], "assessment_percent": stats["assessment_percent"]}


# --------------------------------------------------------------------------
# Questions: multiple choice, structured self-assessment, output rubrics
# --------------------------------------------------------------------------
@bp.post("/answer")
def answer():
    payload = request.get_json(silent=True) or {}
    qid = payload.get("question_id")
    if not qid:
        return _error("question_id is required")

    entry = content_service.lesson_question_index().get(qid)
    if not entry:
        return _error("unknown question", 404)

    question = entry["question"]
    result = evaluation_service.grade_question(question, payload)
    progress_service.record_attempt(
        qid, entry["module_id"], entry["context"],
        payload.get("answer") or payload.get("text") or
        ", ".join(payload.get("covered", []) or []),
        result,
    )

    # XP: only correct/passing attempts, only once per question.
    if result.get("correct") or result.get("percent", 0) >= 75:
        kind = "self_assessment" if result.get("self_assessed") else "quiz_correct"
        progress_service.award_xp(kind, qid)

    return jsonify({
        "result": result,
        "mastery": _mastery(entry["module_id"]),
        "xp": progress_service.rank_progress(),
        "counts": _assessment_counts(entry["module_id"]),
    })


def _assessment_counts(module_id: str | None) -> dict:
    if not module_id:
        return {}
    module = content_service.module(module_id)
    if not module:
        return {}
    qids = [q["id"] for q in module.get("assessment", [])]
    best = progress_service.best_scores(qids)
    answered = sum(1 for q in qids if q in best)
    passed = sum(1 for q in qids if best.get(q, 0) >= 0.75)
    return {"assessment_total": len(qids), "assessment_answered": answered,
            "assessment_passed": passed}


@bp.post("/lesson/<lesson_id>/complete")
def complete_lesson(lesson_id):
    lesson = content_service.lesson(lesson_id)
    if not lesson:
        return _error("unknown lesson", 404)
    progress_service.set_lesson_completed(lesson_id, lesson["module_id"])
    progress_service.award_xp("quiz_correct", f"lesson:{lesson_id}", xp=5)
    stats = progress_service.module_stats(content_service.module(lesson["module_id"]))
    return jsonify({"ok": True, "mastery": stats,
                    "xp": progress_service.rank_progress()})


@bp.post("/checklist/<question_id>")
def checklist(question_id):
    """Explicit checklist submission (used by descriptive answers)."""
    payload = request.get_json(silent=True) or {}
    entry = content_service.lesson_question_index().get(question_id)
    if not entry:
        return _error("unknown question", 404)
    result = evaluation_service.grade_checklist(entry["question"], payload.get("covered", []))
    progress_service.record_attempt(question_id, entry["module_id"], entry["context"],
                                   payload.get("text", ""), result)
    if result["passed"]:
        progress_service.award_xp("self_assessment", question_id)
    return jsonify({"result": result, "mastery": _mastery(entry["module_id"])})


# --------------------------------------------------------------------------
# Command labs
# --------------------------------------------------------------------------
def _lab_module_id(lab: dict) -> str | None:
    return lab.get("module_id")


@bp.post("/lab/<lab_id>/simulate")
def lab_simulate(lab_id):
    lab = content_service.lab(lab_id)
    if not lab:
        return _error("unknown lab", 404)
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers", {})
    questions = lab.get("simulate", {}).get("questions", [])
    if not questions:
        return _error("this lab has no simulated questions", 400)

    results = []
    for q in questions:
        submitted = answers.get(q["id"])
        if submitted is None:
            results.append({"id": q["id"], "percent": 0, "score": 0, "max_score": 1,
                            "feedback": "Not answered.", "correct": False,
                            "correct_answer": q["options"][q["answer"]]})
            continue
        res = evaluation_service.grade_mcq(q, submitted)
        res["id"] = q["id"]
        results.append(res)
        progress_service.record_attempt(q["id"], _lab_module_id(lab), f"lab:{lab_id}",
                                       str(submitted), res)

    summary = evaluation_service.summarise(results)
    state = progress_service.touch_lab(lab_id, _lab_module_id(lab),
                                      sim_percent=summary["percent"])
    if summary["percent"] >= 80:
        progress_service.award_xp("lab_simulated", lab_id)

    return jsonify({
        "summary": summary,
        "results": results,
        "lab_state": state,
        "mastery": _mastery(_lab_module_id(lab)),
        "xp": progress_service.rank_progress(),
    })


@bp.post("/lab/<lab_id>/paste")
def lab_paste(lab_id):
    lab = content_service.lab(lab_id)
    if not lab:
        return _error("unknown lab", 404)
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    if len(text) > 20000:
        return _error("output too large; paste only the relevant lines", 413)
    exercise = lab.get("try", {})
    result = evaluation_service.grade_output(exercise, text)
    progress_service.touch_lab(lab_id, _lab_module_id(lab),
                              real_percent=result["percent"])
    if result["complete"]:
        progress_service.award_xp("lab_real", lab_id)
    # Do not persist raw output (may contain private network details).
    return jsonify({
        "assessment": result,
        "mastery": _mastery(_lab_module_id(lab)),
        "xp": progress_service.rank_progress(),
    })


# --------------------------------------------------------------------------
# Simulations
# --------------------------------------------------------------------------
@bp.post("/simulation/<sim_id>/complete")
def simulation_complete(sim_id):
    sim = content_service.simulation(sim_id)
    if not sim:
        return _error("unknown simulation", 404)
    payload = request.get_json(silent=True) or {}
    answers = payload.get("answers", {})
    questions = sim.get("assessment", [])
    results = []
    for q in questions:
        if q.get("type") == "mcq":
            res = evaluation_service.grade_mcq(q, answers.get(q["id"], -1))
        else:
            res = evaluation_service.grade_checklist(q, answers.get(q["id"], []))
        res["id"] = q["id"]
        results.append(res)
        progress_service.record_attempt(q["id"], sim.get("module_id"), f"sim:{sim_id}",
                                       str(answers.get(q["id"], "")), res)
    summary = evaluation_service.summarise(results)
    state = progress_service.set_simulation_complete(sim_id, summary["percent"])
    if summary["percent"] >= 60:
        progress_service.award_xp("simulation_complete", sim_id)
        progress_service.award_xp("quiz_correct", f"sim:{sim_id}")
    return jsonify({"summary": summary, "results": results, "state": state,
                    "mastery": _mastery(sim.get("module_id")),
                    "xp": progress_service.rank_progress()})


# --------------------------------------------------------------------------
# Case studies / missions
# --------------------------------------------------------------------------
@bp.post("/mission/<mission_id>/evidence")
def mission_evidence(mission_id):
    mission = content_service.mission(mission_id)
    if not mission:
        return _error("unknown mission", 404)
    payload = request.get_json(silent=True) or {}
    eid = payload.get("evidence_id")
    entry = next((e for e in mission["evidence"] if e["id"] == eid), None)
    if not entry:
        return _error("unknown evidence item", 404)

    collected = {r["evidence_id"] for r in query(
        "SELECT evidence_id FROM mission_evidence WHERE mission_id = ?", (mission_id,))}
    missing = [req for req in entry.get("requires", []) if req not in collected]
    if missing:
        return jsonify({
            "blocked": True,
            "message": "That action makes no sense yet. Collect the prerequisite evidence first: "
                       + ", ".join(missing),
        })

    execute(
        "INSERT OR IGNORE INTO mission_evidence(mission_id, evidence_id, collected_at) "
        "VALUES(?, ?, ?)", (mission_id, eid, progress_service.now()))
    progress_service.set_mission_progress(mission_id, solved=False)

    return jsonify({
        "blocked": False,
        "evidence": {"id": eid, "label": entry["label"],
                     "command": entry.get("command", ""),
                     "output": entry.get("output", ""),
                     "insight": entry.get("insight", "")},
        "collected": sorted(collected | {eid}),
    })


@bp.post("/mission/<mission_id>/hypothesis")
def mission_hypothesis(mission_id):
    mission = content_service.mission(mission_id)
    if not mission:
        return _error("unknown mission", 404)
    payload = request.get_json(silent=True) or {}
    idx = payload.get("index")
    try:
        hyp = mission["hypotheses"][int(idx)]
    except (TypeError, ValueError, IndexError):
        return _error("unknown hypothesis", 400)
    return jsonify({"verdict": hyp["verdict"], "why": hyp["why"]})


@bp.post("/mission/<mission_id>/diagnose")
def mission_diagnose(mission_id):
    mission = content_service.mission(mission_id)
    if not mission:
        return _error("unknown mission", 404)
    payload = request.get_json(silent=True) or {}
    diagnosis = payload.get("diagnosis", "")
    if len(diagnosis.strip()) < 10:
        return _error("write at least a sentence describing the root cause")

    collected = [r["evidence_id"] for r in query(
        "SELECT evidence_id FROM mission_evidence WHERE mission_id = ?", (mission_id,))]
    if len(collected) < mission.get("min_evidence", 2):
        return jsonify({
            "blocked": True,
            "message": f"Collect at least {mission.get('min_evidence', 2)} pieces of "
                       "evidence before committing to a root cause.",
        })

    result = evaluation_service.grade_mission_diagnosis(mission, diagnosis,
                                                       payload.get("confidence", "medium"))
    progress_service.record_attempt(f"{mission_id}:diagnosis", mission.get("module_id"),
                                   f"mission:{mission_id}", diagnosis, {
                                       "score": 1 if result["correct"] else 0,
                                       "max_score": 1,
                                       "feedback": result["feedback"],
                                       "self_assessed": False,
                                   })
    solved = result["correct"]
    breadth = min(1.0, len(collected) / max(1, len(mission["evidence"])))
    score = round(60 * (1 if solved else 0) + 40 * breadth)
    progress_service.set_mission_progress(mission_id, solved=solved, score=score)
    if solved:
        progress_service.award_xp("mission_solved", mission_id)

    response = {
        "blocked": False,
        "result": result,
        "evidence_count": len(collected),
        "score": score,
        "mastery": _mastery(mission.get("module_id")),
        "xp": progress_service.rank_progress(),
    }
    if solved:
        response["solution"] = {
            "root_cause": mission["solution"]["root_cause"],
            "resolution": mission["solution"]["resolution"],
            "verification": mission["solution"]["verification"],
            "lessons": mission["solution"].get("lessons", []),
            "interview_questions": mission.get("interview_questions", []),
        }
        response["resolution_options"] = mission.get("resolution_options", [])
    return jsonify(response)


@bp.post("/mission/<mission_id>/resolution")
def mission_resolution(mission_id):
    mission = content_service.mission(mission_id)
    if not mission:
        return _error("unknown mission", 404)
    if progress_service.mission_state(mission_id).get("status") != "solved":
        return _error("fix the root cause first", 403)
    payload = request.get_json(silent=True) or {}
    chosen = payload.get("chosen", [])
    options = mission.get("resolution_options", [])
    correct_texts = [o["text"] for o in options if o.get("correct")]
    selected_correct = [o for o in options if o.get("correct") and o["text"] in chosen]
    wrong = [o for o in options if not o.get("correct") and o["text"] in chosen]
    percent = round(100 * len(selected_correct) / len(correct_texts)) if correct_texts else 100
    if wrong:
        percent = max(0, percent - 20 * len(wrong))
    if percent >= 80:
        progress_service.award_xp("lab_real", f"{mission_id}:resolution")
    return jsonify({
        "percent": percent,
        "correct": correct_texts,
        "rejected": [{"text": o["text"], "why": o.get("why", "")} for o in wrong],
        "notes": [{"text": o["text"], "why": o.get("why", "")} for o in options if o.get("correct")],
    })


# --------------------------------------------------------------------------
# Settings + reset
# --------------------------------------------------------------------------
@bp.post("/settings")
def save_settings():
    payload = request.get_json(silent=True) or {}
    date = payload.get("interview_date", "").strip()
    if date:
        from datetime import date as date_cls
        try:
            date_cls.fromisoformat(date)
        except ValueError:
            return _error("interview_date must look like 2026-11-17")
        progress_service.set_setting("interview_date", date)
    if "accelerated_mode" in payload:
        progress_service.set_setting("accelerated_mode",
                                     "1" if payload["accelerated_mode"] else "0")
    if "name" in payload:
        progress_service.set_setting("name", str(payload["name"])[:60])
    if "daily_target_minutes" in payload:
        try:
            minutes = max(10, min(480, int(payload["daily_target_minutes"])))
            progress_service.set_setting("daily_target_minutes", str(minutes))
        except (TypeError, ValueError):
            return _error("daily_target_minutes must be a number")
    return jsonify({
        "ok": True,
        "interview_date": progress_service.interview_date().isoformat(),
        "days_remaining": progress_service.days_remaining(),
        "accelerated": progress_service.accelerated_mode(),
    })


@bp.post("/settings/reset")
def reset_progress():
    payload = request.get_json(silent=True) or {}
    if payload.get("confirm") != "RESET":
        return _error("send {\"confirm\": \"RESET\"} to erase progress")
    for table in ["module_progress", "lesson_progress", "attempts", "mission_progress",
                  "mission_evidence", "lab_progress", "simulation_progress", "activity",
                  "interview_answers", "interview_sessions"]:
        execute(f"DELETE FROM {table}")
    return jsonify({"ok": True})

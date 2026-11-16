"""Progress statistics and the revision dashboard."""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from database import query
from services import content_service, progress_service

bp = Blueprint("progress", __name__)


@bp.get("/progress")
def stats():
    overall = progress_service.overall()
    history = query(
        "SELECT substr(timestamp,1,10) AS day, COUNT(*) AS attempts FROM attempts "
        "GROUP BY day ORDER BY day DESC LIMIT 21")
    xp_by_day = query(
        "SELECT substr(timestamp,1,10) AS day, SUM(xp_earned) AS xp FROM activity "
        "GROUP BY day ORDER BY day DESC LIMIT 21")
    per_module_attempts = query(
        "SELECT module_id, COUNT(*) AS n, "
        "AVG(CAST(score AS REAL)/NULLIF(max_score,0)) AS avg FROM attempts "
        "WHERE module_id IS NOT NULL GROUP BY module_id")
    latest = query("SELECT * FROM attempts ORDER BY id DESC LIMIT 15")
    return render_template("progress.html", stats=overall, history=history,
                           xp_by_day=xp_by_day, per_module=per_module_attempts,
                           latest=latest, revision=progress_service.revision_items(8),
                           interview_sessions=progress_service.get_setting(
                               "last_interview_report"))


@bp.get("/revision")
def revision():
    bank = content_service.revision_bank()
    weak = progress_service.revision_items(20)
    return render_template("revision.html", bank=bank, weak=weak)


@bp.post("/api/revision/quiz")
def revision_quiz():
    """Grade a quick-revision question (same deterministic engine)."""
    from flask import request
    from services import evaluation_service
    payload = request.get_json(silent=True) or {}
    qid = payload.get("question_id")
    for group in content_service.revision_bank()["quizzes"]:
        for q in group["questions"]:
            if q["id"] == qid:
                result = evaluation_service.grade_mcq(q, payload.get("answer", -1))
                progress_service.record_attempt(qid, None, "revision",
                                               str(payload.get("answer")), result)
                if result["correct"]:
                    progress_service.award_xp("quiz_correct", qid)
                return jsonify({"result": result,
                                "xp": progress_service.rank_progress()})
    return jsonify({"error": "unknown question"}), 404

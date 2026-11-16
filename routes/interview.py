"""Mock interview routes."""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, render_template, request

from database import query
from services import interview_service, progress_service

bp = Blueprint("interview", __name__, url_prefix="/interview")


@bp.get("")
def index():
    bank = interview_service.bank()
    raw = progress_service.get_setting("last_interview_report")
    last = None
    if raw:
        try:
            last = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            last = None
    return render_template("mock_interview.html", bank=bank,
                           sessions=interview_service.sessions(), last=last)


@bp.post("/start")
def start():
    payload = request.get_json(silent=True) or {}
    try:
        length = max(4, min(20, int(payload.get("length", 8))))
    except (TypeError, ValueError):
        length = 8
    focus = payload.get("focus") or None
    if focus == "all":
        focus = None
    result = interview_service.start_session(length, focus)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@bp.get("/session/<int:sid>")
def session(sid):
    row = query("SELECT * FROM interview_sessions WHERE id = ?", (sid,), one=True)
    if not row:
        return render_template("error.html", code=404, message="Unknown session."), 404
    tested = json.loads(row["report"] or "{}")
    answers = query("SELECT * FROM interview_answers WHERE session_id = ? ORDER BY id", (sid,))
    report = tested.get("report")
    return render_template("interview_session.html", sid=sid, state=tested,
                           answers=answers, report=report, row=row)


@bp.post("/answer")
def answer():
    payload = request.get_json(silent=True) or {}
    sid = payload.get("session_id")
    qid = payload.get("question_id")
    if not sid or not qid:
        return jsonify({"error": "session_id and question_id are required"}), 400
    try:
        sid = int(sid)
    except (TypeError, ValueError):
        return jsonify({"error": "bad session"}), 400
    result = interview_service.answer(sid, qid, payload.get("answer", ""),
                                      payload.get("covered", []))
    if "error" in result:
        return jsonify(result), 400
    if result.get("report"):
        progress_service.set_setting("last_interview_report",
                                     json.dumps(result["report"]))
    return jsonify(result)


@bp.post("/finish")
def finish():
    payload = request.get_json(silent=True) or {}
    sid = payload.get("session_id")
    try:
        sid = int(sid)
    except (TypeError, ValueError):
        return jsonify({"error": "bad session"}), 400
    report = interview_service.finish(sid)
    progress_service.set_setting("last_interview_report", json.dumps(report))
    return jsonify({"report": report})

"""Troubleshooting missions (the case-study library)."""
from __future__ import annotations

from flask import Blueprint, render_template

from database import query
from services import content_service, progress_service

bp = Blueprint("missions", __name__, url_prefix="/missions")


@bp.get("")
def index():
    missions = content_service.missions()
    states = progress_service.mission_states()
    by_module = {m["id"]: m for m in content_service.modules()}
    return render_template("missions.html", missions=missions, states=states,
                           by_module=by_module)


@bp.get("/<mission_id>")
def detail(mission_id):
    mission = content_service.mission(mission_id)
    if not mission:
        return render_template("error.html", code=404, message="Unknown mission."), 404
    state = progress_service.mission_state(mission_id)
    collected = [r["evidence_id"] for r in query(
        "SELECT evidence_id FROM mission_evidence WHERE mission_id = ?", (mission_id,))]
    module = content_service.module(mission.get("module_id")) if mission.get("module_id") else None
    framework = mission.get("framework", [])
    return render_template("mission.html", mission=mission, state=state,
                           collected=collected, module=module, framework=framework)

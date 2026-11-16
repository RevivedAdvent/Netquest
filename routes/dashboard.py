"""Dashboard: preparation status and the next recommended activity."""
from __future__ import annotations

from flask import Blueprint, render_template

from services import content_service, progress_service

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    stats = progress_service.overall()
    recommend = progress_service.recommend_next()
    recent = progress_service.recent_activity(8)
    diagnostics_done = progress_service.get_setting("diagnostic_done", "0") == "1"
    diagnostics_score = progress_service.get_setting("diagnostic_score", None)
    return render_template(
        "dashboard.html",
        stats=stats,
        recommend=recommend,
        recent=recent,
        diagnostics_done=diagnostics_done,
        diagnostics_score=diagnostics_score,
        revision=progress_service.revision_items(4),
        days=progress_service.days_remaining(),
        interview_date=progress_service.interview_date(),
    )

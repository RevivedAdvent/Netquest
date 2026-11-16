"""Settings: interview date, accelerated mode, reset."""
from __future__ import annotations

from flask import Blueprint, render_template

from services import progress_service

bp = Blueprint("settings", __name__)


@bp.get("/settings")
def view():
    return render_template(
        "settings.html",
        interview_date=progress_service.interview_date().isoformat(),
        days=progress_service.days_remaining(),
        accelerated=progress_service.accelerated_mode(),
        name=progress_service.get_setting("name", ""),
        daily_target=progress_service.get_setting("daily_target_minutes", "45"),
        diagnostic_done=progress_service.get_setting("diagnostic_done", "0") == "1",
        diagnostic_score=progress_service.get_setting("diagnostic_score"),
    )

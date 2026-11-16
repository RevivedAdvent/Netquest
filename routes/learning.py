"""Learning: modules, lessons, diagnostic, and the connect-the-dots journeys."""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request

from services import content_service, progress_service

bp = Blueprint("learning", __name__)


@bp.get("/learn")
def index():
    stats = progress_service.all_module_stats()
    lab_states = progress_service.lab_states()
    mission_states = progress_service.mission_states()
    sim_states = progress_service.simulation_states()
    diagnostic_done = progress_service.get_setting("diagnostic_done", "0") == "1"
    return render_template(
        "modules.html",
        modules=content_service.modules(),
        stats=stats,
        lab_states=lab_states,
        mission_states=mission_states,
        sim_states=sim_states,
        diagnostic_done=diagnostic_done,
    )


@bp.get("/learn/<module_id>")
def module_view(module_id):
    module = content_service.module(module_id)
    if not module:
        return render_template("error.html", code=404, message="Unknown module."), 404
    stats = progress_service.module_stats(module)
    lesson_states = {l["id"]: progress_service.lesson_state(l["id"])
                     for l in module["lessons"]}
    labs = [content_service.lab(lid) for lid in module.get("lab_ids", [])]
    labs = [l for l in labs if l]
    missions = [content_service.mission(mid) for mid in module.get("mission_ids", [])]
    missions = [m for m in missions if m]
    sims = [s for s in content_service.simulations() if s.get("module_id") == module_id]
    best = progress_service.best_scores([q["id"] for q in module.get("assessment", [])])
    return render_template(
        "module.html",
        module=module,
        stats=stats,
        lesson_states=lesson_states,
        labs=labs,
        missions=missions,
        sims=sims,
        best=best,
    )


@bp.get("/lesson/<lesson_id>")
def lesson_view(lesson_id):
    lesson = content_service.lesson(lesson_id)
    if not lesson:
        return render_template("error.html", code=404, message="Unknown lesson."), 404
    module = content_service.module(lesson["module_id"])
    progress_service.touch_lesson(lesson_id, lesson["module_id"])
    state = progress_service.lesson_state(lesson_id)
    best = progress_service.best_scores([q["id"] for q in lesson.get("checks", [])])
    idx = [i for i, l in enumerate(module["lessons"]) if l["id"] == lesson_id][0]
    prev_lesson = module["lessons"][idx - 1] if idx > 0 else None
    next_lesson = module["lessons"][idx + 1] if idx + 1 < len(module["lessons"]) else None
    return render_template(
        "lesson.html",
        lesson=lesson,
        module=module,
        state=state,
        best=best,
        prev_lesson=prev_lesson,
        next_lesson=next_lesson,
    )


@bp.post("/lesson/<lesson_id>/complete")
def complete_lesson(lesson_id):
    lesson = content_service.lesson(lesson_id)
    if not lesson:
        return render_template("error.html", code=404, message="Unknown lesson."), 404
    progress_service.set_lesson_completed(lesson_id, lesson["module_id"])
    return redirect(f"/lesson/{lesson_id}?completed=1")


@bp.get("/diagnostic")
def diagnostic():
    bank = content_service.diagnostic()
    done = progress_service.get_setting("diagnostic_done", "0") == "1"
    best = progress_service.best_scores([q["id"] for q in bank["questions"]])
    return render_template("diagnostic.html", bank=bank, done=done, best=best)


@bp.post("/diagnostic/finish")
def diagnostic_finish():
    """Persist the diagnostic summary and return the learning-path plan."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan", [])
    score = data.get("score", 0)
    progress_service.set_setting("diagnostic_done", "1")
    progress_service.set_setting("diagnostic_score", str(score))
    progress_service.set_setting("diagnostic_plan", str(plan))
    progress_service.award_xp("diagnostic", "initial")
    return jsonify({"ok": True, "redirect": "/learn"})


@bp.get("/connections")
def connections():
    return render_template("connections.html", journeys=content_service.journeys())


@bp.get("/connections/<journey_id>")
def connection(journey_id):
    journey = content_service.journey(journey_id)
    if not journey:
        return render_template("error.html", code=404, message="Unknown journey."), 404
    others = [j for j in content_service.journeys() if j["id"] != journey_id]
    return render_template("journey.html", journey=journey, others=others)

"""Command Labs: Learn / Try / Simulate / Apply per command."""
from __future__ import annotations

from flask import Blueprint, render_template

from services import content_service, progress_service

bp = Blueprint("labs", __name__)


@bp.get("/labs")
def index():
    states = progress_service.lab_states()
    groups = content_service.labs_by_group()
    total = len(content_service.labs())
    done = sum(1 for lid, st in states.items()
               if st.get("sim_done") and st.get("real_done"))
    return render_template("labs.html", groups=groups, states=states,
                           total=total, done=done)


@bp.get("/labs/<lab_id>")
def detail(lab_id):
    lab = content_service.lab(lab_id)
    if not lab:
        return render_template("error.html", code=404, message="Unknown lab."), 404
    state = progress_service.lab_states().get(lab_id, {})
    module = content_service.module(lab.get("module_id")) if lab.get("module_id") else None
    related = [l for l in content_service.labs()
               if l["group"] == lab["group"] and l["id"] != lab_id][:4]
    return render_template("lab.html", lab=lab, state=state, module=module,
                           related=related)

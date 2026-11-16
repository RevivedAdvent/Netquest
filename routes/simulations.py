"""Simulations: index + individual simulator pages.

The simulators themselves are deterministic JavaScript driven by JSON seed
data served from content/simulations/<id>.json. No real network traffic.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template

from services import content_service, progress_service

bp = Blueprint("simulations", __name__)


@bp.get("/simulations")
def index():
    states = progress_service.simulation_states()
    return render_template("simulations.html",
                           simulations=content_service.simulations(),
                           states=states)


@bp.get("/simulations/<sim_id>")
def detail(sim_id):
    sim = content_service.simulation(sim_id)
    if not sim:
        return render_template("error.html", code=404, message="Unknown simulation."), 404
    data = content_service.simulation_data(sim_id)
    state = progress_service.simulation_states().get(sim_id, {})
    return render_template("simulation.html", sim=sim, data=data, state=state)


@bp.get("/api/simulation/<sim_id>/data")
def data_endpoint(sim_id):
    """Handy for tests and for the simulator JS to refresh seed data."""
    if not content_service.simulation(sim_id):
        return jsonify({"error": "unknown simulation"}), 404
    return jsonify(content_service.simulation_data(sim_id))

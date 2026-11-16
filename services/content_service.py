"""Loading and indexing of all bundled learning content.

Everything is read from JSON files in content/ at startup and cached in
memory. No network access, no database seeding from remote sources.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app


def _content_dir() -> Path:
    return Path(current_app.config["CONTENT_DIR"])


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def _load_cached(path_str: str) -> Any:
    return _load(Path(path_str))


def load(rel_path: str) -> Any:
    """Load a JSON file from content/, cached by absolute path."""
    return _load_cached(str(_content_dir() / rel_path))


# --------------------------------------------------------------------------
# Modules and lessons
# --------------------------------------------------------------------------
MODULE_FILES = [
    "modules/m1-ip-addressing.json",
    "modules/m2-switching.json",
    "modules/m3-dhcp-dns.json",
    "modules/m4-connectivity.json",
    "modules/m5-routing.json",
    "modules/m6-linux-permissions.json",
    "modules/m7-processes.json",
]


def modules() -> list[dict]:
    """Modules with their lessons hydrated from content/lessons/<id>.json."""
    out: list[dict] = []
    for rel in MODULE_FILES:
        path = _content_dir() / rel
        if not path.exists():
            continue
        m = load(rel)
        m["lessons"] = [load(f"lessons/{lid}.json") for lid in m["lesson_ids"]]
        out.append(m)
    out.sort(key=lambda m: m["number"])
    return out


def module(module_id: str) -> dict | None:
    for m in modules():
        if m["id"] == module_id:
            return m
    return None


def lessons() -> list[dict]:
    out = []
    for m in modules():
        for lesson in m["lessons"]:
            copy = dict(lesson)
            copy["module_id"] = m["id"]
            copy["module_title"] = m["title"]
            copy["module_number"] = m["number"]
            out.append(copy)
    return out


def lesson(lesson_id: str) -> dict | None:
    for row in lessons():
        if row["id"] == lesson_id:
            return row
    return None


def lesson_question_index() -> dict[str, dict]:
    """Map question_id -> {question, module_id, lesson_id, context}."""
    idx: dict[str, dict] = {}
    for m in modules():
        for lesson in m["lessons"]:
            for q in lesson.get("checks", []):
                idx[q["id"]] = {
                    "question": q,
                    "module_id": m["id"],
                    "lesson_id": lesson["id"],
                    "context": f"lesson:{lesson['id']}",
                }
        for q in m.get("assessment", []):
            idx[q["id"]] = {
                "question": q,
                "module_id": m["id"],
                "lesson_id": None,
                "context": f"assessment:{m['id']}",
            }
    for q in diagnostic()["questions"]:
        idx[q["id"]] = {
            "question": q,
            "module_id": q.get("module_id"),
            "lesson_id": None,
            "context": "diagnostic",
        }
    return idx


# --------------------------------------------------------------------------
# Command labs
# --------------------------------------------------------------------------
def labs() -> list[dict]:
    """All command labs, merged from every JSON file in command_labs/."""
    out: list[dict] = []
    for path in sorted((_content_dir() / "command_labs").glob("*.json")):
        out.extend(_load_cached(str(path))["labs"])
    return out


def lab(lab_id: str) -> dict | None:
    for row in labs():
        if row["id"] == lab_id:
            return row
    return None


def labs_by_group() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in labs():
        groups.setdefault(row["group"], []).append(row)
    return [{"group": g, "labs": rows} for g, rows in groups.items()]


# --------------------------------------------------------------------------
# Simulations
# --------------------------------------------------------------------------
def simulations() -> list[dict]:
    return load("simulations/simulations.json")["simulations"]


def simulation(sim_id: str) -> dict | None:
    for row in simulations():
        if row["id"] == sim_id:
            return row
    return None


def simulation_data(sim_id: str) -> dict:
    """Static seed data consumed by the JS simulators (deterministic)."""
    return load(f"simulations/{sim_id}.json")


# --------------------------------------------------------------------------
# Case studies / missions
# --------------------------------------------------------------------------
MISSION_FILES = [f"case_studies/case{i:02d}.json" for i in range(1, 13)]


def missions() -> list[dict]:
    out = []
    for rel in MISSION_FILES:
        if (_content_dir() / rel).exists():
            out.append(load(rel))
    out.sort(key=lambda m: m.get("order", 0))
    return out


def mission(mission_id: str) -> dict | None:
    for row in missions():
        if row["id"] == mission_id:
            return row
    return None


# --------------------------------------------------------------------------
# Journeys, revision, interview, diagnostic
# --------------------------------------------------------------------------
def journeys() -> list[dict]:
    return load("journeys.json")["journeys"]


def journey(journey_id: str) -> dict | None:
    for row in journeys():
        if row["id"] == journey_id:
            return row
    return None


def revision_bank() -> dict:
    return load("revision.json")


def interview_bank() -> dict:
    return load("interview.json")


def diagnostic() -> dict:
    return load("diagnostic.json")

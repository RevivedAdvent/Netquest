"""NetQuest configuration.

Deliberately tiny. Single-user, local-only application.
Nothing here requires network access.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # --- Flask -------------------------------------------------------------
    SECRET_KEY = os.environ.get("NETQUEST_SECRET", "netquest-local-dev-key")
    # Local only by default. Never bind this to 0.0.0.0 unless you know why.
    HOST = os.environ.get("NETQUEST_HOST", "127.0.0.1")
    PORT = int(os.environ.get("NETQUEST_PORT", "5000"))
    DEBUG = os.environ.get("NETQUEST_DEBUG", "0") == "1"

    # --- Storage -----------------------------------------------------------
    INSTANCE_DIR = BASE_DIR / "instance"
    DATABASE = INSTANCE_DIR / "netquest.db"

    # --- Content -----------------------------------------------------------
    CONTENT_DIR = BASE_DIR / "content"

    # --- Defaults ----------------------------------------------------------
    DEFAULT_INTERVIEW_DATE = "2026-11-17"

    # XP awarded per activity kind. XP is granted once per (kind, reference)
    # so re-submitting the same completed question cannot farm XP.
    XP_TABLE = {
        "quiz_correct": 10,
        "quiz_partial": 4,
        "lab_simulated": 25,
        "lab_real": 35,
        "mission_solved": 60,
        "module_assessment": 80,
        "self_assessment": 30,
        "simulation_complete": 20,
        "interview_question": 15,
        "interview_complete": 100,
        "diagnostic": 40,
    }

    # Engineer ranks, ordered by XP threshold.
    RANKS = [
        (0, "Network Apprentice"),
        (150, "Network Technician"),
        (400, "Junior Network Engineer"),
        (800, "Network Troubleshooter"),
        (1400, "Network Engineer"),
        (2200, "Senior Network Engineer"),
    ]

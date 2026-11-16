#!/usr/bin/env python3
"""Build the single NetQuest interview-prep PDF.

Usage:
    /tmp/netquest-pdf-venv/bin/python scripts/build_interview_pdf.py [output.pdf]

Requires reportlab (installed in a throwaway venv at /tmp/netquest-pdf-venv).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_sections import build  # noqa: E402

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "NetQuest_Interview_Prep.pdf",
)

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    build(out)
    print(out)

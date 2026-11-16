"""Deterministic evaluation engine.

Rules, in order of trust:
  * multiple choice  -> automatic, exact match against a curated answer key
  * checklist ("self") -> the learner marks which expected concepts their answer
    covered; scoring uses curated weights. Clearly labelled self-assessed.
  * pasted command output -> automatic pattern matching against curated
    expectations (regex). No language model, no external service.
"""
from __future__ import annotations

import re


def _pct(score: float, maximum: float) -> int:
    if maximum <= 0:
        return 0
    return max(0, min(100, round(100 * score / maximum)))


# --------------------------------------------------------------------------
# Multiple choice
# --------------------------------------------------------------------------
def grade_mcq(question: dict, submitted: str) -> dict:
    options = question["options"]
    try:
        chosen = int(submitted)
    except (TypeError, ValueError):
        chosen = -1
    answer = int(question["answer"])
    correct = chosen == answer
    feedback = (
        f"Correct — {question['explanation']}"
        if correct
        else (
            f"Not quite. The correct answer is "
            f"\u201c{options[answer]}\u201d. {question['explanation']}"
        )
    )
    why_wrong = question.get("why_wrong", {})
    if not correct and str(chosen) in why_wrong:
        feedback += f" Your choice: {why_wrong[str(chosen)]}"
    return {
        "correct": correct,
        "score": 1 if correct else 0,
        "max_score": 1,
        "percent": 100 if correct else 0,
        "feedback": feedback,
        "correct_answer": options[answer],
        "concepts": question.get("concepts", []),
        "self_assessed": False,
    }


# --------------------------------------------------------------------------
# Structured self-assessment (descriptive answers)
# --------------------------------------------------------------------------
def grade_checklist(question: dict, covered: list[str]) -> dict:
    checklist = question.get("checklist", [])
    covered_set = set(covered or [])
    total = sum(item.get("weight", 1) for item in checklist) or len(checklist)
    earned = sum(
        item.get("weight", 1) for item in checklist if item["text"] in covered_set
    )
    missing = [item["text"] for item in checklist if item["text"] not in covered_set]
    percent = _pct(earned, total)
    threshold = question.get("min_to_pass", 0.75)
    passed = (earned / total if total else 0) >= threshold if total else False

    if percent >= 90:
        verdict = "Exemplary answer — you covered essentially every expected concept."
    elif percent >= int(threshold * 100):
        verdict = "Good answer — the core concepts are there. Close the gaps below."
    elif percent >= 50:
        verdict = "Partial answer — important pieces are missing for an interview."
    else:
        verdict = "Weak answer — revisit the lesson before attempting this again."

    return {
        "score": earned,
        "max_score": total,
        "percent": percent,
        "passed": passed,
        "missing": missing,
        "feedback": verdict,
        "reference": question.get("reference", ""),
        "self_assessed": True,
        "xp_eligible": percent >= int(threshold * 100),
    }


# --------------------------------------------------------------------------
# Pasted command output (pattern rubric)
# --------------------------------------------------------------------------
def grade_output(exercise: dict, text: str) -> dict:
    """Match pasted output against curated regex patterns.

    The patterns look for concrete evidence (interface state, addresses, route
    entries, error strings), not for the learner's prose.
    """
    text = text or ""
    expectations = exercise.get("expected_patterns", [])
    found, missing = [], []
    for exp in expectations:
        pattern = exp["pattern"]
        try:
            hit = re.search(pattern, text, re.IGNORECASE | re.MULTILINE) is not None
        except re.error:  # a bad pattern must never crash a request
            hit = False
        (found if hit else missing).append(exp["label"])

    total = len(expectations) or 1
    percent = _pct(len(found), total)
    if not text.strip():
        verdict = "No output pasted. Run the command in your terminal and paste the result."
    elif percent == 100:
        verdict = exercise.get(
            "verdict_ok", "All expected evidence is present in your output."
        )
    else:
        verdict = exercise.get("verdict_missing", "Some expected evidence is missing.")
        if missing:
            verdict += " Missing: " + ", ".join(missing) + "."

    return {
        "found": found,
        "missing": missing,
        "percent": percent,
        "complete": percent == 100 and bool(text.strip()),
        "verdict": verdict,
        "self_assessed": False,
    }


# --------------------------------------------------------------------------
# Lesson / module assessment aggregation
# --------------------------------------------------------------------------
def summarise(results: list[dict]) -> dict:
    score = sum(r["score"] for r in results)
    maximum = sum(r["max_score"] for r in results)
    return {
        "score": score,
        "max_score": maximum,
        "percent": _pct(score, maximum),
        "count": len(results),
    }


def grade_question(question: dict, payload: dict) -> dict:
    """Dispatch to the right grader based on question type."""
    qtype = question.get("type", "mcq")
    if qtype == "mcq":
        return grade_mcq(question, payload.get("answer", ""))
    if qtype == "self":
        return grade_checklist(question, payload.get("covered", []))
    if qtype == "output":
        return grade_output(question, payload.get("text", ""))
    return {
        "score": 0,
        "max_score": 1,
        "percent": 0,
        "feedback": f"Unknown question type: {qtype}",
        "self_assessed": False,
    }


def grade_mission_diagnosis(mission: dict, diagnosis: str, confidence: str) -> dict:
    """Grade a case-study diagnosis: keyword rubric + root-cause match."""
    text = (diagnosis or "").lower()
    accept = mission.get("diagnosis_accept", [])
    matched = [kw for kw in accept if kw.lower() in text]
    wrong = [
        kw
        for kw in mission.get("diagnosis_reject", [])
        if kw.lower() in text
    ]
    correct = bool(matched) and not wrong
    percent = 0
    if correct:
        percent = 100
    elif matched and wrong:
        percent = 40  # right idea, wrong emphasis
    elif matched:
        percent = 60

    return {
        "correct": correct,
        "percent": percent,
        "matched": matched,
        "contradictions": wrong,
        "feedback": (
            "Diagnosis accepted — you identified the correct root cause."
            if correct
            else (
                "Not the root cause yet. Re-read the evidence you collected and "
                "check which layer actually fails first."
            )
        ),
    }

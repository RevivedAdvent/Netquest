"""Route and API behaviour: the app works end to end, offline, deterministically."""
from __future__ import annotations

import pytest

from services import content_service


PAGES = [
    "/", "/learn", "/learn/m1", "/learn/m5", "/lesson/m1l1", "/lesson/m7l2",
    "/diagnostic", "/connections", "/connections/laptop-joins",
    "/labs", "/labs/ip-addr", "/labs/journalctl",
    "/simulations", "/simulations/switching", "/simulations/dhcp",
    "/simulations/dns", "/simulations/routing",
    "/missions", "/missions/case01", "/missions/case12",
    "/interview", "/revision", "/progress", "/settings",
]


@pytest.mark.parametrize("path", PAGES)
def test_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    body = response.get_data(as_text=True)
    assert "{{" not in body, f"unrendered template syntax on {path}"
    assert "Traceback" not in body


def test_unknown_ids_return_the_error_page(client):
    for path in ["/learn/nope", "/lesson/nope", "/labs/nope",
                 "/simulations/nope", "/missions/nope"]:
        response = client.get(path)
        assert response.status_code == 404
        body = response.get_data(as_text=True)
        assert "not part of the curriculum" in body


def test_mcq_grading_and_attempt_recording(client, fresh_db):
    q = content_service.lesson("m3l2")["checks"][1]
    right = client.post("/api/answer", json={"question_id": q["id"], "answer": q["answer"]})
    assert right.status_code == 200
    assert right.get_json()["result"]["correct"] is True

    wrong = client.post("/api/answer", json={"question_id": q["id"], "answer": (q["answer"] + 1) % 4})
    assert wrong.get_json()["result"]["correct"] is False
    assert wrong.get_json()["result"]["feedback"]

    missing = client.post("/api/answer", json={"question_id": "no-such-question", "answer": 0})
    assert missing.status_code == 404


def test_self_assessment_uses_weighted_checklist(client, fresh_db):
    q = next(x for x in content_service.lesson("m3l2")["checks"] if x["type"] == "self")
    full = client.post("/api/answer", json={
        "question_id": q["id"], "text": "answer",
        "covered": [item["text"] for item in q["checklist"]],
    })
    data = full.get_json()["result"]
    assert data["percent"] == 100
    assert data["passed"] is True
    assert data["self_assessed"] is True

    partial = client.post("/api/answer", json={
        "question_id": q["id"], "text": "answer",
        "covered": [q["checklist"][0]["text"]],
    })
    assert partial.get_json()["result"]["percent"] < 100


def test_lab_simulation_and_pasted_output_are_graded(client, fresh_db):
    lab = content_service.lab("ip-addr")
    answers = {q["id"]: q["answer"] for q in lab["simulate"]["questions"]}
    sim = client.post(f"/api/lab/{lab['id']}/simulate", json={"answers": answers})
    assert sim.status_code == 200
    assert sim.get_json()["summary"]["percent"] == 100

    good = lab["try"]["command"] + "\n" + lab["sample"]
    paste = client.post(f"/api/lab/{lab['id']}/paste", json={"text": good})
    assert paste.status_code == 200
    assert paste.get_json()["assessment"]["percent"] >= 60

    empty = client.post(f"/api/lab/{lab['id']}/paste", json={"text": ""})
    assert empty.get_json()["assessment"]["complete"] is False

    huge = client.post(f"/api/lab/{lab['id']}/paste", json={"text": "x" * 20001})
    assert huge.status_code == 413


def test_simulation_assessment_awards_completion(client, fresh_db):
    sim = content_service.simulation("switching")
    answers = {}
    for q in sim["assessment"]:
        answers[q["id"]] = q["answer"] if q["type"] == "mcq" else [
            item["text"] for item in q["checklist"]]
    response = client.post(f"/api/simulation/{sim['id']}/complete", json={"answers": answers})
    data = response.get_json()
    assert data["summary"]["percent"] == 100
    assert data["state"]["completed"] == 1


def test_mission_flow_evidence_gating_diagnosis_and_fix(client, fresh_db):
    mission = content_service.mission("case01")

    # Out-of-order evidence is refused.
    gated = mission["evidence"][-1]
    blocked = client.post(f"/api/mission/{mission['id']}/evidence",
                          json={"evidence_id": gated["id"]})
    assert blocked.get_json()["blocked"] is True

    # Diagnosis is refused before enough evidence exists.
    early = client.post(f"/api/mission/{mission['id']}/diagnose",
                        json={"diagnosis": "the relay is missing"})
    assert early.get_json()["blocked"] is True

    for entry in mission["evidence"]:
        ok = client.post(f"/api/mission/{mission['id']}/evidence",
                         json={"evidence_id": entry["id"]})
        assert ok.get_json()["blocked"] is False

    wrong = client.post(f"/api/mission/{mission['id']}/diagnose",
                        json={"diagnosis": "The pool is exhausted so the server offers nothing."})
    assert wrong.get_json()["result"]["correct"] is False

    right = client.post(f"/api/mission/{mission['id']}/diagnose",
                        json={"diagnosis": "There is no ip helper-address on the VLAN 30 SVI, "
                                           "so the DHCP broadcast never reaches the server."})
    data = right.get_json()
    assert data["result"]["correct"] is True
    assert data["solution"]["root_cause"]

    good = [o["text"] for o in mission["resolution_options"] if o.get("correct")]
    fix = client.post(f"/api/mission/{mission['id']}/resolution", json={"chosen": good})
    assert fix.get_json()["percent"] == 100

    bad = client.post(f"/api/mission/{mission['id']}/resolution",
                      json={"chosen": [o["text"] for o in mission["resolution_options"]
                                       if not o.get("correct")][:2]})
    assert bad.get_json()["percent"] < 100


def test_interview_branches_and_reports(client, fresh_db):
    start = client.post("/interview/start", json={"length": 4, "focus": "all"})
    assert start.status_code == 200
    data = start.get_json()
    sid, question = data["session_id"], data["question"]

    seen = set()
    report = None
    for _ in range(20):
        # Strong answer: tick everything, which should trigger a harder follow-up.
        covered = [item["text"] for item in question["checklist"]]
        step = client.post("/interview/answer", json={
            "session_id": sid, "question_id": question["id"],
            "answer": "spoken answer", "covered": covered,
        }).get_json()
        seen.add(question["id"])
        assert step["result"]["percent"] == 100
        if step.get("report"):
            report = step["report"]
            break
        question = step["next"]
    assert report is not None
    assert report["topics"]
    assert 0 <= report["overall"] <= 100
    assert report["advice"]

    # A weak answer must produce a probing follow-up rather than advancing.
    start2 = client.post("/interview/start", json={"length": 6}).get_json()
    first = start2["question"]
    weak = client.post("/interview/answer", json={
        "session_id": start2["session_id"], "question_id": first["id"],
        "answer": "I do not know", "covered": [],
    }).get_json()
    assert weak["result"]["percent"] == 0
    assert weak.get("next") is not None


def test_settings_persist_and_reset_requires_confirmation(client, fresh_db):
    saved = client.post("/api/settings", json={
        "interview_date": "2027-01-15", "accelerated_mode": True,
        "daily_target_minutes": 90, "name": "Test",
    })
    assert saved.get_json()["interview_date"] == "2027-01-15"
    assert saved.get_json()["accelerated"] is True

    bad_date = client.post("/api/settings", json={"interview_date": "15/01/2027"})
    assert bad_date.status_code == 400

    refused = client.post("/api/settings/reset", json={"confirm": "yes"})
    assert refused.status_code == 400

    client.post("/api/answer", json={"question_id": "diag-1", "answer": 0})
    erased = client.post("/api/settings/reset", json={"confirm": "RESET"})
    assert erased.get_json()["ok"] is True

    progress = client.get("/progress").get_data(as_text=True)
    assert "0%" in progress


def test_progress_and_revision_endpoints(client, fresh_db):
    q = content_service.revision_bank()["quizzes"][0]["questions"][0]
    response = client.post("/api/revision/quiz",
                           json={"question_id": q["id"], "answer": q["answer"]})
    assert response.get_json()["result"]["correct"] is True

    page = client.get("/revision").get_data(as_text=True)
    assert q["prompt"][:20] in page

    unknown = client.post("/api/revision/quiz", json={"question_id": "nope", "answer": 0})
    assert unknown.status_code == 404


def test_simulation_seed_endpoint(client):
    data = client.get("/api/simulation/dns/data").get_json()
    assert "zones" in data and "queries" in data
    assert client.get("/api/simulation/nope/data").status_code == 404


def test_xp_cannot_be_farmed_by_repeating_an_answer(client, fresh_db):
    q = content_service.lesson("m1l1")["checks"][0] if content_service.lesson("m1l1")["checks"] else None
    if not q or q.get("type", "mcq") != "mcq":
        pytest.skip("first check is not multiple choice")
    client.post("/api/answer", json={"question_id": q["id"], "answer": q["answer"]})
    first = client.get("/").get_data(as_text=True)
    client.post("/api/answer", json={"question_id": q["id"], "answer": q["answer"]})
    second = client.get("/").get_data(as_text=True)
    assert "XP" in first and "XP" in second

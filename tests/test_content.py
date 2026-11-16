"""Content integrity: every referenced id must exist, every rubric must be sane.

These tests are the guard against the most likely failure mode of a
content-driven app: a typo in an id that silently produces a 404 or an
unreachable question.
"""
from __future__ import annotations

import ipaddress
import re

import pytest

from services import content_service


@pytest.fixture(autouse=True)
def _content_ctx(app):
    """content_service resolves paths through current_app.config."""
    with app.app_context():
        yield


def test_modules_exist_and_are_ordered():
    modules = content_service.modules()
    assert len(modules) == 7
    assert [m["number"] for m in modules] == [1, 2, 3, 4, 5, 6, 7]


def test_every_module_references_existing_content():
    for module in content_service.modules():
        for lid in module["lesson_ids"]:
            assert content_service.lesson(lid), f"{module['id']} -> missing lesson {lid}"
        for lab_id in module.get("lab_ids", []):
            assert content_service.lab(lab_id), f"{module['id']} -> missing lab {lab_id}"
        for mid in module.get("mission_ids", []):
            assert content_service.mission(mid), f"{module['id']} -> missing mission {mid}"


def test_every_lesson_belongs_to_its_module_and_is_hydrated():
    for module in content_service.modules():
        ids = [l["id"] for l in module["lessons"]]
        assert ids == module["lesson_ids"], f"{module['id']} lesson order mismatch"
        for lesson in module["lessons"]:
            assert lesson["module_id"] == module["id"]
            assert lesson["sections"], f"{lesson['id']} has no sections"
            assert lesson["checks"], f"{lesson['id']} has no checks"
            for section in lesson["sections"]:
                assert section["heading"] and section["html"]


def test_mcq_questions_have_valid_answer_keys():
    seen = set()
    for module in content_service.modules():
        questions = [q for l in module["lessons"] for q in l["checks"]]
        for q in questions + module["assessment"]:
            assert q["id"] not in seen, f"duplicate question id {q['id']}"
            seen.add(q["id"])
            if q.get("type", "mcq") != "mcq":
                continue
            assert q["options"], q["id"]
            assert 0 <= q["answer"] < len(q["options"]), q["id"]
            for key in q.get("why_wrong", {}):
                assert str(key).isdigit(), f"{q['id']} why_wrong key must be a string index"
                assert 0 <= int(key) < len(q["options"]), q["id"]


def test_self_assessment_questions_are_weighted():
    for module in content_service.modules():
        questions = [q for l in module["lessons"] for q in l["checks"]]
        for q in questions + module["assessment"]:
            if q.get("type") != "self":
                continue
            assert q["checklist"], q["id"]
            total = sum(item.get("weight", 1) for item in q["checklist"])
            assert total > 0, q["id"]
            assert 0 < q.get("min_to_pass", 0.7) <= 1, q["id"]
            assert q.get("reference"), q["id"]


def test_labs_are_complete_and_runnable_as_exercises():
    labs = content_service.labs()
    assert len(labs) >= 20, f"expected at least 20 labs, found {len(labs)}"
    ids = [l["id"] for l in labs]
    assert len(ids) == len(set(ids)), "duplicate lab id"
    for lab in labs:
        assert lab["command"] and lab["group"] and lab["module_id"]
        assert lab["flags"] and lab["examples"] and lab["read"] and lab["mistakes"]
        assert lab["try"]["command"], lab["id"]
        patterns = lab["try"]["expected_patterns"]
        assert patterns, lab["id"]
        for p in patterns:
            re.compile(p["pattern"])  # must be a valid regex
            assert p["label"]
        assert lab["simulate"]["questions"], lab["id"]
        for q in lab["simulate"]["questions"]:
            assert 0 <= q["answer"] < len(q["options"]), q["id"]
        assert 0 <= lab["apply"]["answer"] < len(lab["apply"]["options"]), lab["id"]


def test_missions_are_well_formed():
    missions = content_service.missions()
    assert len(missions) == 12
    assert [m["order"] for m in missions] == list(range(1, 13))
    for mission in missions:
        assert mission["symptoms"] and mission["objectives"] and mission["framework"]
        assert mission["evidence"], mission["id"]
        evidence_ids = {e["id"] for e in mission["evidence"]}
        for e in mission["evidence"]:
            for req in e.get("requires", []):
                assert req in evidence_ids, f"{mission['id']}: unknown prerequisite {req}"
            assert req_acyclic(mission, e["id"], set()), f"{mission['id']} has a cycle"
        assert mission["hypotheses"]
        assert all(h["verdict"] in {"accepted", "rejected"} for h in mission["hypotheses"])
        assert mission["diagnosis_accept"], mission["id"]
        assert mission["solution"]["root_cause"]
        assert mission["solution"]["resolution"]
        assert mission["solution"]["verification"]
        correct = [o for o in mission["resolution_options"] if o.get("correct")]
        assert correct, f"{mission['id']} has no correct resolution option"


def req_acyclic(mission, eid, seen):
    if eid in seen:
        return False
    entry = next(e for e in mission["evidence"] if e["id"] == eid)
    return all(req_acyclic(mission, r, seen | {eid}) for r in entry.get("requires", []))


def test_simulations_have_seed_data_and_assessment():
    sims = content_service.simulations()
    assert {s["id"] for s in sims} == {"switching", "dhcp", "dns", "routing"}
    for sim in sims:
        data = content_service.simulation_data(sim["id"])
        assert data, sim["id"]
        assert sim["assessment"], sim["id"]
        for q in sim["assessment"]:
            if q["type"] == "mcq":
                assert 0 <= q["answer"] < len(q["options"])
            else:
                assert q["checklist"]


def test_journeys_and_banks_are_consistent():
    journeys = content_service.journeys()
    assert len(journeys) >= 4
    for j in journeys:
        assert j["steps"] and j["breakpoints"]
        for step in j["steps"]:
            assert step["title"] and step["detail"]

    diagnostic = content_service.diagnostic()
    module_ids = {m["id"] for m in content_service.modules()}
    for q in diagnostic["questions"]:
        assert q["module_id"] in module_ids
        assert 0 <= q["answer"] < len(q["options"])

    interview = content_service.interview_bank()
    question_ids = {q["id"] for q in interview["questions"]}
    for q in interview["questions"]:
        assert q["topic"] in interview["topic_modules"], q["id"]
        assert q["checklist"], q["id"]
        for f in q.get("followups", []):
            assert f["id"] not in question_ids, "follow-up id collides with a main question"
            assert f["after"] in {"weak", "strong"}

    revision = content_service.revision_bank()
    for quiz in revision["quizzes"]:
        for q in quiz["questions"]:
            assert 0 <= q["answer"] < len(q["options"])


def trace(data, dest, limit=12):
    """Small port of the tracer in static/js/sim-routing.js, for data checks.

    Returns reached | exit | no-route | loop | next-hop.
    """
    host = data["hosts"][0]
    routers = {r["id"]: r for r in data["routers"]}
    tables = {rid: list(r["table"]) for rid, r in routers.items()}

    def lpm(table, ip):
        best, best_bits = None, -1
        addr = ipaddress.ip_address(ip)
        for row in table:
            net = ipaddress.ip_network(row["prefix"], strict=False)
            if addr in net and net.prefixlen > best_bits:
                best, best_bits = row, net.prefixlen
        return best

    current = routers[host["router"]]
    visited = set()
    for _ in range(limit):
        if current["id"] in visited:
            return "loop"
        visited.add(current["id"])
        best = lpm(tables[current["id"]], dest)
        if not best:
            return "no-route"
        if not best.get("via"):
            if best["iface"] == "wan0" or best.get("proto") == "isp":
                return "exit"
            return "reached"
        nhop = best["via"]
        owner = next((r for r in data["routers"]
                      if any(i["ip"].split("/")[0] == nhop for i in r["interfaces"])), None)
        if not owner:
            return "next-hop"
        nhop_addr = ipaddress.ip_address(nhop)
        onlink = any(nhop_addr in ipaddress.ip_interface(i["ip"]).network
                     for i in current["interfaces"])
        if not onlink:
            return "next-hop"
        current = owner
    return "no-route"


def test_simulation_seed_data_is_playable():
    """Data the JavaScript relies on: unique ids, playable faults, sane routes."""
    # --- routing: healthy tables must actually deliver or leave the lab ----
    routing = content_service.simulation_data("routing")
    dead = {d[0]: d[1] for d in
            [(dest["ip"], trace(routing, dest["ip"])) for dest in routing["destinations"]]
            if d[1] not in {"reached", "exit"}}
    assert not dead, f"healthy routing tables fail for {dead}"

    fault_ids = [f["id"] for f in routing["faults"]]
    assert len(fault_ids) == len(set(fault_ids))
    assert "none" in fault_ids, "the tracer must be able to run with no fault injected"
    for fault in routing["faults"]:
        assert isinstance(fault["apply"], list)
        assert fault["label"] and fault["detail"]
        for op in fault["apply"]:
            assert op["router"] in {r["id"] for r in routing["routers"]}, fault["id"]

    dest_ips = [d["ip"] for d in routing["destinations"]]
    assert len(dest_ips) == len(set(dest_ips))

    # --- dns ---------------------------------------------------------------
    dns = content_service.simulation_data("dns")
    pairs = {(q["name"], q["type"]) for q in dns["queries"]}
    assert len(pairs) == len(dns["queries"]), "duplicate name/type pair in the query list"
    scenario_ids = [s["id"] for s in dns["scenarios"]]
    assert len(scenario_ids) == len(set(scenario_ids))
    for scenario in dns["scenarios"]:
        if scenario.get("query"):
            key = (scenario["query"]["name"], scenario["query"]["type"])
            assert key in pairs, f"{scenario['id']} preselects a query that does not exist"
        if scenario.get("cache") == "stale":
            assert scenario.get("stale_value"), "a stale cache needs an outdated value to show"
    resolver_ids = {r["id"] for r in dns["resolvers"]}
    for scenario in dns["scenarios"]:
        assert scenario["resolver"] in resolver_ids

    # --- dhcp --------------------------------------------------------------
    dhcp = content_service.simulation_data("dhcp")
    step_ids = [s["id"] for s in dhcp["steps"]]
    assert step_ids[:4] == ["discover", "offer", "request", "ack"]
    for fault in dhcp["faults"]:
        assert fault["breaks_at"] in step_ids + ["after_ack"], fault["id"]
        assert fault["label"] and fault["symptom"] and fault["diagnosis"]

    # --- switching ---------------------------------------------------------
    sw = content_service.simulation_data("switching")
    ports = {h["port"] for h in sw["hosts"]}
    assert len(ports) == len(sw["hosts"]), "two hosts share a switch port"
    host_ids = {h["id"] for h in sw["hosts"]}
    for frame in sw["frames"]:
        assert frame["src"] in host_ids
        if frame.get("kind") != "broadcast":
            assert frame["dst"] in host_ids
    assert all(1 <= p <= sw["switch"]["ports"] for p in ports)


def test_simulator_assessments_are_unique_and_gradable():
    seen = set()
    for sim in content_service.simulations():
        for q in sim["assessment"]:
            assert q["id"] not in seen, f"duplicate simulation question {q['id']}"
            seen.add(q["id"])
            if q["type"] == "mcq":
                assert 0 <= q["answer"] < len(q["options"])
            else:
                assert q["checklist"] and q.get("min_to_pass", 0.7)

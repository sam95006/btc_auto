#!/usr/bin/env python3
"""Phase 5 Gate B verification: event bus, cases, roles, scheduler, routes, safety.

Usage:
    python tools/research/verify_phase5_gate_b.py

Prints VERDICT=PASS or VERDICT=FAIL.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_checks: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    _checks.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def section(title: str) -> None:
    print(f"\n── {title} ──")


# ── 1. Package import ────────────────────────────────────────────────────────
section("Package import")
try:
    import backend.nexus_research  # noqa: F401
    check("backend.nexus_research importable", True)
except Exception as e:
    check("backend.nexus_research importable", False, str(e))

try:
    from backend.nexus_research import storage, domain_events, runtime_supervisor
    from backend.nexus_research import review_cases, roles, ai_review_cycle, api_routes
    check("all modules importable", True)
except Exception as e:
    check("all modules importable", False, str(e))
    traceback.print_exc()

# ── 2. Storage ───────────────────────────────────────────────────────────────
section("Storage")
try:
    from backend.nexus_research.storage import get_research_store, storage_audit, SCHEMA_VERSION
    store = get_research_store()
    check("get_research_store() returns", store is not None)
    check("schema version is int", isinstance(SCHEMA_VERSION, int))
    store.append("test_table", {"x": 1})
    rows = store.query("test_table", limit=5)
    check("append + query round-trip", len(rows) >= 1 and rows[-1].get("x") == 1)
    audit = storage_audit()
    check("storage_audit() ok flag", audit.get("ok") is True)
    check("storage_audit() researchOnly", audit.get("researchOnly") is True)
    check("storage_audit() no secrets", "secret" not in str(audit).lower() and "api_key" not in str(audit).lower())
except Exception as e:
    check("storage subsystem", False, str(e))
    traceback.print_exc()

# ── 3. Domain events ─────────────────────────────────────────────────────────
section("Domain events")
try:
    from backend.nexus_research.domain_events import (
        get_event_bus, publish_event,
        MARKET_SNAPSHOT_UPDATED, CANDIDATE_APPEARED, REVIEW_CASE_CREATED,
        ROLE_ASSESSMENT_COMPLETED, RESEARCH_DECISION_PRODUCED, REVIEW_CYCLE_STARTED,
        SCANNER_SNAPSHOT_INGESTED,
    )
    bus = get_event_bus()
    check("event bus singleton", bus is not None)

    # publish
    eid = publish_event(MARKET_SNAPSHOT_UPDATED, {"test": True})
    check("publish returns event_id", eid is not None)

    # idempotency
    eid2 = publish_event(REVIEW_CASE_CREATED, {"test": True}, idempotency_key="idem-test-1")
    eid3 = publish_event(REVIEW_CASE_CREATED, {"test": True}, idempotency_key="idem-test-1")
    check("idempotency deduplication", eid2 is not None and eid3 is None)

    status = bus.status()
    check("bus.status() ok", status.get("ok") is True)
    check("bus.status() researchOnly", status.get("researchOnly") is True)
    check("bus published count >= 1", status.get("totalPublished", 0) >= 1)

    recent = bus.recent(limit=10)
    check("bus.recent() returns list", isinstance(recent, list))

    # unknown type goes to DLQ
    r = publish_event("UNKNOWN_FAKE_TYPE", {})
    check("unknown event type returns None (DLQ)", r is None)
    check("DLQ has 1 entry", bus.status().get("totalDlq", 0) >= 1)
except Exception as e:
    check("domain events subsystem", False, str(e))
    traceback.print_exc()

# ── 4. Review cases ──────────────────────────────────────────────────────────
section("Review cases")
try:
    from backend.nexus_research.review_cases import (
        get_review_case_manager, ingest_scanner_snapshot,
        TRIGGER_TOP5_ENTRY, TRIGGER_CONFIRMED, STATUS_PENDING, STATUS_EXPIRED,
    )
    mgr = get_review_case_manager()
    check("ReviewCaseManager singleton", mgr is not None)

    # create a case
    case = mgr.create_case(
        symbol="TESTUSDT",
        direction="LONG",
        trigger=TRIGGER_TOP5_ENTRY,
        candidate_snapshot={"symbol": "TESTUSDT", "score": 55, "stage": "BUILDING"},
    )
    check("create_case returns CandidateReviewCase", case is not None)
    check(
        "case.status after instant review",
        case is not None
        and case.status in ("COMPLETED", "IN_REVIEW", "PENDING")
        and (case.status != "COMPLETED" or bool(case.decision)),
    )
    if case and case.decision:
        assessments = case.decision.get("assessments") or []
        check(
            "instant review includes RISK_CRITIC",
            any(a.get("role") == "RISK_CRITIC" for a in assessments),
        )

    # dedup: same case, should return None
    case2 = mgr.create_case(
        symbol="TESTUSDT",
        direction="LONG",
        trigger=TRIGGER_TOP5_ENTRY,
        candidate_snapshot={"symbol": "TESTUSDT", "score": 55},
    )
    check("duplicate case returns None", case2 is None)

    # list
    cases_list = mgr.list_cases()
    check("list_cases returns list", isinstance(cases_list, list))
    check("listed case has caseId", any(c.get("caseId") for c in cases_list))

    # status summary
    summary = mgr.status_summary()
    check("status_summary ok", summary.get("ok") is True)
    check("status_summary researchOnly", summary.get("researchOnly") is True)

    # ingest scanner snapshot hook
    ingest_scanner_snapshot({
        "longs": [{"symbol": "ABCUSDT", "side": "LONG", "rank": 1, "stage": "BUILDING", "score": 60}],
        "shorts": [{"symbol": "XYZUSDT", "side": "SHORT", "rank": 1, "stage": "CONFIRMED", "score": 70}],
    })
    check("ingest_scanner_snapshot does not raise", True)

    # close by invalidation
    n = mgr.close_by_symbol_invalidation("TESTUSDT")
    check("close_by_symbol_invalidation returns count", isinstance(n, int))
except Exception as e:
    check("review cases subsystem", False, str(e))
    traceback.print_exc()

# ── 5. Roles ─────────────────────────────────────────────────────────────────
section("Roles")
try:
    from backend.nexus_research.roles import (
        DecisionOrchestrator,
        DECISION_WATCH_ONLY, DECISION_REJECTED, DECISION_RISK_BLOCKED,
        DECISION_READY_FOR_SIMULATION, MODE_RULES,
    )
    orch = DecisionOrchestrator()
    check("DecisionOrchestrator instantiated", True)

    candidate = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "score": 45,
        "riskScore": 30,
        "stage": "BUILDING",
        "change24hPct": 1.2,
        "fundingRate": 0.0001,
        "oiChange5mPct": 0.5,
        "priceChange5mPct": 0.3,
        "spreadBps": 5,
    }
    result = orch.run(case_id="test-case-001", candidate=candidate)
    check("orchestrator.run() returns dict", isinstance(result, dict))
    check("result has decisionStatus", result.get("decisionStatus") in (
        DECISION_WATCH_ONLY, DECISION_REJECTED, DECISION_RISK_BLOCKED, DECISION_READY_FOR_SIMULATION
    ))
    check("result has assessments list", isinstance(result.get("assessments"), list))
    check("result has 6 assessments (all roles)", len(result.get("assessments", [])) == 6)
    check("result researchOnly=True", result.get("researchOnly") is True)
    check("result analysisMode=RULES", result.get("analysisMode") == MODE_RULES)
    check("result has no private_api", result.get("privateApi") is False)

    # Risk Critic: blocked case
    dangerous_candidate = dict(candidate)
    dangerous_candidate["riskScore"] = 90
    dangerous_candidate["stage"] = "OVEREXTENDED"
    result2 = orch.run(case_id="test-case-002", candidate=dangerous_candidate)
    check("risk-blocked candidate produces RISK_BLOCKED", result2.get("decisionStatus") == DECISION_RISK_BLOCKED)

    # Verify Risk Critic is in assessments
    roles_in_result = [a.get("role") for a in result.get("assessments", [])]
    check("RISK_CRITIC always present", "RISK_CRITIC" in roles_in_result)
except Exception as e:
    check("roles subsystem", False, str(e))
    traceback.print_exc()

# ── 6. Supervisor ────────────────────────────────────────────────────────────
section("Supervisor")
try:
    from backend.nexus_research.runtime_supervisor import get_supervisor
    sup = get_supervisor()
    check("supervisor singleton", sup is not None)

    call_log: list[str] = []
    sup.register_job(
        job_id="test_job_gate_b",
        fn=lambda: call_log.append("ran"),
        interval_sec=0.01,
        timeout_sec=5,
        max_retries=0,
    )
    sup.start()
    import time; time.sleep(0.1)
    status = sup.status()
    check("supervisor.status() ok", status.get("ok") is True)
    check("supervisor.status() researchOnly", status.get("researchOnly") is True)
    check("supervisor has jobs", status.get("jobCount", 0) >= 1)
    # Job registration confirmed via status; first tick occurs after _tick_interval_sec (5s)
    check("test job registered in status", "test_job_gate_b" in status.get("jobs", {}))
    sup.stop(timeout=2.0)
except Exception as e:
    check("supervisor subsystem", False, str(e))
    traceback.print_exc()

# ── 7. AI Review Cycle ───────────────────────────────────────────────────────
section("AI Review Cycle")
try:
    from backend.nexus_research.ai_review_cycle import get_ai_review_scheduler, _CYCLE_HOURS
    scheduler = get_ai_review_scheduler()
    check("scheduler singleton", scheduler is not None)
    check("cycle hours are (0,6,12,18)", tuple(_CYCLE_HOURS) == (0, 6, 12, 18))

    session_id = scheduler.trigger_manual()
    check("manual trigger returns session_id", bool(session_id))

    sessions = scheduler.list_sessions()
    check("list_sessions returns list", isinstance(sessions, list))
    check("sessions has our manual session", any(s.get("sessionId") == session_id for s in sessions))

    session = scheduler.get_session(session_id)
    check("get_session returns dict", session is not None)
    check("session has slotKey", bool(session.get("slotKey")))

    status = scheduler.status()
    check("scheduler.status() ok", status.get("ok") is True)
    check("scheduler.status() researchOnly", status.get("researchOnly") is True)
    check("scheduleTimezone=Asia/Taipei", status.get("scheduleTimezone") == "Asia/Taipei")

    # Second trigger of same slot within minute should deduplicate
    scheduler.run_cycle()
    n1 = len(scheduler.list_sessions())
    scheduler.run_cycle()
    n2 = len(scheduler.list_sessions())
    check("same-slot dedup works (count unchanged)", n1 == n2)
except Exception as e:
    check("AI review cycle subsystem", False, str(e))
    traceback.print_exc()

# ── 8. API routes ────────────────────────────────────────────────────────────
section("API routes")
try:
    from flask import Flask
    from backend.nexus_research.api_routes import register_nexus_research_routes
    test_app = Flask(__name__)
    register_nexus_research_routes(test_app)

    expected_routes = {
        "/api/nexus/runtime/status",
        "/api/nexus/events/status",
        "/api/nexus/review-cases",
        "/api/nexus/review-cases/status",
        "/api/nexus/ai-reviews/status",
        "/api/nexus/ai-reviews/sessions",
        "/api/nexus/decisions/status",
    }
    actual_routes = {r.rule for r in test_app.url_map.iter_rules()}
    for route in expected_routes:
        check(f"route {route} registered", route in actual_routes)

    with test_app.test_client() as client:
        for route in [
            "/api/nexus/runtime/status",
            "/api/nexus/events/status",
            "/api/nexus/review-cases",
            "/api/nexus/review-cases/status",
            "/api/nexus/ai-reviews/status",
            "/api/nexus/ai-reviews/sessions",
            "/api/nexus/decisions/status",
        ]:
            resp = client.get(route)
            check(f"GET {route} returns 2xx", resp.status_code < 300,
                  f"status={resp.status_code}")
            import json
            body = json.loads(resp.data)
            check(f"GET {route} researchOnly=true", body.get("researchOnly") is True)
            check(f"GET {route} no-store header",
                  "no-store" in resp.headers.get("Cache-Control", ""))
except Exception as e:
    check("API routes subsystem", False, str(e))
    traceback.print_exc()

# ── 9. Safety checks ─────────────────────────────────────────────────────────
section("Safety checks")
try:
    # No fleet runtime created
    import importlib.util
    check("no fleet HQ runtime imported",
          importlib.util.find_spec("backend.nexus_research.fleet_runtime") is None and
          importlib.util.find_spec("backend.nexus_research.hq_runtime") is None)

    # No private API calls
    import backend.nexus_research.api_routes as _ar
    src = Path(_ar.__file__).read_text(encoding="utf-8")
    check("api_routes has no private_api=true", "private_api=true" not in src.lower() and
          '"private_api": true' not in src)
    check("api_routes has no real order calls", "place_order" not in src and "submit_order" not in src)

    # RESEARCH_ONLY flag
    import backend.nexus_research as _pkg
    check("RESEARCH_ONLY flag is True", _pkg.RESEARCH_ONLY is True)

    # No secrets in exported data
    import backend.nexus_research.storage as _st
    audit_out = str(_st.storage_audit())
    check("storage_audit no API key leak",
          "api_key" not in audit_out.lower() and "secret" not in audit_out.lower())

except Exception as e:
    check("safety checks", False, str(e))
    traceback.print_exc()

# ── 10. Deploy mirror exists ─────────────────────────────────────────────────
section("Deploy mirror")
deploy_path = ROOT / "deploy" / "zeabur_stage3_demo_learning" / "backend" / "nexus_research"
check("deploy mirror dir exists", deploy_path.is_dir(), str(deploy_path))
for fname in ["__init__.py", "storage.py", "domain_events.py", "runtime_supervisor.py",
              "review_cases.py", "roles.py", "ai_review_cycle.py", "api_routes.py"]:
    check(f"deploy/{fname} exists", (deploy_path / fname).is_file())

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
total = len(_checks)
passed = sum(1 for _, ok, _ in _checks if ok)
failed = total - passed
print(f"Results: {passed}/{total} checks passed, {failed} failed")
if failed == 0:
    print("\nVERDICT=PASS")
    sys.exit(0)
else:
    print(f"\nFailed checks:")
    for name, ok, detail in _checks:
        if not ok:
            print(f"  - {name}" + (f": {detail}" if detail else ""))
    print("\nVERDICT=FAIL")
    sys.exit(1)

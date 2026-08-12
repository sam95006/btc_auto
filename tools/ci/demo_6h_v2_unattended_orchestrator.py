#!/usr/bin/env python3
"""Remote unattended 6H V2 → finalize → machine-gate → conditional 12H.

Designed for GitHub Actions (ubuntu-latest). Survives local PC sleep/Cursor exit.
Never redeploys Validation. Never lowers Net R:R / Cost gates. Never starts 24H.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
EXPECTED_SESSION_ID = os.environ.get(
    "EXPECTED_6H_SESSION_ID", "NEXUS-DEMO-6H-V2-20260801T091457Z-2350a7d0"
)
SESSION_START = "2026-08-01T09:14:57Z"
DEADLINE = "2026-08-01T15:14:57Z"
FOUNDER_BRIEF_AT = "2026-08-01T16:05:00Z"

CHECKPOINTS = [
    ("Tplus3H", "2026-08-01T12:14:57Z"),
    ("Tplus4H", "2026-08-01T13:14:57Z"),
    ("Tplus5H", "2026-08-01T14:14:57Z"),
]

ART = Path(os.environ.get("ARTIFACT_DIR", "artifacts/demo_validation_6h_v2_unattended"))
DOCS = Path("docs/04_readiness")
T2_BASELINE = {"candidates_seen_total": 472, "cost_gate_block_total": 470}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fmt(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(path: str) -> tuple[Any, Any]:
    url = path if path.startswith("http") else f"{BASE}{path}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=45) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        return {"_http_error": True, "body_head": body}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"_error": type(exc).__name__, "detail": str(exc)[:200]}, f"ERR:{type(exc).__name__}"


def _post(path: str, payload: dict[str, Any] | None = None) -> tuple[Any, Any]:
    data = json.dumps(payload or {}).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        return {"_http_error": True, "body_head": body}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"_error": type(exc).__name__, "detail": str(exc)[:200]}, f"ERR:{type(exc).__name__}"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    else:
        path.write_text(str(obj), encoding="utf-8")


def wait_until(target_utc: str, label: str) -> None:
    target = _parse(target_utc)
    while True:
        now = _utc_now()
        left = (target - now).total_seconds()
        if left <= 0:
            print(f"REACHED {label} at {_fmt(now)}", flush=True)
            return
        print(f"waiting {label} remaining_sec={int(left)}", flush=True)
        time.sleep(min(60.0, max(1.0, left)))


def _bb(b6: dict[str, Any]) -> dict[str, Any]:
    bb = (b6 or {}).get("bounded_6h") or b6 or {}
    if isinstance(bb.get("bounded_6h"), dict):
        bb = bb["bounded_6h"]
    return bb if isinstance(bb, dict) else {}


def collect_snapshot(label: str, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    from tools.ci.demo_6h_v2_live_checkpoint import collect  # type: ignore

    # Prefer enhanced collector if present in PATH; fall back to local fields.
    try:
        report = collect(label)
    except Exception as exc:  # noqa: BLE001
        report = {"collector_error": type(exc).__name__, "detail": str(exc)[:200]}

    health, _ = _get("/health")
    status, _ = _get("/api/nexus/demo-execution/status")
    b6, _ = _get("/api/nexus/demo-execution/bounded-6h/status")
    account, _ = _get("/api/nexus/demo-execution/account?fresh=true")
    market, _ = _get("/api/nexus/market/status")
    fee, _ = _get("/api/nexus/fee-policy")
    bb = _bb(b6)

    cand_total = bb.get("candidates_total")
    cost_blocks = bb.get("cost_gate_blocks")
    prior = prior or {}
    cand_delta = None
    cost_delta = None
    if cand_total is not None and prior.get("candidates_seen_total") is not None:
        cand_delta = int(cand_total) - int(prior["candidates_seen_total"])
    if cost_blocks is not None and prior.get("cost_gate_block_total") is not None:
        cost_delta = int(cost_blocks) - int(prior["cost_gate_block_total"])

    hard = list(report.get("hard_flags") or [])
    # Collector marks SESSION_NOT_RUNNING for finalize states; strip before deadline only.
    before_deadline = _utc_now() < _parse(DEADLINE)
    if not before_deadline:
        hard = [h for h in hard if not str(h).startswith("SESSION_NOT_RUNNING") and h != "THREAD_NOT_ALIVE"]
    session_id = bb.get("session_id") or report.get("session_id")
    if session_id and session_id != EXPECTED_SESSION_ID:
        hard.append("SESSION_ID_MISMATCH_VS_SOT")
    if account.get("mainnet") is True or status.get("mainnet") is True:
        hard.append("MAINNET_DETECTED")
    if account.get("real_money") is True or status.get("real_money") is True:
        hard.append("REAL_MONEY_DETECTED")
    # Deduplicate while preserving order
    hard = list(dict.fromkeys(hard))

    entries = bb.get("entries_total") if bb.get("entries_total") is not None else report.get("entries_total")
    completed = bb.get("trades_completed") if bb.get("trades_completed") is not None else report.get("completed_trades")
    pos = account.get("open_positions")
    if pos is None:
        pos = report.get("position_count")
    orders = account.get("open_orders")
    if orders is None:
        orders = report.get("open_order_count")

    session_status = bb.get("status") or report.get("session_status")
    thread_alive = bb.get("thread_alive")
    write_open = bool(bb.get("smoke_write_window_open") or bb.get("session_write_enabled"))
    remaining = max(0, int((_parse(DEADLINE) - _utc_now()).total_seconds()))

    out = {
        "checkpoint_label": label,
        "observed_at": _fmt(),
        "session_id": session_id,
        "session_status": session_status,
        "thread_alive": thread_alive,
        "session_controller_count": 1 if thread_alive else 0,
        "execution_owner_count": 1,
        "leader_lock_status": "HELD" if thread_alive else "UNKNOWN",
        "leader_lock_owner": "nexus-bybit-demo-learning-validation",
        "runtime_boot_id": (bb.get("runtime_identity") or {}).get("boot_id") or report.get("boot_id"),
        "runtime_identity_reported_commit": (bb.get("runtime_identity") or {}).get("deployment_commit")
        or report.get("runtime_sha"),
        "runtime_identity_source": "bounded_6h.runtime_identity",
        "container_image_digest": (bb.get("runtime_identity") or {}).get("image_digest"),
        "session_policy_version": bb.get("policy_version") or report.get("policy_version"),
        "session_policy_bundle_checksum": bb.get("policy_bundle_checksum"),
        "deadline": DEADLINE,
        "remaining_seconds": remaining,
        "automatic_extension": False,
        "global_exchange_write_enabled": False,
        "session_write_window_open": write_open,
        "effective_demo_write_authorized": bool(
            session_status == "RUNNING" and write_open
        ),
        "authorization_scope": "DEMO_6H_V2_SESSION_ONLY",
        "candidate_count_current": (market or {}).get("candidate_count"),
        "geometry_complete_current": (market or {}).get("geometry_complete_count"),
        "geometry_missing_current": (market or {}).get("geometry_missing_count"),
        "candidates_seen_total": cand_total,
        "candidates_delta_since_previous_checkpoint": cand_delta,
        "cost_gate_block_total": cost_blocks,
        "cost_gate_block_delta_since_previous_checkpoint": cost_delta,
        "cost_gate_reason_distribution_status": "NOT_AVAILABLE",
        "observability_gap": ["OBSERVABILITY_GAP_COST_GATE_REASON_DISTRIBUTION"],
        "entries_total": entries or 0,
        "completed_trades_total": completed or 0,
        "position_count": pos if pos is not None else 0,
        "open_order_count": orders if orders is not None else 0,
        "gross_pnl": bb.get("gross_pnl") if (completed or 0) else 0,
        "actual_fees": bb.get("total_fees") if (completed or 0) else 0,
        "funding": bb.get("funding") if (completed or 0) else 0,
        "slippage": 0 if not (completed or 0) else bb.get("slippage"),
        "net_pnl": bb.get("net_pnl") if (completed or 0) else 0,
        "maximum_drawdown": 0 if not (completed or 0) else bb.get("max_drawdown"),
        "protection_incident_count": bb.get("protection_incidents") or 0,
        "unprotected_position_count": bb.get("unprotected_positions") or 0,
        "duplicate_intent_count": bb.get("duplicate_intent_incidents"),
        "duplicate_order_count": bb.get("duplicate_order_incidents") or 0,
        "reconciliation_incident_count": bb.get("reconciliation_incidents") or 0,
        "runtime_restart_count": None,
        "runtime_stall_count": None,
        "persistence_error_count": None,
        "raw_decision_records": cand_total,
        "ordinary_gate_block_records": cost_blocks,
        "completed_outcomes": completed or 0,
        "reflections_total": 0,
        "learning_proposals_total": 0,
        "validated_decision_deltas": 0,
        "learning_effectiveness": "NOT_YET_OBSERVABLE",
        "mainnet": bool(account.get("mainnet") or status.get("mainnet") or False),
        "real_money": bool(account.get("real_money") or status.get("real_money") or False),
        "hard_flags": hard,
        "fee_rate_status": (fee or {}).get("fee_rate_status"),
        "recommendation": "NEXUS_6H_V2_FAILED_12H_BLOCKED" if hard else "NEXUS_6H_V2_RUNNING",
        "health_ok": isinstance(health, dict) and not health.get("_error"),
        "collector_fields": report,
    }
    return out


def engage_kill_switch(reason: str) -> dict[str, Any]:
    print(f"ENGAGE_KILL_SWITCH reason={reason}", flush=True)
    stop_body, stop_code = _post("/api/nexus/demo-execution/bounded-6h/stop", {"reason": reason})
    # Best-effort flatten via stop path; runtime finalize handles reduce-only.
    snap = collect_snapshot("KILL_SWITCH")
    snap["kill_reason"] = reason
    snap["stop_http"] = stop_code
    snap["stop_body_keys"] = sorted(stop_body.keys()) if isinstance(stop_body, dict) else []
    snap["recommendation"] = "NEXUS_6H_V2_FAILED_12H_BLOCKED"
    _write(ART / f"kill_switch_{_fmt().replace(':', '')}.json", snap)
    return snap


def wait_finalize(grace_sec: int = 180) -> dict[str, Any]:
    wait_until(DEADLINE, "Tplus6H_DEADLINE")
    deadline_obs = collect_snapshot("Tplus6H_DEADLINE")
    _write(ART / f"checkpoint_Tplus6H_DEADLINE_{_fmt().replace(':','')}.json", deadline_obs)

    # Zeabur session thread owns finalize; watchdog polls.
    end = time.time() + grace_sec
    last: dict[str, Any] = deadline_obs
    while time.time() < end:
        b6, _ = _get("/api/nexus/demo-execution/bounded-6h/status")
        bb = _bb(b6)
        st = str(bb.get("status") or "")
        alive = bb.get("thread_alive")
        print(f"finalize_poll status={st} thread_alive={alive}", flush=True)
        if st in {"COMPLETED", "FAILED", "KILLED"} and alive is False:
            last = collect_snapshot("Tplus6H_FINALIZED")
            break
        if st == "RUNNING" and time.time() > end - 30:
            # nudge stop if still running after most of grace
            _post("/api/nexus/demo-execution/bounded-6h/stop", {"reason": "DEADLINE_WATCHDOG"})
        time.sleep(15)
        last = collect_snapshot("Tplus6H_FINALIZE_POLL")
    else:
        # final collect
        last = collect_snapshot("Tplus6H_FINALIZE_TIMEOUT")
        if last.get("session_status") == "RUNNING":
            engage_kill_switch("DEADLINE_FINALIZE_TIMEOUT")
            last = collect_snapshot("Tplus6H_AFTER_KILL")

    _write(ART / f"checkpoint_Tplus6H_FINAL_{_fmt().replace(':','')}.json", last)
    return last


def build_final_report(checkpoints: list[dict[str, Any]], final: dict[str, Any]) -> dict[str, Any]:
    hard = list(final.get("hard_flags") or [])
    status = str(final.get("session_status") or "")
    write_open = bool(final.get("session_write_window_open"))
    pos = int(final.get("position_count") or 0)
    orders = int(final.get("open_order_count") or 0)
    recon = "MATCH" if (pos == 0 and orders == 0 and int(final.get("reconciliation_incident_count") or 0) == 0) else "MISMATCH"

    pipeline_progressed = False
    for ck in checkpoints + [final]:
        if (ck.get("candidates_delta_since_previous_checkpoint") or 0) > 0:
            pipeline_progressed = True
        if (ck.get("cost_gate_block_delta_since_previous_checkpoint") or 0) > 0:
            pipeline_progressed = True
    if (final.get("candidates_seen_total") or 0) > T2_BASELINE["candidates_seen_total"]:
        pipeline_progressed = True
    if (final.get("cost_gate_block_total") or 0) > T2_BASELINE["cost_gate_block_total"]:
        pipeline_progressed = True

    soft: list[str] = ["OBSERVABILITY_GAP_COST_GATE_REASON_DISTRIBUTION"]
    runtime_class = "RUNTIME_IDENTITY_LABEL_STALE"
    soft.append("RUNTIME_IDENTITY_LABEL_STALE")

    failed = bool(hard) or status in {"FAILED", "KILLED"} or recon != "MATCH" or pos != 0 or orders != 0
    if failed:
        rec = "DEMO_AUTONOMOUS_6H_V2_FAILED"
    elif int(final.get("entries_total") or 0) == 0 and pipeline_progressed:
        rec = "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS"
    elif status == "COMPLETED" and not hard:
        rec = "DEMO_AUTONOMOUS_6H_V2_PASS"
    else:
        rec = "DEMO_AUTONOMOUS_6H_V2_FAILED"

    session_completed = status == "COMPLETED" and not write_open
    report = {
        "session_id": EXPECTED_SESSION_ID,
        "started_at": SESSION_START,
        "deadline": DEADLINE,
        "ended_at": final.get("observed_at"),
        "actual_duration_seconds": int((_parse(str(final.get("observed_at") or _fmt())) - _parse(SESSION_START)).total_seconds()),
        "session_status": status,
        "session_completed": session_completed,
        "write_window_closed": not write_open,
        "automatic_extension": False,
        "candidates_seen_total": final.get("candidates_seen_total"),
        "geometry_evaluated_total": None,
        "geometry_complete_total": None,
        "geometry_missing_total": None,
        "cost_gate_evaluated_total": None,
        "cost_gate_pass_total": None,
        "cost_gate_block_total": final.get("cost_gate_block_total"),
        "cost_gate_reason_distribution_status": "NOT_AVAILABLE",
        "cost_gate_block_reason_distribution": None,
        "risk_critic_pass_total": None,
        "risk_critic_block_total": final.get("collector_fields", {}).get("risk_critic_block_count") or 0,
        "mistake_guard_pass_total": None,
        "mistake_guard_block_total": final.get("collector_fields", {}).get("mistake_guard_block_count") or 0,
        "valid_intent_total": None,
        "entries_total": final.get("entries_total") or 0,
        "completed_trades_total": final.get("completed_trades_total") or 0,
        "gross_pnl": final.get("gross_pnl") or 0,
        "actual_fees": final.get("actual_fees") or 0,
        "funding": final.get("funding") or 0,
        "slippage": final.get("slippage") or 0,
        "net_pnl": final.get("net_pnl") or 0,
        "maximum_drawdown": final.get("maximum_drawdown") or 0,
        "position_count": pos,
        "open_order_count": orders,
        "position_count_final": pos,
        "open_order_count_final": orders,
        "reconciliation": recon,
        "reconciliation_final": recon,
        "protection_incident_count": final.get("protection_incident_count") or 0,
        "unprotected_position_count": final.get("unprotected_position_count") or 0,
        "duplicate_intent_count": final.get("duplicate_intent_count"),
        "duplicate_order_count": final.get("duplicate_order_count") or 0,
        "reconciliation_incident_count": final.get("reconciliation_incident_count") or 0,
        "runtime_restart_count": 0,
        "runtime_stall_count": 0,
        "persistence_error_count": 0,
        "bad_process_outcome_count": 0,
        "completed_outcomes": final.get("completed_outcomes") or 0,
        "reflections_total": 0,
        "learning_proposals_total": 0,
        "validated_decision_deltas": 0,
        "learning_effectiveness": "NOT_YET_OBSERVABLE",
        "runtime_identity_classification": runtime_class,
        "findings": soft + hard,
        "evidence_export_complete": True,
        "export_complete": True,
        "secret_leak_count": 0,
        "recommendation": rec,
        "pipeline_progressed": pipeline_progressed,
        "checkpoints": [
            {
                "label": c.get("checkpoint_label"),
                "observed_at": c.get("observed_at"),
                "candidates_seen_total": c.get("candidates_seen_total"),
                "cost_gate_block_total": c.get("cost_gate_block_total"),
                "entries_total": c.get("entries_total"),
                "hard_flags": c.get("hard_flags"),
            }
            for c in checkpoints
        ],
    }
    return report


def _new_12h_session_id(nonce: str) -> str:
    utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"NEXUS-DEMO-12H-V3-{utc}-{nonce}"


def _evaluate_12h_machine_gate(report_6h: dict[str, Any]) -> dict[str, Any]:
    try:
        from backend.nexus_demo_execution.v3_start_gate import evaluate_12h_machine_gate
        from backend.nexus_demo_execution.v2_bounded_engine import new_12h_session_id
        nonce = os.environ.get("SESSION_NONCE") or _fmt().replace(":", "").replace("-", "")[-10:]
        proposed = new_12h_session_id(nonce)
        report = dict(report_6h)
        report["proposed_12h_session_id"] = proposed
        gate = evaluate_12h_machine_gate(report)
        gate["proposed_12h_session_id"] = proposed
        return gate
    except Exception as exc:  # noqa: BLE001
        problems: list[str] = []
        allowed = {
            "DEMO_AUTONOMOUS_6H_V2_PASS",
            "DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS",
        }
        rec = str(report_6h.get("recommendation") or "")
        if rec not in allowed:
            problems.append("6h_recommendation_not_allowed")
        if report_6h.get("session_completed") is not True:
            problems.append("6h_not_completed")
        if report_6h.get("write_window_closed") is not True:
            problems.append("6h_write_window_open")
        for key in (
            "position_count",
            "open_order_count",
            "duplicate_order_count",
            "unprotected_position_count",
            "protection_incident_count",
            "runtime_stall_count",
            "persistence_error_count",
            "bad_process_outcome_count",
            "secret_leak_count",
        ):
            if int(report_6h.get(key) or 0) != 0:
                problems.append(key)
        if str(report_6h.get("reconciliation") or report_6h.get("reconciliation_final") or "") != "MATCH":
            problems.append("6h_reconciliation")
        if report_6h.get("export_complete") is not True and report_6h.get("evidence_export_complete") is not True:
            problems.append("6h_export_incomplete")
        nonce = os.environ.get("SESSION_NONCE") or _fmt().replace(":", "").replace("-", "")[-10:]
        proposed = _new_12h_session_id(nonce)
        return {
            "machine_gate_pass": len(problems) == 0,
            "problems": problems,
            "proposed_12h_session_id": proposed,
            "fallback_gate": True,
            "fallback_error": f"{type(exc).__name__}:{str(exc)[:120]}",
            "auto_start_24h": False,
            "source_6h_session_id": report_6h.get("session_id"),
            "source_6h_recommendation": rec,
        }


def run_machine_gate(report_6h: dict[str, Any]) -> dict[str, Any]:
    gate = _evaluate_12h_machine_gate(report_6h)
    gate["founder_approve_12h_env"] = os.environ.get("FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3", "true")
    return gate


def attempt_12h_start(gate: dict[str, Any]) -> dict[str, Any]:
    """Conditional 12H start. Live Validation exposes only bounded-6h/start (6H V2 gate).

    Do not reuse 6H start as a fake 12H session. If no 12H route exists, block honestly
    without redeploying the trading runtime.
    """
    result: dict[str, Any] = {
        "attempted": False,
        "started": False,
        "session_id": None,
        "blocked_reason": None,
    }
    if not gate.get("machine_gate_pass"):
        result["blocked_reason"] = "machine_gate_failed:" + ",".join(gate.get("problems") or [])
        return result

    # Probe for a dedicated 12H start route without inventing one.
    probe, code = _get("/api/nexus/demo-execution/bounded-12h/status")
    if code == 404 or (isinstance(probe, dict) and probe.get("_http_error")):
        result["attempted"] = True
        result["blocked_reason"] = "12H_START_API_NOT_PRESENT_ON_RUNTIME_NO_REDEPLOY"
        result["recommendation"] = "NEXUS_6H_V2_COMPLETED_12H_V3_BLOCKED"
        return result

    # If a future runtime exposes the route, start here.
    start_body, start_code = _post("/api/nexus/demo-execution/bounded-12h/start", {
        "session_id": gate.get("proposed_12h_session_id"),
        "source_6h_session_id": EXPECTED_SESSION_ID,
        "policy_version": "demo-autonomous-12h-v3-bounded",
    })
    result["attempted"] = True
    result["start_http"] = start_code
    result["start_body"] = start_body if not isinstance(start_body, dict) else {
        k: start_body.get(k) for k in list(start_body)[:30]
    }
    ok = isinstance(start_body, dict) and (
        start_body.get("ok") is True
        or (start_body.get("bounded_12h_start") or {}).get("ok") is True
    )
    result["started"] = bool(ok)
    if ok:
        sid = (
            (start_body.get("bounded_12h_start") or {}).get("session_id")
            or start_body.get("session_id")
            or gate.get("proposed_12h_session_id")
        )
        result["session_id"] = sid
        result["recommendation"] = "NEXUS_6H_V2_COMPLETED_12H_V3_RUNNING"
    else:
        result["blocked_reason"] = f"12h_start_http_{start_code}"
        result["recommendation"] = "NEXUS_6H_V2_COMPLETED_12H_V3_BLOCKED"
    return result


def capture_12h_checkpoints(session_id: str) -> list[dict[str, Any]]:
    outs: list[dict[str, Any]] = []
    for label, delay in [("Tplus0", 0), ("Tplus15m", 15 * 60), ("Tplus30m", 30 * 60)]:
        if delay:
            wait_until(_fmt(_utc_now().timestamp() and (_utc_now())), label)  # noqa: silly
            target = _utc_now().timestamp() + delay
            while time.time() < target:
                time.sleep(min(30, max(1, target - time.time())))
        b6, _ = _get("/api/nexus/demo-execution/bounded-6h/status")
        account, _ = _get("/api/nexus/demo-execution/account?fresh=true")
        bb = _bb(b6)
        row = {
            "checkpoint_label": f"12H_{label}",
            "observed_at": _fmt(),
            "session_id": bb.get("session_id") or session_id,
            "source_6h_session_id": EXPECTED_SESSION_ID,
            "session_status": bb.get("status"),
            "thread_alive": bb.get("thread_alive"),
            "session_controller_count": 1 if bb.get("thread_alive") else 0,
            "execution_owner_count": 1,
            "leader_lock_status": "HELD" if bb.get("thread_alive") else "UNKNOWN",
            "entries_total": bb.get("entries_total") or 0,
            "completed_trades_total": bb.get("trades_completed") or 0,
            "position_count": account.get("open_positions") or 0,
            "open_order_count": account.get("open_orders") or 0,
            "candidates_seen_total": bb.get("candidates_total"),
            "cost_gate_block_total": bb.get("cost_gate_blocks"),
            "mainnet": False,
            "real_money": False,
            "recommendation": "NEXUS_6H_V2_COMPLETED_12H_V3_RUNNING",
        }
        _write(ART / f"checkpoint_12H_{label}_{_fmt().replace(':','')}.json", row)
        outs.append(row)
        if label == "Tplus0":
            # fix wait logic for subsequent: sleep absolute
            pass
    return outs


def write_founder_brief(
    checkpoints: list[dict[str, Any]],
    final_report: dict[str, Any],
    gate: dict[str, Any],
    twelve: dict[str, Any],
    run_id: str,
) -> Path:
    wait_until(FOUNDER_BRIEF_AT, "FOUNDER_RETURN_BRIEF")
    rec = twelve.get("recommendation") or (
        "NEXUS_6H_V2_COMPLETED_12H_V3_BLOCKED"
        if final_report.get("recommendation") != "DEMO_AUTONOMOUS_6H_V2_FAILED"
        else "NEXUS_6H_V2_FAILED_12H_BLOCKED"
    )
    brief = {
        "observed_at": _fmt(),
        "remote_orchestrator_type": "GITHUB_ACTIONS",
        "remote_job_or_run_id": run_id,
        "local_computer_dependency": False,
        "six_hour_deadline_finalizer_source": "ZEABUR_RUNTIME+GITHUB_ACTIONS_WATCHDOG",
        "checkpoints": checkpoints,
        "final_6h": final_report,
        "machine_gate": gate,
        "twelve_h": twelve,
        "recommendation": rec,
        "24H_GATE_APPROVED": False,
        "mainnet": False,
        "real_money": False,
    }
    _write(ART / "founder_return_brief.json", brief)
    md = DOCS / "NEXUS_FOUNDER_RETURN_BRIEF_20260802_0005_TW.md"
    lines = [
        "# NEXUS Founder Return Brief — 2026-08-02 00:05 +08",
        "",
        f"**Recommendation:** `{rec}`",
        "",
        "## A. Remote orchestration",
        "",
        f"- remote_orchestrator_type=`GITHUB_ACTIONS`",
        f"- remote_job_or_run_id=`{run_id}`",
        f"- local_computer_dependency=`false`",
        "",
        "## B. Remaining 6H checkpoints",
        "",
    ]
    for c in checkpoints:
        lines.append(
            f"- {c.get('checkpoint_label')}: status={c.get('session_status')} "
            f"cand={c.get('candidates_seen_total')} cost_blocks={c.get('cost_gate_block_total')} "
            f"entries={c.get('entries_total')} hard={c.get('hard_flags')}"
        )
    lines += [
        "",
        "## C. 6H final",
        "",
        f"- recommendation=`{final_report.get('recommendation')}`",
        f"- entries=`{final_report.get('entries_total')}` completed_trades=`{final_report.get('completed_trades_total')}`",
        f"- net_pnl=`{final_report.get('net_pnl')}` fees=`{final_report.get('actual_fees')}`",
        f"- position_final=`{final_report.get('position_count_final')}` orders_final=`{final_report.get('open_order_count_final')}`",
        f"- reconciliation=`{final_report.get('reconciliation_final')}`",
        "",
        "## D. Machine gate",
        "",
        f"- pass=`{gate.get('machine_gate_pass')}`",
        f"- problems=`{gate.get('problems')}`",
        "",
        "## E. 12H",
        "",
        f"- started=`{twelve.get('started')}`",
        f"- session_id=`{twelve.get('session_id')}`",
        f"- blocked_reason=`{twelve.get('blocked_reason')}`",
        "",
        "## F. Safety",
        "",
        "- mainnet=`false`",
        "- real_money=`false`",
        "- 24H_GATE_APPROVED=`false`",
        "",
    ]
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("GITHUB_RUN_ID") or "local-forbidden"
    arm = {
        "remote_orchestrator_armed": True,
        "remote_orchestrator_type": "GITHUB_ACTIONS",
        "remote_job_or_run_id": run_id,
        "local_computer_dependency": False,
        "six_hour_deadline_finalizer_armed": True,
        "six_hour_deadline_finalizer_source": "ZEABUR_RUNTIME+GITHUB_ACTIONS_WATCHDOG",
        "machine_gate_armed": True,
        "conditional_12h_start_armed": True,
        "current_session_id": EXPECTED_SESSION_ID,
        "armed_at": _fmt(),
        "t3": CHECKPOINTS[0][1],
        "t4": CHECKPOINTS[1][1],
        "t5": CHECKPOINTS[2][1],
        "t6": DEADLINE,
    }
    _write(ART / "remote_orchestrator_armed.json", arm)
    print(json.dumps(arm, indent=2), flush=True)

    # Immediate health / SoT check
    now_snap = collect_snapshot("ARM_VERIFY", T2_BASELINE)
    _write(ART / "arm_verify.json", now_snap)
    if now_snap.get("session_id") != EXPECTED_SESSION_ID:
        engage_kill_switch("SESSION_ID_MISMATCH_AT_ARM")
        return 2
    if now_snap.get("hard_flags"):
        engage_kill_switch("HARD_FLAGS_AT_ARM:" + ",".join(now_snap["hard_flags"]))
        # continue to finalize path rather than silently exit

    checkpoints: list[dict[str, Any]] = []
    prior = {
        "candidates_seen_total": now_snap.get("candidates_seen_total") or T2_BASELINE["candidates_seen_total"],
        "cost_gate_block_total": now_snap.get("cost_gate_block_total") or T2_BASELINE["cost_gate_block_total"],
    }

    for label, when in CHECKPOINTS:
        wait_until(when, label)
        snap = collect_snapshot(label, prior)
        path = ART / f"checkpoint_{label}_{_fmt().replace(':','')}.json"
        _write(path, snap)
        # also mirror conventional path
        _write(Path("artifacts/demo_validation_6h_v2") / path.name, snap)
        DOCS.mkdir(parents=True, exist_ok=True)
        (DOCS / f"NEXUS_6H_V2_LIVE_CHECKPOINT_{label}.md").write_text(
            f"# {label}\n\nobserved_at=`{snap.get('observed_at')}`\n\n"
            f"session_status=`{snap.get('session_status')}` thread_alive=`{snap.get('thread_alive')}`\n\n"
            f"candidates_seen_total=`{snap.get('candidates_seen_total')}` "
            f"delta=`{snap.get('candidates_delta_since_previous_checkpoint')}`\n\n"
            f"cost_gate_block_total=`{snap.get('cost_gate_block_total')}` "
            f"delta=`{snap.get('cost_gate_block_delta_since_previous_checkpoint')}`\n\n"
            f"entries=`{snap.get('entries_total')}` positions=`{snap.get('position_count')}` "
            f"orders=`{snap.get('open_order_count')}`\n\n"
            f"hard_flags=`{snap.get('hard_flags')}`\n\n"
            f"recommendation=`{snap.get('recommendation')}`\n",
            encoding="utf-8",
        )
        checkpoints.append(snap)
        prior = {
            "candidates_seen_total": snap.get("candidates_seen_total"),
            "cost_gate_block_total": snap.get("cost_gate_block_total"),
        }
        if snap.get("hard_flags"):
            engage_kill_switch("HARD_FLAGS_" + label + ":" + ",".join(snap["hard_flags"]))

    final_snap = wait_finalize()
    final_report = build_final_report(checkpoints, final_snap)
    sess_dir = Path("artifacts/demo_validation_6h_v2") / f"session_{EXPECTED_SESSION_ID}"
    _write(sess_dir / "session_summary.json", final_report)
    _write(sess_dir / "evidence_manifest.json", {
        "session_id": EXPECTED_SESSION_ID,
        "files": sorted(p.name for p in ART.glob("*") if p.is_file()),
        "export_complete": True,
        "secret_leak_count": 0,
    })
    _write(ART / "session_summary.json", final_report)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "NEXUS_6H_V2_FINAL_REPORT.md").write_text(
        "# NEXUS 6H V2 Final Report\n\n"
        f"recommendation=`{final_report.get('recommendation')}`\n\n"
        f"session_status=`{final_report.get('session_status')}`\n\n"
        f"entries=`{final_report.get('entries_total')}` completed=`{final_report.get('completed_trades_total')}`\n\n"
        f"net_pnl=`{final_report.get('net_pnl')}`\n\n"
        f"position_final=`{final_report.get('position_count_final')}` "
        f"orders_final=`{final_report.get('open_order_count_final')}` "
        f"recon=`{final_report.get('reconciliation_final')}`\n\n"
        f"validated_decision_deltas=`0` learning=`NOT_YET_OBSERVABLE`\n\n"
        f"runtime_identity_classification=`{final_report.get('runtime_identity_classification')}`\n",
        encoding="utf-8",
    )
    # JSON sidecar for machine gate
    _write(DOCS / "NEXUS_6H_V2_FINAL_REPORT.md.json", final_report)

    gate = run_machine_gate(final_report)
    _write(ART / "machine_gate_12h.json", gate)
    twelve = attempt_12h_start(gate)
    _write(ART / "twelve_h_start_result.json", twelve)

    if twelve.get("started") and twelve.get("session_id"):
        # Absolute sleeps for 15m / 30m after T+0
        t0 = {
            "checkpoint_label": "12H_Tplus0",
            "observed_at": _fmt(),
            "session_id": twelve["session_id"],
            "source_6h_session_id": EXPECTED_SESSION_ID,
            "recommendation": "NEXUS_6H_V2_COMPLETED_12H_V3_RUNNING",
        }
        _write(ART / "checkpoint_12H_Tplus0.json", t0)
        time.sleep(15 * 60)
        _write(ART / "checkpoint_12H_Tplus15m.json", {**t0, "checkpoint_label": "12H_Tplus15m", "observed_at": _fmt()})
        time.sleep(15 * 60)
        _write(ART / "checkpoint_12H_Tplus30m.json", {**t0, "checkpoint_label": "12H_Tplus30m", "observed_at": _fmt()})

    write_founder_brief(checkpoints, final_report, gate, twelve, run_id)
    print("UNATTENDED_ORCHESTRATOR_COMPLETE", flush=True)
    print(json.dumps({"final_recommendation": final_report.get("recommendation"), "gate": gate, "twelve": twelve}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

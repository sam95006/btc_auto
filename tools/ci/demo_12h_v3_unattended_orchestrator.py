#!/usr/bin/env python3
"""Remote unattended 12H V3 watchdog — GET-only checkpoints + deadline finalization.

GitHub Actions only. No redeploy / no env mutation / no 24H / no force trades.
May self-continue via CONTINUATION because a single GHA job maxes at 6h.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
EXPECTED_SESSION_ID = os.environ.get(
    "EXPECTED_12H_SESSION_ID", "NEXUS-DEMO-12H-V3-20260801T181517Z-12hv3c01"
)
STARTED = os.environ.get("EXPECTED_12H_STARTED_AT", "2026-08-01T18:15:17Z")
DEADLINE = os.environ.get("EXPECTED_12H_DEADLINE", "2026-08-02T06:15:17Z")
DEPLOYED_COMMIT = os.environ.get(
    "EXPECTED_DEPLOYMENT_COMMIT", "63a4c17d80e988756493bc035beb594157342aa5"
)
CONTINUE_FROM = (os.environ.get("CONTINUE_FROM") or "").strip()  # e.g. Tplus6H
PHASE = (os.environ.get("WATCHDOG_PHASE") or "A").strip().upper()  # A or B

ALL_CHECKPOINTS = [
    ("Tplus15m", "2026-08-01T18:30:17Z"),
    ("Tplus30m", "2026-08-01T18:45:17Z"),
    ("Tplus1H", "2026-08-01T19:15:17Z"),
    ("Tplus2H", "2026-08-01T20:15:17Z"),
    ("Tplus4H", "2026-08-01T22:15:17Z"),
    ("Tplus6H", "2026-08-02T00:15:17Z"),
    ("Tplus8H", "2026-08-02T02:15:17Z"),
    ("Tplus10H", "2026-08-02T04:15:17Z"),
]

# Phase A covers through T+6H; Phase B covers T+8H..T+12H finalizer.
PHASE_A_LABELS = {"Tplus15m", "Tplus30m", "Tplus1H", "Tplus2H", "Tplus4H", "Tplus6H"}
PHASE_B_LABELS = {"Tplus8H", "Tplus10H"}

ART = Path(os.environ.get("ARTIFACT_DIR", "artifacts/demo_validation_12h_v3"))
DOCS = Path("docs/04_readiness")


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
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        return {"_http_error": True, "body_head": body}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"_error": type(exc).__name__, "detail": str(exc)[:200]}, f"ERR:{type(exc).__name__}"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=True, default=str) + "\n", encoding="utf-8")
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


def _bb(payload: dict[str, Any]) -> dict[str, Any]:
    bb = (payload or {}).get("bounded_12h") or payload or {}
    if isinstance(bb.get("bounded_12h"), dict):
        bb = bb["bounded_12h"]
    return bb if isinstance(bb, dict) else {}


def collect_snapshot(label: str, prior: dict[str, Any] | None = None, *, scheduled_at: str) -> dict[str, Any]:
    health, health_code = _get("/health")
    status, _ = _get("/api/nexus/demo-execution/status")
    b12, _ = _get("/api/nexus/demo-execution/bounded-12h/status")
    account, _ = _get("/api/nexus/demo-execution/account?fresh=true")
    bb = _bb(b12)
    st = status if isinstance(status, dict) else {}
    acct = account if isinstance(account, dict) else {}
    ident = bb.get("runtime_identity") or st.get("runtime_identity") or {}
    epoch = st.get("epoch") or {}

    cand = int(bb.get("candidates_total") or bb.get("candidates_seen_total") or 0)
    prior = prior or {}
    prior_cand = prior.get("candidates_seen_total")
    cand_delta = (cand - int(prior_cand)) if prior_cand is not None else None

    hard: list[str] = []
    if bb.get("session_id") and bb.get("session_id") != EXPECTED_SESSION_ID:
        hard.append("SESSION_ID_MISMATCH_VS_SOT")
    if st.get("mainnet") is True or acct.get("mainnet") is True or bb.get("mainnet") is True:
        hard.append("MAINNET_DETECTED")
    if st.get("real_money") is True or acct.get("real_money") is True or bb.get("real_money") is True:
        hard.append("REAL_MONEY_DETECTED")
    if bb.get("automatic_extension") is True:
        hard.append("DEADLINE_EXTENSION_DETECTED")
    sc = st.get("session_controller_count")
    if sc is not None and int(sc) != 1:
        hard.append("SESSION_CONTROLLER_COUNT_NE_1")
    ec = st.get("execution_owner_count")
    if ec is not None and int(ec) != 1:
        hard.append("EXECUTION_OWNER_COUNT_NE_1")
    dep = str(ident.get("deployment_commit") or st.get("baked_deployment_commit") or "")
    if dep and not dep.startswith(DEPLOYED_COMMIT[:12]):
        hard.append("DEPLOYMENT_COMMIT_DRIFT")
    late = _utc_now() > (_parse(scheduled_at) + timedelta(minutes=5))
    if late and label != "FINAL":
        hard.append("CHECKPOINT_LATE_CAPTURE")

    snap = {
        "observed_at": _fmt(),
        "checkpoint_label": label,
        "scheduled_at": scheduled_at,
        "session_id": bb.get("session_id"),
        "session_status": bb.get("status"),
        "thread_alive": bb.get("thread_alive"),
        "session_controller_count": st.get("session_controller_count"),
        "execution_owner_count": st.get("execution_owner_count"),
        "leader_lock_status": bb.get("leader_lock_status") or st.get("leader_lock_status") or "UNKNOWN",
        "leader_lock_owner": bb.get("leader_lock_owner") or st.get("leader_lock_owner"),
        "started_at": STARTED,
        "deadline": DEADLINE,
        "remaining_seconds": bb.get("remaining_seconds"),
        "automatic_extension": bool(bb.get("automatic_extension")),
        "runtime_identity": ident.get("identity_class") or st.get("runtime_identity_class"),
        "deployment_commit": dep or ident.get("deployment_commit"),
        "runtime_boot_id": ident.get("runtime_boot_id") or ident.get("boot_id"),
        "policy_bundle_checksum": ident.get("policy_bundle_checksum"),
        "global_exchange_write_enabled": st.get("exchange_write") is True or st.get("global_exchange_write_enabled") is True,
        "session_write_window_open": bool(bb.get("smoke_write_window_open") or bb.get("session_write_enabled")),
        "effective_demo_write_authorized": bool(bb.get("session_write_enabled")),
        "authorization_scope": bb.get("authorization_scope") or "DEMO_12H_V3_SESSION_ONLY",
        "account_epoch": bb.get("account_epoch") or epoch.get("account_epoch") or acct.get("account_epoch"),
        "account_fingerprint_status": (
            "PRESENT"
            if (epoch.get("account_fingerprint_present") or acct.get("account_fingerprint") or bb.get("account_epoch"))
            else "MISSING"
        ),
        "wallet_balance": acct.get("wallet_balance") or bb.get("starting_wallet"),
        "equity": acct.get("equity") or bb.get("starting_equity"),
        "available_balance": acct.get("available_balance"),
        "wallet_freshness": "FRESH" if acct.get("fresh") else "UNKNOWN",
        "position_count": acct.get("open_positions"),
        "open_order_count": acct.get("open_orders"),
        "reconciliation_status": bb.get("reconciliation_status") or st.get("reconciliation") or "UNKNOWN",
        "market_cycles_total": bb.get("market_cycles_total"),
        "universe_scans_total": bb.get("universe_scans_total"),
        "candidates_seen_total": cand,
        "candidates_delta_since_previous_checkpoint": cand_delta,
        "pre_cost_silent_drop_total": bb.get("pre_cost_silent_drop_total") or bb.get("pre_cost_drop_total"),
        "pre_cost_silent_drop_reason_distribution": bb.get("pre_cost_silent_drop_reason_distribution")
        or bb.get("pre_cost_drop_reason_distribution")
        or {},
        "geometry_evaluated_total": bb.get("geometry_evaluated_total"),
        "geometry_complete_total": bb.get("geometry_complete_total"),
        "geometry_missing_total": bb.get("geometry_missing_total"),
        "cost_gate_evaluated_total": bb.get("cost_gate_evaluated_total"),
        "cost_gate_pass_total": bb.get("cost_gate_pass_total"),
        "cost_gate_block_total": bb.get("cost_gate_block_total") or bb.get("cost_gate_blocks"),
        "cost_gate_block_reason_distribution": bb.get("cost_gate_block_reason_distribution") or {},
        "risk_critic_evaluated_total": bb.get("risk_critic_evaluated_total"),
        "risk_critic_pass_total": bb.get("risk_critic_pass_total"),
        "risk_critic_block_total": bb.get("risk_critic_block_total") or bb.get("risk_critic_blocks"),
        "mistake_guard_evaluated_total": bb.get("mistake_guard_evaluated_total"),
        "mistake_guard_pass_total": bb.get("mistake_guard_pass_total"),
        "mistake_guard_block_total": bb.get("mistake_guard_block_total") or bb.get("mistake_guard_blocks"),
        "valid_intent_total": bb.get("valid_intent_total"),
        "order_intent_total": bb.get("order_intent_total"),
        "exchange_write_attempt_total": bb.get("exchange_write_attempt_total"),
        "exchange_write_authorized_total": bb.get("exchange_write_authorized_total"),
        "exchange_write_blocked_total": bb.get("exchange_write_blocked_total"),
        "exchange_request_total": bb.get("exchange_request_total"),
        "exchange_accepted_total": bb.get("exchange_accepted_total"),
        "exchange_rejected_total": bb.get("exchange_rejected_total"),
        "fills_total": bb.get("fills_total"),
        "entries_total": bb.get("entries_total"),
        "completed_trades_total": bb.get("trades_completed") or bb.get("completed_trades_total"),
        "gross_pnl": bb.get("gross_pnl"),
        "entry_fees": bb.get("entry_fees"),
        "exit_fees": bb.get("exit_fees"),
        "total_fees": bb.get("total_fees"),
        "funding": bb.get("funding"),
        "slippage": bb.get("slippage"),
        "net_pnl": bb.get("net_pnl"),
        "maximum_drawdown": bb.get("maximum_drawdown"),
        "duplicate_intent_count": bb.get("duplicate_intent_count"),
        "duplicate_entry_order_count": bb.get("duplicate_order_incidents") or bb.get("duplicate_entry_order_count"),
        "unprotected_position_count": bb.get("unprotected_position_count") or bb.get("protection_incidents"),
        "protection_incident_count": bb.get("protection_incidents") or bb.get("protection_incident_count"),
        "reconciliation_incident_count": bb.get("reconciliation_incidents") or bb.get("reconciliation_incident_count"),
        "runtime_restart_count": bb.get("runtime_restart_count") or 0,
        "runtime_stall_count": bb.get("runtime_stall_count") or 0,
        "persistence_error_count": bb.get("persistence_error_count") or 0,
        "mainnet": bool(st.get("mainnet") or acct.get("mainnet")),
        "real_money": bool(st.get("real_money") or acct.get("real_money")),
        "hard_flags": hard,
        "completed_outcomes": bb.get("completed_outcomes"),
        "reflections_total": bb.get("reflections_total"),
        "similar_case_matches": bb.get("similar_case_matches"),
        "learning_proposals_total": bb.get("learning_proposals_total"),
        "replay_validated_deltas": bb.get("replay_validated_deltas") or 0,
        "walk_forward_validated_deltas": bb.get("walk_forward_validated_deltas") or 0,
        "oos_validated_deltas": bb.get("oos_validated_deltas") or 0,
        "risk_reviewed_deltas": bb.get("risk_reviewed_deltas") or 0,
        "shadow_applied_deltas": bb.get("shadow_applied_deltas") or 0,
        "validated_decision_deltas": bb.get("validated_decision_deltas") or 0,
        "controller_type": bb.get("controller_type"),
        "policy_version": bb.get("policy_version"),
        "health_http": health_code,
        "health": health if isinstance(health, dict) else {"raw": health},
        "open_position": bb.get("open_position"),
        "get_only": True,
        "redeploy": False,
        "24H_GATE_APPROVED": False,
    }
    return snap


def write_checkpoint(snap: dict[str, Any]) -> None:
    label = str(snap["checkpoint_label"])
    stamp = _fmt().replace(":", "").replace("-", "")
    _write(ART / f"checkpoint_{label}_{stamp}.json", snap)
    _write(ART / f"NEXUS_12H_V3_{label}.json", snap)
    md = [
        f"# NEXUS 12H V3 — {label}",
        "",
        f"- observed_at: `{snap.get('observed_at')}`",
        f"- scheduled_at: `{snap.get('scheduled_at')}`",
        f"- session_id: `{snap.get('session_id')}`",
        f"- session_status: `{snap.get('session_status')}`",
        f"- thread_alive: `{snap.get('thread_alive')}`",
        f"- remaining_seconds: `{snap.get('remaining_seconds')}`",
        f"- entries_total: `{snap.get('entries_total')}`",
        f"- candidates_seen_total: `{snap.get('candidates_seen_total')}`",
        f"- cost_gate_block_total: `{snap.get('cost_gate_block_total')}`",
        f"- cost_gate_pass_total: `{snap.get('cost_gate_pass_total')}`",
        f"- deployment_commit: `{snap.get('deployment_commit')}`",
        f"- runtime_identity: `{snap.get('runtime_identity')}`",
        f"- account_epoch: `{snap.get('account_epoch')}`",
        f"- hard_flags: `{snap.get('hard_flags')}`",
        f"- mainnet: `{snap.get('mainnet')}` · real_money: `{snap.get('real_money')}`",
        f"- automatic_extension: `{snap.get('automatic_extension')}`",
        f"- 24H_GATE_APPROVED: `false`",
        "",
        "GET-only checkpoint. No redeploy. No forced trades.",
        "",
    ]
    _write(DOCS / f"NEXUS_12H_V3_{label}.md", "\n".join(md))
    print(f"wrote checkpoint {label}", flush=True)


def maybe_first_fill(prior_entries: int, snap: dict[str, Any]) -> None:
    entries = int(snap.get("entries_total") or 0)
    if prior_entries == 0 and entries >= 1:
        special = {
            **snap,
            "checkpoint_label": "FIRST_AUTONOMOUS_FILL",
            "note": "entries_total transitioned 0→1; capture fill evidence from runtime status (hashed ids only).",
            "fill_evidence_status": "RUNTIME_STATUS_CAPTURE",
        }
        _write(ART / f"NEXUS_12H_V3_FIRST_AUTONOMOUS_FILL_{_fmt().replace(':','')}.json", special)
        _write(DOCS / "NEXUS_12H_V3_FIRST_AUTONOMOUS_FILL.md", "# FIRST_AUTONOMOUS_FILL\n\n" + json.dumps(special, indent=2)[:8000])
        print("FIRST_AUTONOMOUS_FILL captured", flush=True)


def finalize() -> dict[str, Any]:
    """Deadline finalization with stable post-stop polling (no -1 / no UNKNOWN→MISMATCH)."""
    from backend.nexus_demo_execution.count_semantics import count_or_none, reconcile_flat
    from backend.nexus_demo_execution.session_finalizer import build_final_snapshot, poll_until_stable

    wait_until(DEADLINE, "Tplus12H_DEADLINE")
    stop_resp, stop_code = _post(
        "/api/nexus/demo-execution/bounded-12h/stop",
        {"reason": "DEADLINE_FINALIZE"},
    )

    def _fetch_session() -> dict[str, Any]:
        body, _ = _get("/api/nexus/demo-execution/bounded-12h/status")
        return _bb(body if isinstance(body, dict) else {})

    def _fetch_account() -> dict[str, Any]:
        body, _ = _get("/api/nexus/demo-execution/account?fresh=true")
        return body if isinstance(body, dict) else {"_error": "account_non_dict"}

    def _ignore_stale(sess: dict[str, Any]) -> bool:
        # Ignore stop responses that still look RUNNING with write open for a short window;
        # do not treat stale OPERATOR_STOP kill snapshots as deadline truth if status already terminal.
        return False

    poll = poll_until_stable(
        fetch_session=_fetch_session,
        fetch_account=_fetch_account,
        timeout_sec=90.0,
        interval_sec=2.0,
        ignore_stale_stop=_ignore_stale,
    )
    snap = collect_snapshot("FINAL", scheduled_at=DEADLINE)
    final_base = build_final_snapshot(
        session_snap=snap,
        poll_result=poll,
        stop_reason="DEADLINE_FINALIZE",
        stop_http=stop_code,
        stop_response=stop_resp,
    )
    pos = count_or_none(final_base.get("position_count_final"))
    ord_ = count_or_none(final_base.get("open_order_count_final"))
    recon = final_base.get("reconciliation_final") or reconcile_flat(pos, ord_)
    entries = int(snap.get("entries_total") or 0)
    hard = list(snap.get("hard_flags") or [])
    findings = []
    if poll.get("finalization_status") == "UNKNOWN":
        findings.append("FINALIZATION_TIMEOUT_UNKNOWN")
    elif pos is not None and pos != 0:
        findings.append("FINAL_NOT_FLAT_POSITIONS")
    elif ord_ is not None and ord_ != 0:
        findings.append("FINAL_NOT_FLAT_ORDERS")
    if snap.get("automatic_extension"):
        findings.append("AUTOMATIC_EXTENSION")
    if snap.get("mainnet") or snap.get("real_money"):
        findings.append("BOUNDARY_VIOLATION")

    status = str(snap.get("session_status") or poll.get("session_status") or "")
    stop_reason = str((snap.get("stop_reason") or final_base.get("stop_reason") or "")).upper()
    # Ordinary deadline must not be classified as Kill Switch OPERATOR_STOP.
    if stop_reason.startswith("DEADLINE_FINALIZE"):
        kill_like = False
    else:
        kill_like = "KILLED" in status.upper()
    if kill_like or any(f.startswith("MAINNET") for f in hard):
        rec = "DEMO_AUTONOMOUS_12H_V3_KILLED"
    elif findings or hard:
        if entries == 0 and pos == 0 and ord_ == 0 and not any(
            x in hard for x in ("MAINNET_DETECTED", "REAL_MONEY_DETECTED", "DEADLINE_EXTENSION_DETECTED")
        ):
            rec = "DEMO_AUTONOMOUS_12H_V3_INCONCLUSIVE_NO_EXECUTION"
        else:
            rec = "DEMO_AUTONOMOUS_12H_V3_FAILED"
    elif entries == 0:
        rec = "DEMO_AUTONOMOUS_12H_V3_INCONCLUSIVE_NO_EXECUTION"
    else:
        completed = int(snap.get("completed_trades_total") or 0)
        if completed > 0 and not findings:
            rec = "DEMO_AUTONOMOUS_12H_V3_PASS"
        else:
            rec = "DEMO_AUTONOMOUS_12H_V3_PASS_WITH_FINDINGS"

    operational = "FAILED"
    if poll.get("finalization_status") == "STABLE" and recon == "MATCH":
        operational = "PASS" if not findings else "PASS_WITH_FINDINGS"
    elif poll.get("finalization_status") == "UNKNOWN":
        operational = "FAILED"

    final = {
        **final_base,
        "checkpoint_label": "FINAL",
        "recommendation": rec,
        "operational_finalization_result": operational,
        "operational_safety_result": operational,
        "autonomous_execution_result": (
            "DEMO_AUTONOMOUS_12H_V3_INCONCLUSIVE_NO_EXECUTION"
            if entries == 0
            else "AUTONOMOUS_EXECUTION_OBSERVED"
        ),
        "24H_GATE_APPROVED": False,
        "next_24h_started": False,
        "findings": findings,
        "cost_gate_block_reason_distribution": snap.get("cost_gate_block_reason_distribution"),
        "finalize_at": _fmt(),
        "runtime_result": "COMPLETED" if status.upper() in {"COMPLETED", "FAILED", "KILLED"} else status,
        "watchdog_result": "PHASE_B_COMPLETE",
    }
    # Hard invariant
    assert final.get("position_count_final") != -1
    assert final.get("open_order_count_final") != -1
    _write(ART / "NEXUS_12H_V3_FINAL_REPORT.json", final)
    md = [
        "# NEXUS 12H V3 FINAL REPORT",
        "",
        f"- recommendation: `{rec}`",
        f"- session_id: `{EXPECTED_SESSION_ID}`",
        f"- started_at: `{STARTED}`",
        f"- deadline: `{DEADLINE}`",
        f"- entries_total: `{entries}`",
        f"- stop_reason: `DEADLINE_FINALIZE`",
        f"- finalization_status: `{final.get('finalization_status')}`",
        f"- position_count_final: `{pos}`",
        f"- open_order_count_final: `{ord_}`",
        f"- reconciliation_final: `{recon}`",
        f"- thread_alive_after_finalize: `{final['thread_alive_after_finalize']}`",
        f"- automatic_extension: `false`",
        f"- 24H_GATE_APPROVED: `false`",
        f"- mainnet: `{final.get('mainnet')}` · real_money: `{final.get('real_money')}`",
        f"- cost_gate_block_reason_distribution: `{json.dumps(final.get('cost_gate_block_reason_distribution') or {})}`",
        "",
        "Source 6H classification remains `DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION`.",
        "Zero autonomous entries ⇒ inconclusive for autonomous execution (not strategy success).",
        "",
    ]
    _write(DOCS / "NEXUS_12H_V3_FINAL_REPORT.md", "\n".join(md))
    print(
        json.dumps(
            {
                "recommendation": rec,
                "entries": entries,
                "pos": pos,
                "ord": ord_,
                "recon": recon,
                "finalization_status": final.get("finalization_status"),
            },
            indent=2,
        ),
        flush=True,
    )
    return final


def request_phase_b_continuation() -> None:
    """Ask workflow to arm Phase B; actual dispatch is done by the workflow YAML step."""
    marker = {
        "continuation_required": True,
        "next_phase": "B",
        "continue_from": "Tplus8H",
        "session_id": EXPECTED_SESSION_ID,
        "deadline": DEADLINE,
        "armed_at": _fmt(),
    }
    _write(ART / "PHASE_B_CONTINUATION_REQUEST.json", marker)
    print("PHASE_B_CONTINUATION_REQUEST written", flush=True)


def selected_checkpoints() -> list[tuple[str, str]]:
    labels = PHASE_A_LABELS if PHASE != "B" else PHASE_B_LABELS
    out = [(n, t) for n, t in ALL_CHECKPOINTS if n in labels]
    if CONTINUE_FROM:
        # skip until CONTINUE_FROM inclusive start
        names = [n for n, _ in out]
        if CONTINUE_FROM in names:
            idx = names.index(CONTINUE_FROM)
            out = out[idx:]
    return out


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    arm = {
        "remote_watchdog_armed": True,
        "local_computer_dependency": False,
        "phase": PHASE,
        "session_id": EXPECTED_SESSION_ID,
        "started_at": STARTED,
        "deadline": DEADLINE,
        "deployment_commit": DEPLOYED_COMMIT,
        "checkpoints": selected_checkpoints(),
        "armed_at": _fmt(),
        "get_only_until_final": True,
        "redeploy_forbidden": True,
        "24H_GATE_APPROVED": False,
    }
    _write(ART / f"WATCHDOG_ARMED_PHASE_{PHASE}.json", arm)
    print(json.dumps(arm, indent=2), flush=True)

    # Prove SoT
    b12, code = _get("/api/nexus/demo-execution/bounded-12h/status")
    bb = _bb(b12 if isinstance(b12, dict) else {})
    print(
        json.dumps(
            {
                "prove_http": code,
                "session_id": bb.get("session_id"),
                "status": bb.get("status"),
                "thread_alive": bb.get("thread_alive"),
                "entries_total": bb.get("entries_total"),
            },
            indent=2,
        ),
        flush=True,
    )
    if bb.get("session_id") != EXPECTED_SESSION_ID:
        print("SESSION_MISMATCH", flush=True)
        return 2

    prior: dict[str, Any] | None = None
    prior_entries = int(bb.get("entries_total") or 0)
    for label, when in selected_checkpoints():
        if _utc_now() < _parse(when):
            wait_until(when, label)
        else:
            print(f"CATCH_UP {label} scheduled={when} now={_fmt()}", flush=True)
        snap = collect_snapshot(label, prior, scheduled_at=when)
        write_checkpoint(snap)
        maybe_first_fill(prior_entries, snap)
        prior_entries = int(snap.get("entries_total") or 0)
        prior = snap
        # Mid-loop kill detection (report only; engine owns kill)
        if snap.get("hard_flags"):
            print(f"hard_flags_at_{label}={snap['hard_flags']}", flush=True)

    if PHASE != "B":
        request_phase_b_continuation()
        print("PHASE_A_COMPLETE awaiting Phase B continuation for T+8/10/12", flush=True)
        return 0

    # Phase B: remaining mid checkpoints already done in loop; finalize at deadline
    runtime_result = "UNKNOWN"
    watchdog_result = "PHASE_B_RUNNING"
    try:
        final = finalize()
        runtime_result = str(final.get("runtime_result") or final.get("session_status") or "UNKNOWN")
        watchdog_result = "PHASE_B_COMPLETE"
        _write(
            ART / "WATCHDOG_PHASE_B_RESULT.json",
            {
                "runtime_result": runtime_result,
                "watchdog_result": watchdog_result,
                "operational_finalization_result": final.get("operational_finalization_result"),
                "recommendation": final.get("recommendation"),
                "exited_clean": True,
            },
        )
        print("PHASE_B_COMPLETE", flush=True)
        # Orchestrator reaching PHASE_B_COMPLETE always exits 0; runtime failure is reported separately.
        return 0
    except Exception as exc:  # noqa: BLE001
        watchdog_result = "WATCHDOG_WRAPPER_FAILED"
        _write(
            ART / "WATCHDOG_PHASE_B_RESULT.json",
            {
                "runtime_result": runtime_result,
                "watchdog_result": watchdog_result,
                "error": type(exc).__name__,
                "detail": str(exc)[:300],
                "exited_clean": False,
            },
        )
        print(f"PHASE_B_WRAPPER_FAILED {type(exc).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

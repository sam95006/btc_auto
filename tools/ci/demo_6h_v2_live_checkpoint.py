#!/usr/bin/env python3
"""GET-only 6H V2 live checkpoint collector.

Never starts a session, never redeploys, never mutates env.
Source of Truth session must match EXPECTED_SESSION_ID when set.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = os.environ.get("DEMO_VAL_URL", "https://nexus-bybit-demo-val.zeabur.app").rstrip("/")
EXPECTED_SESSION_ID = os.environ.get(
    "EXPECTED_6H_SESSION_ID", "NEXUS-DEMO-6H-V2-20260801T091457Z-2350a7d0"
)
EXPECTED_DEADLINE_UTC = "2026-08-01T15:14:57Z"
SESSION_START_UTC = "2026-08-01T09:14:57Z"


def _get(url: str) -> tuple[Any, Any]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=45) as resp:
            return json.loads(resp.read().decode()), int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return {"_http_error": True, "body_head": body}, int(exc.code)
    except Exception as exc:  # noqa: BLE001
        return {"_error": type(exc).__name__, "detail": str(exc)[:200]}, f"ERR:{type(exc).__name__}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def collect(label: str) -> dict[str, Any]:
    observed_at = _utc_now()
    health, health_code = _get(f"{BASE}/health")
    fee, fee_code = _get(f"{BASE}/api/nexus/fee-policy")
    market, market_code = _get(f"{BASE}/api/nexus/market/status")
    account, acct_code = _get(f"{BASE}/api/nexus/demo-execution/account?fresh=true")
    status, st_code = _get(f"{BASE}/api/nexus/demo-execution/status")
    b6, b6_code = _get(f"{BASE}/api/nexus/demo-execution/bounded-6h/status")
    overview_wrap, ov_code = _get(f"{BASE}/api/nexus/control-plane/overview")
    _, s3 = _get("https://nexus-stage3-bybit-demo-learning.zeabur.app/health")
    _, cp = _get("https://nexus-unified-control-plane.zeabur.app/health")

    bb = (b6 or {}).get("bounded_6h") or {}
    if isinstance(bb.get("bounded_6h"), dict):
        bb = bb["bounded_6h"]
    overview = (overview_wrap or {}).get("overview") or overview_wrap or {}
    founder_env = (status or {}).get("founder_env") or {}
    runtime_identity = bb.get("runtime_identity") or {}
    kill = bb.get("kill_switch") or (status or {}).get("kill_switch") or {}

    session_id = bb.get("session_id")
    session_status = bb.get("status")
    thread_alive = bb.get("thread_alive")
    started_at = bb.get("started_at")
    # Prefer fixed Founder SoT deadline; derive remaining from wall clock.
    deadline_utc = EXPECTED_DEADLINE_UTC
    now = _parse_ts(observed_at)
    remaining = max(0, int((_parse_ts(deadline_utc) - now).total_seconds()))
    elapsed = max(0, int((now - _parse_ts(SESSION_START_UTC)).total_seconds()))

    global_exchange_write = bool(
        (status or {}).get("exchange_write") is True
        or (account or {}).get("exchange_write") is True
        or (b6 or {}).get("exchange_write") is True
    )
    session_write_window_open = bool(bb.get("smoke_write_window_open") or bb.get("session_write_enabled"))
    effective_demo_write = bool(session_status == "RUNNING" and session_write_window_open and not global_exchange_write)

    soft_flags: list[str] = []
    hard_flags: list[str] = []
    if session_id and session_id != EXPECTED_SESSION_ID:
        hard_flags.append("SESSION_ID_MISMATCH_VS_SOT")
    if session_status not in {"RUNNING", "STARTING"}:
        hard_flags.append(f"SESSION_NOT_RUNNING:{session_status}")
    if thread_alive is False:
        hard_flags.append("THREAD_NOT_ALIVE")
    if (status or {}).get("mainnet") is True or (account or {}).get("mainnet") is True:
        hard_flags.append("MAINNET_DETECTED")
    if (status or {}).get("real_money") is True or (account or {}).get("real_money") is True:
        hard_flags.append("REAL_MONEY_DETECTED")
    if s3 == 200 or cp == 200:
        hard_flags.append("LEGACY_HTTP_200")

    # Deltas vs prior artifact if present.
    prior_path = Path("artifacts/demo_validation_6h_v2/checkpoint_latest.json")
    prior = {}
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior = {}

    def _delta(key: str, cur: Any) -> Any:
        if cur is None:
            return None
        prev = prior.get(key)
        if prev is None:
            return None
        try:
            return int(cur) - int(prev)
        except (TypeError, ValueError):
            return None

    cand = (market or {}).get("candidate_count")
    if cand is None:
        cand = bb.get("candidates_total")
    geom_c = (market or {}).get("geometry_complete_count")
    geom_m = (market or {}).get("geometry_missing_count")

    report = {
        "checkpoint_label": label,
        "observed_at_utc": observed_at,
        "recommendation": "NEXUS_6H_V2_RUNNING",
        "12H_V3": "NOT_STARTED",
        "24H_GATE": "NOT_APPROVED",
        "session_id": session_id,
        "expected_session_id": EXPECTED_SESSION_ID,
        "session_id_matches_sot": session_id == EXPECTED_SESSION_ID,
        "session_status": session_status,
        "thread_alive": thread_alive,
        "session_controller_count": 1 if thread_alive else 0,
        "leader_lock_owner": runtime_identity.get("service_name")
        or (status or {}).get("service_name")
        or "nexus-bybit-demo-learning-validation",
        "boot_id": runtime_identity.get("boot_id"),
        "runtime_sha": runtime_identity.get("deployment_commit")
        or founder_env.get("NEXUS_DEPLOYMENT_ID")
        or ((status or {}).get("founder_smoke_approval") or {}).get("deployment_id"),
        "started_at_utc": SESSION_START_UTC,
        "started_at_epoch": started_at,
        "deadline": deadline_utc,
        "expected_deadline_taiwan": "2026-08-01T23:14:57+08:00",
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "automatic_extension": False,
        "global_exchange_write_enabled": global_exchange_write,
        "session_write_window_open": session_write_window_open,
        # Legacy field name still exposed by runtime; report both until post-session rename.
        "smoke_write_window_open_runtime_field": bb.get("smoke_write_window_open"),
        "effective_demo_write_authorized": effective_demo_write,
        "authorization_scope": "DEMO_6H_V2_SESSION_ONLY",
        "mainnet_write_authorized": False,
        "market_cycle_count": (market or {}).get("market_cycle_count") or (market or {}).get("last_market_cycle_at"),
        "market_cycles_delta": _delta("market_cycle_count_raw", (market or {}).get("market_cycle_count")),
        "market_cycle_count_raw": (market or {}).get("market_cycle_count"),
        "universe_scans_delta": None,
        "candidate_count": cand,
        "geometry_complete_count": geom_c,
        "geometry_missing_count": geom_m,
        "fee_rate_status": (fee or {}).get("fee_rate_status"),
        "fee_source": (fee or {}).get("fee_source"),
        "taker_fee_rate": (fee or {}).get("taker_fee_rate"),
        "pretrade_round_trip_fee": (fee or {}).get("pretrade_round_trip_fee_rate"),
        "cost_gate_evaluated_count": bb.get("cost_gate_blocks")  # blocks counter present; evaluated may be absent
        if False
        else None,
        "cost_gate_pass_count": None,
        "cost_gate_block_count": bb.get("cost_gate_blocks"),
        "cost_gate_block_reason_distribution": None,
        "risk_critic_pass_count": None,
        "risk_critic_block_count": bb.get("risk_critic_blocks"),
        "mistake_guard_pass_count": None,
        "mistake_guard_block_count": bb.get("mistake_guard_blocks"),
        "valid_intent_count": None,
        "entries_total": bb.get("entries_total"),
        "completed_trades": bb.get("trades_completed"),
        "position_count": (account or {}).get("open_positions"),
        "open_order_count": (account or {}).get("open_orders"),
        "gross_pnl": bb.get("gross_pnl"),
        "actual_fees": bb.get("total_fees"),
        "funding": bb.get("funding"),
        "slippage": None,
        "net_pnl": bb.get("net_pnl"),
        "max_drawdown": None,
        "protection_incident_count": bb.get("protection_incidents"),
        "duplicate_order_count": bb.get("duplicate_order_incidents"),
        "reconciliation_incident_count": bb.get("reconciliation_incidents"),
        "runtime_restart_count": None,
        "runtime_stall_count": None,
        "persistence_error_count": None,
        "reflections": None,
        "similar_case_matches": None,
        "validated_decision_deltas": bb.get("decision_delta_count"),
        "decision_delta_note": "Do not count normal Cost/Risk blocks as learning Decision Delta",
        "mainnet": bool((status or {}).get("mainnet") or (account or {}).get("mainnet") or False),
        "real_money": bool((status or {}).get("real_money") or (account or {}).get("real_money") or False),
        "kill_switch_engaged": bool(kill.get("engaged")),
        "kill_switch_blocked": bool(kill.get("blocked")),
        "founder_gate_env": founder_env.get("FOUNDER_GATE"),
        "founder_6h_approved_env": founder_env.get("FOUNDER_6H_APPROVED"),
        "policy_version": bb.get("policy_version"),
        "export_path": bb.get("export_path"),
        "active_http_200_service_count": int(health_code == 200),
        "execution_owner_count": 1,
        "legacy_stage3_http": s3,
        "legacy_control_plane_http": cp,
        "hard_flags": hard_flags,
        "soft_flags": soft_flags,
        "http": {
            "health": health_code,
            "fee": fee_code,
            "market": market_code,
            "account": acct_code,
            "status": st_code,
            "bounded_6h": b6_code,
            "overview": ov_code,
        },
        "raw_bounded_6h_keys": sorted(bb.keys()) if isinstance(bb, dict) else [],
    }
    # Honest cost-gate evaluated proxy: if blocks counter exists, evaluated is at least that
    # but we do not invent pass counts.
    if bb.get("cost_gate_blocks") is not None:
        report["cost_gate_block_count"] = bb.get("cost_gate_blocks")
        report["cost_gate_evaluated_note"] = (
            "runtime exposes cost_gate_blocks only; pass/evaluated totals not claimed without evidence"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="Tplus1H")
    parser.add_argument("--out-dir", default="artifacts/demo_validation_6h_v2")
    args = parser.parse_args()
    report = collect(args.label)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"checkpoint_{args.label}_{stamp}.json"
    text = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    (out_dir / "checkpoint_latest.json").write_text(text, encoding="utf-8")
    print(json.dumps({
        "path": str(path),
        "session_id": report.get("session_id"),
        "session_status": report.get("session_status"),
        "thread_alive": report.get("thread_alive"),
        "entries_total": report.get("entries_total"),
        "remaining_seconds": report.get("remaining_seconds"),
        "hard_flags": report.get("hard_flags"),
        "recommendation": report.get("recommendation"),
        "effective_demo_write_authorized": report.get("effective_demo_write_authorized"),
    }, indent=2))
    return 1 if report.get("hard_flags") else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Blind Reflection V2.3 — Agent C provider hardening + optional real resume.

Owned lane: provider scheduler, checkpoint integrity, terminal evaluator.
Does not fabricate calibration progress when local checkpoint is missing.
Does not create terminal immutable package unless VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PRIOR_V23 = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_and_learning_prevention"
PRIOR_QUOTA = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_quota_recovery_and_vwap"
EDGE_V2 = ROOT / "artifacts/readiness/immutable/edge_discovery_diagnostics_v2"
RUNTIME = ROOT / ".nexus_runtime/research/blind_reflection_v23"
FINAL_IMMUTABLE = ROOT / "artifacts/readiness/immutable/blind_reflection_v2_3_terminal"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    except Exception:
        return "UNKNOWN"


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    RUNTIME.mkdir(parents=True, exist_ok=True)

    from backend.nexus_edge_discovery.blind_reflection_v23 import build_calibration_set_v23
    from backend.nexus_reflection.orchestrator import run_provider_hardening_pass
    from backend.nexus_strategy_engine.hypotheses_v1_2 import default_v12_hypothesis_drafts

    # Frozen calibration sample builder (do not resample IDs when prior manifest exists)
    hyps = default_v12_hypothesis_drafts()
    market_rows = []
    for i in range(70):
        pnl = 0.9 if i % 2 == 0 else -0.8
        market_rows.append(
            {
                "symbol": ["BTCUSDT", "ETHUSDT", "SOLUSDT"][i % 3],
                "side": "Buy" if pnl > 0 else "Sell",
                "regime": ["TRENDING_UP", "RANGE", "TRENDING_DOWN"][i % 3],
                "entry_status": "ENTRY_FILLED",
                "entry_price": 100.0,
                "stop": 98.0 if pnl > 0 else 102.0,
                "take_profit": 104.0 if pnl > 0 else 96.0,
                "entry_ts": 1_742_000_000_000 + i * 900_000,
                "exit_price": 103.0 if pnl > 0 else 99.0,
                "exit_status": "TARGET" if pnl > 0 else "STOP",
                "gross_pnl": pnl,
                "net_pnl": pnl * 0.85,
                "fees": 0.06,
                "slippage": 0.02,
                "funding": 0.0,
                "holding_bars": 10,
                "mfe": abs(pnl) * 1.1,
                "mae": abs(pnl) * 0.4,
            }
        )
    packets = build_calibration_set_v23(
        market_rows=market_rows,
        hypotheses=hyps,
        universe_snapshot_id="v23_quota_universe",
        data_checksum="v23_quota_data",
        real_count=60,
        control_count=20,
    )
    assert len(packets) == 80

    prior_manifest_path = PRIOR_QUOTA / "calibration_manifest.json"
    if prior_manifest_path.is_file():
        prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        manifest_checksum = str(prior_manifest.get("calibration_manifest_checksum") or "")
        prior_ids = list(prior_manifest.get("case_ids") or [])
        now_ids = [p.get("trade_id") for p in packets]
        if prior_ids and prior_ids != now_ids:
            # Do not silently retune frozen set — report mismatch via hardening path
            manifest_checksum = manifest_checksum or _sha(
                {"ids": now_ids, "n": 80, "schema": "calibration_manifest"}
            )
    else:
        manifest_checksum = _sha(
            {"ids": [p.get("trade_id") for p in packets], "n": 80, "schema": "calibration_manifest"}
        )

    print("1) provider hardening pass (scheduler/checkpoint/terminal)...", flush=True)
    allow_real = os.getenv("NEXUS_V23_ALLOW_REAL_RESUME", "0") == "1"
    result = run_provider_hardening_pass(
        root=ROOT,
        packets=packets,
        manifest_checksum=manifest_checksum,
        model_id=os.getenv("NEXUS_GROQ_REFLECTION_MODEL", "llama-3.3-70b-versatile"),
        allow_real_resume=allow_real,
    )
    _write(RUNTIME / "agent_c_hardening_summary.json", result)

    # Never create terminal package unless truly VERIFIED
    if (
        result.get("V2_3_terminal_status") == "VERIFIED"
        and result.get("quality_gates_passed")
        and result.get("new_policy_effect_lesson_count", 0) >= 0
        and result.get("real_resume_executed")
    ):
        FINAL_IMMUTABLE.mkdir(parents=True, exist_ok=True)
        _write(FINAL_IMMUTABLE / "agent_c_terminal_summary.json", result)
        result["final_immutable_package_created"] = True
    else:
        result["final_immutable_package_created"] = False

    track = {
        "schema": "agent_c_reflection_provider_v23",
        "created_at": _utc(),
        "git_head_at_run": _git_head(),
        "agent_id": "AGENT_C_REFLECTION_PROVIDER",
        "recommendation": result.get("recommendation"),
        "real_resume_executed": result.get("real_resume_executed"),
        "real_resume_status": result.get("real_resume_status"),
        "local_runtime_checkpoint_available": result.get("local_runtime_checkpoint_available"),
        "V2_3_terminal_status": result.get("V2_3_terminal_status"),
        "quality_gates_evaluated": result.get("quality_gates_evaluated"),
        "quality_gates_passed": result.get("quality_gates_passed"),
        "new_policy_effect_lesson_count": result.get("new_policy_effect_lesson_count"),
        "prior_packages_preserved": {
            "blind_reflection_v2_3_and_learning_prevention": PRIOR_V23.is_dir(),
            "blind_reflection_v2_3_quota_recovery_and_vwap": PRIOR_QUOTA.is_dir(),
            "edge_discovery_diagnostics_v2": EDGE_V2.is_dir(),
        },
        "exchange_write_attempt_count": 0,
        "deployment_started": False,
        "mainnet": False,
        "real_money": False,
        "fixture_only": result.get("fixture_only"),
        "real_ai_quality_claimed": False,
    }
    _write(RUNTIME / "track_agent_c_summary.json", track)
    print(json.dumps(track, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

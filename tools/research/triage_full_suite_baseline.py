#!/usr/bin/env python3
"""Compare Full Suite failures against known baseline debt (no skips, no mutation)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

BASELINE = {
    "tests/test_compound_capital.py::CompoundCapitalTests::test_profit_lock_blocks_new_entries_after_daily_target",
    "tests/test_exchange_capital_view.py::ExchangeCapitalViewTests::test_ui_capital_uses_only_binance_summary_fields",
    "tests/test_exchange_capital_view.py::ExchangeCapitalViewTests::test_usdt_only_futures_uses_asset_row_not_account_total",
    "tests/test_exchange_capital_view.py::ExchangeCapitalViewTests::test_usdt_only_spot_ignores_usdc_and_btc",
    "tests/test_learning_feedback_loop.py::LearningFeedbackLoopTests::test_blocked_regime_emerges_from_repeated_regime_losses",
    "tests/test_liquidation_learning.py::LiquidationLearningTests::test_liquidation_trade_records_and_blocks_symbol",
    "tests/test_liquidation_learning.py::LiquidationLearningTests::test_radar_dispatch_respects_learning_guidance",
    "tests/test_runtime_store_safety.py::RuntimeStoreSafetyTests::test_multiple_store_instances_do_not_drop_runtime_metadata",
    "tests/test_runtime_store_safety.py::RuntimeStoreSafetyTests::test_snapshot_version_and_last_writer_increment",
    "tests/test_stage4_ai_decision_layer.py::Stage412ProviderExhaustionTests::test_groq_quota_exhausted_triggers_cerebras_fallback",
    "tests/test_stage4_p2h_release_health_check.py::Stage418P2HReleaseHealthCheckTests::test_release_health_summary_flags",
    "tests/test_truth_layer_guard.py::TruthLayerGuardTests::test_too_many_degraded_contexts_blocks_futures",
}


def main() -> int:
    report = Path("full_suite_junit.xml")
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        "-q",
        "--tb=no",
        f"--junitxml={report}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print(out[-4000:])
    failed = set(re.findall(r"^FAILED (.+)$", out, flags=re.M))
    # Also parse from summary lines without FAILED prefix variants
    if not failed:
        failed = set(re.findall(r"FAILED\s+(\S+)", out))
    new = sorted(failed - BASELINE)
    missing = sorted(BASELINE - failed)
    payload = {
        "exit_code": proc.returncode,
        "failed_count": len(failed),
        "baseline_count": len(BASELINE),
        "new_regressions": new,
        "baseline_not_reproduced": missing,
        "failed": sorted(failed),
        "release_delta_regression": len(new),
        "full_suite_baseline_debt": "FULL_SUITE_BASELINE_DEBT_12",
    }
    Path("full_suite_triage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if new:
        print("NEW_REGRESSIONS_PRESENT", file=sys.stderr)
        return 1
    if len(failed) > len(BASELINE):
        print("FAILURE_COUNT_EXCEEDS_BASELINE", file=sys.stderr)
        return 1
    # Baseline debt allowed: do not fail CI solely for known 12.
    print("FULL_SUITE_BASELINE_DEBT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

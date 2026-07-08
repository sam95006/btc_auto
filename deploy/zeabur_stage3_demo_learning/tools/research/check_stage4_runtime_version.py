#!/usr/bin/env python3
"""Stage 4.18-H — verify Stage4 research runtime files before cloud regression (no LLM/orders)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402

DEFAULT_APP_ROOT = Path(os.environ.get("STAGE4_APP_ROOT", "/app"))
TOOLS_RESEARCH = "tools/research"

REQUIRED_FILES = (
    "stage4_prompt_builder.py",
    "stage4_paper_readiness.py",
    "stage4_paper_event_logger.py",
    "stage4_paper_guard_inputs.py",
    "stage4_mae_calibration_analysis.py",
    "validate_stage4_ai_decision_outputs.py",
    "run_stage4_ai_decision_dry_run.py",
    "stage4_decision_schema.py",
    "stage4_ai_decision_agent.py",
    "stage4_schema_repair.py",
    "stage4_watchlist_followup_simulator.py",
    "stage4_mae_regression_compare.py",
)

PROMPT_HINTS_418F = (
    "0.25 = 0.25%",
    "mae_risk_too_high",
    "max_adverse_move_pct",
)

PROMPT_HINTS_418H = (
    "Stage 4.18-H",
    "NOT ATR",
    "watch survival target",
    "0.28%",
    "invalidation distance",
    "directional_bias is LONG/SHORT",
)

PROMPT_HINTS_418I = (
    "Stage 4.18-I",
    "invalidation distance",
    "BTC graduation recovery",
    "watch_followup_required",
    "PEPE in high volatility",
)

PROMPT_HINTS_418J = (
    "Stage 4.18-J",
    "ETH acceptable watch",
    "ETH too-risky",
    "reference_price=3000",
    "mae_risk_estimate_pct=0.30",
)

PROMPT_HINTS_418L = (
    "Stage 4.18-L",
    "BTC valid watch WITH side",
    "ETH valid watch WITH side",
    "candidate_side=SELL",
    "candidate_side=BUY",
    "LONG bias → candidate_side=BUY",
    "entry_trigger.type=none is invalid",
    "directional_bias_without_candidate_side",
)

PROMPT_HINTS_418M = (
    "Stage 4.18-M",
    "Structured output contract",
    "candidate_side NONE is ONLY allowed for soft_skip or hard_skip",
    "Bad output (INVALID)",
)

PROMPT_HINTS_418N = (
    "Stage 4.18-N",
    "GROQ STRICT OUTPUT RULE",
    "CEREBRAS STRICT OUTPUT RULE",
    "candidate_side must not be NONE",
    "entry_trigger.type must not be none",
)

PATCH_MARKER_FILES = (
    "stage4_paper_readiness.py",
    "stage4_prompt_builder.py",
    "stage4_mae_calibration_analysis.py",
    "stage4_mae_regression_compare.py",
)

MIN_PAPER_READINESS_BYTES = 15_000


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _file_present(app_root: Path, name: str) -> bool:
    return (app_root / TOOLS_RESEARCH / name).is_file()


def _prompt_hints_present(app_root: Path) -> tuple[bool, List[str]]:
    text = _read_text(app_root / TOOLS_RESEARCH / "stage4_prompt_builder.py")
    all_hints = (
        PROMPT_HINTS_418F
        + PROMPT_HINTS_418H
        + PROMPT_HINTS_418I
        + PROMPT_HINTS_418J
        + PROMPT_HINTS_418L
        + PROMPT_HINTS_418M
        + PROMPT_HINTS_418N
    )
    missing = [h for h in all_hints if h not in text]
    return len(missing) == 0, missing


def _schema_enforcement_present(app_root: Path) -> bool:
    text = _read_text(app_root / TOOLS_RESEARCH / "stage4_paper_readiness.py")
    return "apply_schema_level_enforcement" in text and "mae_above_symbol_cap" in text


def _compare_tool_present(app_root: Path) -> bool:
    return _file_present(app_root, "stage4_mae_regression_compare.py")


def _paper_readiness_markers(app_root: Path) -> tuple[bool, bool]:
    text = _read_text(app_root / TOOLS_RESEARCH / "stage4_paper_readiness.py")
    has_metrics = "def build_mae_calibration_metrics" in text
    return has_metrics, has_metrics


def _import_checks(app_root: Path) -> Dict[str, bool]:
    tools = app_root / TOOLS_RESEARCH
    results: Dict[str, bool] = {
        "get_paper_mae_pct_present": False,
        "build_mae_metrics_present": False,
        "mae_analysis_main_present": False,
    }
    guard_path = tools / "stage4_paper_guard_inputs.py"
    if guard_path.is_file():
        spec = importlib.util.spec_from_file_location("stage4_paper_guard_inputs_rt", guard_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            results["get_paper_mae_pct_present"] = hasattr(mod, "get_paper_mae_pct")

    readiness_path = tools / "stage4_paper_readiness.py"
    if readiness_path.is_file():
        spec = importlib.util.spec_from_file_location("stage4_paper_readiness_rt", readiness_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            results["build_mae_metrics_present"] = hasattr(mod, "build_mae_calibration_metrics")

    analysis_path = tools / "stage4_mae_calibration_analysis.py"
    if analysis_path.is_file():
        spec = importlib.util.spec_from_file_location("stage4_mae_calibration_analysis_rt", analysis_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            results["mae_analysis_main_present"] = hasattr(mod, "main")

    return results


def _stale_suspected(app_root: Path) -> tuple[bool, List[str]]:
    reasons: List[str] = []
    pr = app_root / TOOLS_RESEARCH / "stage4_paper_readiness.py"
    if pr.is_file() and pr.stat().st_size < MIN_PAPER_READINESS_BYTES:
        reasons.append("stage4_paper_readiness.py_too_small")
    if not _file_present(app_root, "stage4_mae_calibration_analysis.py"):
        reasons.append("stage4_mae_calibration_analysis.py_missing")
    if not _file_present(app_root, "stage4_paper_guard_inputs.py"):
        reasons.append("stage4_paper_guard_inputs.py_missing")
    hints_ok, missing_hints = _prompt_hints_present(app_root)
    if not hints_ok:
        reasons.append(f"prompt_hints_missing:{','.join(missing_hints[:5])}")
    return bool(reasons), reasons


def apply_runtime_patch(
    *,
    patch_dir: Path,
    app_root: Path = DEFAULT_APP_ROOT,
) -> Dict[str, Any]:
    """Copy persisted .py patches from /data into /app/tools/research (read-only deploy aid)."""
    patch_dir = patch_dir.expanduser().resolve()
    dest = app_root / TOOLS_RESEARCH
    dest.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    skipped: List[str] = []
    for name in REQUIRED_FILES:
        src = patch_dir / name
        if not src.is_file():
            skipped.append(name)
            continue
        target = dest / name
        target.write_bytes(src.read_bytes())
        copied.append(name)
    return {
        "patch_dir": str(patch_dir),
        "app_root": str(app_root),
        "files_copied": copied,
        "files_skipped": skipped,
        "copied_count": len(copied),
    }


def check_runtime_version(*, app_root: Optional[Path] = None) -> Dict[str, Any]:
    app_root = (app_root or DEFAULT_APP_ROOT).expanduser().resolve()
    missing_files = [n for n in REQUIRED_FILES if not _file_present(app_root, n)]
    hints_ok, missing_hints = _prompt_hints_present(app_root)
    build_ok, _ = _paper_readiness_markers(app_root)
    imports = _import_checks(app_root)
    stale, stale_reasons = _stale_suspected(app_root)

    mae_script = _file_present(app_root, "stage4_mae_calibration_analysis.py")
    guard_inputs = _file_present(app_root, "stage4_paper_guard_inputs.py")
    schema_enforcement = _schema_enforcement_present(app_root)
    compare_tool = _compare_tool_present(app_root)

    passed = (
        not missing_files
        and hints_ok
        and mae_script
        and build_ok
        and guard_inputs
        and schema_enforcement
        and compare_tool
        and imports["get_paper_mae_pct_present"]
        and imports["build_mae_metrics_present"]
        and imports["mae_analysis_main_present"]
        and not stale
    )

    return {
        "record_type": "stage4_runtime_version_check",
        "generated_at_utc": utc_now_iso(),
        "app_root": str(app_root),
        "runtime_version_check_passed": passed,
        "prompt_hints_present": hints_ok,
        "missing_prompt_hints": missing_hints,
        "schema_enforcement_present": schema_enforcement,
        "compare_tool_present": compare_tool,
        "mae_analysis_script_present": mae_script,
        "build_mae_metrics_present": build_ok and imports["build_mae_metrics_present"],
        "paper_guard_inputs_present": guard_inputs,
        "get_paper_mae_pct_present": imports["get_paper_mae_pct_present"],
        "mae_analysis_main_present": imports["mae_analysis_main_present"],
        "app_file_stale_suspected": stale,
        "stale_reasons": stale_reasons,
        "missing_required_files": missing_files,
        "required_files_checked": list(REQUIRED_FILES),
        "stage_marker": "4.18-N",
    }


def runtime_version_gate_enabled() -> bool:
    raw = os.environ.get("STAGE4_REQUIRE_RUNTIME_VERSION_CHECK", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    # Default: gate cloud real-LLM regressions
    return os.environ.get("STAGE4_REQUIRE_REAL_LLM", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 runtime version check (418-H)")
    parser.add_argument("--app-root", default=str(DEFAULT_APP_ROOT))
    parser.add_argument("--output", default="", help="Optional JSON output path")
    parser.add_argument("--gate", action="store_true", help="Exit 1 if check fails")
    parser.add_argument(
        "--apply-patch-dir",
        default="",
        help="Copy .py files from persisted patch dir before check",
    )
    args = parser.parse_args()

    app_root = Path(args.app_root)
    if args.apply_patch_dir.strip():
        apply_runtime_patch(patch_dir=Path(args.apply_patch_dir), app_root=app_root)

    summary = check_runtime_version(app_root=app_root)
    if args.output.strip():
        write_json(Path(args.output), summary)
    print(json.dumps(summary, indent=2))
    if args.gate and not summary.get("runtime_version_check_passed"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

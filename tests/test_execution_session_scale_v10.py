"""V10 Execution Session Scale — fuzz 100k + 30d/90d Session + injection probes.

Defaults use smoke-scale env overrides so pytest stays CI-fast. Full targets
are exercised by ``tools/research/run_execution_session_scale_v10.py`` (and
optionally this module when ``NEXUS_V10_SMOKE`` is unset).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

# Force smoke defaults for unit tests unless caller already set an override.
os.environ.setdefault("NEXUS_V10_SMOKE", "1")
os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_autonomy.session_scale_v10 import (  # noqa: E402
    PASS_STATUS as SESSION_PASS,
    run_focused_injection_probes,
    run_scaled_session,
    run_session_scale_campaign,
)
from backend.nexus_execution.orchestrator_adapter_v1 import (  # noqa: E402
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
)
from backend.nexus_execution.scale_.config import (  # noqa: E402
    DEFAULT_FUZZ_SCENARIOS,
    load_scale_config,
)
from backend.nexus_execution.scale_.injections import (  # noqa: E402
    SCALE_FAULT_CLASSES,
    SCALE_INJECTION_CATALOG,
    SCALE_LONG_SESSION_INJECTIONS,
    injection_matrix,
)
from backend.nexus_execution.scale_v10 import (  # noqa: E402
    PASS_STATUS,
    run_scale_fuzz,
    write_scale_artifacts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNED_FILES = (
    REPO_ROOT / "backend/nexus_execution/scale_v10.py",
    REPO_ROOT / "backend/nexus_autonomy/session_scale_v10.py",
    REPO_ROOT / "tools/research/run_execution_session_scale_v10.py",
    REPO_ROOT / "tests/test_execution_session_scale_v10.py",
)
OWNED_DIRS = (REPO_ROOT / "backend/nexus_execution/scale_",)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def test_canonical_engine_single_authority() -> None:
    assert CANONICAL_EXECUTION_ENGINE_COUNT == 1
    assert (
        CANONICAL_EXECUTION_ENGINE
        == "backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11"
    )
    assert ADAPTER_ID == "NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1"


def test_scale_config_smoke_defaults() -> None:
    cfg = load_scale_config()
    assert cfg.smoke is True
    assert cfg.fuzz_scenarios < DEFAULT_FUZZ_SCENARIOS
    assert cfg.fuzz_scenarios >= 1
    assert cfg.day_30_hours == 30 * 24
    assert cfg.day_90_hours == 90 * 24


def test_injection_matrix_covers_founder_fault_classes() -> None:
    matrix = injection_matrix()
    for fault in SCALE_FAULT_CLASSES:
        assert fault in matrix["fault_class_to_injections"]
        assert matrix["fault_class_to_injections"][fault]
    for flag in (
        "process_termination",
        "partial_fill_before_crash",
        "duplicate_order_intent",
        "clock_jump_forward",
        "groq_429",
        "disk_soft_limit",
        "ledger_corruption_probe",
        "snapshot_corruption",
    ):
        assert flag in SCALE_INJECTION_CATALOG or flag in SCALE_LONG_SESSION_INJECTIONS


def test_execution_fuzz_scale_smoke_pass() -> None:
    cfg = load_scale_config()
    report = run_scale_fuzz(config=cfg)
    assert report["generated_execution_scenario_count"] == cfg.fuzz_scenarios
    assert report["pass"] is True
    assert report["exchange_write_attempt_count"] == 0
    assert report["demo_order_count"] == 0
    assert report["mainnet"] is False
    assert report["real_money"] is False
    assert report["invariants"]["scenarios_with_violations"] == 0
    assert report["canonical_execution_engine"] == CANONICAL_EXECUTION_ENGINE


def test_scaled_session_30d_smoke(tmp_path: Path) -> None:
    cfg = load_scale_config()
    report = run_scaled_session(
        tmp_path / "s30",
        session_id="SESSION_30D",
        logical_hours=cfg.day_30_hours,
        candidate_count=cfg.session_candidate_count_30d,
        seed=cfg.session_seed,
    )
    assert report["logical_duration_hours"] == cfg.day_30_hours
    assert report["session_pass"] is True
    assert report["final_state"] in {"COMPLETED", "BLOCKED"}
    assert report["exchange_write_attempt_count"] == 0
    assert report["restart_count"] >= 1  # process_termination injection
    assert "partial_fill_before_crash" in report["injection_flags"]
    assert "duplicate_order_intent" in report["injection_flags"]


def test_scaled_session_90d_smoke(tmp_path: Path) -> None:
    cfg = load_scale_config()
    report = run_scaled_session(
        tmp_path / "s90",
        session_id="SESSION_90D",
        logical_hours=cfg.day_90_hours,
        candidate_count=cfg.session_candidate_count_90d,
        seed=cfg.session_seed + 1,
    )
    assert report["logical_duration_hours"] == cfg.day_90_hours
    assert report["session_pass"] is True
    assert report["exchange_write_attempt_count"] == 0


def test_focused_injection_probes_fail_closed(tmp_path: Path) -> None:
    focused = run_focused_injection_probes(tmp_path / "focused", seed=42)
    assert focused["probe_pass"] is True
    probes = focused["probes"]
    assert probes["snapshot_corruption_probe"]["probe_pass"] is True
    assert probes["ledger_corruption_probe"]["probe_pass"] is True
    for flag in ("clock_jump_forward", "clock_jump_backward", "disk_hard_limit"):
        assert probes[flag]["probe_pass"] is True
        assert probes[flag]["exchange_write_attempt_count"] == 0


def test_session_scale_campaign_smoke(tmp_path: Path) -> None:
    cfg = load_scale_config()
    package = run_session_scale_campaign(tmp_path / "campaign", config=cfg)
    assert package["Session_Scale_status"] == SESSION_PASS
    assert package["session_scale_pass"] is True
    assert set(package["sessions"]) == {"SESSION_30D", "SESSION_90D"}
    assert package["logical_sessions_hours"] == [cfg.day_30_hours, cfg.day_90_hours]
    assert package["exchange_write_attempt_count"] == 0
    assert package["canonical_execution_engine_count"] == 1


def test_write_scale_artifacts_and_secret_scan(tmp_path: Path) -> None:
    cfg = load_scale_config()
    fuzz = run_scale_fuzz(config=cfg)
    session = run_session_scale_campaign(tmp_path / "sess", config=cfg)

    # Inline secret scan over owned paths.
    hits: list[str] = []
    files: list[Path] = list(OWNED_FILES)
    for d in OWNED_DIRS:
        files.extend(sorted(p for p in d.rglob("*.py") if p.is_file()))
    for fp in files:
        text = fp.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                hits.append(str(fp))
                break
    secret_scan = {
        "schema": "v10_execution_session_scale_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": len(files),
    }
    assert secret_scan["secret_leak_count"] == 0

    out = tmp_path / "artifacts"
    paths = write_scale_artifacts(out, fuzz=fuzz, session=session, secret_scan=secret_scan)
    status = json.loads(paths["scale_status.json"].read_text(encoding="utf-8"))
    assert status["status"] == PASS_STATUS
    assert status["fuzz_pass"] is True
    assert status["session_scale_pass"] is True
    assert status["secret_scan_pass"] is True
    readiness = json.loads(paths["readiness_report.json"].read_text(encoding="utf-8"))
    assert readiness["recommendation"] == PASS_STATUS


def test_full_target_constants_documented() -> None:
    """Full Lane B targets remain 100k / 30d / 90d regardless of smoke env."""
    assert DEFAULT_FUZZ_SCENARIOS == 100_000
    cfg = load_scale_config()
    assert cfg.day_30_hours == 720
    assert cfg.day_90_hours == 2160

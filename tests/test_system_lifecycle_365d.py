"""V11.1 365-day System Lifecycle Campaign — system correctness tests.

Defaults force smoke candidate density for CI. Full targets are exercised by
``tools/research/run_system_lifecycle_365d.py``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("NEXUS_V11_1_SYSTEM_365D_SMOKE", "1")
os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_system.lifecycle_365d import (  # noqa: E402
    HARD_BANS,
    PASS_STATUS,
    REQUIRED_ZERO_INVARIANTS,
    campaign_digest,
    injection_matrix,
    load_lifecycle_365_config,
    run_system_lifecycle_365d_campaign,
)
from backend.nexus_system.lifecycle_365d.campaign import run_lifecycle_session  # noqa: E402
from backend.nexus_system.lifecycle_365d.config import LOGICAL_DAYS, LOGICAL_HOURS  # noqa: E402
from backend.nexus_system.lifecycle_365d.injections import (  # noqa: E402
    LIFECYCLE_FAULT_CLASSES,
    LIFECYCLE_INJECTION_CATALOG,
)
from backend.nexus_system.lifecycle_365d.invariants import invariants_pass  # noqa: E402
from backend.nexus_system.lifecycle_365d.probes import (  # noqa: E402
    run_cancel_replace_probe,
    run_focused_lifecycle_probes,
    run_liquidity_collapse_probe,
    run_qualification_blocks_probe,
)
from backend.nexus_system.lifecycle_365d.universe import (  # noqa: E402
    SYMBOLS,
    VOL_REGIMES,
    build_lifecycle_candidates,
    universe_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNED = (
    REPO_ROOT / "backend/nexus_system/lifecycle_365d",
    REPO_ROOT / "tools/research/run_system_lifecycle_365d.py",
    REPO_ROOT / "tests/test_system_lifecycle_365d.py",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def test_config_logical_window_smoke() -> None:
    cfg = load_lifecycle_365_config()
    assert cfg.logical_days == LOGICAL_DAYS == 365
    assert cfg.logical_hours == float(LOGICAL_HOURS)
    assert cfg.smoke is True
    assert cfg.candidate_count >= 16


def test_universe_multi_symbol_multi_regime() -> None:
    cands = build_lifecycle_candidates(120, seed=42, logical_days=365)
    uni = universe_summary(cands)
    assert uni["symbol_count"] >= 5
    assert set(uni["symbols"]) == set(SYMBOLS)
    assert uni["vol_regime_count"] >= 3
    assert set(VOL_REGIMES).issuperset(set(uni["vol_regimes"]))
    assert uni["liquidity_collapse_events"] >= 1
    assert uni["logical_day_span"]["distinct_days"] >= 100
    assert all(c.get("edge_claim") is False for c in cands)
    assert all(c.get("profitability_measured") is False for c in cands)


def test_injection_matrix_covers_founder_classes() -> None:
    matrix = injection_matrix()
    for fault in LIFECYCLE_FAULT_CLASSES:
        assert fault in matrix["fault_class_to_coverage"]
        assert matrix["fault_class_to_coverage"][fault]
    for flag in (
        "provider_timeout",
        "clock_jump_forward",
        "disk_soft_limit",
        "partial_fill_before_crash",
        "cancel_replace_probe",
        "reflection_interruption",
        "lesson_storage_interruption",
        "kill_switch_during_open_position",
        "process_termination",
        "qualification_blocks_probe",
        "liquidity_collapse_probe",
    ):
        assert flag in LIFECYCLE_INJECTION_CATALOG


def test_hard_bans_and_required_invariants() -> None:
    assert "no_formal_walk_forward" in HARD_BANS
    assert "no_oos_consumption" in HARD_BANS
    assert "no_edge_claim" in HARD_BANS
    assert "no_strategy_selection" in HARD_BANS
    for key in (
        "exchange_write_attempt_count",
        "orphan_lifecycle_count",
        "duplicate_position_count",
        "unclosed_intent_count",
        "untracked_fill_count",
        "cost_bridge_failure_count",
        "risk_limit_bypass_count",
        "evidence_binding_failure_count",
        "checkpoint_loss_count",
    ):
        assert key in REQUIRED_ZERO_INVARIANTS


def test_cancel_replace_probe() -> None:
    probe = run_cancel_replace_probe()
    assert probe["probe_pass"] is True
    assert probe["cancel_replace_count"] >= 1
    assert probe["invariants"]["exchange_write_attempt_count"] == 0
    assert probe["invariants"]["cost_bridge_failure_count"] == 0


def test_liquidity_and_qualification_probes() -> None:
    liq = run_liquidity_collapse_probe()
    assert liq["probe_pass"] is True
    assert liq["new_entry_allowed"] is False
    qual = run_qualification_blocks_probe()
    assert qual["probe_pass"] is True
    assert qual["formal_walk_forward_executed"] is False
    assert qual["oos_consumed"] is False
    assert qual["strategy_selected"] is False


def test_lifecycle_session_smoke(tmp_path: Path) -> None:
    cfg = load_lifecycle_365_config()
    report = run_lifecycle_session(tmp_path / "s365", config=cfg)
    assert report["logical_duration_hours"] == cfg.logical_hours
    assert report["logical_days"] == 365
    assert report["session_pass"] is True
    assert report["exchange_write_attempt_count"] == 0
    assert report["restart_count"] >= 1
    assert invariants_pass(report["invariants_counts"])
    assert "partial_fill_before_crash" in report["injection_flags"]
    assert "reflection_interruption" in report["injection_flags"]
    assert "lesson_storage_interruption" in report["injection_flags"]
    uni = report["universe"]
    assert uni["symbol_count"] >= 2
    assert uni["vol_regime_count"] >= 2


def test_focused_probes_aggregate(tmp_path: Path) -> None:
    focused = run_focused_lifecycle_probes(tmp_path / "focused", seed=911_365)
    assert focused["probe_pass"] is True
    assert focused["probes"]["cancel_replace_probe"]["probe_pass"] is True
    assert focused["probes"]["qualification_blocks_probe"]["probe_pass"] is True
    assert focused["probes"]["restart_recovery_probe"]["probe_pass"] is True
    assert focused["invariants"]["checkpoint_loss_count"] == 0


def test_full_campaign_smoke_two_pass(tmp_path: Path) -> None:
    cfg = load_lifecycle_365_config()
    a = run_system_lifecycle_365d_campaign(tmp_path / "pass1", config=cfg)
    b = run_system_lifecycle_365d_campaign(tmp_path / "pass2", config=cfg)
    assert a["System_Lifecycle_365d_status"] == PASS_STATUS
    assert b["System_Lifecycle_365d_status"] == PASS_STATUS
    assert a["system_lifecycle_365d_pass"] is True
    assert campaign_digest(a) == campaign_digest(b)
    assert a["campaign_digest"] == b["campaign_digest"]
    for key in REQUIRED_ZERO_INVARIANTS:
        assert a["invariants"][key] == 0
        assert b["invariants"][key] == 0
    assert a["edge_claim"] is False
    assert a["profitability_measured"] is False
    assert a["formal_walk_forward_executed"] is False
    assert a["oos_consumed"] is False
    assert a["strategy_selected"] is False


def test_negative_invariant_detection() -> None:
    bad = {k: 0 for k in REQUIRED_ZERO_INVARIANTS}
    bad["orphan_lifecycle_count"] = 2
    assert invariants_pass(bad) is False


def test_owned_paths_no_secret_leak() -> None:
    hits: list[str] = []
    for root in OWNED:
        if root.is_dir():
            files = list(root.rglob("*.py"))
        elif root.is_file():
            files = [root]
        else:
            continue
        for fp in files:
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(fp))
                    break
    assert hits == []


def test_adversarial_false_pass_guards(tmp_path: Path) -> None:
    """PASS 2 adversarial: package must not claim edge / WF / OOS / profitability."""
    cfg = load_lifecycle_365_config()
    pkg = run_system_lifecycle_365d_campaign(tmp_path / "adv", config=cfg)
    assert pkg["system_correctness_only"] is True
    assert pkg.get("edge_claim") is False
    assert pkg.get("oos_consumed") is False
    assert pkg.get("formal_walk_forward_executed") is False
    assert pkg.get("profitability_measured") is False
    assert pkg.get("strategy_selected") is False
    for k in REQUIRED_ZERO_INVARIANTS:
        assert k in pkg["invariants"]
    # Digest must be stable across identical configs (no silent non-determinism).
    again = run_system_lifecycle_365d_campaign(tmp_path / "adv2", config=cfg)
    assert campaign_digest(pkg) == campaign_digest(again)

"""Focused tests for Founder-private Observability SLO V11.1.

Pass 1: SLO definitions, domain collectors, alert wiring, hard bans, secret-free.
Pass 2: adversarial breaches, all alert classes, no mutation / no public routes,
        false-PASS hunt, forbidden key rejection.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.nexus_observability import (
    ALERT_CLASSES,
    HARD_BANS,
    OBSERVABILITY_DOMAINS,
    apply_pass2_adversarial_overrides,
    build_private_observability_slo,
    collect_alerts,
    hard_bans_document,
    slo_catalog,
)
from backend.nexus_observability.constants import (
    ARTIFACT_REL,
    FORBIDDEN_OBSERVABILITY_KEYS,
    OWNED_PATHS,
    STALENESS_THRESHOLD_SECONDS,
)
from backend.nexus_observability.sanitize import assert_no_forbidden_keys, redact_forbidden_keys


SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


# ---------------------------------------------------------------------------
# Pass 1 — contract / happy path
# ---------------------------------------------------------------------------


def test_owned_paths_contract() -> None:
    assert "backend/nexus_observability" in OWNED_PATHS
    assert ARTIFACT_REL in OWNED_PATHS
    assert "tools/research/run_private_observability_slo_v11_1.py" in OWNED_PATHS


def test_slo_catalog_covers_all_domains() -> None:
    defs = slo_catalog()
    domains = {d.domain for d in defs}
    assert set(OBSERVABILITY_DOMAINS) == domains
    assert len(defs) >= len(OBSERVABILITY_DOMAINS)


def test_hard_bans_include_s2_explicit() -> None:
    required = {
        "no_public_routes",
        "no_account_secrets",
        "no_execution_mutation_endpoint",
        "read_only_only",
    }
    assert required.issubset(set(HARD_BANS))
    doc = hard_bans_document()
    assert doc["public_routes"] is False
    assert doc["execution_mutation_endpoint"] is False
    assert doc["account_secrets"] is False


def test_pass1_baseline_bundle(tmp_path: Path) -> None:
    # Force healthy storage so baseline is clean regardless of host disk.
    overrides = {
        "storage_budget": {
            "floor_ok": True,
            "mode": "NORMAL",
            "free_bytes": 100 * (1024**3),
            "minimum_free_disk_bytes": 30 * (1024**3),
        }
    }
    bundle = build_private_observability_slo(tmp_path, overrides=overrides, pass_number=1)
    assert bundle["status"]["status"] == "PASS"
    assert bundle["status"]["founder_private"] is True
    assert bundle["status"]["read_only"] is True
    assert bundle["status"]["public_routes"] is False
    assert bundle["status"]["execution_mutation_endpoint"] is False
    assert bundle["status"]["exchange_write_attempt_count"] == 0
    assert bundle["status"]["secrets_present"] is False
    assert bundle["slo_evaluation"]["passed"] == bundle["slo_evaluation"]["total"]
    assert set(bundle["domain_health_snapshot"]["domains"]) == set(OBSERVABILITY_DOMAINS)


def test_alert_classes_supported() -> None:
    assert set(ALERT_CLASSES) == {
        "failure_state",
        "staleness",
        "data_quality",
        "ambiguous_state",
        "storage_floor",
        "provider_capacity",
    }


def test_staleness_alert_on_old_evidence(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "decision_lifecycle": {
                "max_evidence_age_seconds": STALENESS_THRESHOLD_SECONDS + 1,
                "stale": True,
            },
            "storage_budget": {"floor_ok": True, "mode": "NORMAL"},
        },
    )
    classes = {a["alert_class"] for a in bundle["alert_matrix"]["alerts"] if a["active"]}
    assert "staleness" in classes
    # Breach alerted => SLO still covered
    assert bundle["status"]["status"] == "PASS"


def test_provider_capacity_alert(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "provider_health": {
                "transport_status": "CIRCUIT_OPEN",
                "success_count": 5,
                "pending_count": 40,
                "capacity_blocked": True,
            },
            "storage_budget": {"floor_ok": True, "mode": "NORMAL"},
        },
    )
    codes = {a["code"] for a in bundle["alert_matrix"]["alerts"] if a["active"]}
    assert "PROVIDER_CAPACITY_BLOCKED" in codes


def test_storage_floor_alert(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "storage_budget": {
                "floor_ok": False,
                "mode": "STORAGE_BUDGET_BLOCKED",
                "free_bytes": 1,
                "stop_reason": "minimum_free_disk_fail",
            }
        },
    )
    codes = {a["code"] for a in bundle["alert_matrix"]["alerts"] if a["active"]}
    assert "STORAGE_FLOOR_OR_HARD_CAP" in codes


def test_ambiguous_state_alert(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "ledger_snapshot_checkpoint": {
                "ambiguous_state": True,
                "ambiguous_count": 3,
            },
            "storage_budget": {"floor_ok": True, "mode": "NORMAL"},
        },
    )
    codes = {a["code"] for a in bundle["alert_matrix"]["alerts"] if a["active"]}
    assert "DURABILITY_BLOCKED_AMBIGUOUS_STATE" in codes


def test_qualification_remains_blocked(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={"storage_budget": {"floor_ok": True, "mode": "NORMAL"}},
    )
    qual = bundle["domain_health_snapshot"]["domains"]["qualification_block_state"]
    assert qual["all_stages_blocked"] is True
    assert qual["hard_bans_intact"] is True


def test_lesson_gate_blocks_unverified(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "lesson_gate": {
                "terminal_status": "INCOMPLETE_PROVIDER_CAPACITY",
                "quality_gates_passed": False,
                "proposed_policy_effect_lesson_count": 4,
            },
            "storage_budget": {"floor_ok": True, "mode": "NORMAL"},
        },
    )
    gate = bundle["domain_health_snapshot"]["domains"]["lesson_gate"]["gate"]
    assert gate["policy_effect_lesson_allowed"] is False
    assert gate["new_policy_effect_lesson_count"] == 0


def test_kill_switch_readiness_surface(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "kill_switch_readiness": {
                "reachable": True,
                "kill_switch_engaged": True,
                "state": "KILLED",
            },
            "storage_budget": {"floor_ok": True, "mode": "NORMAL"},
        },
    )
    ks = bundle["domain_health_snapshot"]["domains"]["kill_switch_readiness"]
    assert ks["reachable"] is True
    assert ks["kill_switch_engaged"] is True
    assert ks["observability_read_only"] is True


def test_no_forbidden_keys_in_bundle(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={"storage_budget": {"floor_ok": True, "mode": "NORMAL"}},
    )
    assert_no_forbidden_keys(bundle)
    blob = json.dumps(bundle).lower()
    for key in ("api_key", "api_secret", "wallet_address", "account_balance"):
        # Flag fields may mention keys as ban names; ensure values aren't secrets.
        assert "sk-" not in blob
        assert "begin rsa private key" not in blob


# ---------------------------------------------------------------------------
# Pass 2 — adversarial / negative
# ---------------------------------------------------------------------------


def test_pass2_all_alert_classes_exercised(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides=apply_pass2_adversarial_overrides(),
        pass_number=2,
    )
    active = {a["alert_class"] for a in bundle["alert_matrix"]["alerts"] if a["active"]}
    missing = set(ALERT_CLASSES) - active
    assert not missing, f"missing alert classes: {missing}"
    # Coverage via alerts => PASS (observability must not silent-fail)
    assert bundle["status"]["status"] == "PASS"
    assert bundle["status"]["execution_mutation_endpoint"] is False
    assert bundle["status"]["public_routes"] is False


def test_pass2_secret_key_injection_rejected(tmp_path: Path) -> None:
    dirty = {"api_key": "SHOULD_NEVER_APPEAR", "nested": {"wallet_address": "0xabc"}}
    with pytest.raises(RuntimeError, match="observability_secret_keys"):
        assert_no_forbidden_keys(dirty)
    cleaned = redact_forbidden_keys(dirty)
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["wallet_address"] == "[REDACTED]"


def test_pass2_mutation_endpoint_ban(tmp_path: Path) -> None:
    # Even adversarial pass must keep mutation endpoint count at 0.
    ov = apply_pass2_adversarial_overrides()
    assert ov["execution_simulator"]["mutation_endpoint_count"] == 0
    bundle = build_private_observability_slo(tmp_path, overrides=ov, pass_number=2)
    sim = bundle["domain_health_snapshot"]["domains"]["execution_simulator"]
    assert sim["mutation_endpoint_count"] == 0
    assert sim["execution_mutation_endpoint"] is False


def test_pass2_qualification_unblock_alerts(tmp_path: Path) -> None:
    bundle = build_private_observability_slo(
        tmp_path,
        overrides={
            "qualification_block_state": {
                "all_stages_blocked": False,
                "stages": {"CANDIDATE_FREEZE": "EXECUTED"},
            },
            "storage_budget": {"floor_ok": True, "mode": "NORMAL"},
        },
    )
    codes = {a["code"] for a in bundle["alert_matrix"]["alerts"] if a["active"]}
    assert "QUALIFICATION_STAGE_UNBLOCKED" in codes


def test_pass2_collect_alerts_direct() -> None:
    domain_health = {
        "decision_lifecycle": {
            "stale": True,
            "max_evidence_age_seconds": 999,
            "data_quality_ok": False,
            "blocked_ambiguous_count": 1,
            "failure_trap": True,
        },
        "session_lifecycle": {"terminal_failure_states": ["BLOCKED"], "failed_safe": True},
        "risk_gates": {"gates_intact": False},
        "provider_health": {
            "transport_status": "RATE_LIMITED",
            "capacity_blocked": True,
            "success_count": 1,
            "pending_count": 9,
        },
        "reflection_queue": {"stale_queue": True, "pending_count": 9, "success_count": 1},
        "lesson_gate": {"unauthorized_lesson_count": 2},
        "ledger_snapshot_checkpoint": {"ambiguous_state": True, "ambiguous_count": 1, "data_quality_ok": False},
        "microstructure_health": {"integrity_ok": False},
        "storage_budget": {"floor_ok": False, "mode": "STORAGE_BUDGET_BLOCKED"},
        "kill_switch_readiness": {"reachable": False},
        "qualification_block_state": {"all_stages_blocked": False},
    }
    alerts = collect_alerts(domain_health)
    active = {a["alert_class"] for a in alerts if a["active"]}
    assert set(ALERT_CLASSES).issubset(active)


def test_owned_path_secret_scan() -> None:
    root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in {".py", ".json"}]
            if target.is_dir()
            else [target]
        )
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(path))
                    break
    assert hits == [], f"secret-like patterns in owned paths: {hits}"


def test_forbidden_key_set_covers_accounts() -> None:
    for k in ("api_key", "api_secret", "wallet_address", "account_balance", "strategy_parameters"):
        assert k in FORBIDDEN_OBSERVABILITY_KEYS

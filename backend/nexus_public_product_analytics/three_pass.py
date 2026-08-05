"""Three-pass runner for PUB2-I (impl → adversarial → break attempts)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.nexus_public_product_analytics.constants import LANE, PACKAGE, SCHEMA_VERSION
from backend.nexus_public_product_analytics.hard_bans import (
    HardBanViolation,
    refuse_fabrication,
    refuse_status_json_emission,
    run_hard_ban_pass,
)
from backend.nexus_public_product_analytics.metrics import (
    aggregate_metrics,
    assert_no_fabricated_snapshot,
)
from backend.nexus_public_product_analytics.schema import (
    build_metric_schema,
    validate_schema_document,
)
from backend.nexus_public_product_analytics.store import LocalAnalyticsStore
from backend.nexus_public_product_analytics.tracker import ProductAnalyticsTracker


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def pass1_implementation(root: Path) -> dict[str, Any]:
    """Pass 1: schema validity, empty honest snapshot, consent gate smoke."""
    schema = build_metric_schema()
    schema_path = root / "docs" / "product_analytics" / "NEXUS_PUBLIC_V2_PRODUCT_ANALYTICS_METRIC_SCHEMA_V1.json"
    errors = validate_schema_document(schema)
    store = LocalAnalyticsStore()
    tracker = ProductAnalyticsTracker(store=store)
    # Without consent → drop
    dropped = tracker.track("watchlist_activation", raw_subject_id="member_a", props={"symbol_count_bucket": "1"})
    assert dropped is None
    tracker.grant_consent("member_a")
    recorded = tracker.track(
        "watchlist_activation",
        raw_subject_id="member_a",
        props={"symbol_count_bucket": "1", "source_surface": "mobile"},
    )
    assert recorded is not None
    snap = aggregate_metrics(store)
    assert_no_fabricated_snapshot(snap)
    bans = run_hard_ban_pass(root)
    body = {
        "pass": 1,
        "name": "implementation",
        "ok": bans["ok"] and not errors and snap["north_star"]["value"] is None,
        "schema_errors": errors,
        "schema_version": SCHEMA_VERSION,
        "schema_path_exists": schema_path.exists(),
        "recorded_events": tracker.recorded,
        "dropped_without_consent": tracker.dropped_without_consent,
        "snapshot_event_total": snap["event_total"],
        "north_star_status": snap["north_star"]["status"],
        "hard_ban": bans,
    }
    body["digest"] = _digest({k: v for k, v in body.items() if k != "digest"})
    return body


def pass2_adversarial(root: Path) -> dict[str, Any]:
    """Pass 2: attempt fabrication, PII props, production DB, status.json."""
    findings: list[dict[str, str]] = []
    tracker = ProductAnalyticsTracker()
    tracker.grant_consent("member_b")

    try:
        tracker.track(
            "session_active",
            raw_subject_id="fake_wau_user",
            props={"surface": "web"},
        )
        findings.append({"attack": "fabricated_subject", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "fabricated_subject", "result": "FIXED"})

    try:
        tracker.track(
            "upgrade_intent",
            raw_subject_id="member_b",
            props={"intent_kind": "stated", "email": "leak@example.com"},
        )
        findings.append({"attack": "pii_prop", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "pii_prop", "result": "FIXED"})

    try:
        LocalAnalyticsStore(production_customer_database=True)
        findings.append({"attack": "production_db", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "production_db", "result": "FIXED"})

    try:
        refuse_status_json_emission(root / "artifacts" / "pub2_i_lane_status.json")
        findings.append({"attack": "status_json", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "status_json", "result": "FIXED"})

    try:
        refuse_fabrication("dummy_wau=42")
        findings.append({"attack": "fabricate_wau", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "fabricate_wau", "result": "FIXED"})

    bans = run_hard_ban_pass(root)
    survivors = [f for f in findings if f["result"] == "SURVIVOR"]
    body = {
        "pass": 2,
        "name": "adversarial",
        "ok": bans["ok"] and len(survivors) == 0,
        "findings": findings,
        "survivor_count": len(survivors),
        "hard_ban": bans,
    }
    body["digest"] = _digest({k: v for k, v in body.items() if k != "digest"})
    return body


def pass3_break_attempts(root: Path) -> dict[str, Any]:
    """Pass 3: independent break attempts on aggregation honesty and unknown events."""
    findings: list[dict[str, str]] = []
    store = LocalAnalyticsStore()
    empty = aggregate_metrics(store)
    try:
        assert_no_fabricated_snapshot(empty)
        findings.append({"attack": "empty_snapshot_honest", "result": "FIXED"})
    except HardBanViolation:
        findings.append({"attack": "empty_snapshot_honest", "result": "SURVIVOR"})

    # Inject a forged snapshot and ensure guard catches it.
    forged = {
        "north_star": {
            "status": "NO_OBSERVATIONS",
            "value": 0.87,
            "count": 0,
        },
        "metrics": {
            "weekly_active_use": {
                "status": "NO_OBSERVATIONS",
                "value": 1200,
                "count": 0,
            }
        },
    }
    try:
        assert_no_fabricated_snapshot(forged)
        findings.append({"attack": "forged_snapshot", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "forged_snapshot", "result": "FIXED"})

    tracker = ProductAnalyticsTracker(store=store)
    tracker.grant_consent("member_c")
    try:
        tracker.track("private_execution_fill", raw_subject_id="member_c", props={})
        findings.append({"attack": "unknown_event", "result": "SURVIVOR"})
    except HardBanViolation:
        findings.append({"attack": "unknown_event", "result": "FIXED"})

    # Schema must list all required metric ids.
    schema_errors = validate_schema_document(build_metric_schema())
    if schema_errors:
        findings.append({"attack": "schema_complete", "result": "SURVIVOR"})
    else:
        findings.append({"attack": "schema_complete", "result": "FIXED"})

    bans = run_hard_ban_pass(root)
    survivors = [f for f in findings if f["result"] == "SURVIVOR"]
    body = {
        "pass": 3,
        "name": "break_attempts",
        "ok": bans["ok"] and len(survivors) == 0,
        "findings": findings,
        "survivor_count": len(survivors),
        "empty_north_star": empty["north_star"],
        "hard_ban": bans,
    }
    body["digest"] = _digest({k: v for k, v in body.items() if k != "digest"})
    return body


def run_three_passes(root: Path) -> dict[str, Any]:
    p1 = pass1_implementation(root)
    p2 = pass2_adversarial(root)
    p3 = pass3_break_attempts(root)
    ok = bool(p1["ok"] and p2["ok"] and p3["ok"])
    return {
        "lane": LANE,
        "package": PACKAGE,
        "ok": ok,
        "pass1": p1,
        "pass2": p2,
        "pass3": p3,
        "status_json_emitted": False,
        "fabricated_metrics": False,
    }


def write_three_pass_proof(root: Path, proof_dir: Path | None = None) -> Path:
    """Write three-pass proof JSON (never *_status.json)."""
    out_dir = proof_dir or (root / "artifacts" / "product_analytics")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pub2_i_three_pass_proof.json"
    refuse_status_json_emission(out_path)
    result = run_three_passes(root)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path

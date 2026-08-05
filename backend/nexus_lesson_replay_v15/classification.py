"""Process classification: wins/losses never auto-map to GOOD/BAD process."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_replay_v15.constants import (
    INFORMATIVE_CLASSES,
    PROCESS_CLASSES,
    SCHEMA_CLASSIFICATION,
)
from backend.nexus_strategy_engine.evidence_v2 import deterministic_process_baseline


def migrate_classification(raw: str | None) -> str:
    s = str(raw or "").strip().upper()
    if s in {"UNDETERMINED_PROCESS", "PROCESS_UNDETERMINED", "INCONCLUSIVE"}:
        return "UNDETERMINED"
    if s in PROCESS_CLASSES:
        return s
    return "UNDETERMINED"


def classify_from_evidence(packet: dict[str, Any]) -> dict[str, Any]:
    """Classify using deterministic process status + PnL.

    Hard rule: a loss is NOT automatic BAD_PROCESS; a win is NOT automatic GOOD_PROCESS.
    PnL only selects WIN vs LOSS after process compliance is known.
    """
    base = deterministic_process_baseline(packet)
    det = str(base.get("deterministic_process_status") or "")
    pnl_raw = packet.get("net_pnl")
    pnl = float(pnl_raw) if isinstance(pnl_raw, (int, float)) else 0.0
    win = pnl > 0.0

    if det == "PROCESS_EVIDENCE_INSUFFICIENT":
        cls = "UNDETERMINED"
    elif det == "PROCESS_COMPLIANT":
        cls = "GOOD_PROCESS_WIN" if win else "GOOD_PROCESS_LOSS"
    elif det == "PROCESS_NONCOMPLIANT":
        cls = "BAD_PROCESS_WIN" if win else "BAD_PROCESS_LOSS"
    else:
        cls = "UNDETERMINED"

    return {
        "schema": SCHEMA_CLASSIFICATION,
        "process_classification": cls,
        "deterministic_process_status": det,
        "noncompliant_reasons": list(base.get("noncompliant_reasons") or []),
        "pnl": pnl,
        "pnl_does_not_decide_process": True,
        "loss_is_not_automatic_bad_process": True,
        "win_is_not_automatic_good_process": True,
        "informative": cls in INFORMATIVE_CLASSES,
        "is_bad_process": cls.startswith("BAD_PROCESS"),
        "is_good_process": cls.startswith("GOOD_PROCESS"),
        "is_undetermined": cls == "UNDETERMINED",
        "is_loss": not win,
        "is_win": win,
        "trade_id": packet.get("trade_id"),
        "source_kind": packet.get("source_kind"),
        "fixture_label": packet.get("fixture_label"),
    }


def assert_loss_not_auto_bad(packet: dict[str, Any]) -> bool:
    """Return True when a compliant loss is NOT labeled BAD_PROCESS_*."""
    result = classify_from_evidence(packet)
    if result["deterministic_process_status"] == "PROCESS_COMPLIANT" and result["is_loss"]:
        return result["process_classification"] == "GOOD_PROCESS_LOSS"
    return True


def error_signature(packet: dict[str, Any]) -> str:
    base = deterministic_process_baseline(packet)
    reasons = list(base.get("noncompliant_reasons") or [])
    if not reasons:
        if packet.get("cost_gate_status") in {"FAIL", "BLOCK", "FAILED"}:
            reasons.append("cost_gate_failed")
        if packet.get("data_quality_status") == "STALE":
            reasons.append("stale_data")
        if packet.get("stop_price") in (None, "", "MISSING"):
            reasons.append("missing_stop")
    return "ERR|" + "|".join(sorted(reasons) or ["process_noncompliant"])

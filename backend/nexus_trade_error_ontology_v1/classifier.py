"""Deterministic trade-error classifier (authoritative; AI cannot override)."""
from __future__ import annotations

from typing import Any

from backend.nexus_trade_error_ontology_v1.constants import (
    LEGACY_CLASS_MAP,
    ONTOLOGY_VERSION,
    PROCESS_CLASSES,
    SCHEMA,
    SCHEMA_CLASSIFICATION,
)
from backend.nexus_trade_error_ontology_v1.gene_bank import build_gene_bank, match_genes

CLASSIFIER_VERSION = "v1.0.0"

_SEVERITY_RANK = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_AVOID_RANK = {
    "UNKNOWN": 0,
    "UNAVOIDABLE": 1,
    "PARTIALLY_AVOIDABLE": 2,
    "AVOIDABLE": 3,
}

_CRITICAL_EVIDENCE_KEYS = (
    "entry_price",
    "stop_price",
    "target_price",
    "cost_gate_status",
    "data_quality_status",
)

_UNKNOWNISH = {None, "", "UNKNOWN", "MISSING", "UNAVAILABLE"}


def migrate_classification(raw: str | None) -> str:
    s = str(raw or "").strip().upper()
    if s in LEGACY_CLASS_MAP:
        return LEGACY_CLASS_MAP[s]
    if s in PROCESS_CLASSES:
        return s
    return "INSUFFICIENT_EVIDENCE"


def _pnl(packet: dict[str, Any]) -> float:
    raw = packet.get("net_pnl")
    if raw is None:
        raw = packet.get("pnl")
    if raw is None:
        raw = packet.get("pnl_usd")
    return float(raw) if isinstance(raw, (int, float)) else 0.0


def _collect_signals(packet: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    hard = list(packet.get("hard_block_reasons") or [])
    if hard:
        signals.append("hard_gate_present")
        for h in hard:
            hs = str(h).strip().lower()
            if hs:
                signals.append(hs)

    cost = str(packet.get("cost_gate_status") or "").upper()
    if cost in {"FAIL", "BLOCK", "FAILED"}:
        signals.append("cost_gate_failed")

    risk = str(packet.get("risk_gate_status") or "").upper()
    if risk in {"FAIL", "BLOCK", "FAILED", "EXCEEDED"}:
        signals.append("risk_exceeded")

    data_q = str(packet.get("data_quality_status") or "").upper()
    if data_q in {"STALE", "INVALID"}:
        signals.append("stale_or_invalid_data")
        signals.append(f"data_quality:{data_q}")

    stop = packet.get("stop_price")
    # Explicit invalid stop → noncompliance. None/UNKNOWN → insufficiency via critical keys.
    if stop in ("MISSING", "UNAVAILABLE", 0, 0.0):
        signals.append("invalid_or_absent_stop")

    if packet.get("position_size_valid") is False:
        signals.append("invalid_position_size")
    if packet.get("liquidation_distance_valid") is False:
        signals.append("liquidation_distance_invalid")
        signals.append("liquidity_stress")

    if int(packet.get("rule_violation_count") or 0) > 0:
        signals.append("rule_violation")
    if int(packet.get("prohibited_action_count") or 0) > 0:
        signals.append("prohibited_action")

    entry = str(packet.get("entry_rule_compliance") or "").upper()
    if entry in {"FAIL", "VIOLATION", "NONCOMPLIANT"}:
        signals.append("rule_violation")

    exit_c = str(packet.get("exit_rule_compliance") or "").upper()
    if exit_c in {"FAIL", "VIOLATION", "NONCOMPLIANT"}:
        signals.append("exit_noncompliant")
        signals.append("exit_rule:FAIL")

    if packet.get("regime_mismatch") is True:
        signals.append("regime_mismatch")
    rc = packet.get("regime_confidence")
    if isinstance(rc, (int, float)) and float(rc) < 0.35:
        signals.append("regime_confidence_low")

    if packet.get("portfolio_exposure_breach") is True:
        signals.append("portfolio_exposure_breach")
    if packet.get("correlated_overexposure") is True:
        signals.append("correlated_overexposure")

    if packet.get("infra_fault") is True or packet.get("pipeline_timeout") is True:
        signals.append("infra_fault")
        if packet.get("pipeline_timeout") is True:
            signals.append("pipeline_timeout")

    if packet.get("ai_ungrounded") is True:
        signals.append("ai_ungrounded")
    missing = packet.get("missing_evidence")
    if isinstance(missing, list) and missing and packet.get("ai_claim_present") is True:
        signals.append("missing_evidence_for_ai_claim")

    # External shock signals
    if packet.get("external_shock_flag") is True:
        signals.append("external_shock")
    shock_type = str(packet.get("external_shock_type") or "").strip().lower()
    if shock_type:
        signals.append(shock_type)
        signals.append("external_shock")

    # Explicit noncompliant_reasons passthrough
    for r in packet.get("noncompliant_reasons") or []:
        rs = str(r).strip().lower()
        if rs:
            signals.append(rs)

    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _critical_evidence_known(packet: dict[str, Any]) -> bool:
    for k in _CRITICAL_EVIDENCE_KEYS:
        if packet.get(k) in _UNKNOWNISH:
            return False
    return True


def _process_status(signals: list[str], packet: dict[str, Any]) -> str:
    """Return PROCESS_COMPLIANT | PROCESS_NONCOMPLIANT | PROCESS_EVIDENCE_INSUFFICIENT | UNAVOIDABLE_SHOCK."""
    shock_signals = {
        "external_shock",
        "flash_crash",
        "exchange_halt",
        "oracle_dislocation",
        "unavoidable_external_shock",
    }
    process_bad = {
        "hard_gate_present",
        "cost_gate_failed",
        "risk_exceeded",
        "stale_or_invalid_data",
        "invalid_or_absent_stop",
        "invalid_position_size",
        "liquidation_distance_invalid",
        "rule_violation",
        "prohibited_action",
        "exit_noncompliant",
        "regime_mismatch",
        "portfolio_exposure_breach",
        "correlated_overexposure",
        "ai_ungrounded",
        "liquidity_stress",
    }
    sigset = set(signals)
    has_process_fault = bool(sigset & process_bad)
    has_shock = bool(sigset & shock_signals) or packet.get("external_shock_flag") is True

    if has_shock and not has_process_fault:
        return "UNAVOIDABLE_SHOCK"
    if has_process_fault:
        return "PROCESS_NONCOMPLIANT"
    if not _critical_evidence_known(packet):
        return "PROCESS_EVIDENCE_INSUFFICIENT"
    if "infra_fault" in sigset or "pipeline_timeout" in sigset:
        # Infra alone without other process faults → insufficient for process adjudication.
        return "PROCESS_EVIDENCE_INSUFFICIENT"
    return "PROCESS_COMPLIANT"


def _build_evidence_refs(packet: dict[str, Any], genes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys: list[str] = []
    for g in genes:
        for k in g.get("evidence_ref_keys") or []:
            if k not in keys:
                keys.append(k)
    # Always include core outcome/process keys when present.
    for k in (
        "trade_id",
        "net_pnl",
        "cost_gate_status",
        "risk_gate_status",
        "data_quality_status",
        "stop_price",
        "entry_price",
        "external_shock_flag",
        "external_shock_type",
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "missing_evidence",
    ):
        if k not in keys and k in packet:
            keys.append(k)
    refs: list[dict[str, Any]] = []
    for k in keys:
        if k in packet:
            refs.append({"ref_key": k, "ref_value": packet.get(k), "source": "trade_packet"})
    return refs


def _aggregate_severity(genes: list[dict[str, Any]], status: str) -> str:
    if status == "PROCESS_COMPLIANT":
        return "NONE"
    if status == "PROCESS_EVIDENCE_INSUFFICIENT":
        return "LOW"
    if not genes:
        if status == "UNAVOIDABLE_SHOCK":
            return "HIGH"
        return "MEDIUM"
    best = max(genes, key=lambda g: _SEVERITY_RANK.get(str(g.get("severity")), 0))
    return str(best["severity"])


def _aggregate_avoidability(genes: list[dict[str, Any]], status: str) -> str:
    if status == "UNAVOIDABLE_SHOCK":
        return "UNAVOIDABLE"
    if status == "PROCESS_EVIDENCE_INSUFFICIENT":
        return "UNKNOWN"
    if status == "PROCESS_COMPLIANT":
        return "AVOIDABLE"  # good process — residual risk was accepted under plan
    if not genes:
        return "AVOIDABLE"
    # Most avoidable signal wins for learning priority (AVOIDABLE > PARTIAL > UNAVOIDABLE).
    best = max(genes, key=lambda g: _AVOID_RANK.get(str(g.get("avoidability")), 0))
    return str(best["avoidability"])


def _causal_confidence(genes: list[dict[str, Any]], status: str, signals: list[str]) -> float:
    if status == "PROCESS_EVIDENCE_INSUFFICIENT":
        return 0.25
    if status == "PROCESS_COMPLIANT":
        return 0.85 if _critical_evidence_known({"entry_price": 1, "stop_price": 1, "target_price": 1, "cost_gate_status": "PASS", "data_quality_status": "OK"}) else 0.70
    if not genes:
        return 0.55 if signals else 0.35
    floors = [float(g["causal_confidence_floor"]) for g in genes]
    # Confidence rises slightly with corroborating gene count, capped at 0.99.
    base = max(floors)
    boost = min(0.08 * (len(genes) - 1), 0.12)
    return round(min(0.99, base + boost), 4)


def _recurrence_signature(
    *,
    cls: str,
    dimensions: list[str],
    genes: list[dict[str, Any]],
    signals: list[str],
) -> str:
    gene_part = ",".join(sorted(g["gene_id"] for g in genes)) or "NONE"
    dim_part = ",".join(dimensions) or "NONE"
    sig_part = ",".join(sorted(signals)[:12]) or "NONE"
    return f"RS|{cls}|DIM={dim_part}|GENES={gene_part}|SIG={sig_part}"


def classify_trade_error(packet: dict[str, Any]) -> dict[str, Any]:
    """Classify a completed trade into the V16-A error ontology.

    Hard rules:
    - PnL never decides process quality (only WIN vs LOSS after process known).
    - Profitable BAD_PROCESS_WIN is first-class.
    - UNAVOIDABLE_SHOCK when external shock without process fault.
    - INSUFFICIENT_EVIDENCE when critical evidence missing.
    """
    bank = build_gene_bank()
    signals = _collect_signals(packet)
    status = _process_status(signals, packet)
    pnl = _pnl(packet)
    win = pnl > 0.0
    loss = pnl < 0.0

    if status == "UNAVOIDABLE_SHOCK":
        cls = "UNAVOIDABLE_SHOCK"
    elif status == "PROCESS_EVIDENCE_INSUFFICIENT":
        cls = "INSUFFICIENT_EVIDENCE"
    elif status == "PROCESS_COMPLIANT":
        cls = "GOOD_PROCESS_WIN" if win else "GOOD_PROCESS_LOSS"
    elif status == "PROCESS_NONCOMPLIANT":
        cls = "BAD_PROCESS_WIN" if win else "BAD_PROCESS_LOSS"
    else:
        cls = "INSUFFICIENT_EVIDENCE"

    assert cls in PROCESS_CLASSES

    genes = match_genes(signals, bank)
    if cls == "UNAVOIDABLE_SHOCK":
        genes = [g for g in genes if g["dimension"] == "EXTERNAL_SHOCK"] or match_genes(
            ["external_shock", "unavoidable_external_shock"], bank
        )
    if cls == "INSUFFICIENT_EVIDENCE" and not genes:
        genes = match_genes(["evidence_insufficient"], bank)

    dimensions = sorted({g["dimension"] for g in genes})
    if cls == "UNAVOIDABLE_SHOCK" and "EXTERNAL_SHOCK" not in dimensions:
        dimensions = ["EXTERNAL_SHOCK"] + dimensions
    if cls.startswith("GOOD_PROCESS") and not dimensions:
        dimensions = []

    severity = _aggregate_severity(genes, status)
    avoidability = _aggregate_avoidability(genes, status)
    causal = _causal_confidence(genes, status, signals)
    # Fix causal for compliant: use actual packet critical keys
    if status == "PROCESS_COMPLIANT":
        causal = 0.85 if _critical_evidence_known(packet) else 0.70

    evidence_refs = _build_evidence_refs(packet, genes)
    recurrence = _recurrence_signature(
        cls=cls, dimensions=dimensions, genes=genes, signals=signals
    )

    noncompliant = [s for s in signals if s not in {"external_shock"}]

    return {
        "schema": SCHEMA,
        "record_type": SCHEMA_CLASSIFICATION,
        "ontology_version": ONTOLOGY_VERSION,
        "process_classification": cls,
        "deterministic_class": cls,
        "ai_proposed_class": None,
        "dimensions": dimensions,
        "matched_gene_ids": [g["gene_id"] for g in genes],
        "evidence_refs": evidence_refs,
        "severity": severity,
        "avoidability": avoidability,
        "recurrence_signature": recurrence,
        "causal_confidence": causal,
        "classifier_authority": {
            "deterministic_is_final": True,
            "ai_can_override": False,
            "fallback": "deterministic_classifier",
            "ai_disagreement": False,
        },
        "versioning": {
            "ontology_version": ONTOLOGY_VERSION,
            "gene_bank_checksum": bank["checksum_sha256"],
            "classifier_version": CLASSIFIER_VERSION,
        },
        "pnl": pnl,
        "is_win": win,
        "is_loss": loss,
        "is_bad_process": cls.startswith("BAD_PROCESS"),
        "is_good_process": cls.startswith("GOOD_PROCESS"),
        "is_unavoidable_shock": cls == "UNAVOIDABLE_SHOCK",
        "is_insufficient_evidence": cls == "INSUFFICIENT_EVIDENCE",
        "supports_profitable_bad_process_win": True,
        "pnl_does_not_decide_process": True,
        "loss_is_not_automatic_bad_process": True,
        "win_is_not_automatic_good_process": True,
        "deterministic_process_status": status,
        "noncompliant_reasons": noncompliant,
        "signals": signals,
        "trade_id": packet.get("trade_id"),
        "source_kind": packet.get("source_kind"),
    }


def assert_loss_not_auto_bad(packet: dict[str, Any]) -> bool:
    result = classify_trade_error(packet)
    if result["deterministic_process_status"] == "PROCESS_COMPLIANT" and result["is_loss"]:
        return result["process_classification"] == "GOOD_PROCESS_LOSS"
    return True


def assert_win_not_auto_good(packet: dict[str, Any]) -> bool:
    result = classify_trade_error(packet)
    if result["deterministic_process_status"] == "PROCESS_NONCOMPLIANT" and result["is_win"]:
        return result["process_classification"] == "BAD_PROCESS_WIN"
    return True

"""Machine-readable trade error gene bank (V16-A)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from backend.nexus_trade_error_ontology_v1.constants import (
    AVOIDABILITY_LEVELS,
    ERROR_DIMENSIONS,
    GENE_BANK_REL,
    ONTOLOGY_VERSION,
    PROCESS_CLASSES,
    SCHEMA,
    SCHEMA_GENE,
    SEVERITY_LEVELS,
)

# Gene bank: each gene is a typed, versioned error pattern — not AI prose.
_GENES: tuple[dict[str, Any], ...] = (
    {
        "gene_id": "TEG.DATA.STALE_FEED",
        "dimension": "DATA",
        "label": "stale_or_invalid_market_data",
        "severity": "HIGH",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["data_quality_status", "data_freshness", "supporting_evidence_ids"],
        "trigger_signals": ["stale_or_invalid_data", "data_quality:STALE", "data_quality:INVALID"],
        "recurrence_signature_template": "DIM=DATA|SIG=stale_or_invalid_data",
        "causal_confidence_floor": 0.75,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.REGIME.MISMATCH",
        "dimension": "REGIME",
        "label": "regime_mismatch_vs_strategy",
        "severity": "MEDIUM",
        "avoidability": "PARTIALLY_AVOIDABLE",
        "evidence_ref_keys": ["market_regime", "regime_confidence", "strategy_family"],
        "trigger_signals": ["regime_mismatch", "regime_confidence_low"],
        "recurrence_signature_template": "DIM=REGIME|SIG=regime_mismatch",
        "causal_confidence_floor": 0.55,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.STRATEGY.RULE_VIOLATION",
        "dimension": "STRATEGY",
        "label": "strategy_rule_violation",
        "severity": "HIGH",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["rule_violation_count", "hard_block_reasons"],
        "trigger_signals": ["rule_violation", "hard_gate_present"],
        "recurrence_signature_template": "DIM=STRATEGY|SIG=rule_violation",
        "causal_confidence_floor": 0.80,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.ENTRY.MISSING_STOP",
        "dimension": "ENTRY",
        "label": "invalid_or_absent_stop_at_entry",
        "severity": "CRITICAL",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["stop_price", "entry_price", "entry_rule_compliance"],
        "trigger_signals": ["invalid_or_absent_stop"],
        "recurrence_signature_template": "DIM=ENTRY|SIG=invalid_or_absent_stop",
        "causal_confidence_floor": 0.90,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.EXIT.NONCOMPLIANT",
        "dimension": "EXIT",
        "label": "exit_rule_noncompliance",
        "severity": "HIGH",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["exit_reason", "exit_rule_compliance", "actual_exit_price"],
        "trigger_signals": ["exit_noncompliant", "exit_rule:FAIL"],
        "recurrence_signature_template": "DIM=EXIT|SIG=exit_noncompliant",
        "causal_confidence_floor": 0.70,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.EXECUTION.PROHIBITED",
        "dimension": "EXECUTION",
        "label": "prohibited_execution_action",
        "severity": "CRITICAL",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["prohibited_action_count", "hard_block_reasons"],
        "trigger_signals": ["prohibited_action"],
        "recurrence_signature_template": "DIM=EXECUTION|SIG=prohibited_action",
        "causal_confidence_floor": 0.95,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.LIQUIDITY.STRESS",
        "dimension": "LIQUIDITY",
        "label": "liquidity_stress_at_fill",
        "severity": "MEDIUM",
        "avoidability": "PARTIALLY_AVOIDABLE",
        "evidence_ref_keys": ["spread_bps", "estimated_slippage_bps", "liquidation_distance_valid"],
        "trigger_signals": ["liquidity_stress", "liquidation_distance_invalid"],
        "recurrence_signature_template": "DIM=LIQUIDITY|SIG=liquidity_stress",
        "causal_confidence_floor": 0.60,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.COST.GATE_FAIL",
        "dimension": "COST",
        "label": "cost_gate_failed",
        "severity": "HIGH",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["cost_gate_status", "expected_total_cost", "fees", "slippage"],
        "trigger_signals": ["cost_gate_failed"],
        "recurrence_signature_template": "DIM=COST|SIG=cost_gate_failed",
        "causal_confidence_floor": 0.85,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.AI.UNGROUNDED",
        "dimension": "AI_REASONING",
        "label": "ai_reasoning_without_evidence",
        "severity": "MEDIUM",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["supporting_evidence_ids", "contradicting_evidence_ids", "missing_evidence"],
        "trigger_signals": ["ai_ungrounded", "missing_evidence_for_ai_claim"],
        "recurrence_signature_template": "DIM=AI_REASONING|SIG=ai_ungrounded",
        "causal_confidence_floor": 0.50,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.RISK.GATE_EXCEEDED",
        "dimension": "RISK",
        "label": "risk_gate_exceeded",
        "severity": "CRITICAL",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["risk_gate_status", "position_size_valid", "leverage_valid"],
        "trigger_signals": ["risk_exceeded", "invalid_position_size"],
        "recurrence_signature_template": "DIM=RISK|SIG=risk_exceeded",
        "causal_confidence_floor": 0.90,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.PORTFOLIO.EXPOSURE",
        "dimension": "PORTFOLIO",
        "label": "portfolio_exposure_breach",
        "severity": "HIGH",
        "avoidability": "AVOIDABLE",
        "evidence_ref_keys": ["hard_block_reasons", "position_size_valid"],
        "trigger_signals": ["portfolio_exposure_breach", "correlated_overexposure"],
        "recurrence_signature_template": "DIM=PORTFOLIO|SIG=portfolio_exposure_breach",
        "causal_confidence_floor": 0.70,
        "maps_to_process_hint": "BAD_PROCESS",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.INFRA.PIPELINE_FAULT",
        "dimension": "INFRASTRUCTURE",
        "label": "infrastructure_pipeline_fault",
        "severity": "HIGH",
        "avoidability": "PARTIALLY_AVOIDABLE",
        "evidence_ref_keys": ["data_quality_status", "hard_block_reasons"],
        "trigger_signals": ["infra_fault", "pipeline_timeout"],
        "recurrence_signature_template": "DIM=INFRASTRUCTURE|SIG=infra_fault",
        "causal_confidence_floor": 0.65,
        "maps_to_process_hint": "INSUFFICIENT_EVIDENCE",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.EXTERNAL.UNAVOIDABLE_SHOCK",
        "dimension": "EXTERNAL_SHOCK",
        "label": "unavoidable_external_shock",
        "severity": "HIGH",
        "avoidability": "UNAVOIDABLE",
        "evidence_ref_keys": ["external_shock_flag", "external_shock_type", "supporting_evidence_ids"],
        "trigger_signals": ["external_shock", "flash_crash", "exchange_halt", "oracle_dislocation"],
        "recurrence_signature_template": "DIM=EXTERNAL_SHOCK|SIG=unavoidable_external_shock",
        "causal_confidence_floor": 0.70,
        "maps_to_process_hint": "UNAVOIDABLE_SHOCK",
        "version": "1.0.0",
    },
    {
        "gene_id": "TEG.META.INSUFFICIENT_EVIDENCE",
        "dimension": "DATA",
        "label": "insufficient_process_evidence",
        "severity": "LOW",
        "avoidability": "UNKNOWN",
        "evidence_ref_keys": ["missing_evidence", "entry_price", "stop_price", "cost_gate_status"],
        "trigger_signals": ["evidence_insufficient"],
        "recurrence_signature_template": "DIM=DATA|SIG=evidence_insufficient",
        "causal_confidence_floor": 0.30,
        "maps_to_process_hint": "INSUFFICIENT_EVIDENCE",
        "version": "1.0.0",
    },
)


def _gene_checksum(genes: list[dict[str, Any]]) -> str:
    payload = json.dumps(genes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_gene_bank() -> dict[str, Any]:
    genes = [dict(g) for g in _GENES]
    for g in genes:
        g["schema"] = SCHEMA_GENE
        assert g["dimension"] in ERROR_DIMENSIONS
        assert g["severity"] in SEVERITY_LEVELS
        assert g["avoidability"] in AVOIDABILITY_LEVELS
        assert 0.0 <= float(g["causal_confidence_floor"]) <= 1.0
    return {
        "schema": SCHEMA,
        "ontology_version": ONTOLOGY_VERSION,
        "process_classes": list(PROCESS_CLASSES),
        "error_dimensions": list(ERROR_DIMENSIONS),
        "severity_levels": list(SEVERITY_LEVELS),
        "avoidability_levels": list(AVOIDABILITY_LEVELS),
        "gene_count": len(genes),
        "genes": genes,
        "gene_ids": [g["gene_id"] for g in genes],
        "checksum_sha256": _gene_checksum(genes),
        "policy": {
            "ai_proposes_only": True,
            "ai_cannot_override_deterministic": True,
            "pnl_does_not_decide_process": True,
            "supports_profitable_bad_process_win": True,
            "exchange_write": False,
            "mainnet": False,
            "real_money": False,
        },
    }


def load_gene_bank(root: Path | None = None) -> dict[str, Any]:
    """Load immutable gene bank artifact if present; else build in-memory."""
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / GENE_BANK_REL
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return build_gene_bank()


def genes_by_dimension(bank: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    bank = bank or build_gene_bank()
    out: dict[str, list[dict[str, Any]]] = {d: [] for d in ERROR_DIMENSIONS}
    for g in bank["genes"]:
        out.setdefault(g["dimension"], []).append(g)
    return out


def match_genes(signals: list[str], bank: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Match trigger signals to genes (deterministic, order-stable)."""
    bank = bank or build_gene_bank()
    sigset = {str(s).strip().lower() for s in signals if s}
    matched: list[dict[str, Any]] = []
    for g in bank["genes"]:
        triggers = {str(t).strip().lower() for t in g.get("trigger_signals") or []}
        if sigset & triggers:
            matched.append(g)
    return matched


def write_gene_bank_artifact(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / GENE_BANK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    bank = build_gene_bank()
    path.write_text(json.dumps(bank, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

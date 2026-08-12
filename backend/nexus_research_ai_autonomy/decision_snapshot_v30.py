"""Point-in-time decision snapshots — no hindsight values."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


SNAPSHOT_SCHEMA = "v30_decision_snapshot_v1"


def snapshot_dir(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "decision_snapshots"


def build_decision_snapshot(
    *,
    cycle_id: str,
    enrichment: dict[str, Any],
    regime_info: dict[str, Any],
    side: str,
    direction_scores: dict[str, float],
    entry_quality: dict[str, Any],
    edge: dict[str, Any],
    supporting_evidence: list[str],
    contradicting_evidence: list[str],
    gate_results: dict[str, Any],
    final_action: str,
    final_reason: str,
    rank: int | None = None,
    rank_percentile: float | None = None,
    risk_flags: list[str] | None = None,
) -> dict[str, Any]:
    ts = int(enrichment.get("timestamp_ms") or time.time() * 1000)
    decision_id = f"dec_{uuid.uuid4().hex[:16]}"
    oi_rel = None
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import classify_oi_relationship

    oi_rel = classify_oi_relationship(enrichment, side)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "decision_id": decision_id,
        "cycle_id": cycle_id,
        "timestamp_ms": ts,
        "symbol": enrichment.get("symbol"),
        "side": side,
        "price": enrichment.get("price"),
        "turnover": enrichment.get("turnover"),
        "volume": enrichment.get("volume"),
        "spread_bps": enrichment.get("spread_bps"),
        "depth_near_mid": enrichment.get("depth_near_mid"),
        "estimated_slippage": enrichment.get("estimated_slippage"),
        "activity_score": enrichment.get("activity_score"),
        "activity_source": enrichment.get("activity_source"),
        "activity_freshness_ms": enrichment.get("activity_freshness_ms"),
        "activity_fallback": enrichment.get("activity_fallback"),
        "momentum_1m": enrichment.get("momentum_1m"),
        "momentum_5m": enrichment.get("momentum_5m"),
        "momentum_15m": enrichment.get("momentum_15m"),
        "volatility": enrichment.get("volatility"),
        "open_interest": enrichment.get("open_interest"),
        "oi_delta_short": enrichment.get("oi_delta_short"),
        "oi_delta_medium": enrichment.get("oi_delta_medium"),
        "oi_relationship": oi_rel,
        "funding_rate": enrichment.get("funding_rate"),
        "funding_delta": enrichment.get("funding_delta"),
        "cvd": enrichment.get("cvd"),
        "cvd_source": enrichment.get("cvd_source"),
        "liquidation_long_intensity": enrichment.get("liquidation_long_intensity"),
        "liquidation_short_intensity": enrichment.get("liquidation_short_intensity"),
        "liquidation_imbalance": enrichment.get("liquidation_imbalance"),
        "liquidations_source": enrichment.get("liquidations_source"),
        "market_structure": regime_info.get("market_structure"),
        "regime": regime_info.get("regime"),
        "regime_confidence": regime_info.get("regime_confidence"),
        "long_score": direction_scores.get("LONG"),
        "short_score": direction_scores.get("SHORT"),
        "direction_score_delta": direction_scores.get("direction_score_delta"),
        "entry_quality_score": entry_quality.get("entry_quality_score"),
        "entry_quality_components": entry_quality.get("components"),
        "expected_gross_edge": edge.get("expected_gross_edge"),
        "estimated_round_trip_fee": edge.get("estimated_round_trip_fee"),
        "estimated_slippage_cost": edge.get("estimated_slippage_cost"),
        "estimated_funding_cost": edge.get("estimated_funding_cost"),
        "expected_net_edge": edge.get("expected_net_edge"),
        "edge_to_cost_ratio": edge.get("edge_to_cost_ratio"),
        "direction_confidence_quant": direction_scores.get("LONG")
        if side.upper() == "LONG"
        else direction_scores.get("SHORT"),
        "supporting_evidence": list(supporting_evidence),
        "contradicting_evidence": list(contradicting_evidence),
        "risk_flags": list(risk_flags or []),
        "gate_results": gate_results,
        "final_action": final_action,
        "final_reason": final_reason,
        "rank": rank,
        "rank_percentile": rank_percentile,
        "data_freshness_ms": enrichment.get("data_freshness_ms"),
        "no_hindsight": True,
    }


def persist_cycle_snapshots(campaign_root: Path, cycle_id: str, snapshots: list[dict[str, Any]]) -> Path:
    d = snapshot_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"cycle_{cycle_id}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for snap in snapshots:
            fh.write(json.dumps(snap, default=str) + "\n")
    latest = d / "latest_cycle_snapshots.json"
    tmp = latest.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"cycle_id": cycle_id, "count": len(snapshots), "snapshots": snapshots[:20]}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(latest)
    return path


def load_latest_snapshots(campaign_root: Path) -> list[dict[str, Any]]:
    path = snapshot_dir(campaign_root) / "latest_cycle_snapshots.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("snapshots") or [])
    except Exception:  # noqa: BLE001
        return []

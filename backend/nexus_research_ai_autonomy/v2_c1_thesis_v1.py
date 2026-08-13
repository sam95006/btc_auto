"""V2-C1 isolated thesis state — separate namespace from Champion V1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

V2_THESIS_NAMESPACE = "V2_C1"
V1_THESIS_NAMESPACE = "V1"
V2_THESIS_STATE_FILE = "v2_c1_thesis_state.json"
ACTION_EVIDENCE_POST_ISOLATION = "POST_V2_THESIS_ISOLATION"
ACTION_EVIDENCE_PRE_ISOLATION = "PRE_V2_THESIS_ISOLATION"


def _material_change(prev: dict[str, Any], curr: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    if prev.get("regime") != curr.get("regime"):
        changes.append("regime_changed")
    if prev.get("market_structure") != curr.get("market_structure"):
        changes.append("structure_changed")
    pm5 = (prev.get("momentum_5m") or {}).get("return")
    cm5 = (curr.get("momentum_5m") or {}).get("return")
    if pm5 is not None and cm5 is not None:
        if abs(float(cm5) - float(pm5)) >= 0.15:
            changes.append("momentum_materially_changed")
    poi = prev.get("oi_delta_short")
    coi = curr.get("oi_delta_short")
    if poi is not None and coi is not None and abs(float(coi) - float(poi)) >= 0.05:
        changes.append("oi_state_changed")
    pf = prev.get("funding_rate")
    cf = curr.get("funding_rate")
    if pf is not None and cf is not None and abs(float(cf) - float(pf)) >= 0.0001:
        changes.append("funding_crowding_changed")
    pp = float(prev.get("price") or 0)
    cp = float(curr.get("price") or 0)
    if pp > 0 and cp > 0 and abs(cp - pp) / pp * 100.0 >= 0.35:
        changes.append("price_materially_repositioned")
    pne = float(prev.get("expected_net_edge") or 0)
    cne = float(curr.get("expected_net_edge") or 0)
    if cne - pne >= 0.5:
        changes.append("expected_net_edge_materially_improved")
    return changes


def v2_c1_thesis_state_path(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / V2_THESIS_STATE_FILE


def evaluate_v2_c1_thesis_novelty(
    *,
    campaign_root: Path,
    symbol: str,
    side: str,
    current_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Novelty against V2-C1 action-cohort thesis history only — never V1 state."""
    path = v2_c1_thesis_state_path(campaign_root)
    state: dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
    key = f"{symbol}|{side.upper()}"
    prev = state.get(key)
    if not prev:
        return {
            "pass": True,
            "reason": "no_prior_thesis",
            "material_changes": [],
            "thesis_namespace": V2_THESIS_NAMESPACE,
        }
    material = _material_change(prev, current_snapshot)
    if material:
        return {
            "pass": True,
            "reason": "thesis_materially_changed",
            "material_changes": material,
            "thesis_namespace": V2_THESIS_NAMESPACE,
        }
    return {
        "pass": False,
        "reason": "REPEATED_THESIS_NO_NEW_EDGE",
        "material_changes": [],
        "prior_timestamp_ms": prev.get("timestamp_ms"),
        "thesis_namespace": V2_THESIS_NAMESPACE,
    }


def record_v2_c1_thesis(campaign_root: Path, snapshot: dict[str, Any]) -> None:
    """Record V2-C1 thesis on READY action only — never writes V1 namespace."""
    path = v2_c1_thesis_state_path(campaign_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {}
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
    key = f"{snapshot.get('symbol')}|{str(snapshot.get('side') or '').upper()}"
    state[key] = {
        "timestamp_ms": snapshot.get("timestamp_ms"),
        "regime": snapshot.get("regime"),
        "market_structure": snapshot.get("market_structure"),
        "momentum_5m": snapshot.get("momentum_5m"),
        "oi_delta_short": snapshot.get("oi_delta_short"),
        "funding_rate": snapshot.get("funding_rate"),
        "price": snapshot.get("price"),
        "expected_net_edge": snapshot.get("expected_net_edge"),
        "setup_signature": snapshot.get("setup_signature"),
        "thesis_namespace": V2_THESIS_NAMESPACE,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def action_evidence_epoch(row: dict[str, Any]) -> str:
    return str(row.get("action_evidence_generation") or ACTION_EVIDENCE_PRE_ISOLATION)


def resolve_abstention_diagnostic(row: dict[str, Any]) -> str:
    """P0.6 legacy rows without diagnostic → legacy_missing, not other."""
    diag = row.get("abstention_diagnostic")
    if diag is None or str(diag).strip() == "":
        return "legacy_missing"
    return str(diag)

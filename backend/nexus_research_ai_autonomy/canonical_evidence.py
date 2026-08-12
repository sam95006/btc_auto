"""Canonical evidence sealing — V18.2.28 metric consistency.

Intermediate agent/session results MUST NOT override sealed funnel or gate values.
One canonical schema; metric_consistency_pass when all mirrors agree.
"""
from __future__ import annotations

from typing import Any

CANONICAL_EVIDENCE_SCHEMA = "v18_2_28_canonical_evidence_v1"

# Sealed metric keys — authoritative source is full-market scan funnel + selection
SEALED_FUNNEL_KEYS = (
    "eligible",
    "liquidity_data_pass",
    "economic_pass",
    "economic_edge_pass",
    "horizon_pass",
    "horizon_feasibility_pass",
    "both_pass",
    "risk_pass",
    "prepared",
    "triggered",
    "real_orders",
)

SEALED_GATE_KEYS = (
    "ECONOMIC_EDGE_PASS",
    "HORIZON_FEASIBILITY_PASS",
)


def seal_funnel_metrics(
    *,
    funnel: dict[str, Any] | None,
    selection: dict[str, Any] | None = None,
    selected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build sealed funnel counts from canonical scan — single source of truth."""
    f = dict(funnel or {})
    sel = dict(selection or {})
    best = dict(selected or sel.get("selected") or {})

    sealed: dict[str, Any] = {
        "schema": CANONICAL_EVIDENCE_SCHEMA,
        "source": "full_market_scan",
        "intermediate_override_blocked": True,
    }
    for k in SEALED_FUNNEL_KEYS:
        if k in f and f[k] is not None:
            sealed[k] = f[k]
        elif k in sel.get("funnel", {}):
            sealed[k] = sel["funnel"][k]

    if best:
        sealed["selected_symbol"] = best.get("symbol")
        sealed["selected_direction"] = best.get("direction") or best.get("selected_side")
        sealed["selected_long_score"] = best.get("long_score")
        sealed["selected_short_score"] = best.get("short_score")
        if best.get("economic_edge_pass") is not None:
            sealed["selected_economic_edge_pass"] = bool(best["economic_edge_pass"])
        if best.get("horizon_feasibility_pass") is not None:
            sealed["selected_horizon_feasibility_pass"] = bool(best["horizon_feasibility_pass"])

    return sealed


def seal_gate_metrics(
    *,
    pnl_pack: dict[str, Any] | None,
    selected: dict[str, Any] | None = None,
    funnel_sealed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Seal ECONOMIC_EDGE_PASS / HORIZON_FEASIBILITY_PASS from authoritative context."""
    pnl = dict(pnl_pack or {})
    best = dict(selected or {})
    fs = dict(funnel_sealed or {})

    econ: bool | None = None
    horiz: bool | None = None

    # Priority: executed trade pack > selected candidate > WAIT with explicit gates
    if pnl.get("executed"):
        econ = pnl.get("ECONOMIC_EDGE_PASS")
        horiz = pnl.get("HORIZON_FEASIBILITY_PASS")
    elif best.get("economic_edge_pass") is not None:
        econ = bool(best["economic_edge_pass"])
        horiz = bool(best.get("horizon_feasibility_pass", False))
    elif pnl.get("WAIT"):
        econ = pnl.get("ECONOMIC_EDGE_PASS")
        horiz = pnl.get("HORIZON_FEASIBILITY_PASS")

    # Never leave null when selected candidate has explicit booleans
    if econ is None and fs.get("selected_economic_edge_pass") is not None:
        econ = bool(fs["selected_economic_edge_pass"])
    if horiz is None and fs.get("selected_horizon_feasibility_pass") is not None:
        horiz = bool(fs["selected_horizon_feasibility_pass"])

    return {
        "schema": CANONICAL_EVIDENCE_SCHEMA,
        "ECONOMIC_EDGE_PASS": econ,
        "HORIZON_FEASIBILITY_PASS": horiz,
        "source": "sealed_gates",
        "intermediate_override_blocked": True,
    }


def _mirror_values(sections: list[tuple[str, dict[str, Any], list[str]]]) -> list[dict[str, Any]]:
    """Compare metric keys across sections; report conflicts."""
    conflicts: list[dict[str, Any]] = []
    by_key: dict[str, list[tuple[str, Any]]] = {}
    for section_name, data, keys in sections:
        for k in keys:
            if k not in data:
                continue
            v = data[k]
            if v is None:
                continue
            by_key.setdefault(k, []).append((section_name, v))

    for k, pairs in by_key.items():
        unique = {v for _, v in pairs}
        if len(unique) > 1:
            conflicts.append(
                {
                    "metric": k,
                    "values": {name: val for name, val in pairs},
                    "resolution": "sealed_funnel_wins",
                }
            )
    return conflicts


def validate_metric_consistency(
    *,
    funnel_sealed: dict[str, Any],
    gate_sealed: dict[str, Any],
    time_basis: dict[str, Any] | None = None,
    market_opportunity: dict[str, Any] | None = None,
    session_pnl_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metric_consistency_pass and any detected intermediate overrides."""
    tb = dict(time_basis or {})
    mo = dict(market_opportunity or {})
    mo_funnel = mo.get("funnel") or mo.get("selection", {}).get("funnel") or {}
    pnl = dict(session_pnl_pack or {})

    conflicts = _mirror_values(
        [
            ("funnel_sealed", funnel_sealed, list(SEALED_FUNNEL_KEYS)),
            ("market_opportunity_funnel", mo_funnel if isinstance(mo_funnel, dict) else {}, list(SEALED_FUNNEL_KEYS)),
            ("gate_sealed", gate_sealed, list(SEALED_GATE_KEYS)),
            ("time_basis", tb, list(SEALED_GATE_KEYS)),
            ("session_pnl_pack", pnl, list(SEALED_GATE_KEYS)),
        ]
    )

    # Null in time_basis while sealed has value = intermediate leak
    for k in SEALED_GATE_KEYS:
        sealed_v = gate_sealed.get(k)
        tb_v = tb.get(k)
        if sealed_v is not None and tb_v is None:
            conflicts.append(
                {
                    "metric": k,
                    "values": {"gate_sealed": sealed_v, "time_basis": tb_v},
                    "resolution": "time_basis_must_mirror_sealed",
                    "kind": "intermediate_null_override",
                }
            )

    return {
        "schema": "v18_2_28_metric_consistency_v1",
        "metric_consistency_pass": len(conflicts) == 0,
        "conflicts": conflicts,
        "sealed_funnel_keys": list(SEALED_FUNNEL_KEYS),
        "sealed_gate_keys": list(SEALED_GATE_KEYS),
        "intermediate_override_blocked": True,
    }


def apply_sealed_to_time_basis(
    time_basis: dict[str, Any],
    *,
    gate_sealed: dict[str, Any],
    funnel_sealed: dict[str, Any],
) -> dict[str, Any]:
    """Mirror sealed gates into TIME_BASIS — no null when sealed has truth."""
    out = dict(time_basis)
    for k in SEALED_GATE_KEYS:
        if gate_sealed.get(k) is not None:
            out[k] = gate_sealed[k]
    out["metric_consistency"] = {
        "sealed_from": "full_market_scan",
        "funnel_sealed_schema": funnel_sealed.get("schema"),
    }
    return out

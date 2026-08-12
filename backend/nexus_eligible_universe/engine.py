"""Core classification + funnel for V18-C Live Eligible Universe."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from backend.nexus_eligible_universe.constants import (
    CLASS_SEVERITY,
    FUNNEL_KEYS,
    GATES,
    SCHEMA,
    UNIVERSE_CLASSES,
)
from backend.nexus_eligible_universe.gates import run_all_gates
from backend.nexus_eligible_universe.models import (
    GateResult,
    InstrumentSnapshot,
    UniverseDecision,
)


def _worse_class(a: str, b: str) -> str:
    return a if CLASS_SEVERITY[a] >= CLASS_SEVERITY[b] else b


def _gate_map(gates: list[GateResult]) -> dict[str, GateResult]:
    return {g.gate: g for g in gates}


def classify_instrument(
    inst: InstrumentSnapshot,
    *,
    as_of_ms: int,
) -> UniverseDecision:
    """Classify one instrument. UNKNOWN/missing never yields ELIGIBLE."""
    gates = run_all_gates(inst, as_of_ms=as_of_ms)
    gm = _gate_map(gates)
    reasons: list[str] = []
    universe_class = "ELIGIBLE"

    def fail(cls: str, reason: str) -> None:
        nonlocal universe_class
        universe_class = _worse_class(universe_class, cls)
        reasons.append(reason)

    # --- Hard availability / license / halt / delist / specs ---
    ts = gm["trading_status"]
    if not ts.known:
        fail("UNAVAILABLE", "trading_status_unknown")
    elif not ts.passed:
        if "DELIST" in str(ts.detail).upper() or inst.status in {
            "PreDelisting",
            "Settling",
            "Closed",
        }:
            fail("DELISTING_RISK", ts.detail)
        elif "HALT" in str(ts.detail).upper() or "SUSPEND" in str(ts.detail).upper():
            fail("MARKET_HALTED", ts.detail)
        else:
            fail("MARKET_HALTED", ts.detail)

    ds = gm["delisting_state"]
    if not ds.known:
        fail("UNAVAILABLE", "delisting_state_unknown")
    elif not ds.passed:
        fail("DELISTING_RISK", ds.detail)

    cs = gm["contract_specs"]
    if not cs.known:
        fail("UNAVAILABLE", "contract_specs_unknown")
    elif not cs.passed:
        fail("UNAVAILABLE", cs.detail)

    dt = gm["data_trust"]
    if not dt.known:
        fail("UNAVAILABLE", "data_trust_unknown")
    elif dt.detail == "TRUST_LICENSE_BLOCKED":
        fail("LICENSE_BLOCKED", str(dt.measured_value))
    elif dt.detail == "TRUST_UNAVAILABLE":
        fail("UNAVAILABLE", "data_trust_unavailable")
    elif not dt.passed:
        fail("DATA_DEGRADED", str(dt.measured_value or dt.detail))

    dc = gm["data_completeness"]
    if not dc.known:
        fail("UNAVAILABLE", "data_completeness_unknown")
    elif not dc.passed:
        fail("DATA_DEGRADED", dc.detail)

    # --- Listing / history ---
    la = gm["listing_age"]
    if not la.known:
        fail("UNAVAILABLE", "listing_age_unknown")
    elif not la.passed:
        fail("NEW_LISTING", la.detail)

    hist = gm.get("history_bars")
    if hist is not None:
        if not hist.known:
            fail("UNAVAILABLE", "history_unknown")
        elif not hist.passed:
            fail("INSUFFICIENT_HISTORY", hist.detail)

    # --- Liquidity cluster ---
    for gname, cls, reason_prefix in (
        ("turnover_24h", "LOW_LIQUIDITY", "turnover"),
        ("trade_frequency", "LOW_LIQUIDITY", "trade_frequency"),
        ("book_depth", "LOW_LIQUIDITY", "book_depth"),
    ):
        g = gm[gname]
        if not g.known:
            fail("UNAVAILABLE", f"{gname}_unknown")
        elif not g.passed:
            fail(cls, f"{reason_prefix}:{g.detail}")

    sp = gm["spread"]
    if not sp.known:
        fail("UNAVAILABLE", "spread_unknown")
    elif not sp.passed:
        fail("WIDE_SPREAD", sp.detail)

    # --- Cost ---
    cf = gm["cost_feasibility"]
    if not cf.known:
        fail("UNAVAILABLE", "cost_unknown")
    elif not cf.passed:
        fail("COST_INFEASIBLE", cf.detail)

    # --- Funding / OI: missing known-false → OBSERVE_ONLY (not ELIGIBLE) ---
    # Unknown → UNAVAILABLE (fail-closed). Present but low OI → OBSERVE_ONLY.
    for gname in ("funding_availability", "oi_availability"):
        g = gm[gname]
        if not g.known:
            fail("UNAVAILABLE", f"{gname}_unknown")
        elif not g.passed:
            # Known absence / too-low OI → observe, not full eligible
            fail("OBSERVE_ONLY", f"{gname}:{g.detail}")

    # USABLE_WITH_LIMITS trust already passed gate, but force observe-only
    if (
        universe_class == "ELIGIBLE"
        and inst.data_trust_status == "USABLE_WITH_LIMITS"
    ):
        fail("OBSERVE_ONLY", "trust_usable_with_limits")

    # Absolute fail-closed: any unknown gate forbids ELIGIBLE
    if universe_class == "ELIGIBLE":
        for g in gates:
            if not g.known:
                fail("UNAVAILABLE", f"unknown_gate:{g.gate}")
            elif not g.passed:
                fail("UNAVAILABLE", f"unmapped_fail:{g.gate}:{g.detail}")

    observe_only = universe_class == "OBSERVE_ONLY"
    stage = _funnel_stage_for_class(universe_class, gm)
    return UniverseDecision(
        symbol=inst.symbol,
        universe_class=universe_class,
        gates=gates,
        reasons=reasons,
        funnel_stage_reached=stage,
        as_of_ms=as_of_ms,
        data_trust_status=inst.data_trust_status,
        observe_only=observe_only,
    )


def _funnel_stage_for_class(universe_class: str, gm: dict[str, GateResult]) -> str:
    if universe_class == "ELIGIBLE":
        return "eligible"
    if universe_class == "OBSERVE_ONLY":
        return "observe_only"
    # Determine how far the instrument progressed before blocking
    catalog_ok = gm["contract_specs"].passed and gm["contract_specs"].known
    if not catalog_ok:
        return "total_exchange"
    data_ok = (
        gm["data_completeness"].passed
        and gm["data_trust"].passed
        and gm["data_completeness"].known
        and gm["data_trust"].known
    )
    if not data_ok:
        return "catalog_valid"
    liq_ok = all(
        gm[k].passed and gm[k].known
        for k in ("turnover_24h", "trade_frequency", "spread", "book_depth")
    )
    if not liq_ok:
        return "data_available"
    cost_ok = gm["cost_feasibility"].passed and gm["cost_feasibility"].known
    if not cost_ok:
        return "liquidity_pass"
    return "cost_pass"


def compute_funnel(decisions: Iterable[UniverseDecision]) -> dict[str, int]:
    """Compute funnel counts from real classification results (never hardcoded)."""
    rows = list(decisions)
    total = len(rows)

    catalog_valid = 0
    data_available = 0
    liquidity_pass = 0
    cost_pass = 0
    eligible = 0
    observe = 0

    for d in rows:
        gm = _gate_map(d.gates)
        specs_ok = gm["contract_specs"].known and gm["contract_specs"].passed
        trading_known = gm["trading_status"].known
        if not (specs_ok and trading_known):
            continue
        catalog_valid += 1

        data_ok = (
            gm["data_completeness"].known
            and gm["data_completeness"].passed
            and gm["data_trust"].known
            and gm["data_trust"].passed
        )
        if not data_ok:
            continue
        data_available += 1

        liq_ok = all(
            gm[k].known and gm[k].passed
            for k in ("turnover_24h", "trade_frequency", "spread", "book_depth")
        )
        if not liq_ok:
            continue
        liquidity_pass += 1

        cost_ok = gm["cost_feasibility"].known and gm["cost_feasibility"].passed
        if not cost_ok:
            continue
        cost_pass += 1

    for d in rows:
        if d.universe_class == "ELIGIBLE":
            eligible += 1
        elif d.universe_class == "OBSERVE_ONLY":
            observe += 1

    blocked = total - eligible - observe

    funnel = {
        "total_exchange_contracts": total,
        "catalog_valid_contracts": catalog_valid,
        "data_available_contracts": data_available,
        "liquidity_pass_contracts": liquidity_pass,
        "cost_pass_contracts": cost_pass,
        "eligible_contracts": eligible,
        "observe_only_contracts": observe,
        "blocked_contracts": blocked,
    }
    assert all(k in funnel for k in FUNNEL_KEYS)
    assert (
        funnel["eligible_contracts"]
        + funnel["observe_only_contracts"]
        + funnel["blocked_contracts"]
        == funnel["total_exchange_contracts"]
    )
    assert funnel["total_exchange_contracts"] >= funnel["catalog_valid_contracts"]
    assert funnel["catalog_valid_contracts"] >= funnel["data_available_contracts"]
    assert funnel["data_available_contracts"] >= funnel["liquidity_pass_contracts"]
    assert funnel["liquidity_pass_contracts"] >= funnel["cost_pass_contracts"]
    assert funnel["cost_pass_contracts"] >= funnel["eligible_contracts"]
    return funnel


def evaluate_universe(
    instruments: list[InstrumentSnapshot],
    *,
    as_of_ms: int,
) -> dict[str, Any]:
    decisions = [classify_instrument(i, as_of_ms=as_of_ms) for i in instruments]
    funnel = compute_funnel(decisions)
    class_hist = Counter(d.universe_class for d in decisions)
    return {
        "schema": SCHEMA,
        "as_of_ms": as_of_ms,
        "instrument_count": len(instruments),
        "funnel": funnel,
        "class_histogram": {c: int(class_hist.get(c, 0)) for c in UNIVERSE_CLASSES},
        "gates": list(GATES),
        "decisions": [d.to_dict() for d in decisions],
        "hard_rule": "UNKNOWN_OR_MISSING_MUST_NOT_DEFAULT_TO_ELIGIBLE",
    }

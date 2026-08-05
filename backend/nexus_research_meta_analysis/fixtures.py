"""Synthetic cross-experiment corpus for V15-D meta-analysis (development only)."""
from __future__ import annotations

import hashlib
import math
from typing import Any

from backend.nexus_research_meta_analysis.constants import (
    DEVELOPMENT_INTERVAL_ID,
    RANDOM_SEED,
)


def _digest(*parts: str) -> str:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _series(
    n: int,
    *,
    mean: float,
    amp: float,
    phase: float,
    noise: float,
    seed: int,
) -> list[float]:
    out: list[float] = []
    for i in range(n):
        # Deterministic pseudo-noise from seed+i
        u = ((seed * 1103515245 + i * 12345) & 0x7FFFFFFF) / 0x7FFFFFFF
        out.append(mean + amp * math.sin(0.35 * i + phase) + noise * (u - 0.5))
    return out


def build_synthetic_experiments(*, seed: int = RANDOM_SEED) -> list[dict[str, Any]]:
    """Build a candidacy-aware experiment corpus with failed siblings.

    Groups:
      G_PROMISING — one promising run + two failed siblings (must retain)
      G_DUP — near-duplicate pair (duplication detection)
      G_CHERRY — favorable-run selection adversarial set
      G_FRAGILE — regime/symbol/capacity fragile
      G_COST — cost/turnover destroyed
      G_FDR — weak p-values for multiple-testing rejection
    """
    experiments: list[dict[str, Any]] = []

    def add(
        *,
        eid: str,
        family: str,
        mechanism: str,
        group: str,
        role: str,
        p_value: float,
        net_mean: float,
        amp: float,
        phase: float,
        neighbor: list[float],
        regime_net: dict[str, float],
        symbol_net: dict[str, float],
        gross: float,
        net: float,
        turnover: float,
        capacity_assumptions: dict[str, float],
        intended_label_hint: str,
        n: int = 64,
        noise: float = 0.004,
        params: dict[str, float] | None = None,
    ) -> None:
        series = _series(
            n, mean=net_mean, amp=amp, phase=phase, noise=noise, seed=seed + len(experiments)
        )
        params = params or {"lookback": 20.0, "threshold": 0.5, "size": 1.0}
        experiments.append(
            {
                "experiment_id": eid,
                "candidacy_group": group,
                "role": role,  # promising | failed_sibling | duplicate | cherry_favorable | cherry_omitted | ...
                "research_family": family,
                "mechanism_semantic_id": mechanism,
                "development_interval_id": DEVELOPMENT_INTERVAL_ID,
                "p_value": p_value,
                "net_series": series,
                "neighbor_metrics": neighbor,
                "regime_net": regime_net,
                "symbol_net": symbol_net,
                "gross_pnl": gross,
                "net_pnl": net,
                "turnover_notional": turnover,
                "capacity_assumptions": capacity_assumptions,
                "parameters": params,
                "parameter_checksum": _digest(eid, str(sorted(params.items()))),
                "feature_version": "fv_meta_v15d_1",
                "universe_checksum": _digest("UNI", group),
                "data_fixture_id": f"FIX_{group}",
                "cost_components": {
                    "entry_fee": abs(turnover) * 0.0002,
                    "exit_fee": abs(turnover) * 0.0002,
                    "spread_cost": abs(turnover) * 0.0003,
                    "slippage_cost": abs(turnover) * 0.0004,
                    "funding_cost": abs(turnover) * 0.0001,
                    "partial_fill_cost": abs(turnover) * 0.00005,
                    "cancel_replace_cost": abs(turnover) * 0.00005,
                    "market_impact_approximation": abs(turnover) * 0.0002,
                    "turnover_cost": abs(turnover) * 0.0005,
                },
                "intended_label_hint": intended_label_hint,
                "fixture_synthetic": True,
                "qualification_claim": False,
            }
        )

    # --- Promising group with failed siblings ---
    add(
        eid="EXP_PROM_001",
        family="ORDER_FLOW_IMBALANCE",
        mechanism="MECH_OFI_ABSORPTION",
        group="G_PROMISING",
        role="promising",
        p_value=0.004,
        net_mean=0.018,
        amp=0.004,
        phase=0.1,
        neighbor=[0.016, 0.017, 0.019, 0.018],
        regime_net={"RANGE": 0.012, "TREND": 0.008, "SHOCK": 0.006, "QUIET": 0.007},
        symbol_net={"BTCUSDT": 0.01, "ETHUSDT": 0.008, "SOLUSDT": 0.006, "BNBUSDT": 0.005},
        gross=1.4,
        net=0.9,
        turnover=800.0,
        capacity_assumptions={"size_btc": 0.2, "size_eth": 0.2, "size_alt": 0.15},
        intended_label_hint="DEVELOPMENT_PROMISING_NOT_QUALIFIED",
    )
    add(
        eid="EXP_PROM_FAIL_A",
        family="ORDER_FLOW_IMBALANCE",
        mechanism="MECH_OFI_ABSORPTION",
        group="G_PROMISING",
        role="failed_sibling",
        p_value=0.42,
        net_mean=-0.004,
        amp=0.006,
        phase=1.2,
        neighbor=[-0.005, -0.003, 0.001, -0.004],
        regime_net={"RANGE": -0.002, "TREND": -0.01, "SHOCK": 0.001, "QUIET": -0.003},
        symbol_net={"BTCUSDT": -0.002, "ETHUSDT": -0.004, "SOLUSDT": 0.001, "BNBUSDT": -0.003},
        gross=0.2,
        net=-0.3,
        turnover=900.0,
        capacity_assumptions={"size_btc": 0.2, "size_eth": 0.2, "size_alt": 0.15},
        intended_label_hint="REJECTED",
        params={"lookback": 20.0, "threshold": 0.35, "size": 1.0},
    )
    add(
        eid="EXP_PROM_FAIL_B",
        family="ORDER_FLOW_IMBALANCE",
        mechanism="MECH_OFI_ABSORPTION",
        group="G_PROMISING",
        role="failed_sibling",
        p_value=0.55,
        net_mean=-0.008,
        amp=0.005,
        phase=2.1,
        neighbor=[-0.007, -0.009, -0.006, -0.01],
        regime_net={"RANGE": 0.001, "TREND": -0.012, "SHOCK": -0.004, "QUIET": -0.002},
        symbol_net={"BTCUSDT": -0.005, "ETHUSDT": -0.003, "SOLUSDT": -0.004, "BNBUSDT": -0.002},
        gross=0.1,
        net=-0.45,
        turnover=950.0,
        capacity_assumptions={"size_btc": 0.25, "size_eth": 0.2, "size_alt": 0.1},
        intended_label_hint="REJECTED",
        params={"lookback": 28.0, "threshold": 0.5, "size": 1.2},
    )

    # --- Near-duplicates ---
    add(
        eid="EXP_DUP_001",
        family="LIQUIDATION_CASCADE",
        mechanism="MECH_LIQ_CASCADE_V1",
        group="G_DUP",
        role="duplicate_primary",
        p_value=0.03,
        net_mean=0.012,
        amp=0.003,
        phase=0.5,
        neighbor=[0.011, 0.012, 0.013],
        regime_net={"RANGE": 0.004, "TREND": 0.005, "SHOCK": 0.003},
        symbol_net={"BTCUSDT": 0.006, "ETHUSDT": 0.005},
        gross=0.8,
        net=0.4,
        turnover=500.0,
        capacity_assumptions={"size_btc": 0.3, "size_eth": 0.25},
        intended_label_hint="DUPLICATE_EXPERIMENT",
        params={"lookback": 12.0, "threshold": 0.7, "size": 0.8},
    )
    add(
        eid="EXP_DUP_002",
        family="LIQUIDATION_CASCADE",
        mechanism="MECH_LIQ_CASCADE_V1",
        group="G_DUP",
        role="duplicate_clone",
        p_value=0.031,
        net_mean=0.0121,
        amp=0.003,
        phase=0.51,
        neighbor=[0.011, 0.012, 0.013],
        regime_net={"RANGE": 0.004, "TREND": 0.005, "SHOCK": 0.003},
        symbol_net={"BTCUSDT": 0.006, "ETHUSDT": 0.005},
        gross=0.81,
        net=0.41,
        turnover=505.0,
        capacity_assumptions={"size_btc": 0.3, "size_eth": 0.25},
        intended_label_hint="DUPLICATE_EXPERIMENT",
        params={"lookback": 12.1, "threshold": 0.705, "size": 0.8},
    )

    # --- Cherry-pick adversarial set ---
    add(
        eid="EXP_CHERRY_FAV",
        family="FUNDING_BASIS_DISLOCATION",
        mechanism="MECH_FUNDING_BASIS",
        group="G_CHERRY",
        role="cherry_favorable",
        p_value=0.01,
        net_mean=0.022,
        amp=0.005,
        phase=0.3,
        neighbor=[0.02, 0.021, 0.023],
        regime_net={"RANGE": 0.01, "TREND": 0.008, "SHOCK": 0.004},
        symbol_net={"BTCUSDT": 0.012, "ETHUSDT": 0.009},
        gross=1.6,
        net=1.1,
        turnover=700.0,
        capacity_assumptions={"size_btc": 0.35, "size_eth": 0.2},
        intended_label_hint="FAVORABLE_SELECTION_BLOCKED",
    )
    add(
        eid="EXP_CHERRY_OMIT_A",
        family="FUNDING_BASIS_DISLOCATION",
        mechanism="MECH_FUNDING_BASIS",
        group="G_CHERRY",
        role="cherry_omitted",
        p_value=0.61,
        net_mean=-0.01,
        amp=0.004,
        phase=1.7,
        neighbor=[-0.01, -0.008, -0.012],
        regime_net={"RANGE": -0.004, "TREND": -0.008, "SHOCK": -0.002},
        symbol_net={"BTCUSDT": -0.006, "ETHUSDT": -0.005},
        gross=0.05,
        net=-0.4,
        turnover=720.0,
        capacity_assumptions={"size_btc": 0.35, "size_eth": 0.2},
        intended_label_hint="REJECTED",
    )
    add(
        eid="EXP_CHERRY_OMIT_B",
        family="FUNDING_BASIS_DISLOCATION",
        mechanism="MECH_FUNDING_BASIS",
        group="G_CHERRY",
        role="cherry_omitted",
        p_value=0.7,
        net_mean=-0.015,
        amp=0.004,
        phase=2.4,
        neighbor=[-0.014, -0.016, -0.013],
        regime_net={"RANGE": -0.005, "TREND": -0.01, "SHOCK": -0.003},
        symbol_net={"BTCUSDT": -0.008, "ETHUSDT": -0.007},
        gross=0.02,
        net=-0.5,
        turnover=740.0,
        capacity_assumptions={"size_btc": 0.35, "size_eth": 0.2},
        intended_label_hint="REJECTED",
    )

    # --- Regime / symbol / capacity fragile ---
    add(
        eid="EXP_FRAG_001",
        family="REGIME_MEAN_REVERSION",
        mechanism="MECH_REGIME_MR",
        group="G_FRAGILE",
        role="fragile",
        p_value=0.02,
        net_mean=0.01,
        amp=0.008,
        phase=0.8,
        neighbor=[0.002, -0.004, 0.015, 0.001],  # neighborhood unstable
        regime_net={"RANGE": 0.04, "TREND": -0.001, "SHOCK": 0.0},  # concentrated
        symbol_net={"BTCUSDT": 0.03, "ETHUSDT": -0.01, "SOLUSDT": -0.008},
        gross=0.9,
        net=0.35,
        turnover=600.0,
        capacity_assumptions={"size_btc": 0.9, "size_eth": 0.05, "size_alt": 0.05},
        intended_label_hint="REGIME_FRAGILE",
    )

    # --- Cost destroyed ---
    add(
        eid="EXP_COST_001",
        family="SPREAD_SHOCK",
        mechanism="MECH_SPREAD_SHOCK",
        group="G_COST",
        role="cost_destroyed",
        p_value=0.05,
        net_mean=0.002,
        amp=0.003,
        phase=0.2,
        neighbor=[0.001, 0.002, 0.003],
        regime_net={"RANGE": 0.003, "TREND": 0.002, "SHOCK": 0.001},
        symbol_net={"BTCUSDT": 0.002, "ETHUSDT": 0.001},
        gross=0.6,
        net=-0.1,
        turnover=5000.0,
        capacity_assumptions={"size_btc": 0.4, "size_eth": 0.3},
        intended_label_hint="COST_DESTROYED",
    )

    # --- FDR weak family ---
    for i, p in enumerate([0.08, 0.12, 0.15, 0.22], start=1):
        add(
            eid=f"EXP_FDR_{i:03d}",
            family="VOL_EXPANSION_COMPRESSION",
            mechanism="MECH_VOL_COMPRESS",
            group="G_FDR",
            role="fdr_weak",
            p_value=p,
            net_mean=0.003,
            amp=0.004,
            phase=0.4 * i,
            neighbor=[0.002, 0.003, 0.004],
            regime_net={"RANGE": 0.002, "TREND": 0.001, "SHOCK": 0.001},
            symbol_net={"BTCUSDT": 0.002, "ETHUSDT": 0.001},
            gross=0.3,
            net=0.05,
            turnover=400.0,
            capacity_assumptions={"size_btc": 0.2, "size_eth": 0.2},
            intended_label_hint="MULTIPLE_TESTING_REJECTED",
            params={"lookback": 10.0 + i, "threshold": 0.4, "size": 0.5},
        )

    # Review-only borderline
    add(
        eid="EXP_REVIEW_001",
        family="CROSS_ASSET_LEAD_LAG",
        mechanism="MECH_LEAD_LAG",
        group="G_REVIEW",
        role="review",
        p_value=0.025,
        net_mean=0.008,
        amp=0.003,
        phase=1.0,
        neighbor=[0.007, 0.008, 0.009, 0.006],
        regime_net={"RANGE": 0.004, "TREND": 0.003, "SHOCK": 0.002, "QUIET": 0.002},
        symbol_net={"BTCUSDT": 0.004, "ETHUSDT": 0.003, "SOLUSDT": 0.002},
        gross=0.7,
        net=0.35,
        turnover=450.0,
        capacity_assumptions={"size_btc": 0.25, "size_eth": 0.25, "size_alt": 0.2},
        intended_label_hint="DEVELOPMENT_REVIEW",
    )

    return experiments


def fixture_manifest(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [e["experiment_id"] for e in experiments]
    digest = _digest(*ids, DEVELOPMENT_INTERVAL_ID)
    groups: dict[str, list[str]] = {}
    for e in experiments:
        groups.setdefault(e["candidacy_group"], []).append(e["experiment_id"])
    return {
        "schema": "v15_d_fixture_manifest",
        "batch_digest": digest,
        "experiment_count": len(experiments),
        "experiment_ids": ids,
        "candidacy_groups": {k: sorted(v) for k, v in sorted(groups.items())},
        "development_interval_id": DEVELOPMENT_INTERVAL_ID,
        "fixture_synthetic": True,
        "not_oos": True,
        "formal_walk_forward": False,
    }

"""Synthetic development candidates for V14-D robustness lab (fixture-only)."""
from __future__ import annotations

import hashlib
import random
from typing import Any

from backend.nexus_research_validation.constants import (
    RANDOM_SEED,
    REQUIRED_COST_COMPONENTS,
    RESEARCH_FAMILIES,
)


def _series(rng: random.Random, n: int, mean: float, noise: float, ar: float = 0.0) -> list[float]:
    out: list[float] = []
    prev = 0.0
    for _ in range(n):
        eps = rng.gauss(0.0, noise)
        x = mean + eps + ar * prev
        out.append(x)
        prev = x
    return out


def _cost_components(rng: random.Random, *, heavy: bool = False) -> dict[str, float]:
    """Absolute cost units vs gross_pnl (not fee rates)."""
    if heavy:
        comps = {
            "entry_fee": 0.12,
            "exit_fee": 0.12,
            "spread_cost": 0.18,
            "slippage_cost": 0.15 + rng.random() * 0.02,
            "funding_cost": 0.08,
            "partial_fill_cost": 0.05,
            "cancel_replace_cost": 0.04,
            "market_impact_approximation": 0.10,
            "turnover_cost": 0.25,
        }
    else:
        comps = {
            "entry_fee": 0.02,
            "exit_fee": 0.02,
            "spread_cost": 0.03,
            "slippage_cost": 0.02 + rng.random() * 0.005,
            "funding_cost": 0.01,
            "partial_fill_cost": 0.005,
            "cancel_replace_cost": 0.004,
            "market_impact_approximation": 0.015,
            "turnover_cost": 0.02,
        }
    for k in REQUIRED_COST_COMPONENTS:
        assert k in comps
    return comps


def build_synthetic_candidates(*, seed: int = RANDOM_SEED) -> list[dict[str, Any]]:
    """Deterministic fixture candidates covering every allowed label pathway."""
    rng = random.Random(seed)
    cands: list[dict[str, Any]] = []

    def _add(spec: dict[str, Any]) -> None:
        cid = spec["candidate_id"]
        blob = f"{cid}:{seed}:{spec['research_family']}"
        param_checksum = hashlib.sha256(blob.encode()).hexdigest()[:16]
        series = spec["net_series"]
        neighbor = [
            sum(series) / len(series) * (1.0 + rng.uniform(-0.05, 0.05))
            for _ in range(5)
        ]
        if spec.get("fragile_neighbors"):
            neighbor = [-abs(sum(series) / len(series)) for _ in range(5)]
        cands.append(
            {
                **spec,
                "parameter_checksum": param_checksum,
                "feature_version": "FIXTURE_FEATURE_V14D_1",
                "universe_checksum": hashlib.sha256(
                    f"universe-{seed}".encode()
                ).hexdigest()[:24],
                "data_fixture_id": f"SYNTH_ROBUSTNESS_{seed}",
                "neighbor_metrics": neighbor,
                "development_only": True,
                "fixture_synthetic": True,
                "oos_consumed": False,
                "formal_walk_forward": False,
            }
        )

    # 1) DEVELOPMENT_ROBUST pathway
    robust_series = _series(rng, 80, mean=0.012, noise=0.004, ar=0.05)
    robust_gross = 1.20
    robust_costs = _cost_components(rng, heavy=False)
    robust_net = robust_gross - sum(robust_costs.values())
    _add(
        {
            "candidate_id": "CAND_ROBUST_001",
            "research_family": RESEARCH_FAMILIES[0],
            "mechanism_semantic_id": "MECH_OFI_DEV_001",
            "parent_experiment_id": None,
            "net_series": robust_series,
            "n_observations": len(robust_series),
            "n_trades": 40,
            "p_value": 0.004,
            "gross_pnl": robust_gross,
            "net_pnl": robust_net,
            "cost_components": robust_costs,
            "turnover_notional": 50.0,
            "regime_net": {
                "VOL_LOW": 0.25,
                "VOL_HIGH": 0.30,
                "LIQ_NORMAL": 0.20,
                "STRESS": 0.15,
            },
            "symbol_net": {
                "BTCUSDT": 0.35,
                "ETHUSDT": 0.28,
                "SOLUSDT": 0.22,
                "BNBUSDT": 0.18,
            },
            "data_quality_ok": True,
            "intended_pathway": "DEVELOPMENT_ROBUST",
        }
    )

    # 2) Correlated twin (clustering) — also robust-ish but will share cluster
    twin = [x + rng.gauss(0, 0.0005) for x in robust_series]
    twin_costs = _cost_components(rng, heavy=False)
    twin_gross = 1.15
    twin_net = twin_gross - sum(twin_costs.values())
    _add(
        {
            "candidate_id": "CAND_ROBUST_002",
            "research_family": RESEARCH_FAMILIES[0],
            "mechanism_semantic_id": "MECH_OFI_DEV_002",
            "parent_experiment_id": "CAND_ROBUST_001",
            "net_series": twin,
            "n_observations": len(twin),
            "n_trades": 38,
            "p_value": 0.006,
            "gross_pnl": twin_gross,
            "net_pnl": twin_net,
            "cost_components": twin_costs,
            "turnover_notional": 48.0,
            "regime_net": {
                "VOL_LOW": 0.22,
                "VOL_HIGH": 0.28,
                "LIQ_NORMAL": 0.21,
                "STRESS": 0.16,
            },
            "symbol_net": {
                "BTCUSDT": 0.32,
                "ETHUSDT": 0.27,
                "SOLUSDT": 0.24,
                "BNBUSDT": 0.17,
            },
            "data_quality_ok": True,
            "intended_pathway": "DEVELOPMENT_ROBUST",
        }
    )

    # 3) INSUFFICIENT_SAMPLE
    short = _series(rng, 20, mean=0.02, noise=0.01, ar=0.1)
    sc = _cost_components(rng)
    _add(
        {
            "candidate_id": "CAND_SAMPLE_001",
            "research_family": RESEARCH_FAMILIES[1],
            "mechanism_semantic_id": "MECH_LIQ_DEV_001",
            "parent_experiment_id": None,
            "net_series": short,
            "n_observations": len(short),
            "n_trades": 8,
            "p_value": 0.02,
            "gross_pnl": 0.5,
            "net_pnl": 0.5 - sum(sc.values()),
            "cost_components": sc,
            "turnover_notional": 10.0,
            "regime_net": {"VOL_LOW": 0.4, "VOL_HIGH": 0.1},
            "symbol_net": {"BTCUSDT": 0.4, "ETHUSDT": -0.1},
            "data_quality_ok": True,
            "intended_pathway": "INSUFFICIENT_SAMPLE",
        }
    )

    # 4) MULTIPLE_TESTING_REJECTED — high p within large family
    weak = _series(rng, 60, mean=0.002, noise=0.01, ar=0.1)
    wc = _cost_components(rng)
    _add(
        {
            "candidate_id": "CAND_MT_REJECT_001",
            "research_family": RESEARCH_FAMILIES[2],
            "mechanism_semantic_id": "MECH_ABS_DEV_001",
            "parent_experiment_id": None,
            "net_series": weak,
            "n_observations": len(weak),
            "n_trades": 25,
            "p_value": 0.42,
            "gross_pnl": 0.3,
            "net_pnl": 0.3 - sum(wc.values()),
            "cost_components": wc,
            "turnover_notional": 20.0,
            "regime_net": {
                "VOL_LOW": 0.1,
                "VOL_HIGH": 0.1,
                "LIQ_NORMAL": 0.1,
                "STRESS": 0.05,
            },
            "symbol_net": {
                "BTCUSDT": 0.1,
                "ETHUSDT": 0.05,
                "SOLUSDT": 0.02,
            },
            "data_quality_ok": True,
            "intended_pathway": "MULTIPLE_TESTING_REJECTED",
        }
    )

    # 5) COST_DESTROYED
    cost_series = _series(rng, 70, mean=0.01, noise=0.005, ar=0.08)
    heavy = _cost_components(rng, heavy=True)
    gross = 0.8
    net = gross - sum(heavy.values())  # negative
    assert net <= 0
    _add(
        {
            "candidate_id": "CAND_COST_001",
            "research_family": RESEARCH_FAMILIES[3],
            "mechanism_semantic_id": "MECH_AGG_DEV_001",
            "parent_experiment_id": None,
            "net_series": cost_series,
            "n_observations": len(cost_series),
            "n_trades": 30,
            "p_value": 0.01,
            "gross_pnl": gross,
            "net_pnl": net,
            "cost_components": heavy,
            "turnover_notional": 200.0,
            "regime_net": {
                "VOL_LOW": 0.2,
                "VOL_HIGH": 0.2,
                "LIQ_NORMAL": 0.2,
                "STRESS": 0.1,
            },
            "symbol_net": {
                "BTCUSDT": 0.2,
                "ETHUSDT": 0.15,
                "SOLUSDT": 0.1,
            },
            "data_quality_ok": True,
            "intended_pathway": "COST_DESTROYED",
        }
    )

    # 6) DEVELOPMENT_FRAGILE — regime concentration + fragile neighbors
    # Keep sample/n_eff sufficient and p strong so label priority reaches fragility.
    frag = _series(rng, 90, mean=0.008, noise=0.004, ar=0.05)
    fc = _cost_components(rng)
    _add(
        {
            "candidate_id": "CAND_FRAGILE_001",
            "research_family": RESEARCH_FAMILIES[4],
            "mechanism_semantic_id": "MECH_FUND_DEV_001",
            "parent_experiment_id": None,
            "net_series": frag,
            "n_observations": len(frag),
            "n_trades": 32,
            "p_value": 0.005,
            "gross_pnl": 0.9,
            "net_pnl": 0.9 - sum(fc.values()),
            "cost_components": fc,
            "turnover_notional": 40.0,
            "regime_net": {
                "VOL_LOW": 0.9,
                "VOL_HIGH": 0.02,
                "LIQ_NORMAL": 0.01,
                "STRESS": -0.05,
            },
            "symbol_net": {
                "BTCUSDT": 0.8,
                "ETHUSDT": -0.2,
                "SOLUSDT": -0.1,
                "BNBUSDT": -0.05,
            },
            "data_quality_ok": True,
            "fragile_neighbors": True,
            "intended_pathway": "DEVELOPMENT_FRAGILE",
        }
    )

    # 7) DATA_QUALITY_BLOCKED
    dq = _series(rng, 55, mean=0.01, noise=0.005, ar=0.05)
    dc = _cost_components(rng)
    _add(
        {
            "candidate_id": "CAND_DATA_BLOCK_001",
            "research_family": RESEARCH_FAMILIES[5],
            "mechanism_semantic_id": "MECH_VOL_DEV_001",
            "parent_experiment_id": None,
            "net_series": dq,
            "n_observations": len(dq),
            "n_trades": 22,
            "p_value": 0.03,
            "gross_pnl": 0.6,
            "net_pnl": 0.6 - sum(dc.values()),
            "cost_components": dc,
            "turnover_notional": 30.0,
            "regime_net": {"VOL_LOW": 0.2, "VOL_HIGH": 0.2},
            "symbol_net": {"BTCUSDT": 0.2, "ETHUSDT": 0.15},
            "data_quality_ok": False,
            "data_quality_reason": "MISSING_CLOCK_QUALITY_AND_GAP_FLAGS",
            "intended_pathway": "DATA_QUALITY_BLOCKED",
        }
    )

    # 8) Extra family member with mid p for FDR family context
    mid = _series(rng, 50, mean=0.004, noise=0.008, ar=0.15)
    mc = _cost_components(rng)
    _add(
        {
            "candidate_id": "CAND_MT_BORDER_001",
            "research_family": RESEARCH_FAMILIES[2],
            "mechanism_semantic_id": "MECH_ABS_DEV_002",
            "parent_experiment_id": "CAND_MT_REJECT_001",
            "net_series": mid,
            "n_observations": len(mid),
            "n_trades": 20,
            "p_value": 0.09,
            "gross_pnl": 0.4,
            "net_pnl": 0.4 - sum(mc.values()),
            "cost_components": mc,
            "turnover_notional": 25.0,
            "regime_net": {
                "VOL_LOW": 0.15,
                "VOL_HIGH": 0.12,
                "LIQ_NORMAL": 0.1,
            },
            "symbol_net": {"BTCUSDT": 0.12, "ETHUSDT": 0.08, "SOLUSDT": 0.05},
            "data_quality_ok": True,
            "intended_pathway": "MULTIPLE_TESTING_REJECTED",
        }
    )

    # 9-10) Additional families for lineage coverage (fragile / sample)
    for i, fam in enumerate(RESEARCH_FAMILIES[6:8]):
        s = _series(rng, 40 + i * 5, mean=0.003, noise=0.01, ar=0.4)
        cc = _cost_components(rng)
        _add(
            {
                "candidate_id": f"CAND_EXTRA_{i+1:03d}",
                "research_family": fam,
                "mechanism_semantic_id": f"MECH_EXTRA_{i+1:03d}",
                "parent_experiment_id": None,
                "net_series": s,
                "n_observations": len(s),
                "n_trades": 12 + i,
                "p_value": 0.15 + i * 0.05,
                "gross_pnl": 0.35,
                "net_pnl": 0.35 - sum(cc.values()),
                "cost_components": cc,
                "turnover_notional": 15.0,
                "regime_net": {"VOL_LOW": 0.5, "STRESS": 0.01},
                "symbol_net": {"BTCUSDT": 0.3, "ETHUSDT": -0.1},
                "data_quality_ok": True,
                "intended_pathway": "INSUFFICIENT_SAMPLE",
            }
        )

    assert len(cands) >= 8
    # Ensure fixture checksum stability
    digest = hashlib.sha256(
        ",".join(c["candidate_id"] for c in cands).encode()
    ).hexdigest()
    for c in cands:
        c["fixture_batch_digest"] = digest
    return cands


def fixture_manifest(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "v14_d_fixture_manifest",
        "fixture_synthetic": True,
        "not_real_strategy_candidates": True,
        "candidate_count": len(candidates),
        "candidate_ids": [c["candidate_id"] for c in candidates],
        "families_represented": sorted({c["research_family"] for c in candidates}),
        "batch_digest": candidates[0]["fixture_batch_digest"] if candidates else None,
        "oos_consumed": False,
        "formal_walk_forward": False,
        "qualification_claim": False,
    }

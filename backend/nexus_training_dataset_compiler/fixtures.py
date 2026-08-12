"""Sample fixtures for V17-H — synthetic development data only."""
from __future__ import annotations

from backend.nexus_training_dataset_compiler.contracts import ConsumerPlan, Provenance, RawSample

_BASE_TS = 1_700_000_000_000

_DEFAULT_PLAN = ConsumerPlan(
    numeric_stat_models=("rolling_vol_z", "liquidity_stress_score"),
    llm_reasoners=("regime_narrative_reasoner",),
    tick_primary_consumer="rolling_vol_z",
)

_PROV = Provenance(
    source_id="SYN_DEV_FIXTURE_V17H",
    lineage="SYNTHETIC_DEVELOPMENT_FIXTURE",
    license_class="INTERNAL_SYNTHETIC",
    synthetic=True,
)


def _sample(
    *,
    sample_id: str,
    offset_ms: int,
    target_label: str,
    label_payload: dict,
    declared_split: str | None = None,
    features: dict | None = None,
) -> RawSample:
    ts = _BASE_TS + offset_ms
    return RawSample(
        sample_id=sample_id,
        symbol="BTCUSDT",
        ts_ms=ts,
        feature_cutoff_ms=ts - 60_000,
        label_available_ms=ts + 300_000,
        target_label=target_label,
        features=features
        or {
            "ret_1m": 0.001,
            "vol_z": 1.2,
            "spread_bps": 2.5,
            "depth_imbalance": -0.1,
        },
        label_payload=label_payload,
        provenance=_PROV,
        consumer_plan=_DEFAULT_PLAN,
        declared_split=declared_split,
    )


# 14 samples: cover all 8 target labels + all 7 splits (trainable + reserved).
RAW_FIXTURES: tuple[RawSample, ...] = (
    _sample(
        sample_id="TDS_DEV_REGIME_001",
        offset_ms=0,
        target_label="REGIME",
        label_payload={"regime": "COMPRESSION", "confidence": 0.61},
        declared_split="DEVELOPMENT",
    ),
    _sample(
        sample_id="TDS_DEV_VOL_002",
        offset_ms=60_000,
        target_label="VOL_FORECAST",
        label_payload={"horizon_bars": 12, "realized_vol": 0.018},
        declared_split="DEVELOPMENT",
    ),
    _sample(
        sample_id="TDS_DEV_LIQ_003",
        offset_ms=120_000,
        target_label="LIQUIDITY_STRESS",
        label_payload={"stress_level": "ELEVATED", "score": 0.72},
        declared_split="DEVELOPMENT",
    ),
    _sample(
        sample_id="TDS_DEV_RANK_004",
        offset_ms=180_000,
        target_label="CANDIDATE_RANKING",
        label_payload={"candidate_id": "CAND_A", "rank": 2},
        declared_split="DEVELOPMENT",
    ),
    _sample(
        sample_id="TDS_VAL_ROUTE_005",
        offset_ms=240_000,
        target_label="STRATEGY_ROUTING",
        label_payload={"expert": "breakout_long", "route": "DEFER"},
        declared_split="VALIDATION",
    ),
    _sample(
        sample_id="TDS_VAL_ABSTAIN_006",
        offset_ms=300_000,
        target_label="ABSTENTION",
        label_payload={"abstain": True, "reason": "UNCERTAINTY_HIGH"},
        declared_split="VALIDATION",
    ),
    _sample(
        sample_id="TDS_HASH_ERR_007",
        offset_ms=360_000,
        target_label="ERROR_CLASSIFICATION",
        label_payload={"process_class": "GOOD_PROCESS_LOSS"},
        declared_split=None,  # hash → DEVELOPMENT or VALIDATION
    ),
    _sample(
        sample_id="TDS_HASH_CF_008",
        offset_ms=420_000,
        target_label="COUNTERFACTUAL",
        label_payload={"cf_delta_r": -0.3, "as_real_pnl": False},
        declared_split=None,
    ),
    # Reserved partitions — present in catalog, never trainable.
    _sample(
        sample_id="TDS_WF_RES_009",
        offset_ms=10_000_000,
        target_label="REGIME",
        label_payload={"regime": "TREND", "confidence": 0.55},
        declared_split="WALK_FORWARD_RESERVED",
    ),
    _sample(
        sample_id="TDS_OOS_RES_010",
        offset_ms=20_000_000,
        target_label="VOL_FORECAST",
        label_payload={"horizon_bars": 24, "realized_vol": 0.022},
        declared_split="OOS_RESERVED",
    ),
    _sample(
        sample_id="TDS_SHADOW_011",
        offset_ms=30_000_000,
        target_label="STRATEGY_ROUTING",
        label_payload={"expert": "mean_revert", "route": "WAIT"},
        declared_split="SHADOW",
    ),
    _sample(
        sample_id="TDS_DEMO_012",
        offset_ms=40_000_000,
        target_label="ABSTENTION",
        label_payload={"abstain": True, "reason": "DEMO_CONTEXT"},
        declared_split="DEMO",
    ),
    _sample(
        sample_id="TDS_REAL_PRIV_013",
        offset_ms=50_000_000,
        target_label="ERROR_CLASSIFICATION",
        label_payload={"process_class": "BAD_PROCESS_WIN"},
        declared_split="REAL_PRIVATE",
    ),
    _sample(
        sample_id="TDS_DEV_LIQ_014",
        offset_ms=480_000,
        target_label="LIQUIDITY_STRESS",
        label_payload={"stress_level": "NORMAL", "score": 0.21},
        declared_split="DEVELOPMENT",
    ),
)


def fixture_count() -> int:
    return len(RAW_FIXTURES)

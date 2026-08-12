"""Horizon-consistent entry — thesis hold windows, not transport timers.

Do NOT use one generic ~180s max_hold for all strategies.
If required target move is unrealistic inside the horizon → HORIZON_TARGET_MISMATCH → WAIT.
Do NOT shrink target merely to force entry.

V18.2.26: all expected-move / target / hold / exit comparisons use the SAME forecast horizon.
INVALID_HORIZON_CONFIGURATION blocks when hard_max_hold < recommended_hold_window_min or
expected_time_to_target > hard_max_hold without explicit strategy reason.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Standard feasibility curve horizons (seconds)
STANDARD_FORECAST_HORIZONS_SEC = (300, 900, 1800, 3600)
INVALID_HORIZON_CONFIGURATION = "INVALID_HORIZON_CONFIGURATION"

# Strategy-family thesis horizons (seconds) — provenance: RESEARCH_DEMO_FAMILY_TABLE_V25
FAMILY_HORIZON_DEFAULTS: dict[str, dict[str, Any]] = {
    "TREND": {
        "entry_horizon": "SWING_INTRADAY",
        "recommended_hold_window_sec": (900, 3600),
        "hard_max_hold_sec": 3600,
        "expected_time_to_target_sec": 1200,
        "expected_time_to_stop_sec": 600,
        "typical_target_move_pct": 0.55,
        "typical_stop_move_pct": 0.40,
    },
    "MOMENTUM": {
        "entry_horizon": "INTRADAY_BURST",
        "recommended_hold_window_sec": (600, 2400),
        "hard_max_hold_sec": 2400,
        "expected_time_to_target_sec": 900,
        "expected_time_to_stop_sec": 450,
        "typical_target_move_pct": 0.45,
        "typical_stop_move_pct": 0.35,
    },
    "MEAN_REVERSION": {
        "entry_horizon": "MEAN_REVERT_SESSION",
        "recommended_hold_window_sec": (300, 1800),
        "hard_max_hold_sec": 1800,
        "expected_time_to_target_sec": 600,
        "expected_time_to_stop_sec": 300,
        "typical_target_move_pct": 0.35,
        "typical_stop_move_pct": 0.30,
    },
    "BREAKOUT": {
        "entry_horizon": "BREAKOUT_CONFIRM",
        "recommended_hold_window_sec": (480, 2700),
        "hard_max_hold_sec": 2700,
        "expected_time_to_target_sec": 900,
        "expected_time_to_stop_sec": 360,
        "typical_target_move_pct": 0.50,
        "typical_stop_move_pct": 0.35,
    },
    "VOLATILITY": {
        "entry_horizon": "VOL_EXPANSION",
        "recommended_hold_window_sec": (180, 1200),
        "hard_max_hold_sec": 1200,
        "expected_time_to_target_sec": 420,
        "expected_time_to_stop_sec": 240,
        "typical_target_move_pct": 0.60,
        "typical_stop_move_pct": 0.45,
    },
    "STRUCTURE": {
        "entry_horizon": "STRUCTURE_HOLD",
        "recommended_hold_window_sec": (600, 3600),
        "hard_max_hold_sec": 3600,
        "expected_time_to_target_sec": 1500,
        "expected_time_to_stop_sec": 700,
        "typical_target_move_pct": 0.50,
        "typical_stop_move_pct": 0.40,
    },
    "REVERSAL": {
        "entry_horizon": "REVERSAL_PROBE",
        "recommended_hold_window_sec": (300, 1500),
        "hard_max_hold_sec": 1500,
        "expected_time_to_target_sec": 540,
        "expected_time_to_stop_sec": 300,
        "typical_target_move_pct": 0.40,
        "typical_stop_move_pct": 0.35,
    },
    "CROSS_SECTIONAL": {
        "entry_horizon": "CROSS_SECTION_ROTATION",
        "recommended_hold_window_sec": (900, 7200),
        "hard_max_hold_sec": 7200,
        "expected_time_to_target_sec": 1800,
        "expected_time_to_stop_sec": 900,
        "typical_target_move_pct": 0.45,
        "typical_stop_move_pct": 0.40,
    },
    "DERIVATIVES": {
        "entry_horizon": "DERIV_BASIS",
        "recommended_hold_window_sec": (600, 3600),
        "hard_max_hold_sec": 3600,
        "expected_time_to_target_sec": 1200,
        "expected_time_to_stop_sec": 600,
        "typical_target_move_pct": 0.40,
        "typical_stop_move_pct": 0.35,
    },
}

DEFAULT_FAMILY = "TREND"
# Feasibility: expected move reachable if ATR/vol can cover target within horizon
MIN_FEASIBLE_VOL_COVER_RATIO = 0.85  # need ≥85% of target covered by expected path range


@dataclass
class ForecastMoveEstimate:
    forecast_horizon_sec: int
    expected_move_pct: float
    expected_move_method: str
    volatility_window: str
    sample_timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HorizonPlan:
    strategy_family: str
    entry_horizon: str
    expected_target_move_pct: float
    stop_move_pct: float
    target_price: float
    stop_price: float
    expected_time_to_target: float
    expected_time_to_stop: float
    recommended_hold_window: tuple[float, float]
    hard_max_hold: int
    provenance: str
    atr_pct: float | None = None
    expected_path_range_pct: float | None = None
    vol_cover_ratio: float | None = None
    forecast_horizon_sec: int | None = None
    expected_move_curve: list[dict[str, Any]] = field(default_factory=list)
    regime: str = "UNCERTAIN"
    activity_score: float | None = None
    liquidity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["recommended_hold_window"] = list(self.recommended_hold_window)
        return d


@dataclass
class HorizonFeasibilityResult:
    action: str  # PASS | WAIT
    horizon_feasibility_pass: bool
    economic_edge_pass: bool | None
    block_code: str | None
    reasons: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    plan: HorizonPlan | None = None
    shrunk_target_to_force_entry: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if self.plan is not None:
            out["plan"] = self.plan.to_dict()
        return out


def family_horizon_table(family: str) -> dict[str, Any]:
    key = str(family or DEFAULT_FAMILY).upper()
    return dict(FAMILY_HORIZON_DEFAULTS.get(key) or FAMILY_HORIZON_DEFAULTS[DEFAULT_FAMILY])


def estimate_atr_pct(
    *,
    atr_pct: float | None = None,
    realized_vol_pct_per_hour: float | None = None,
    regime: str = "UNCERTAIN",
) -> float:
    """ATR-like % move expectation. Prefer measured ATR; else vol; else regime prior."""
    if atr_pct is not None and float(atr_pct) > 0:
        return float(atr_pct)
    if realized_vol_pct_per_hour is not None and float(realized_vol_pct_per_hour) > 0:
        return float(realized_vol_pct_per_hour)
    regime_u = str(regime or "").upper()
    priors = {
        "HIGH_VOLATILITY": 0.90,
        "BREAKOUT": 0.70,
        "TREND_UP": 0.45,
        "TREND_DOWN": 0.45,
        "RANGE": 0.25,
        "LOW_VOLATILITY": 0.15,
        "LIQUIDITY_STRESS": 0.80,
        "CROWDING": 0.40,
        "UNCERTAIN": 0.35,
    }
    return float(priors.get(regime_u, 0.35))


def expected_path_range_pct(*, atr_pct: float, horizon_sec: float, activity: float = 0.7) -> float:
    """Scale ATR by sqrt(time/hour) and activity/liquidity dampener."""
    hours = max(1e-6, float(horizon_sec) / 3600.0)
    act = max(0.2, min(1.2, float(activity)))
    return float(atr_pct) * (hours**0.5) * act


def build_expected_move_curve(
    *,
    atr_pct: float,
    activity: float = 0.7,
    liquidity: float = 0.9,
    horizons_sec: tuple[int, ...] = STANDARD_FORECAST_HORIZONS_SEC,
    sample_timestamp: int | None = None,
) -> list[ForecastMoveEstimate]:
    """Feasibility curve — not price certainty. Uses actual ATR/vol input only."""
    ts = int(sample_timestamp or time.time())
    act = max(0.2, min(1.2, float(activity) * float(liquidity)))
    out: list[ForecastMoveEstimate] = []
    for h in horizons_sec:
        move = expected_path_range_pct(atr_pct=float(atr_pct), horizon_sec=float(h), activity=act)
        out.append(
            ForecastMoveEstimate(
                forecast_horizon_sec=int(h),
                expected_move_pct=float(move),
                expected_move_method="ATR_SQRT_TIME_SCALED",
                volatility_window=f"atr_pct={atr_pct:.6f}",
                sample_timestamp=ts,
            )
        )
    return out


def compatible_forecast_horizon_sec(plan: HorizonPlan) -> int:
    """Horizon used to compare target_move_pct vs expected_move — must match strategy thesis."""
    win = plan.recommended_hold_window
    ett = int(plan.expected_time_to_target or win[0])
    # Compare at strategy expected time-to-target, clamped inside recommended window and hard max
    return int(max(win[0], min(float(plan.hard_max_hold), float(ett))))


def validate_horizon_configuration(
    plan: HorizonPlan,
    *,
    allow_expected_time_exceeds_hard: bool = False,
) -> tuple[bool, list[str], str | None]:
    """PreparedDecision must fail if hold config is internally inconsistent."""
    blocks: list[str] = []
    reasons: list[str] = []
    win_min = float(plan.recommended_hold_window[0])
    hard = float(plan.hard_max_hold)
    ett = float(plan.expected_time_to_target or win_min)

    if hard + 1e-9 < win_min:
        blocks.append(INVALID_HORIZON_CONFIGURATION)
        reasons.append(
            f"hard_max_hold={hard:.0f}s < recommended_hold_window_min={win_min:.0f}s"
        )
    if ett > hard + 1e-9 and not allow_expected_time_exceeds_hard:
        blocks.append(INVALID_HORIZON_CONFIGURATION)
        reasons.append(f"expected_time_to_target={ett:.0f}s > hard_max_hold={hard:.0f}s")

    ok = not blocks
    return ok, reasons, (blocks[0] if blocks else None)


def build_horizon_plan(
    *,
    strategy_family: str,
    side: str,
    entry_price: float,
    expected_target_move_pct: float | None = None,
    stop_move_pct: float | None = None,
    atr_pct: float | None = None,
    realized_vol_pct_per_hour: float | None = None,
    regime: str = "UNCERTAIN",
    activity_score: float = 0.7,
    liquidity: float = 0.9,
    hard_max_hold_override: int | None = None,
) -> HorizonPlan:
    table = family_horizon_table(strategy_family)
    tgt = float(
        expected_target_move_pct
        if expected_target_move_pct is not None
        else table["typical_target_move_pct"]
    )
    stop = float(stop_move_pct if stop_move_pct is not None else table["typical_stop_move_pct"])
    hard = int(hard_max_hold_override or table["hard_max_hold_sec"])
    win = tuple(table["recommended_hold_window_sec"])
    atr = estimate_atr_pct(
        atr_pct=atr_pct, realized_vol_pct_per_hour=realized_vol_pct_per_hour, regime=regime
    )
    # Expected times scale with target/ATR; clamp into recommended window
    ett = float(table["expected_time_to_target_sec"])
    ets = float(table["expected_time_to_stop_sec"])
    if atr > 1e-9:
        # time ~ (target/atr)^2 hours → seconds; clamp into [win_min, hard]
        ett = max(win[0] * 0.5, min(hard, (tgt / atr) ** 2 * 3600.0))
        ets = max(win[0] * 0.25, min(hard, (stop / atr) ** 2 * 3600.0))
    move_curve = build_expected_move_curve(
        atr_pct=atr,
        activity=activity_score,
        liquidity=liquidity,
    )
    forecast_h = int(max(win[0], min(hard, ett)))
    path = expected_path_range_pct(
        atr_pct=atr, horizon_sec=float(forecast_h), activity=activity_score * liquidity
    )
    cover = (path / tgt) if tgt > 1e-12 else 0.0
    px = float(entry_price)
    side_u = str(side or "LONG").upper()
    if side_u in {"LONG", "BUY"}:
        target_price = px * (1.0 + tgt / 100.0)
        stop_price = px * (1.0 - stop / 100.0)
    else:
        target_price = px * (1.0 - tgt / 100.0)
        stop_price = px * (1.0 + stop / 100.0)
    return HorizonPlan(
        strategy_family=str(strategy_family or DEFAULT_FAMILY).upper(),
        entry_horizon=str(table["entry_horizon"]),
        expected_target_move_pct=tgt,
        stop_move_pct=stop,
        target_price=target_price,
        stop_price=stop_price,
        expected_time_to_target=float(ett),
        expected_time_to_stop=float(ets),
        recommended_hold_window=(float(win[0]), float(win[1])),
        hard_max_hold=hard,
        provenance="RESEARCH_DEMO_FAMILY_TABLE_V26+ATR_SCALED+SAME_HORIZON",
        atr_pct=atr,
        expected_path_range_pct=path,
        vol_cover_ratio=cover,
        forecast_horizon_sec=forecast_h,
        expected_move_curve=[e.to_dict() for e in move_curve],
        regime=str(regime or "UNCERTAIN"),
        activity_score=float(activity_score),
        liquidity=float(liquidity),
    )


def evaluate_horizon_feasibility(
    *,
    plan: HorizonPlan,
    economic_edge_pass: bool | None = None,
    min_cover_ratio: float = MIN_FEASIBLE_VOL_COVER_RATIO,
    forbid_shrink_target: bool = True,
) -> HorizonFeasibilityResult:
    """Both ECONOMIC_EDGE_PASS and HORIZON_FEASIBILITY_PASS required to enter."""
    blocks: list[str] = []
    reasons: list[str] = []

    cfg_ok, cfg_reasons, cfg_block = validate_horizon_configuration(plan)
    if not cfg_ok:
        blocks.extend([cfg_block or INVALID_HORIZON_CONFIGURATION])
        reasons.extend(cfg_reasons)
        return HorizonFeasibilityResult(
            action="WAIT",
            horizon_feasibility_pass=False,
            economic_edge_pass=economic_edge_pass,
            block_code=cfg_block,
            reasons=reasons + ["INVALID_HORIZON_CONFIG_do_not_silently_clamp"],
            blocks=blocks,
            plan=plan,
            shrunk_target_to_force_entry=False,
        )

    # Same-horizon comparison: expected move at forecast_horizon_sec vs target
    fh = int(plan.forecast_horizon_sec or compatible_forecast_horizon_sec(plan))
    curve = plan.expected_move_curve or []
    path_at_fh = plan.expected_path_range_pct
    if curve:
        for pt in curve:
            if int(pt.get("forecast_horizon_sec") or 0) == fh:
                path_at_fh = float(pt.get("expected_move_pct") or path_at_fh or 0.0)
                break
    tgt = float(plan.expected_target_move_pct)
    cover = (float(path_at_fh or 0.0) / tgt) if tgt > 1e-12 else 0.0
    if cover + 1e-12 < float(min_cover_ratio):
        blocks.append("HORIZON_TARGET_MISMATCH")
        reasons.append(
            f"expected_move_pct@{fh}s={float(path_at_fh or 0.0):.4f} "
            f"< target={tgt:.4f} (cover={cover:.3f}<{min_cover_ratio})"
        )
        reasons.append("WAIT_do_not_shrink_target_to_force_entry")
        reasons.append(f"same_horizon_forecast_sec={fh}")
    else:
        reasons.append(f"horizon_cover_ok={cover:.3f}@forecast_horizon_sec={fh}")

    if plan.liquidity is not None and float(plan.liquidity) < 0.25:
        blocks.append("liquidity_too_thin_for_horizon")
        reasons.append(f"liquidity={plan.liquidity}")

    if plan.hard_max_hold < 60:
        blocks.append("hard_max_hold_transport_like")
        reasons.append("hard_max_hold looks like transport timer (<60s)")

    horizon_pass = not blocks
    econ_ok = economic_edge_pass
    action = "PASS"
    block_code = None
    if not horizon_pass:
        action = "WAIT"
        block_code = blocks[0]
    elif econ_ok is False:
        action = "WAIT"
        block_code = "ECONOMIC_EDGE_FAIL"
        blocks.append("ECONOMIC_EDGE_FAIL")
        reasons.append("economic_edge_not_passed")
    else:
        reasons.append("HORIZON_FEASIBILITY_PASS")
        if econ_ok is True:
            reasons.append("ECONOMIC_EDGE_PASS")

    return HorizonFeasibilityResult(
        action=action,
        horizon_feasibility_pass=horizon_pass,
        economic_edge_pass=econ_ok,
        block_code=block_code,
        reasons=reasons,
        blocks=blocks,
        plan=plan,
        shrunk_target_to_force_entry=False if forbid_shrink_target else False,
    )


def annotate_prepared_decision_horizon(decision: dict[str, Any], plan: HorizonPlan) -> dict[str, Any]:
    """Attach required PreparedDecision horizon fields."""
    out = dict(decision)
    out.update(
        {
            "strategy_family": plan.strategy_family,
            "entry_horizon": plan.entry_horizon,
            "expected_target_move_pct": plan.expected_target_move_pct,
            "stop_move_pct": plan.stop_move_pct,
            "target_price": plan.target_price,
            "stop_price": plan.stop_price,
            "expected_time_to_target": plan.expected_time_to_target,
            "expected_time_to_stop": plan.expected_time_to_stop,
            "recommended_hold_window": list(plan.recommended_hold_window),
            "hard_max_hold": plan.hard_max_hold,
            "max_hold": plan.hard_max_hold,  # alias — thesis expired, not transport
            "forecast_horizon_sec": plan.forecast_horizon_sec,
            "expected_move_curve": plan.expected_move_curve,
            "horizon_provenance": plan.provenance,
            "stop_logic": {
                **dict(out.get("stop_logic") or {}),
                "price": plan.stop_price,
                "pct": plan.stop_move_pct,
            },
            "take_profit_logic": {
                **dict(out.get("take_profit_logic") or {}),
                "price": plan.target_price,
                "pct": plan.expected_target_move_pct,
            },
        }
    )
    return out

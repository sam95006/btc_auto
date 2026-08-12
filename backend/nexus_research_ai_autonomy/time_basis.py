"""Time-basis consistency — re-exports and helpers atop horizon_feasibility V26."""
from __future__ import annotations

from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    INVALID_HORIZON_CONFIGURATION,
    STANDARD_FORECAST_HORIZONS_SEC,
    ForecastMoveEstimate,
    build_expected_move_curve,
    compatible_forecast_horizon_sec,
    estimate_atr_pct,
    expected_path_range_pct,
    validate_horizon_configuration,
)

CURVE_HORIZONS_SEC = STANDARD_FORECAST_HORIZONS_SEC
CURVE_LABELS: dict[int, str] = {300: "5m", 900: "15m", 1800: "30m", 3600: "60m"}

# Alias for tests / runners
ExpectedMoveEstimate = ForecastMoveEstimate


def resolve_strategy_horizon_sec(*, strategy_family: str, hard_max_hold: int | float | None = None) -> float:
    from backend.nexus_research_ai_autonomy.horizon_feasibility import family_horizon_table

    table = family_horizon_table(strategy_family)
    ett = float(table.get("expected_time_to_target_sec") or 1200)
    hard = float(hard_max_hold) if hard_max_hold is not None else float(table.get("hard_max_hold_sec") or ett)
    return min(ett, hard) if hard > 0 else ett


def evaluate_compatible_horizon_feasibility(
    *,
    target_move_pct: float,
    strategy_horizon_sec: float,
    curve: list,
    economic_edge_pass: bool | None = None,
    min_cover_ratio: float = 0.85,
) -> dict:
    """Compare target vs curve point at same horizon."""
    from backend.nexus_research_ai_autonomy.horizon_feasibility import MIN_FEASIBLE_VOL_COVER_RATIO

    min_cover_ratio = min_cover_ratio or MIN_FEASIBLE_VOL_COVER_RATIO
    path = None
    hz = int(strategy_horizon_sec)
    for pt in curve:
        d = pt.to_dict() if hasattr(pt, "to_dict") else pt
        if int(d.get("forecast_horizon_sec") or 0) == hz:
            path = float(d.get("expected_move_pct") or 0)
            break
    if path is None and curve:
        last = curve[-1]
        d = last.to_dict() if hasattr(last, "to_dict") else last
        path = float(d.get("expected_move_pct") or 0)
    path = path or 0.0
    cover = (path / target_move_pct) if target_move_pct > 1e-12 else 0.0
    blocks = []
    reasons = []
    if cover + 1e-12 < min_cover_ratio:
        blocks.append("HORIZON_TARGET_MISMATCH")
        reasons.append(f"expected_path_at_{hz}s={path:.4f} < target={target_move_pct:.4f}")
    horizon_pass = not blocks
    return {
        "action": "PASS" if horizon_pass and economic_edge_pass is not False else "WAIT",
        "horizon_feasibility_pass": horizon_pass,
        "economic_edge_pass": economic_edge_pass,
        "block_code": blocks[0] if blocks else None,
        "reasons": reasons,
        "blocks": blocks,
        "strategy_horizon_sec": hz,
        "expected_path_range_pct": path,
        "vol_cover_ratio": cover,
        "time_basis": "COMPATIBLE_HORIZON",
    }

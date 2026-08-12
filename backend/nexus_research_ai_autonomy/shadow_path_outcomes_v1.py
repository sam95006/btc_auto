"""Shadow path outcome evaluation — fixed entry timestamp, no hindsight optimization."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, _float
from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    record_shadow_outcome,
    shadow_dir,
)

# Observational horizons (seconds)
SHADOW_HORIZONS_SEC = (60, 180, 300, 900, 1800)

# Research-only alternative configs — NEVER auto-promoted to live STOP/TARGET
RESEARCH_CONFIGS = (
    {"name": "champion_v30", "stop_pct": 0.40, "target_pct": 0.55, "trail_pct": 0.30},
    {"name": "wider_stop", "stop_pct": 0.60, "target_pct": 0.55, "trail_pct": 0.30},
    {"name": "tighter_target", "stop_pct": 0.40, "target_pct": 0.35, "trail_pct": 0.25},
    {"name": "wider_both", "stop_pct": 0.70, "target_pct": 0.80, "trail_pct": 0.40},
    {"name": "narrow_scalp", "stop_pct": 0.25, "target_pct": 0.30, "trail_pct": 0.20},
)

DEFAULT_FEE_RATE_RT = 0.0011


def _fetch_closes_after(
    client: DemoWriteClient,
    *,
    symbol: str,
    entry_ts_ms: int,
    horizon_sec: int,
) -> list[tuple[int, float]]:
    """Return (ts_ms, close) points within [entry, entry+horizon] from 1m klines.

    Entry timestamp is fixed — never re-optimize entry using future data.
    """
    try:
        raw = client.public_get(
            "/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "1",
                "limit": "200",
            },
        )
        rows = (raw.get("result") or {}).get("list") or []
    except Exception:  # noqa: BLE001
        return []

    points: list[tuple[int, float]] = []
    end_ms = int(entry_ts_ms) + int(horizon_sec) * 1000
    for r in rows:
        if isinstance(r, (list, tuple)) and len(r) >= 5:
            ts = int(float(r[0]))
            close = float(r[4])
        elif isinstance(r, dict):
            ts = int(_float(r.get("startTime") or r.get("start") or 0))
            close = _float(r.get("close") or r.get("c"))
        else:
            continue
        if close <= 0:
            continue
        if entry_ts_ms <= ts <= end_ms:
            points.append((ts, close))
    points.sort(key=lambda x: x[0])
    return points


def evaluate_path_mfe_mae(
    *,
    entry_price: float,
    direction: str,
    path: list[tuple[int, float]],
    stop_pct: float,
    target_pct: float,
    notional: float = 350.0,
    fee_rate_rt: float = DEFAULT_FEE_RATE_RT,
) -> dict[str, Any]:
    """Compute MFE/MAE and first-touch target-vs-stop on a fixed path."""
    if entry_price <= 0 or not path:
        return {
            "MFE": None,
            "MAE": None,
            "target_before_stop": None,
            "stop_before_target": None,
            "post_cost_hypothetical": None,
            "path_points": 0,
        }

    side = str(direction or "LONG").upper()
    mfe_pct = 0.0
    mae_pct = 0.0
    target_hit_first: bool | None = None
    stop_hit_first: bool | None = None
    exit_pct = 0.0

    for _, px in path:
        if side == "LONG":
            move = (px - entry_price) / entry_price * 100.0
        else:
            move = (entry_price - px) / entry_price * 100.0
        mfe_pct = max(mfe_pct, move)
        mae_pct = min(mae_pct, move)
        if target_hit_first is None and stop_hit_first is None:
            if move >= target_pct:
                target_hit_first = True
                stop_hit_first = False
                exit_pct = target_pct
            elif move <= -stop_pct:
                target_hit_first = False
                stop_hit_first = True
                exit_pct = -stop_pct

    if target_hit_first is None:
        # Horizon expired — mark-to-market at last close
        last = path[-1][1]
        if side == "LONG":
            exit_pct = (last - entry_price) / entry_price * 100.0
        else:
            exit_pct = (entry_price - last) / entry_price * 100.0

    gross = notional * (exit_pct / 100.0)
    cost = notional * fee_rate_rt
    net = gross - cost
    mfe_usdt = notional * (mfe_pct / 100.0)
    mae_usdt = notional * (mae_pct / 100.0)

    return {
        "MFE": round(mfe_usdt, 6),
        "MAE": round(mae_usdt, 6),
        "mfe_pct": round(mfe_pct, 6),
        "mae_pct": round(mae_pct, 6),
        "target_before_stop": target_hit_first,
        "stop_before_target": stop_hit_first,
        "exit_pct": round(exit_pct, 6),
        "gross_hypothetical": round(gross, 6),
        "estimated_cost": round(cost, 6),
        "post_cost_hypothetical": round(net, 6),
        "path_points": len(path),
        "stop_pct": stop_pct,
        "target_pct": target_pct,
    }


def evaluate_signal_horizons(
    client: DemoWriteClient,
    *,
    signal: dict[str, Any],
    campaign_root: Path,
    stop_pct: float = 0.40,
    target_pct: float = 0.55,
    notional: float = 350.0,
    horizons: tuple[int, ...] = SHADOW_HORIZONS_SEC,
) -> list[dict[str, Any]]:
    """Evaluate mature horizons for one shadow signal; persist outcomes."""
    symbol = str(signal.get("symbol") or "")
    entry = float(signal.get("entry_price") or 0)
    direction = str(signal.get("direction") or "LONG")
    entry_ts = int(signal.get("detected_at_ms") or 0)
    signal_id = str(signal.get("signal_id") or "")
    if not symbol or entry <= 0 or entry_ts <= 0 or not signal_id:
        return []

    now_ms = int(time.time() * 1000)
    results: list[dict[str, Any]] = []
    for h in horizons:
        if now_ms < entry_ts + h * 1000:
            # Horizon not yet mature — skip (no future peek)
            continue
        path = _fetch_closes_after(client, symbol=symbol, entry_ts_ms=entry_ts, horizon_sec=h)
        metrics = evaluate_path_mfe_mae(
            entry_price=entry,
            direction=direction,
            path=path,
            stop_pct=stop_pct,
            target_pct=target_pct,
            notional=notional,
        )
        metrics["horizon_sec"] = h
        metrics["signal_id"] = signal_id
        metrics["symbol"] = symbol
        metrics["direction"] = direction
        metrics["entry_price"] = entry
        metrics["entry_ts_ms"] = entry_ts
        record_shadow_outcome(
            campaign_root,
            signal_id=signal_id,
            horizon_sec=h,
            mfe=metrics.get("MFE"),
            mae=metrics.get("MAE"),
            post_cost_hypothetical=metrics.get("post_cost_hypothetical"),
            target_before_stop=metrics.get("target_before_stop"),
        )
        results.append(metrics)
    return results


def load_active_shadow_signals(campaign_root: Path) -> list[dict[str, Any]]:
    path = shadow_dir(campaign_root) / "active_shadow_signals_latest.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("signals") or [])
    except Exception:  # noqa: BLE001
        return []


def refresh_mature_shadow_outcomes(
    client: DemoWriteClient,
    *,
    campaign_root: Path,
) -> dict[str, Any]:
    """Evaluate all active READY/WATCH signals whose horizons have matured."""
    signals = load_active_shadow_signals(campaign_root)
    evaluated = 0
    outcomes: list[dict[str, Any]] = []
    for sig in signals:
        if sig.get("lifecycle_state") not in {"READY", "WATCH", "DETECTED"}:
            continue
        rows = evaluate_signal_horizons(client, signal=sig, campaign_root=campaign_root)
        if rows:
            evaluated += 1
            outcomes.extend(rows)
            sig["lifecycle_state"] = "OUTCOME"
            sig["outcome"] = rows[-1]
    # Persist updated lifecycle states
    if signals:
        from backend.nexus_research_ai_autonomy.shadow_signal_v1 import persist_shadow_signals

        persist_shadow_signals(campaign_root, signals)
    return {
        "signals_checked": len(signals),
        "signals_evaluated": evaluated,
        "outcomes_written": len(outcomes),
        "horizons": list(SHADOW_HORIZONS_SEC),
    }

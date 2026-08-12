"""Feature availability + signal evaluation for V15-C mechanisms on development panels."""
from __future__ import annotations

import math
from typing import Any

from backend.nexus_dev_research_campaign_v15.constants import DERIVABLE_FEATURES
from backend.nexus_dev_research_campaign_v15.data import DevelopmentBar, DevelopmentPanel, regime_label
from backend.nexus_mechanism_lab_v4.catalog import MechanismSpec


TIMESTAMP_FEATURES = frozenset({"exchange_ts_ms", "receive_ts_ms"})


def available_feature_set(panel: DevelopmentPanel) -> set[str]:
    """Features derivable from the loaded development panel (not invented micro)."""
    feats = set(DERIVABLE_FEATURES)
    # Drop funding/OI derived if no observations present.
    has_fund = any(
        b.funding_rate is not None
        for bars in panel.bars_by_symbol.values()
        for b in bars
    )
    has_oi = any(
        b.open_interest is not None
        for bars in panel.bars_by_symbol.values()
        for b in bars
    )
    if not has_fund:
        feats.discard("funding_z")
        feats.discard("funding_rate")
    if not has_oi:
        feats.discard("oi_change")
    if len(panel.symbols) < 2:
        feats.discard("lead_return")
        feats.discard("lag_return")
        feats.discard("lead_lag_score")
        feats.discard("cross_corr")
        feats.discard("pair_residual")
    return feats


def missing_required(spec: MechanismSpec, available: set[str]) -> list[str]:
    missing: list[str] = []
    for feat in spec.required_data:
        if feat in TIMESTAMP_FEATURES:
            continue
        # Map aliases that we can satisfy via proxies.
        if feat == "spread_bps" and "spread_bps_range_proxy" in available:
            continue
        if feat in available:
            continue
        # Some catalog features map onto derivable proxies:
        alias = {
            "range_low_break": "range_low_break",
            "vol_expansion": "range_expansion",
            "vol_compression": "range_compression",
        }.get(feat)
        if alias and alias in available:
            continue
        missing.append(feat)
    return missing


def _rolling_std(xs: list[float], i: int, win: int = 24) -> float:
    lo = max(0, i - win + 1)
    window = xs[lo : i + 1]
    if len(window) < 3:
        return 0.0
    m = sum(window) / len(window)
    var = sum((x - m) ** 2 for x in window) / len(window)
    return math.sqrt(var)


def enrich_symbol_bars(bars: list[DevelopmentBar]) -> list[dict[str, Any]]:
    """Point-in-time feature rows — no lookahead beyond index i."""
    closes = [b.mid for b in bars]
    rets = [b.mid_return for b in bars]
    vols = [b.volume for b in bars]
    funds = [b.funding_rate if b.funding_rate is not None else float("nan") for b in bars]
    ois = [b.open_interest if b.open_interest is not None else float("nan") for b in bars]
    rows: list[dict[str, Any]] = []
    for i, b in enumerate(bars):
        rng = (b.high - b.low) / b.mid if b.mid else 0.0
        # rolling range mean for expansion/compression
        lo = max(0, i - 23)
        rngs = [((bars[j].high - bars[j].low) / bars[j].mid if bars[j].mid else 0.0) for j in range(lo, i + 1)]
        mean_rng = sum(rngs) / len(rngs)
        range_expansion = rng - mean_rng
        range_compression = mean_rng - rng
        range_compression_lag = 0.0
        if i >= 1:
            prev = bars[i - 1]
            prev_rng = (prev.high - prev.low) / prev.mid if prev.mid else 0.0
            range_compression_lag = mean_rng - prev_rng
        # level break vs 24-bar high/low
        win_hi = max(bars[j].high for j in range(lo, i + 1))
        win_lo = min(bars[j].low for j in range(lo, i + 1))
        range_high_break = 1.0 if b.close >= win_hi and i > lo else 0.0
        range_low_break = 1.0 if b.close <= win_lo and i > lo else 0.0
        # volume z
        v_lo = max(0, i - 47)
        vwin = vols[v_lo : i + 1]
        vmean = sum(vwin) / len(vwin)
        vstd = math.sqrt(sum((x - vmean) ** 2 for x in vwin) / len(vwin)) or 1e-9
        volume_z = (b.volume - vmean) / vstd
        # volume-price divergence: rising volume with falling price or vice versa
        volume_price_divergence = volume_z * (-1.0 if b.mid_return < 0 else 1.0)
        rvol = _rolling_std(rets, i, 24)
        # funding z
        funding_z = None
        if not math.isnan(funds[i]):
            f_lo = max(0, i - 47)
            fwin = [x for x in funds[f_lo : i + 1] if not math.isnan(x)]
            if len(fwin) >= 5:
                fm = sum(fwin) / len(fwin)
                fs = math.sqrt(sum((x - fm) ** 2 for x in fwin) / len(fwin)) or 1e-12
                funding_z = (funds[i] - fm) / fs
        oi_change = None
        if i >= 1 and not math.isnan(ois[i]) and not math.isnan(ois[i - 1]) and ois[i - 1] != 0:
            oi_change = (ois[i] - ois[i - 1]) / abs(ois[i - 1])
        # breakout fail: prior break then reverse
        breakout_fail_flag = 0.0
        if i >= 2 and rows[i - 1].get("range_high_break", 0) > 0 and b.mid_return < 0:
            breakout_fail_flag = 1.0
        if i >= 2 and rows[i - 1].get("range_low_break", 0) > 0 and b.mid_return > 0:
            breakout_fail_flag = 1.0
        dist_bps = 0.0
        if win_hi > 0:
            dist_bps = abs(b.close - win_hi) / b.close * 10_000.0
        hour = (b.ts_ms // 3_600_000) % 24
        session = "ASIA" if hour < 8 else ("EU" if hour < 16 else "US")
        rows.append(
            {
                "ts_ms": b.ts_ms,
                "symbol": b.symbol,
                "mid": b.mid,
                "mid_return": b.mid_return,
                "exchange_ts_ms": b.ts_ms,
                "receive_ts_ms": b.ts_ms,
                "range_expansion": range_expansion,
                "range_compression": range_compression,
                "range_compression_lag": range_compression_lag,
                "range_high_break": range_high_break,
                "range_low_break": range_low_break,
                "volume_z": volume_z,
                "volume_price_divergence": volume_price_divergence,
                "tod_hour_utc": hour,
                "tod_session_bucket": session,
                "funding_z": funding_z,
                "funding_rate": None if math.isnan(funds[i]) else funds[i],
                "oi_change": oi_change,
                "realized_vol": rvol,
                "spread_bps_range_proxy": rng * 10_000.0 * 0.25,
                "spread_bps": rng * 10_000.0 * 0.25,  # proxy alias; provenance noted elsewhere
                "distance_to_level_bps": dist_bps,
                "breakout_fail_flag": breakout_fail_flag,
                "regime": regime_label(b.mid_return, rvol),
                "data_quality_ok": b.data_quality_ok,
            }
        )
    return rows


def attach_cross_asset(rows_by_symbol: dict[str, list[dict[str, Any]]], symbols: list[str]) -> None:
    """Add lead/lag features using BTC as lead when present, else first symbol."""
    if len(symbols) < 2:
        return
    lead_sym = "BTCUSDT" if "BTCUSDT" in symbols else symbols[0]
    lead_rows = rows_by_symbol.get(lead_sym) or []
    lead_by_ts = {r["ts_ms"]: r for r in lead_rows}
    for sym in symbols:
        if sym == lead_sym:
            for r in rows_by_symbol[sym]:
                r["lead_return"] = r["mid_return"]
                r["lag_return"] = r["mid_return"]
                r["lead_lag_score"] = 0.0
                r["cross_corr"] = 1.0
                r["pair_residual"] = 0.0
            continue
        for r in rows_by_symbol[sym]:
            lead = lead_by_ts.get(r["ts_ms"])
            if lead is None:
                r["lead_return"] = None
                r["lag_return"] = r["mid_return"]
                r["lead_lag_score"] = None
                r["cross_corr"] = None
                r["pair_residual"] = None
                continue
            r["lead_return"] = lead["mid_return"]
            r["lag_return"] = r["mid_return"]
            r["lead_lag_score"] = float(lead["mid_return"]) - float(r["mid_return"])
            r["cross_corr"] = 1.0 if lead["mid_return"] * r["mid_return"] > 0 else -1.0
            r["pair_residual"] = float(r["mid_return"]) - float(lead["mid_return"])


def signal_for_spec(spec: MechanismSpec, row: dict[str, Any], prev: dict[str, Any] | None) -> int | None:
    """Return +1 / -1 / None from PIT features. Conservative development thresholds."""
    kind = spec.signal_kind
    primary = spec.primary_feature
    # Resolve feature with proxy fallbacks
    def _get(name: str) -> Any:
        if name == "spread_bps":
            return row.get("spread_bps_range_proxy", row.get("spread_bps"))
        return row.get(name)

    p = _get(primary)
    if p is None:
        return None

    mode = spec.direction_mode
    if kind in {"signed_threshold", "continuation"} or mode == "continuation":
        if primary in {"range_expansion", "range_high_break", "oi_change", "funding_z", "volume_z"}:
            thr = 0.0
            if primary == "range_expansion":
                thr = 0.002
            elif primary in {"range_high_break", "breakout_fail_flag"}:
                if float(p) <= 0:
                    return None
                return 1
            elif primary == "funding_z":
                thr = 1.0
            elif primary == "oi_change":
                thr = 0.01
            elif primary == "volume_z":
                thr = 1.25
            if abs(float(p)) <= thr:
                return None
            sig = 1 if float(p) > 0 else -1
            return sig
        if primary in {"mid_return", "lead_return", "lead_lag_score", "pair_residual"}:
            if abs(float(p)) < 0.0015:
                return None
            return 1 if float(p) > 0 else -1

    if kind in {"fade", "exhaustion"} or mode == "fade":
        if primary in {"range_expansion", "funding_z", "volume_z", "oi_change", "mid_return"}:
            thr = 1.5 if primary in {"funding_z", "volume_z"} else 0.003
            if abs(float(p)) < thr:
                return None
            return -1 if float(p) > 0 else 1
        if primary == "breakout_fail_flag":
            if float(p) <= 0:
                return None
            # fade prior direction using prev mid_return
            if prev is None:
                return None
            pr = float(prev.get("mid_return") or 0.0)
            if abs(pr) < 1e-9:
                return None
            return -1 if pr > 0 else 1

    if kind in {"divergence", "mean_reversion"} or "MEAN_REVERSION" in spec.family:
        mr = float(row.get("mid_return") or 0.0)
        if abs(mr) < 0.001:
            return None
        return -1 if mr > 0 else 1

    if "TIME_OF_DAY" in spec.family or primary in {"tod_hour_utc", "tod_session_bucket"}:
        hour = int(row.get("tod_hour_utc") or 0)
        # development hypothesis: fade overnight US close hour cluster
        if hour in {13, 14, 20, 21}:
            mr = float(row.get("mid_return") or 0.0)
            if abs(mr) < 0.0005:
                return None
            return -1 if mr > 0 else 1
        return None

    if "VOL_EXPANSION" in spec.family:
        if float(row.get("range_expansion") or 0.0) <= 0.002:
            return None
        mr = float(row.get("mid_return") or 0.0)
        return 1 if mr > 0 else -1 if mr < 0 else None

    if "VOL_COMPRESSION" in spec.family:
        if float(row.get("range_compression") or 0.0) <= 0.001:
            return None
        # breakout anticipation: direction of last return
        mr = float(row.get("mid_return") or 0.0)
        return 1 if mr >= 0 else -1

    if "BREAKOUT" in spec.family:
        if float(row.get("range_high_break") or 0.0) > 0:
            return 1
        if float(row.get("range_low_break") or 0.0) > 0:
            return -1
        return None

    if "FAILED_BREAKOUT" in spec.family:
        if float(row.get("breakout_fail_flag") or 0.0) <= 0:
            return None
        mr = float(prev.get("mid_return") or 0.0) if prev else 0.0
        return -1 if mr > 0 else 1 if mr < 0 else None

    if "VOLUME_PRICE" in spec.family:
        vpd = float(row.get("volume_price_divergence") or 0.0)
        if abs(vpd) < 1.0:
            return None
        return 1 if vpd > 0 else -1

    if "FUNDING" in spec.family:
        fz = row.get("funding_z")
        if fz is None or abs(float(fz)) < 1.25:
            return None
        return -1 if float(fz) > 0 else 1

    if "OI_DISLOCATION" in spec.family:
        oi = row.get("oi_change")
        if oi is None or abs(float(oi)) < 0.015:
            return None
        mr = float(row.get("mid_return") or 0.0)
        # OI up + price up continuation; OI up + price down fade inventory
        if float(oi) > 0 and mr > 0:
            return 1
        if float(oi) > 0 and mr < 0:
            return -1
        return None

    if "CROSS_ASSET" in spec.family or "LEAD_LAG" in spec.family:
        score = row.get("lead_lag_score")
        if score is None or abs(float(score)) < 0.002:
            return None
        return 1 if float(score) > 0 else -1

    # Default: unsigned dormant
    return None

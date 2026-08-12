"""V17-G single-authority feature formulas (pure, deterministic, PIT-safe)."""
from __future__ import annotations

import math
from typing import Any, Optional

from backend.nexus_gold_feature_factory.catalog import FEATURE_CATALOG
from backend.nexus_gold_feature_factory.constants import (
    DEFAULT_LOOKBACK_BARS,
    DEFAULT_STALE_AFTER_MS,
    FEATURE_VERSION,
)
from backend.nexus_gold_feature_factory.guards import (
    assert_no_future_price_labels,
    assert_observation_marks_missing,
)
from backend.nexus_gold_feature_factory.hashing import calculation_hash, fingerprint_rows
from backend.nexus_gold_feature_factory.types import FeatureObservation


def _pit_filter(
    rows: list[dict[str, Any]],
    *,
    as_of: int,
    ts_key: str = "exchange_ts",
    recv_key: str = "receive_ts",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        ex = r.get(ts_key)
        recv = r.get(recv_key)
        if ex is None or recv is None:
            continue
        if int(ex) <= as_of and int(recv) <= as_of:
            out.append(r)
    return out


def _available_at(rows: list[dict[str, Any]]) -> Optional[int]:
    if not rows:
        return None
    return max(int(r["receive_ts"]) for r in rows)


def _stale(as_of: int, available_at: Optional[int]) -> tuple[bool, Optional[int]]:
    if available_at is None:
        return False, None
    staleness = max(0, int(as_of) - int(available_at))
    return staleness > DEFAULT_STALE_AFTER_MS, staleness


def _log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a <= 0 or b <= 0:
            continue
        out.append(math.log(b / a))
    return out


def _mean(xs: list[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def _std(xs: list[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def _obs(
    feature_id: str,
    *,
    value: Any,
    quality: str,
    as_of: int,
    available_at: Optional[int],
    lookback: int,
    inputs_fingerprint: str,
    reason: Optional[str] = None,
    extras: Optional[dict[str, Any]] = None,
) -> FeatureObservation:
    meta = FEATURE_CATALOG[feature_id]
    stale, staleness_ms = _stale(as_of, available_at)
    ch = calculation_hash(
        feature_id=feature_id,
        formula_id=meta["formula_id"],
        feature_version=FEATURE_VERSION,
        lookback=lookback,
        normalization=meta["normalization"],
        inputs_fingerprint=inputs_fingerprint,
        as_of=as_of,
    )
    observation = FeatureObservation(
        feature_id=feature_id,
        value=value,
        quality=quality,
        feature_version=FEATURE_VERSION,
        source_lineage=tuple(meta["source_lineage"]),
        as_of=as_of,
        available_at=available_at,
        lookback=lookback,
        normalization=meta["normalization"],
        missing_policy=meta["missing_policy"],
        license_scope=meta["license_scope"],
        calculation_hash=ch,
        definition=meta["definition"],
        units=meta["units"],
        reason=reason,
        stale=stale,
        staleness_ms=staleness_ms,
        extras=extras or {},
    )
    assert_observation_marks_missing(observation.to_dict())
    return observation


def compute_trend(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    primary = market["primary_symbol"]
    bars = _pit_filter(market["ohlcv"][primary], as_of=as_of)[-lookback:]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[b["exchange_ts"] for b in bars])
    fp = fingerprint_rows(bars, ("exchange_ts", "close"))
    if len(bars) < max(3, lookback // 2):
        return _obs(
            "trend",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(bars),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="insufficient_bars",
        )
    closes = [float(b["close"]) for b in bars]
    n = len(closes)
    x_mean = (n - 1) / 2.0
    y_mean = sum(closes) / n
    num = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den else 0.0
    value = slope / y_mean if y_mean else None
    quality = "COMPLETE" if len(bars) >= lookback else "PARTIAL"
    if value is None:
        return _obs(
            "trend",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(bars),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="zero_mean_close",
        )
    return _obs(
        "trend",
        value=value,
        quality=quality,
        as_of=as_of,
        available_at=_available_at(bars),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_volatility(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    primary = market["primary_symbol"]
    bars = _pit_filter(market["ohlcv"][primary], as_of=as_of)[-lookback:]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[b["exchange_ts"] for b in bars])
    fp = fingerprint_rows(bars, ("exchange_ts", "close"))
    rets = _log_returns([float(b["close"]) for b in bars])
    s = _std(rets)
    if s is None:
        return _obs(
            "volatility",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(bars),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="insufficient_returns",
        )
    quality = "COMPLETE" if len(bars) >= lookback else "PARTIAL"
    return _obs(
        "volatility",
        value=s,
        quality=quality,
        as_of=as_of,
        available_at=_available_at(bars),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_liquidity(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    primary = market["primary_symbol"]
    bars = _pit_filter(market["ohlcv"][primary], as_of=as_of)[-lookback:]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[b["exchange_ts"] for b in bars])
    fp = fingerprint_rows(bars, ("exchange_ts", "close", "volume"))
    if len(bars) < 3:
        return _obs(
            "liquidity",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(bars),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="insufficient_bars",
        )
    vols = [float(b["volume"]) for b in bars]
    rets = _log_returns([float(b["close"]) for b in bars])
    abs_rets = [abs(r) for r in rets]
    mv, mr = _mean(vols), _mean(abs_rets)
    if mv is None or mr is None:
        return _obs(
            "liquidity",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(bars),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="empty_series",
        )
    value = mv / (1e-12 + mr)
    quality = "COMPLETE" if len(bars) >= lookback else "PARTIAL"
    return _obs(
        "liquidity",
        value=value,
        quality=quality,
        as_of=as_of,
        available_at=_available_at(bars),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_spread(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    rows = _pit_filter(market["quotes"], as_of=as_of)[-lookback:]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[r["exchange_ts"] for r in rows])
    fp = fingerprint_rows(rows, ("exchange_ts", "bid", "ask"))
    rels: list[float] = []
    for r in rows:
        bid, ask = float(r["bid"]), float(r["ask"])
        mid = (bid + ask) / 2.0
        if mid <= 0 or ask < bid:
            continue
        rels.append((ask - bid) / mid)
    m = _mean(rels)
    if m is None:
        return _obs(
            "spread",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(rows),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_valid_quotes",
        )
    quality = "COMPLETE" if len(rows) >= lookback else "PARTIAL"
    return _obs(
        "spread",
        value=m,
        quality=quality,
        as_of=as_of,
        available_at=_available_at(rows),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_turnover(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    primary = market["primary_symbol"]
    bars = _pit_filter(market["ohlcv"][primary], as_of=as_of)[-lookback:]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[b["exchange_ts"] for b in bars])
    fp = fingerprint_rows(bars, ("exchange_ts", "close", "volume"))
    if not bars:
        return _obs(
            "turnover",
            value=None,
            quality="MISSING",
            as_of=as_of,
            available_at=None,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_eligible_bars",
        )
    total = sum(float(b["close"]) * float(b["volume"]) for b in bars)
    quality = "COMPLETE" if len(bars) >= lookback else "PARTIAL"
    return _obs(
        "turnover",
        value=total,
        quality=quality,
        as_of=as_of,
        available_at=_available_at(bars),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_funding(market: dict[str, Any], *, as_of: int, lookback: int = 1) -> FeatureObservation:
    rows = _pit_filter(market["funding"], as_of=as_of)
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[r["exchange_ts"] for r in rows])
    fp = fingerprint_rows(rows[-1:], ("exchange_ts", "funding_rate")) if rows else "empty"
    if not rows:
        return _obs(
            "funding",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=None,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_eligible_funding",
        )
    last = rows[-1]
    return _obs(
        "funding",
        value=float(last["funding_rate"]),
        quality="COMPLETE",
        as_of=as_of,
        available_at=int(last["receive_ts"]),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_open_interest(market: dict[str, Any], *, as_of: int, lookback: int = 1) -> FeatureObservation:
    rows = _pit_filter(market["open_interest"], as_of=as_of)
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[r["exchange_ts"] for r in rows])
    fp = fingerprint_rows(rows[-1:], ("exchange_ts", "open_interest")) if rows else "empty"
    if not rows:
        return _obs(
            "open_interest",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=None,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_eligible_oi",
        )
    last = rows[-1]
    return _obs(
        "open_interest",
        value=float(last["open_interest"]),
        quality="COMPLETE",
        as_of=as_of,
        available_at=int(last["receive_ts"]),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_liquidation(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    bar_ms = int(market.get("bar_ms") or 60_000)
    window_start = as_of - lookback * bar_ms
    rows = [
        r
        for r in _pit_filter(market["liquidations"], as_of=as_of)
        if int(r["exchange_ts"]) >= window_start
    ]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[r["exchange_ts"] for r in rows])
    fp = fingerprint_rows(rows, ("exchange_ts", "notional"))
    if not rows:
        return _obs(
            "liquidation",
            value=None,
            quality="MISSING",
            as_of=as_of,
            available_at=None,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_liquidations_in_window",
        )
    total = sum(float(r["notional"]) for r in rows)
    return _obs(
        "liquidation",
        value=total,
        quality="COMPLETE",
        as_of=as_of,
        available_at=_available_at(rows),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_crowding(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    fund = compute_funding(market, as_of=as_of)
    oi = compute_open_interest(market, as_of=as_of)
    turn = compute_turnover(market, as_of=as_of, lookback=lookback)
    fp = f"{fund.calculation_hash}|{oi.calculation_hash}|{turn.calculation_hash}"
    avail_candidates = [x for x in (fund.available_at, oi.available_at, turn.available_at) if x is not None]
    available_at = max(avail_candidates) if avail_candidates else None
    if fund.value is None or oi.value is None or turn.value is None:
        return _obs(
            "crowding",
            value=None,
            quality="PARTIAL",
            as_of=as_of,
            available_at=available_at,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="propagated_upstream_missing",
        )
    mean_turn = float(turn.value) / max(1, lookback)
    value = abs(float(fund.value)) * float(oi.value) / (1e-12 + mean_turn)
    return _obs(
        "crowding",
        value=value,
        quality="COMPLETE",
        as_of=as_of,
        available_at=available_at,
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_order_flow(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    bar_ms = int(market.get("bar_ms") or 60_000)
    window_start = as_of - lookback * bar_ms
    rows = [
        r
        for r in _pit_filter(market["trades"], as_of=as_of)
        if int(r["exchange_ts"]) >= window_start
    ]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[r["exchange_ts"] for r in rows])
    fp = fingerprint_rows(rows, ("exchange_ts", "side", "notional"))
    buy = sell = 0.0
    for r in rows:
        side = str(r.get("side") or "UNKNOWN").upper()
        notional = float(r["notional"])
        if side == "BUY":
            buy += notional
        elif side == "SELL":
            sell += notional
        # UNKNOWN excluded — never imputed
    denom = buy + sell
    if denom <= 0:
        return _obs(
            "order_flow",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=_available_at(rows),
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_signed_aggressor_notional",
        )
    return _obs(
        "order_flow",
        value=(buy - sell) / denom,
        quality="COMPLETE",
        as_of=as_of,
        available_at=_available_at(rows),
        lookback=lookback,
        inputs_fingerprint=fp,
        extras={"buy_notional": buy, "sell_notional": sell, "unknown_excluded": True},
    )


def compute_cross_asset(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    primary = market["primary_symbol"]
    peer = market["peer_symbol"]
    a = _pit_filter(market["ohlcv"][primary], as_of=as_of)[-lookback:]
    b = _pit_filter(market["ohlcv"][peer], as_of=as_of)[-lookback:]
    assert_no_future_price_labels(
        as_of=as_of,
        used_exchange_ts=[x["exchange_ts"] for x in a] + [x["exchange_ts"] for x in b],
    )
    fp = fingerprint_rows(a, ("exchange_ts", "close")) + fingerprint_rows(b, ("exchange_ts", "close"))
    # Align on exchange_ts intersection
    b_map = {int(r["exchange_ts"]): float(r["close"]) for r in b}
    paired_a: list[float] = []
    paired_b: list[float] = []
    for r in a:
        ts = int(r["exchange_ts"])
        if ts in b_map:
            paired_a.append(float(r["close"]))
            paired_b.append(b_map[ts])
    ra, rb = _log_returns(paired_a), _log_returns(paired_b)
    n = min(len(ra), len(rb))
    corr = _pearson(ra[:n], rb[:n])
    available_at = _available_at(a + b)
    if corr is None:
        return _obs(
            "cross_asset",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=available_at,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="insufficient_overlapping_returns",
        )
    quality = "COMPLETE" if len(a) >= lookback and len(b) >= lookback else "PARTIAL"
    return _obs(
        "cross_asset",
        value=corr,
        quality=quality,
        as_of=as_of,
        available_at=available_at,
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_session(market: dict[str, Any], *, as_of: int, lookback: int = 0) -> FeatureObservation:
    # UTC hour from as_of ms
    hour = (int(as_of) // 1000 // 3600) % 24
    if 0 <= hour < 8:
        bucket = "ASIA"
    elif 8 <= hour < 13:
        bucket = "EUROPE"
    elif 13 <= hour < 21:
        bucket = "US"
    else:
        bucket = "OFF"
    return _obs(
        "session",
        value=bucket,
        quality="COMPLETE",
        as_of=as_of,
        available_at=as_of,
        lookback=lookback,
        inputs_fingerprint=str(as_of),
        extras={"utc_hour": hour},
    )


def compute_event_risk(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    bar_ms = int(market.get("bar_ms") or 60_000)
    window_start = as_of - lookback * bar_ms
    rows = []
    for e in market["events"]:
        announce = int(e["announce_ts"])
        recv = int(e["receive_ts"])
        if announce <= as_of and recv <= as_of and announce >= window_start:
            rows.append(e)
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[e["announce_ts"] for e in rows])
    fp = fingerprint_rows(rows, ("event_id", "announce_ts"))
    if not rows:
        return _obs(
            "event_risk",
            value=None,
            quality="MISSING",
            as_of=as_of,
            available_at=None,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_events_in_window",
        )
    return _obs(
        "event_risk",
        value=len(rows),
        quality="COMPLETE",
        as_of=as_of,
        available_at=max(int(e["receive_ts"]) for e in rows),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_market_breadth(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    advancing = 0
    considered = 0
    avail: list[int] = []
    fps: list[str] = []
    for sym in market["universe"]:
        bars = _pit_filter(market["ohlcv"][sym], as_of=as_of)
        fps.append(fingerprint_rows(bars[-lookback:], ("exchange_ts", "close")))
        if len(bars) < 2:
            continue
        window = bars[-lookback:] if len(bars) >= 2 else bars
        assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[b["exchange_ts"] for b in window])
        first, last = float(window[0]["close"]), float(window[-1]["close"])
        considered += 1
        if last > first:
            advancing += 1
        aa = _available_at(window)
        if aa is not None:
            avail.append(aa)
    fp = "|".join(fps)
    available_at = max(avail) if avail else None
    if considered == 0:
        return _obs(
            "market_breadth",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=available_at,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="empty_universe_eligible",
        )
    quality = "COMPLETE" if considered == len(market["universe"]) else "PARTIAL"
    return _obs(
        "market_breadth",
        value=advancing / considered,
        quality=quality,
        as_of=as_of,
        available_at=available_at,
        lookback=lookback,
        inputs_fingerprint=fp,
        extras={"advancing": advancing, "considered": considered},
    )


def compute_stablecoin_stress(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    bar_ms = int(market.get("bar_ms") or 60_000)
    window_start = as_of - lookback * bar_ms
    rows = [
        r
        for r in _pit_filter(market["stablecoins"], as_of=as_of)
        if int(r["exchange_ts"]) >= window_start
    ]
    assert_no_future_price_labels(as_of=as_of, used_exchange_ts=[r["exchange_ts"] for r in rows])
    fp = fingerprint_rows(rows, ("exchange_ts", "symbol", "price"))
    if not rows:
        return _obs(
            "stablecoin_stress",
            value=None,
            quality="UNAVAILABLE",
            as_of=as_of,
            available_at=None,
            lookback=lookback,
            inputs_fingerprint=fp,
            reason="no_stablecoin_rows",
        )
    devs = [abs(float(r["price"]) - 1.0) for r in rows]
    return _obs(
        "stablecoin_stress",
        value=_mean(devs),
        quality="COMPLETE",
        as_of=as_of,
        available_at=_available_at(rows),
        lookback=lookback,
        inputs_fingerprint=fp,
    )


def compute_data_trust(market: dict[str, Any], *, as_of: int, lookback: int = DEFAULT_LOOKBACK_BARS) -> FeatureObservation:
    primary = market["primary_symbol"]
    families = {
        "ohlcv": bool(_pit_filter(market["ohlcv"][primary], as_of=as_of)[-lookback:]),
        "quotes": bool(_pit_filter(market["quotes"], as_of=as_of)[-lookback:]),
        "funding": bool(_pit_filter(market["funding"], as_of=as_of)),
        "open_interest": bool(_pit_filter(market["open_interest"], as_of=as_of)),
        "trades": bool(_pit_filter(market["trades"], as_of=as_of)),
        "stablecoins": bool(_pit_filter(market["stablecoins"], as_of=as_of)),
    }
    present = sum(1 for v in families.values() if v)
    completeness = present / len(families)
    # Freshness from latest primary bar receive
    bars = _pit_filter(market["ohlcv"][primary], as_of=as_of)
    available_at = _available_at(bars)
    if available_at is None:
        freshness = 0.0
    else:
        age = max(0, as_of - available_at)
        freshness = max(0.0, 1.0 - age / float(DEFAULT_STALE_AFTER_MS))
    score = completeness * 0.7 + freshness * 0.3
    quality = "COMPLETE" if completeness == 1.0 else "PARTIAL"
    fp = str(sorted(families.items()))
    return _obs(
        "data_trust",
        value=score,
        quality=quality,
        as_of=as_of,
        available_at=available_at,
        lookback=lookback,
        inputs_fingerprint=fp,
        extras={"families": families, "completeness": completeness, "freshness": freshness},
    )


FORMULA_DISPATCH = {
    "trend": compute_trend,
    "volatility": compute_volatility,
    "liquidity": compute_liquidity,
    "spread": compute_spread,
    "turnover": compute_turnover,
    "funding": compute_funding,
    "open_interest": compute_open_interest,
    "liquidation": compute_liquidation,
    "crowding": compute_crowding,
    "order_flow": compute_order_flow,
    "cross_asset": compute_cross_asset,
    "session": compute_session,
    "event_risk": compute_event_risk,
    "market_breadth": compute_market_breadth,
    "stablecoin_stress": compute_stablecoin_stress,
    "data_trust": compute_data_trust,
}

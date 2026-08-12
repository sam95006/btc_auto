"""Point-in-time symbol profiles — labels/features, not fleets."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Versioned curated meme base taxonomy (explicit; not ticker-spelling inference alone).
MEME_TAXONOMY_VERSION = "meme_taxonomy_v1"
MEME_BASE_COINS = frozenset(
    {
        "DOGE",
        "SHIB",
        "PEPE",
        "WIF",
        "BONK",
        "FLOKI",
        "MEME",
        "BRETT",
        "NEIRO",
        "MOG",
        "POPCAT",
        "MEW",
        "PNUT",
        "TRUMP",
        "FARTCOIN",
        "GOAT",
        "ACT",
        "BOME",
        "DOG",
        "MYRO",
    }
)


@dataclass
class SymbolProfile:
    symbol: str
    timestamp: str
    market_size_class: str
    meme_classification: str
    liquidity_percentile: float | None
    turnover_percentile: float | None
    open_interest_percentile: float | None
    spread_bps: float | None
    estimated_slippage_bps: float | None
    volatility_percentile: float | None
    listing_age_days: float | None
    data_completeness: str
    funding_availability: str
    oi_availability: str
    mark_price_availability: str
    current_regime: str
    quality_status: str
    taxonomy_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pct_rank(values: list[float], x: float) -> float:
    if not values:
        return 0.5
    below = sum(1 for v in values if v <= x)
    return below / len(values)


def classify_meme(base_coin: str, *, taxonomy_available: bool = True) -> str:
    if not taxonomy_available:
        return "UNKNOWN"
    return "MEME" if base_coin.upper() in MEME_BASE_COINS else "NON_MEME"


def build_profiles(
    *,
    instruments: list[dict[str, Any]],
    tickers: dict[str, dict[str, Any]],
    timestamp: str,
    as_of_ms: int | None = None,
) -> list[SymbolProfile]:
    eligible = [i for i in instruments if i.get("eligible")]
    turnovers: list[float] = []
    ois: list[float] = []
    for i in eligible:
        t = tickers.get(i["symbol"]) or {}
        try:
            turnovers.append(float(t.get("turnover24h") or 0))
        except (TypeError, ValueError):
            turnovers.append(0.0)
        try:
            ois.append(float(t.get("openInterestValue") or t.get("openInterest") or 0))
        except (TypeError, ValueError):
            ois.append(0.0)

    profiles: list[SymbolProfile] = []
    for idx, i in enumerate(eligible):
        sym = i["symbol"]
        t = tickers.get(sym) or {}
        to = turnovers[idx] if idx < len(turnovers) else 0.0
        oi = ois[idx] if idx < len(ois) else 0.0
        to_p = _pct_rank(turnovers, to)
        oi_p = _pct_rank(ois, oi)
        liq_p = 0.5 * to_p + 0.5 * oi_p
        if liq_p >= 0.70:
            size = "MAINSTREAM"
        elif liq_p >= 0.35:
            size = "MID_SIZE"
        else:
            size = "SMALL"
        launch = i.get("launch_time")
        age = None
        if as_of_ms and launch:
            age = max(0.0, (as_of_ms - int(launch)) / 86_400_000)
        bid = t.get("bid1Price")
        ask = t.get("ask1Price")
        last = t.get("lastPrice")
        spread = None
        try:
            b, a, l = float(bid), float(ask), float(last or 0)
            mid = (b + a) / 2 if b and a else l
            if mid > 0 and a >= b:
                spread = (a - b) / mid * 10_000
        except (TypeError, ValueError):
            spread = None
        meme = classify_meme(str(i.get("base_coin") or ""), taxonomy_available=True)
        quality = "PASS"
        if spread is not None and spread > 25:
            quality = "WIDE_SPREAD"
        profiles.append(
            SymbolProfile(
                symbol=sym,
                timestamp=timestamp,
                market_size_class=size,
                meme_classification=meme,
                liquidity_percentile=round(liq_p, 6),
                turnover_percentile=round(to_p, 6),
                open_interest_percentile=round(oi_p, 6),
                spread_bps=spread,
                estimated_slippage_bps=(spread * 0.5 if spread is not None else None),
                volatility_percentile=None,
                listing_age_days=age,
                data_completeness="UNKNOWN",
                funding_availability="UNKNOWN",
                oi_availability="UNKNOWN",
                mark_price_availability="UNKNOWN",
                current_regime="UNKNOWN",
                quality_status=quality,
                taxonomy_version=MEME_TAXONOMY_VERSION,
            )
        )
    return profiles


def coverage_report(profiles: list[SymbolProfile]) -> dict[str, Any]:
    def count(pred) -> int:
        return sum(1 for p in profiles if pred(p))

    return {
        "schema": "dynamic_universe_coverage_v1",
        "note": "Coverage only — not fleets",
        "total_profiles": len(profiles),
        "MAINSTREAM": count(lambda p: p.market_size_class == "MAINSTREAM"),
        "MID_SIZE": count(lambda p: p.market_size_class == "MID_SIZE"),
        "SMALL": count(lambda p: p.market_size_class == "SMALL"),
        "MEME": count(lambda p: p.meme_classification == "MEME"),
        "NON_MEME": count(lambda p: p.meme_classification == "NON_MEME"),
        "UNKNOWN": count(lambda p: p.meme_classification == "UNKNOWN"),
    }


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

"""Dynamic Bybit Demo USDT-Perpetual universe + tradability gates."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class LiquidityTier(str, Enum):
    TIER_A_MAJOR = "TIER_A_MAJOR"
    TIER_B_LARGE = "TIER_B_LARGE"
    TIER_C_MID = "TIER_C_MID"
    TIER_D_SMALL_HIGH_RISK = "TIER_D_SMALL_HIGH_RISK"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class InstrumentMeta:
    symbol: str
    status: str
    tick_size: float
    qty_step: float
    min_qty: float
    min_notional: float
    max_leverage: float
    funding_interval_h: float = 8.0
    launch_age_days: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "tickSize": self.tick_size,
            "qtyStep": self.qty_step,
            "minQty": self.min_qty,
            "minNotional": self.min_notional,
            "maxLeverage": self.max_leverage,
            "fundingIntervalH": self.funding_interval_h,
            "launchAgeDays": self.launch_age_days,
        }


@dataclass
class MarketQualitySnapshot:
    symbol: str
    turnover_24h: float
    spread_bps: float
    volume_24h: float
    open_interest: float
    atr_pct: float
    freshness_ms: int
    depth_score: float = 50.0
    price_continuity: float = 1.0
    funding_abnormal: bool = False
    last_price: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "turnover24h": self.turnover_24h,
            "spreadBps": self.spread_bps,
            "volume24h": self.volume_24h,
            "openInterest": self.open_interest,
            "atrPct": self.atr_pct,
            "freshnessMs": self.freshness_ms,
            "depthScore": self.depth_score,
            "priceContinuity": self.price_continuity,
            "fundingAbnormal": self.funding_abnormal,
            "lastPrice": self.last_price,
        }


@dataclass
class TradableContract:
    meta: InstrumentMeta
    quality: MarketQualitySnapshot
    tier: LiquidityTier
    block_reasons: list[str] = field(default_factory=list)

    @property
    def allow_trade(self) -> bool:
        return self.tier != LiquidityTier.BLOCKED and not self.block_reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.meta.symbol,
            "tier": self.tier.value,
            "allowTrade": self.allow_trade,
            "blockReasons": list(self.block_reasons),
            "meta": self.meta.to_dict(),
            "quality": self.quality.to_dict(),
        }


MAJOR_HINTS = frozenset({"BTCUSDT", "ETHUSDT"})
LARGE_HINTS = frozenset({"SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT"})


class TradabilityGate:
    """Fail-closed tradability checks."""

    MAX_SPREAD_BPS = {
        LiquidityTier.TIER_A_MAJOR: 8.0,
        LiquidityTier.TIER_B_LARGE: 12.0,
        LiquidityTier.TIER_C_MID: 20.0,
        LiquidityTier.TIER_D_SMALL_HIGH_RISK: 35.0,
    }
    MIN_TURNOVER = {
        LiquidityTier.TIER_A_MAJOR: 5e8,
        LiquidityTier.TIER_B_LARGE: 5e7,
        LiquidityTier.TIER_C_MID: 5e6,
        LiquidityTier.TIER_D_SMALL_HIGH_RISK: 5e5,
    }
    MAX_FRESHNESS_MS = 120_000
    MIN_LISTING_DAYS = 14.0

    def evaluate(
        self,
        meta: InstrumentMeta,
        quality: MarketQualitySnapshot,
        tier: LiquidityTier,
    ) -> list[str]:
        blocks: list[str] = []
        if str(meta.status).upper() not in {"TRADING", "LIVE", ""}:
            blocks.append(f"status:{meta.status}")
        if meta.tick_size <= 0 or meta.qty_step <= 0 or meta.min_qty <= 0:
            blocks.append("precision_unknown")
        if meta.max_leverage <= 1:
            blocks.append("max_leverage_unknown")
        if quality.freshness_ms > self.MAX_FRESHNESS_MS:
            blocks.append(f"stale:{quality.freshness_ms}")
        if quality.spread_bps > self.MAX_SPREAD_BPS.get(tier, 35.0):
            blocks.append(f"spread_bps:{quality.spread_bps}")
        if quality.turnover_24h < self.MIN_TURNOVER.get(tier, 5e5):
            blocks.append(f"turnover_low:{quality.turnover_24h}")
        if quality.funding_abnormal:
            blocks.append("funding_abnormal")
        if quality.price_continuity < 0.8:
            blocks.append("price_discontinuity")
        if meta.launch_age_days is not None and meta.launch_age_days < self.MIN_LISTING_DAYS:
            blocks.append(f"listing_too_new:{meta.launch_age_days}")
        if tier == LiquidityTier.BLOCKED:
            blocks.append("tier_blocked")
        return blocks


class LiquidityTierClassifier:
    def classify(self, meta: InstrumentMeta, quality: MarketQualitySnapshot) -> LiquidityTier:
        sym = meta.symbol.upper()
        if quality.spread_bps > 50 or quality.turnover_24h < 1e5 or quality.atr_pct > 12:
            return LiquidityTier.BLOCKED
        if sym in MAJOR_HINTS and quality.turnover_24h >= 5e8 and quality.spread_bps <= 8:
            return LiquidityTier.TIER_A_MAJOR
        if (sym in LARGE_HINTS or quality.turnover_24h >= 5e7) and quality.spread_bps <= 15:
            return LiquidityTier.TIER_B_LARGE
        if quality.turnover_24h >= 5e6 and quality.spread_bps <= 25:
            return LiquidityTier.TIER_C_MID
        if quality.turnover_24h >= 5e5:
            return LiquidityTier.TIER_D_SMALL_HIGH_RISK
        return LiquidityTier.BLOCKED


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class DynamicContractUniverse:
    """Build tradable universe from instruments + market quality inputs."""

    def __init__(self) -> None:
        self._classifier = LiquidityTierClassifier()
        self._gate = TradabilityGate()

    def build(
        self,
        instruments: list[dict[str, Any]],
        quality_by_symbol: dict[str, MarketQualitySnapshot] | None = None,
    ) -> list[TradableContract]:
        quality_by_symbol = quality_by_symbol or {}
        out: list[TradableContract] = []
        for row in instruments:
            symbol = str(row.get("symbol") or "")
            if not symbol.endswith("USDT"):
                continue
            # linear perpetual filter
            contract_type = str(row.get("contractType") or row.get("contract_type") or "LinearPerpetual")
            if "PERP" not in contract_type.upper() and contract_type not in ("", "LinearPerpetual"):
                # still allow when Bybit omits field for linear
                if str(row.get("category") or "linear").lower() != "linear":
                    continue
            lot = row.get("lotSizeFilter") or {}
            price = row.get("priceFilter") or {}
            lev = row.get("leverageFilter") or {}
            launch_age = row.get("launchAgeDays")
            meta = InstrumentMeta(
                symbol=symbol,
                status=str(row.get("status") or "Trading"),
                tick_size=_as_float(price.get("tickSize"), 0.0),
                qty_step=_as_float(lot.get("qtyStep") or lot.get("basePrecision"), 0.0),
                min_qty=_as_float(lot.get("minOrderQty"), 0.0),
                min_notional=_as_float(lot.get("minNotionalValue") or lot.get("minOrderAmt"), 0.0),
                max_leverage=_as_float(lev.get("maxLeverage"), 0.0),
                funding_interval_h=8.0,
                launch_age_days=_as_float(launch_age) if launch_age is not None else None,
            )
            q = quality_by_symbol.get(symbol) or MarketQualitySnapshot(
                symbol=symbol,
                turnover_24h=0.0,
                spread_bps=999.0,
                volume_24h=0.0,
                open_interest=0.0,
                atr_pct=0.0,
                freshness_ms=999_999,
            )
            tier = self._classifier.classify(meta, q)
            blocks = self._gate.evaluate(meta, q, tier)
            if blocks and tier != LiquidityTier.BLOCKED:
                # hard blocks force BLOCKED
                if any(
                    b.startswith(p)
                    for b in blocks
                    for p in ("status:", "precision_", "max_leverage", "stale:", "listing_")
                ):
                    tier = LiquidityTier.BLOCKED
            out.append(TradableContract(meta=meta, quality=q, tier=tier, block_reasons=blocks))
        return out

    def summary(self, contracts: list[TradableContract]) -> dict[str, Any]:
        counts = {t.value: 0 for t in LiquidityTier}
        for c in contracts:
            counts[c.tier.value] += 1
        return {
            "totalContracts": len(contracts),
            "tradableContracts": sum(1 for c in contracts if c.allow_trade),
            "tierCounts": counts,
            "capturedAtMs": int(time.time() * 1000),
        }


# Fixture instruments for offline tests
FIXTURE_INSTRUMENTS: list[dict[str, Any]] = [
    {
        "symbol": "BTCUSDT",
        "status": "Trading",
        "contractType": "LinearPerpetual",
        "category": "linear",
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.1"},
        "leverageFilter": {"maxLeverage": "100"},
        "launchAgeDays": 1000,
    },
    {
        "symbol": "ETHUSDT",
        "status": "Trading",
        "contractType": "LinearPerpetual",
        "category": "linear",
        "lotSizeFilter": {"qtyStep": "0.01", "minOrderQty": "0.01", "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.01"},
        "leverageFilter": {"maxLeverage": "100"},
        "launchAgeDays": 1000,
    },
    {
        "symbol": "SOLUSDT",
        "status": "Trading",
        "contractType": "LinearPerpetual",
        "category": "linear",
        "lotSizeFilter": {"qtyStep": "0.1", "minOrderQty": "0.1", "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.01"},
        "leverageFilter": {"maxLeverage": "50"},
        "launchAgeDays": 800,
    },
    {
        "symbol": "PEPEUSDT",
        "status": "Trading",
        "contractType": "LinearPerpetual",
        "category": "linear",
        "lotSizeFilter": {"qtyStep": "100", "minOrderQty": "100", "minNotionalValue": "5"},
        "priceFilter": {"tickSize": "0.0000001"},
        "leverageFilter": {"maxLeverage": "25"},
        "launchAgeDays": 200,
    },
]


def fixture_quality() -> dict[str, MarketQualitySnapshot]:
    return {
        "BTCUSDT": MarketQualitySnapshot("BTCUSDT", 2e10, 1.2, 2.8e10, 1e10, 1.8, 3000, 90),
        "ETHUSDT": MarketQualitySnapshot("ETHUSDT", 8e9, 1.5, 1e10, 5e9, 2.2, 4000, 85),
        "SOLUSDT": MarketQualitySnapshot("SOLUSDT", 2e9, 2.5, 3e9, 1e9, 3.5, 5000, 70),
        "PEPEUSDT": MarketQualitySnapshot("PEPEUSDT", 8e6, 18.0, 1e7, 2e8, 8.0, 8000, 40),
    }

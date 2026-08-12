"""Dynamic instrument discovery from public Bybit instruments-info responses."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.nexus_global_shadow.contracts import new_id, now_ms
from backend.nexus_real_shadow.constitution import PublicMarketDataConstitution
from backend.nexus_real_shadow.http_client import PublicHttpClient

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
PUBLIC_INSTRUMENTS_URL = "https://api.bybit.com/v5/market/instruments-info"


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def parse_instruments_info(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Bybit instruments-info style payload into normalized instrument rows."""
    if not payload or payload.get("retCode") not in (0, "0", None):
        return []
    result = payload.get("result") or {}
    rows = result.get("list") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("contractType") or "") != "LinearPerpetual":
            continue
        if str(row.get("quoteCoin") or "") != "USDT":
            continue
        if str(row.get("status") or "") != "Trading":
            continue
        lot = row.get("lotSizeFilter") or {}
        price = row.get("priceFilter") or {}
        lev = row.get("leverageFilter") or {}
        out.append(
            {
                "symbol": row.get("symbol"),
                "base_coin": row.get("baseCoin"),
                "quote_coin": row.get("quoteCoin"),
                "contract_type": row.get("contractType"),
                "status": row.get("status"),
                "tick_size": float(price.get("tickSize") or 0) or None,
                "qty_step": float(lot.get("qtyStep") or 0) or None,
                "min_order_qty": float(lot.get("minOrderQty") or 0) or None,
                "min_notional": float(lot.get("minNotionalValue") or 0) or None,
                "max_leverage_available": float(lev.get("maxLeverage") or 0) or None,
            }
        )
    return out


@dataclass
class UniverseFunnelCounts:
    raw_count: int = 0
    linear_usdt_count: int = 0
    trading_count: int = 0
    eligible_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "raw_count": self.raw_count,
            "linear_usdt_count": self.linear_usdt_count,
            "trading_count": self.trading_count,
            "eligible_count": self.eligible_count,
        }


@dataclass
class UniverseDiscoverySnapshot:
    universe_snapshot_id: str
    instruments: list[dict[str, Any]]
    funnel: UniverseFunnelCounts
    provider_status: str
    freshness: str
    captured_at: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_snapshot_id": self.universe_snapshot_id,
            "total_markets": self.funnel.trading_count,
            "eligible_markets": self.funnel.eligible_count,
            "excluded_markets": max(0, self.funnel.trading_count - self.funnel.eligible_count),
            "instruments": self.instruments,
            "funnel": self.funnel.to_dict(),
            "provider_status": self.provider_status,
            "freshness": self.freshness,
            "captured_at": self.captured_at,
            "error": self.error,
        }


class BybitPublicInstrumentProvider:
    """Fetch and parse public instruments-info (injectable transport/fixtures)."""

    def __init__(
        self,
        *,
        constitution: PublicMarketDataConstitution | None = None,
        http_client: PublicHttpClient | None = None,
        fixture_loader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.constitution = constitution or PublicMarketDataConstitution()
        self.http_client = http_client or PublicHttpClient(constitution=self.constitution)
        self.fixture_loader = fixture_loader

    def fetch(self) -> tuple[list[dict[str, Any]], str]:
        if self.fixture_loader:
            payload = self.fixture_loader()
            rows = parse_instruments_info(payload)
            return rows, "OK" if rows else "UNIVERSE_DEGRADED"

        url = f"{PUBLIC_INSTRUMENTS_URL}?category=linear"
        result = self.http_client.get(url)
        payload = result.get("json") or result
        rows = parse_instruments_info(payload)
        return rows, "OK" if rows else "UNIVERSE_DEGRADED"


class DynamicInstrumentDiscoveryWorker:
    """Worker that discovers instruments and emits universe snapshots."""

    def __init__(self, provider: BybitPublicInstrumentProvider | None = None) -> None:
        self.provider = provider or BybitPublicInstrumentProvider(
            fixture_loader=lambda: load_fixture("instruments_info.json")
        )
        self.last_snapshot: UniverseDiscoverySnapshot | None = None
        self.last_error: str | None = None

    def discover(self) -> UniverseDiscoverySnapshot:
        raw_payload = load_fixture("instruments_info.json")
        raw_list = raw_payload.get("result", {}).get("list") or []
        funnel = UniverseFunnelCounts(raw_count=len(raw_list))
        for row in raw_list:
            if str(row.get("contractType") or "") == "LinearPerpetual":
                funnel.linear_usdt_count += 1
                if str(row.get("quoteCoin") or "") == "USDT":
                    if str(row.get("status") or "") == "Trading":
                        funnel.trading_count += 1

        try:
            instruments, status = self.provider.fetch()
        except Exception as exc:
            self.last_error = str(exc)
            snap = UniverseDiscoverySnapshot(
                universe_snapshot_id=new_id("uni"),
                instruments=[],
                funnel=funnel,
                provider_status="UNIVERSE_UNAVAILABLE",
                freshness="UNAVAILABLE",
                captured_at=now_ms(),
                error=str(exc),
            )
            self.last_snapshot = snap
            return snap

        if status in {"UNIVERSE_UNAVAILABLE", "UNIVERSE_DEGRADED"} and not instruments:
            self.last_error = status
            snap = UniverseDiscoverySnapshot(
                universe_snapshot_id=new_id("uni"),
                instruments=[],
                funnel=funnel,
                provider_status=status,
                freshness="UNAVAILABLE",
                captured_at=now_ms(),
                error=status,
            )
            self.last_snapshot = snap
            return snap

        funnel.eligible_count = len(instruments)
        snap = UniverseDiscoverySnapshot(
            universe_snapshot_id=new_id("uni"),
            instruments=instruments,
            funnel=funnel,
            provider_status=status,
            freshness="FRESH",
            captured_at=now_ms(),
        )
        self.last_snapshot = snap
        self.last_error = None
        return snap

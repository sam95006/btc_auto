"""Sanitized Point-in-Time market metadata fixtures.

These fixtures are era-bound historical snapshots. Discovery for a past
as_of_ms MUST select a snapshot whose availability_ms <= as_of_ms and MUST
NOT invent membership from a later (e.g. "today") universe.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_market_discovery.lineage import sha_obj

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# Canonical fixture eras (ms since epoch, UTC)
# 2024-06-01T00:00:00Z
ERA_2024_06_01_MS = 1_717_200_000_000
# 2024-12-01T00:00:00Z
ERA_2024_12_01_MS = 1_733_020_800_000
# 2025-03-01T00:00:00Z
ERA_2025_03_01_MS = 1_740_787_200_000


def _instrument(
    *,
    symbol: str,
    base: str,
    listing_ms: int,
    delisting_ms: int | None,
    status: str,
    observation_ms: int,
    liquidity_score: float,
    turnover_usdt: float,
    volume_usdt: float,
    spread_bps: float,
    depth_usdt: float,
    open_interest_usdt: float | None,
    funding_available: bool,
    completeness: float,
    staleness_ms: int,
    mapping: str | None,
    tick_size: float | None,
    qty_step: float | None,
    min_notional: float | None,
    min_qty: float | None = 0.001,
    contract_type: str = "LinearPerpetual",
    quote: str = "USDT",
    settle: str = "USDT",
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "base_coin": base,
        "quote_coin": quote,
        "settle_coin": settle,
        "status": status,
        "contract_type": contract_type,
        "listing_ms": listing_ms,
        "delisting_ms": delisting_ms,
        "observation_ms": observation_ms,
        "liquidity_score": liquidity_score,
        "turnover_usdt": turnover_usdt,
        "volume_usdt": volume_usdt,
        "spread_bps": spread_bps,
        "depth_usdt": depth_usdt,
        "open_interest_usdt": open_interest_usdt,
        "funding_available": funding_available,
        "data_completeness": completeness,
        "staleness_ms": staleness_ms,
        "symbol_mapping": mapping,
        "tick_size": tick_size,
        "qty_step": qty_step,
        "minimum_notional": min_notional,
        "minimum_order_qty": min_qty,
        "contract_specification": {
            "contract_type": contract_type,
            "quote_coin": quote,
            "settle_coin": settle,
            "tick_size": tick_size,
            "qty_step": qty_step,
            "minimum_notional": min_notional,
            "minimum_order_qty": min_qty,
        },
    }


def _snapshot(snapshot_id: str, availability_ms: int, instruments: list[dict[str, Any]]) -> dict[str, Any]:
    body = {
        "schema": "nexus_pit_market_fixture_v1",
        "snapshot_id": snapshot_id,
        "availability_ms": availability_ms,
        "source_kind": "sanitized_fixture",
        "trading_write": False,
        "mainnet_trading": False,
        "real_money": False,
        "demo": False,
        "instruments": instruments,
    }
    body["source_checksum"] = sha_obj(
        {
            "snapshot_id": snapshot_id,
            "availability_ms": availability_ms,
            "symbols": sorted(i["symbol"] for i in instruments),
            "instrument_checksums": [sha_obj(i) for i in sorted(instruments, key=lambda x: x["symbol"])],
        }
    )
    return body


def build_builtin_fixtures() -> dict[str, dict[str, Any]]:
    """Three era-bound snapshots with listing/delisting and quality variation."""
    # Shared listing timelines
    btc_list = 1_577_836_800_000  # 2020-01-01
    eth_list = 1_577_836_800_000
    sol_list = 1_640_995_200_000  # 2022-01-01
    pepe_list = 1_704_067_200_000  # 2024-01-01
    late_list = 1_735_689_600_000  # 2025-01-01 — not in mid-2024 era
    ghost_list = 1_609_459_200_000  # 2021
    ghost_delist = 1_725_000_000_000  # delisted mid-2024 (~2024-08)

    def era_instruments(obs: int) -> list[dict[str, Any]]:
        rows = [
            _instrument(
                symbol="BTCUSDT",
                base="BTC",
                listing_ms=btc_list,
                delisting_ms=None,
                status="Trading",
                observation_ms=obs,
                liquidity_score=0.99,
                turnover_usdt=5_000_000_000,
                volume_usdt=2_000_000_000,
                spread_bps=0.5,
                depth_usdt=8_000_000,
                open_interest_usdt=2_500_000_000,
                funding_available=True,
                completeness=0.99,
                staleness_ms=5_000,
                mapping="bybit:linear:BTCUSDT",
                tick_size=0.1,
                qty_step=0.001,
                min_notional=5.0,
            ),
            _instrument(
                symbol="ETHUSDT",
                base="ETH",
                listing_ms=eth_list,
                delisting_ms=None,
                status="Trading",
                observation_ms=obs,
                liquidity_score=0.95,
                turnover_usdt=1_800_000_000,
                volume_usdt=900_000_000,
                spread_bps=0.8,
                depth_usdt=3_500_000,
                open_interest_usdt=900_000_000,
                funding_available=True,
                completeness=0.98,
                staleness_ms=8_000,
                mapping="bybit:linear:ETHUSDT",
                tick_size=0.01,
                qty_step=0.01,
                min_notional=5.0,
            ),
            _instrument(
                symbol="SOLUSDT",
                base="SOL",
                listing_ms=sol_list,
                delisting_ms=None,
                status="Trading",
                observation_ms=obs,
                liquidity_score=0.82,
                turnover_usdt=420_000_000,
                volume_usdt=210_000_000,
                spread_bps=1.5,
                depth_usdt=900_000,
                open_interest_usdt=180_000_000,
                funding_available=True,
                completeness=0.96,
                staleness_ms=12_000,
                mapping="bybit:linear:SOLUSDT",
                tick_size=0.001,
                qty_step=0.1,
                min_notional=5.0,
            ),
            _instrument(
                symbol="PEPEUSDT",
                base="PEPE",
                listing_ms=pepe_list,
                delisting_ms=None,
                status="Trading",
                observation_ms=obs,
                liquidity_score=0.55,
                turnover_usdt=12_000_000,
                volume_usdt=6_000_000,
                spread_bps=8.0,
                depth_usdt=120_000,
                open_interest_usdt=4_500_000,
                funding_available=True,
                completeness=0.90,
                staleness_ms=40_000,
                mapping="bybit:linear:1000PEPEUSDT",
                tick_size=0.0000001,
                qty_step=100.0,
                min_notional=5.0,
            ),
            # Thin / wide-spread reject candidate
            _instrument(
                symbol="THINUSDT",
                base="THIN",
                listing_ms=1_672_531_200_000,  # 2023-01-01
                delisting_ms=None,
                status="Trading",
                observation_ms=obs,
                liquidity_score=0.12,
                turnover_usdt=80_000,
                volume_usdt=40_000,
                spread_bps=55.0,
                depth_usdt=4_000,
                open_interest_usdt=15_000,
                funding_available=False,
                completeness=0.60,
                staleness_ms=2_000_000,
                mapping=None,
                tick_size=0.01,
                qty_step=1.0,
                min_notional=5.0,
            ),
            # Invalid contract specs
            _instrument(
                symbol="BROKENUSDT",
                base="BROKEN",
                listing_ms=1_672_531_200_000,
                delisting_ms=None,
                status="Trading",
                observation_ms=obs,
                liquidity_score=0.70,
                turnover_usdt=2_000_000,
                volume_usdt=1_000_000,
                spread_bps=5.0,
                depth_usdt=80_000,
                open_interest_usdt=500_000,
                funding_available=True,
                completeness=0.92,
                staleness_ms=20_000,
                mapping="bybit:linear:BROKENUSDT",
                tick_size=0.0,
                qty_step=-1.0,
                min_notional=None,
            ),
            # Delisted mid-2024
            _instrument(
                symbol="GHOSTUSDT",
                base="GHOST",
                listing_ms=ghost_list,
                delisting_ms=ghost_delist,
                status="Closed" if obs >= ghost_delist else "Trading",
                observation_ms=obs,
                liquidity_score=0.40,
                turnover_usdt=600_000,
                volume_usdt=300_000,
                spread_bps=12.0,
                depth_usdt=30_000,
                open_interest_usdt=120_000,
                funding_available=True,
                completeness=0.88,
                staleness_ms=30_000,
                mapping="bybit:linear:GHOSTUSDT",
                tick_size=0.001,
                qty_step=1.0,
                min_notional=5.0,
            ),
        ]
        # Late-listed only appears in later eras' raw instrument tables,
        # but still carries listing_ms so PIT membership excludes early as_of.
        if obs >= late_list:
            rows.append(
                _instrument(
                    symbol="LATEUSDT",
                    base="LATE",
                    listing_ms=late_list,
                    delisting_ms=None,
                    status="Trading",
                    observation_ms=obs,
                    liquidity_score=0.48,
                    turnover_usdt=900_000,
                    volume_usdt=450_000,
                    spread_bps=9.0,
                    depth_usdt=55_000,
                    open_interest_usdt=220_000,
                    funding_available=True,
                    completeness=0.91,
                    staleness_ms=25_000,
                    mapping="bybit:linear:LATEUSDT",
                    tick_size=0.01,
                    qty_step=0.1,
                    min_notional=5.0,
                )
            )
        # PreLaunch noise in late snapshot
        if obs >= ERA_2025_03_01_MS:
            rows.append(
                _instrument(
                    symbol="PREUSDT",
                    base="PRE",
                    listing_ms=obs + 86_400_000,
                    delisting_ms=None,
                    status="PreLaunch",
                    observation_ms=obs,
                    liquidity_score=0.0,
                    turnover_usdt=0.0,
                    volume_usdt=0.0,
                    spread_bps=999.0,
                    depth_usdt=0.0,
                    open_interest_usdt=None,
                    funding_available=False,
                    completeness=0.1,
                    staleness_ms=0,
                    mapping=None,
                    tick_size=0.01,
                    qty_step=1.0,
                    min_notional=5.0,
                )
            )
        return rows

    return {
        "era_2024_06_01": _snapshot("era_2024_06_01", ERA_2024_06_01_MS, era_instruments(ERA_2024_06_01_MS)),
        "era_2024_12_01": _snapshot("era_2024_12_01", ERA_2024_12_01_MS, era_instruments(ERA_2024_12_01_MS)),
        "era_2025_03_01": _snapshot("era_2025_03_01", ERA_2025_03_01_MS, era_instruments(ERA_2025_03_01_MS)),
    }


def materialize_fixtures(target_dir: Path | None = None) -> list[Path]:
    """Write builtin fixtures to disk (idempotent)."""
    out_dir = target_dir or FIXTURES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for snap_id, snap in build_builtin_fixtures().items():
        path = out_dir / f"{snap_id}.json"
        path.write_text(json.dumps(snap, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    index = {
        "schema": "nexus_pit_market_fixture_index_v1",
        "snapshots": sorted(
            [
                {
                    "snapshot_id": s["snapshot_id"],
                    "availability_ms": s["availability_ms"],
                    "source_checksum": s["source_checksum"],
                    "instrument_count": len(s["instruments"]),
                    "path": f"{s['snapshot_id']}.json",
                }
                for s in build_builtin_fixtures().values()
            ],
            key=lambda x: x["availability_ms"],
        ),
        "note": "Point-in-Time only — never substitute a later snapshot for an earlier as_of",
    }
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    written.append(index_path)
    return written


def load_fixture_index(fixtures_dir: Path | None = None) -> dict[str, Any]:
    root = fixtures_dir or FIXTURES_DIR
    index_path = root / "index.json"
    if not index_path.exists():
        materialize_fixtures(root)
    return json.loads(index_path.read_text(encoding="utf-8"))


def load_snapshot(snapshot_id: str, fixtures_dir: Path | None = None) -> dict[str, Any]:
    root = fixtures_dir or FIXTURES_DIR
    path = root / f"{snapshot_id}.json"
    if not path.exists():
        materialize_fixtures(root)
    return json.loads(path.read_text(encoding="utf-8"))


class PitSnapshotError(ValueError):
    """Raised when PIT snapshot selection would violate historical integrity."""


def select_snapshot_for_as_of(
    as_of_ms: int,
    *,
    fixtures_dir: Path | None = None,
    allow_exact_or_earlier_only: bool = True,
) -> dict[str, Any]:
    """Select the newest fixture with availability_ms <= as_of_ms.

    HARD BAN: never select a later snapshot (e.g. today) to simulate the past.
    """
    index = load_fixture_index(fixtures_dir)
    candidates = [
        e
        for e in index.get("snapshots") or []
        if int(e["availability_ms"]) <= int(as_of_ms)
    ]
    if not candidates:
        raise PitSnapshotError(
            f"no_historical_snapshot_for_as_of:{as_of_ms}:refusing_to_use_future_or_today_universe"
        )
    best = max(candidates, key=lambda e: int(e["availability_ms"]))
    if allow_exact_or_earlier_only and int(best["availability_ms"]) > int(as_of_ms):
        raise PitSnapshotError("future_snapshot_selected")
    snap = load_snapshot(str(best["snapshot_id"]), fixtures_dir)
    if int(snap["availability_ms"]) > int(as_of_ms):
        raise PitSnapshotError("snapshot_availability_after_as_of")
    return snap

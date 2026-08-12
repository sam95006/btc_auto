"""Cross-exchange symbol collision attacks (identity must not collapse)."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.fixtures import (
    raw_binance_perp_btcusdt,
    raw_binance_spot_btcusdt,
    raw_bybit_perp_btcusdt,
)
from backend.nexus_silver_symbol_identity.hard_bans import HardBanViolation
from backend.nexus_silver_symbol_identity.identity import (
    build_canonical_instrument_id,
    instruments_are_same_instrument,
    instruments_share_symbol_string,
)
from backend.nexus_silver_symbol_identity.normalize import normalize_raw_instrument
from backend.nexus_silver_symbol_identity.registry import SilverInstrumentRegistry


def _attack(name: str, blocked: bool, detail: str, **extra: Any) -> dict[str, Any]:
    return {
        "attack_id": name,
        "blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
        **extra,
    }


def attack_collapse_cross_exchange_btcusdt() -> dict[str, Any]:
    """Attack: treat Binance BTCUSDT perp and Bybit BTCUSDT perp as one instrument."""
    binance = normalize_raw_instrument(raw_binance_perp_btcusdt())
    bybit = normalize_raw_instrument(raw_bybit_perp_btcusdt())
    share = instruments_share_symbol_string(binance, bybit)
    same = instruments_are_same_instrument(binance, bybit)
    # Attack claim: symbol-only identity key.
    attack_key_a = binance["exchange_symbol"].upper()
    attack_key_b = bybit["exchange_symbol"].upper()
    collapsed = attack_key_a == attack_key_b and same
    honest_distinct = share and not same and binance["canonical_instrument_id"] != bybit["canonical_instrument_id"]
    blocked = honest_distinct and not collapsed
    return _attack(
        "collapse_cross_exchange_btcusdt",
        blocked,
        f"share={share} same={same}",
        binance_id=binance["canonical_instrument_id"],
        bybit_id=bybit["canonical_instrument_id"],
    )


def attack_symbol_only_registry_merge() -> dict[str, Any]:
    """Attack: upsert by exchange_symbol alone into one registry slot."""
    reg = SilverInstrumentRegistry()
    a = reg.upsert_raw(raw_binance_perp_btcusdt())
    b = reg.upsert_raw(raw_bybit_perp_btcusdt())
    all_rows = reg.list_all(include_delisted=True)
    by_symbol = {}
    # Attack reconstruction: last-writer-wins on symbol string.
    for row in all_rows:
        by_symbol[row["exchange_symbol"].upper()] = row["canonical_instrument_id"]
    collapsed_count = len(by_symbol)
    honest_count = len({r["canonical_instrument_id"] for r in all_rows})
    # Honest registry must keep both; attack map collapses to 1 for BTCUSDT.
    blocked = honest_count >= 2 and a["canonical_instrument_id"] != b["canonical_instrument_id"] and collapsed_count == 1
    # Wait: blocked means attack was blocked by honest system. The collapse map is the attack artifact;
    # the honest registry still has 2. So attack is blocked when honest keeps both despite attack map size 1.
    blocked = (
        a["canonical_instrument_id"] != b["canonical_instrument_id"]
        and honest_count >= 2
        and reg.get(a["canonical_instrument_id"]) is not None
        and reg.get(b["canonical_instrument_id"]) is not None
    )
    return _attack(
        "symbol_only_registry_merge",
        blocked,
        f"honest_count={honest_count} attack_map_size={collapsed_count}",
        attack_map_size=collapsed_count,
        honest_count=honest_count,
    )


def attack_collapse_spot_perp() -> dict[str, Any]:
    spot = normalize_raw_instrument(raw_binance_spot_btcusdt())
    perp = normalize_raw_instrument(raw_binance_perp_btcusdt())
    same = instruments_are_same_instrument(spot, perp)
    blocked = (not same) and spot["canonical_instrument_id"] != perp["canonical_instrument_id"]
    return _attack(
        "collapse_spot_perp_btcusdt",
        blocked,
        f"same={same}",
        spot_id=spot["canonical_instrument_id"],
        perp_id=perp["canonical_instrument_id"],
    )


def attack_missing_exchange_component() -> dict[str, Any]:
    """Attack: build identity without exchange — must fail closed."""
    try:
        build_canonical_instrument_id(
            exchange="",
            exchange_symbol="BTCUSDT",
            market_type="perp",
            quote_asset="USDT",
            margin_kind="linear",
            contract_multiplier=1,
            contract_rule_version="v1",
        )
        return _attack("missing_exchange_component", False, "accepted_empty_exchange")
    except ValueError as exc:
        return _attack("missing_exchange_component", True, str(exc), status="REJECTED")


def attack_cross_venue_liquidity_substitution_by_symbol() -> dict[str, Any]:
    """Attack: copy Bybit liquidity/score identity onto Binance symbol-matched row."""
    binance = normalize_raw_instrument(raw_binance_perp_btcusdt())
    bybit = normalize_raw_instrument(raw_bybit_perp_btcusdt())
    # Fabricate collapsed claim
    claimed_same = binance["exchange_symbol"] == bybit["exchange_symbol"]
    if claimed_same and instruments_are_same_instrument(binance, bybit):
        return _attack("cross_venue_liquidity_by_symbol", False, "identity_collapsed")
    # Guard: refuse treating venues as interchangeable under symbol equality.
    refused = claimed_same and not instruments_are_same_instrument(binance, bybit)
    return _attack(
        "cross_venue_liquidity_by_symbol",
        refused,
        "venue_interchange_refused" if refused else "not_refused",
        status="VENUE_DISTINCT" if refused else "COLLAPSED",
    )


def attack_hard_ban_collapse_declared() -> dict[str, Any]:
    from backend.nexus_silver_symbol_identity.constants import HARD_BANS

    required = {
        "no_collapse_cross_exchange_symbols",
        "no_collapse_spot_perp_identity",
    }
    missing = sorted(required - set(HARD_BANS))
    blocked = len(missing) == 0
    return _attack(
        "hard_ban_collapse_declared",
        blocked,
        "ok" if blocked else f"missing={missing}",
        missing=missing,
    )


def run_symbol_collision_attacks() -> dict[str, Any]:
    attacks = [
        attack_collapse_cross_exchange_btcusdt(),
        attack_symbol_only_registry_merge(),
        attack_collapse_spot_perp(),
        attack_missing_exchange_component(),
        attack_cross_venue_liquidity_substitution_by_symbol(),
        attack_hard_ban_collapse_declared(),
    ]
    survivors = [a["attack_id"] for a in attacks if a.get("survivor")]
    return {
        "schema": "v17_deep_symbol_collision_v1",
        "attack_count": len(attacks),
        "blocked_count": sum(1 for a in attacks if a.get("blocked")),
        "survivor_count": len(survivors),
        "survivors": survivors,
        "pass": len(survivors) == 0,
        "attacks": attacks,
    }

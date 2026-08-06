"""Canonical identity construction and equality rules for silver instruments."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from backend.nexus_silver_symbol_identity.constants import (
    IDENTITY_VERSION,
    MARGIN_KINDS,
    MARKET_TYPES,
)

_ASSET_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


def _norm_token(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_asset_code(asset: str) -> str:
    """Normalize base/quote asset codes for stable asset ids."""
    code = _norm_token(asset).replace(" ", "")
    # Common stablecoin / wrapped aliases retained as distinct unless mapped.
    aliases = {
        "xbt": "btc",
        "bitcoin": "btc",
        "ether": "eth",
        "ethereum": "eth",
    }
    return aliases.get(code, code)


def build_canonical_asset_id(base_asset: str) -> str:
    code = normalize_asset_code(base_asset)
    if not code or not _ASSET_RE.match(code):
        raise ValueError(f"invalid_base_asset:{base_asset!r}")
    return f"asset:{code}"


def _require_market_type(market_type: str) -> str:
    mt = _norm_token(market_type)
    if mt not in MARKET_TYPES:
        raise ValueError(f"invalid_market_type:{market_type!r}")
    return mt


def _require_margin_kind(margin_kind: str, *, market_type: str) -> str:
    mk = _norm_token(margin_kind)
    if market_type == "spot":
        return "na"
    if mk not in ("linear", "inverse"):
        raise ValueError(f"invalid_margin_kind:{margin_kind!r}")
    if mk not in MARGIN_KINDS:
        raise ValueError(f"invalid_margin_kind:{margin_kind!r}")
    return mk


def build_canonical_instrument_id(
    *,
    exchange: str,
    exchange_symbol: str,
    market_type: str,
    quote_asset: str,
    margin_kind: str,
    contract_multiplier: float | int | str,
    contract_rule_version: str,
) -> str:
    """Stable instrument id — exchange+product+spec version, never symbol alone.

    Same ``BTCUSDT`` on two exchanges yields distinct ids.
    Spot and perp of the same ticker yield distinct ids.
    Contract rule version changes yield distinct ids.
    """
    ex = _norm_token(exchange)
    sym = str(exchange_symbol or "").strip().upper()
    mt = _require_market_type(market_type)
    mk = _require_margin_kind(margin_kind, market_type=mt)
    quote = normalize_asset_code(quote_asset)
    ver = str(contract_rule_version or "").strip()
    if not ex or not sym or not quote or not ver:
        raise ValueError("missing_identity_component")
    try:
        mult = format(float(contract_multiplier), ".12g")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_contract_multiplier:{contract_multiplier!r}") from exc

    material = {
        "v": IDENTITY_VERSION,
        "exchange": ex,
        "exchange_symbol": sym,
        "market_type": mt,
        "quote_asset": quote,
        "margin_kind": mk,
        "contract_multiplier": mult,
        "contract_rule_version": ver,
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    # Human-readable prefix + collision-resistant digest.
    return f"inst:{ex}:{mt}:{mk}:{sym}:{ver}:{digest}"


def identity_key_tuple(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _norm_token(str(record.get("exchange") or "")),
        str(record.get("exchange_symbol") or "").strip().upper(),
        _norm_token(str(record.get("market_type") or "")),
        normalize_asset_code(str(record.get("quote_asset") or "")),
        _norm_token(str(record.get("margin_kind") or "na")),
        format(float(record.get("contract_multiplier") or 1), ".12g"),
        str(record.get("contract_rule_version") or "").strip(),
    )


def instruments_share_symbol_string(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return str(a.get("exchange_symbol") or "").upper() == str(b.get("exchange_symbol") or "").upper()


def instruments_are_same_instrument(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("canonical_instrument_id") == b.get("canonical_instrument_id")

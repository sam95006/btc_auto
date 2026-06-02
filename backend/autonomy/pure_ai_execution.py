"""Last-mile Pure AI order preparation so proposals actually reach Binance testnet."""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from backend.autonomy.pure_ai_orchestrator import PureAiOrchestrator
from config.pure_ai_trading_config import PURE_AI_MAX_MARGIN_USD, PURE_AI_PREFERRED_SYMBOLS, PURE_AI_UNIVERSE_MAX_SYMBOLS


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return default


def tradable_symbol_set(futures_client) -> Set[str]:
    """
    Tradable set used for last-mile remapping.
    Prefer the runtime-provided universe (via futures_client ticker filter) but fall back to preferred symbols.
    """
    base = list(PURE_AI_PREFERRED_SYMBOLS)
    if futures_client is None:
        return set(base)
    try:
        if hasattr(futures_client, "is_configured") and not futures_client.is_configured():
            return set(base)
        # If available, use top liquidity list from exchange to widen symbol choices.
        if hasattr(futures_client, "fetch_24h_tickers"):
            from backend.market.universe_filter_service import UniverseFilterService

            svc = UniverseFilterService(max_symbols=50)
            universe = svc.resolve_pure_ai_universe(
                futures_client=futures_client,
                radar_scan={},
                max_symbols=int(PURE_AI_UNIVERSE_MAX_SYMBOLS),
                include_core_first=True,
            )
            base = list(universe or base)
        if hasattr(futures_client, "filter_tradable_symbols"):
            return set(futures_client.filter_tradable_symbols(list(base)))
    except Exception:
        return set(base)
    return set(base)


def remap_to_tradable_symbol(symbol: str, tradable: Set[str]) -> Optional[str]:
    symbol = str(symbol or "").upper().replace("/", "")
    if not symbol:
        return None
    if symbol in tradable:
        return symbol
    for candidate in PURE_AI_PREFERRED_SYMBOLS:
        if candidate in tradable:
            return candidate
    return None


def prepare_pure_ai_execution_request(
    request: Dict[str, Any],
    *,
    deployable_pool: float,
    radar_available: float,
    futures_client=None,
) -> Dict[str, Any]:
    """
    Re-apply Pure AI sizing after generic finalize(), remap invalid testnet symbols,
    and strip fields that inflate margin.
    """
    request = dict(request or {})
    source = str(request.get("decision_source") or "")
    if not source.startswith(("pure_ai", "ai_flex")):
        return request

    tradable = tradable_symbol_set(futures_client)
    symbol = str(request.get("symbol") or request.get("symbol_override") or "").upper()
    mapped = remap_to_tradable_symbol(symbol, tradable)
    if not mapped:
        request["_execution_block"] = "no_tradable_symbol"
        return request
    if mapped != symbol:
        request["symbol"] = mapped
        request["symbol_override"] = mapped
        request["remapped_from"] = symbol
    from config.fleet_routing_config import core_fleet_for_symbol, is_core_symbol

    final_symbol = str(request.get("symbol") or "").upper()
    if is_core_symbol(final_symbol):
        owner = core_fleet_for_symbol(final_symbol)
        if owner:
            request["fleet"] = owner
            request["capital_pool"] = "fleet"

    request.pop("margin_pct_deployable", None)
    request = PureAiOrchestrator.apply_aggressive_sizing(
        request,
        deployable_pool=_safe_float(deployable_pool),
        radar_available=_safe_float(radar_available),
    )

    margin = _safe_float(request.get("margin"))
    if margin <= 0 or margin > PURE_AI_MAX_MARGIN_USD + 0.01:
        request["_execution_block"] = "pure_ai_margin_invalid"
    return request


def resolve_execution_price(symbol: str, symbol_prices: Dict[str, float], futures_client=None) -> float:
    symbol = str(symbol or "").upper()
    price = _safe_float((symbol_prices or {}).get(symbol))
    if price > 0:
        return price
    if futures_client is None:
        return 0.0
    try:
        ticker = futures_client.get_book_ticker(symbol)
        bid = _safe_float(ticker.get("bidPrice"))
        ask = _safe_float(ticker.get("askPrice"))
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2.0, 8)
        if bid > 0:
            return bid
        if ask > 0:
            return ask
    except Exception:
        return 0.0
    return 0.0

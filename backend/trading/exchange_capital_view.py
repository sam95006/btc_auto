"""Build UI capital numbers strictly from Binance REST account payloads."""

from __future__ import annotations

from typing import Any, Dict


def _safe_float(value) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _balance_total(balances: dict, asset: str) -> float:
    payload = balances.get(asset, {}) if isinstance(balances, dict) else {}
    if not isinstance(payload, dict):
        return 0.0
    return _safe_float(payload.get("free")) + _safe_float(payload.get("locked"))


def build_spot_capital_from_binance(spot_account: dict | None) -> Dict[str, Any]:
    """Spot treasury from Binance Spot testnet `GET /api/v3/account` balances."""
    spot_account = spot_account or {}
    balances = spot_account.get("balances") or {}

    usdt_total = _safe_float(spot_account.get("usdt_total"))
    usdc_total = _safe_float(spot_account.get("usdc_total"))
    if not usdt_total and balances:
        usdt_total = _balance_total(balances, "USDT")
    if not usdc_total and balances:
        usdc_total = _balance_total(balances, "USDC")

    stable_total = _safe_float(spot_account.get("spot_stable_total") or spot_account.get("stable_total"))
    if not stable_total:
        stable_total = usdt_total + usdc_total

    return {
        "source": "binance_spot_rest",
        "usdt_total": round(usdt_total, 4),
        "usdc_total": round(usdc_total, 4),
        "stable_total": round(stable_total, 4),
        "stable_free": round(_safe_float(spot_account.get("stable_free")), 4),
        "update_time": int(spot_account.get("update_time") or 0),
        "sync_status": str(spot_account.get("sync_status") or ""),
        "sync_error": str(spot_account.get("sync_error") or ""),
    }


def futures_equity_from_account(futures_account: dict | None) -> float:
    """USDT-M account equity from Binance `fapi/v2/account` summary fields."""
    futures_account = futures_account or {}
    exchange = futures_account.get("exchange_account") or {}
    equity = _safe_float(exchange.get("totalMarginBalance"))
    if not equity:
        equity = _safe_float(futures_account.get("exchange_margin_balance"))
    if not equity:
        equity = _safe_float(futures_account.get("margin_total"))
    return equity


def build_futures_capital_from_binance(futures_account: dict | None) -> Dict[str, Any]:
    """Futures equity from Binance USDT-M `GET /fapi/v2/account` summary fields."""
    futures_account = futures_account or {}
    exchange = futures_account.get("exchange_account") or {}

    wallet = _safe_float(exchange.get("totalWalletBalance"))
    if not wallet:
        wallet = _safe_float(futures_account.get("exchange_wallet_balance"))

    equity = _safe_float(exchange.get("totalMarginBalance"))
    if not equity:
        equity = _safe_float(futures_account.get("exchange_margin_balance"))

    unrealized = _safe_float(exchange.get("totalUnrealizedProfit"))
    if not unrealized:
        unrealized = _safe_float(futures_account.get("unrealized_pnl"))

    available = _safe_float(exchange.get("availableBalance"))
    if not available:
        available = _safe_float(futures_account.get("available_balance"))

    return {
        "source": "binance_futures_rest",
        "wallet_balance": round(wallet, 4),
        "margin_balance": round(equity, 4),
        "unrealized_pnl": round(unrealized, 4),
        "available_balance": round(available, 4),
        "update_time": int(futures_account.get("update_time") or 0),
        "sync_status": str(futures_account.get("sync_status") or ""),
        "sync_error": str(futures_account.get("sync_error") or ""),
    }


def build_ui_capital(
    spot_account: dict | None,
    futures_account: dict | None,
    *,
    futures_configured: bool = True,
    spot_configured: bool = True,
) -> Dict[str, Any]:
    """
    Capital block for dashboard — every displayed total comes from Binance REST.
    Internal ledger allocations are intentionally excluded from `total`.
    """
    spot = build_spot_capital_from_binance(spot_account if spot_configured else {})
    futures = build_futures_capital_from_binance(futures_account if futures_configured else {})

    spot_stable = spot["stable_total"] if spot_configured else 0.0
    futures_equity = futures["margin_balance"] if futures_configured else 0.0
    combined = round(spot_stable + futures_equity, 4)

    return {
        "source": "binance_rest",
        "total": combined,
        "spot_total": spot_stable,
        "spot_stable_total": spot_stable,
        "spot_usdt_total": spot["usdt_total"],
        "spot_usdc_total": spot["usdc_total"],
        "spot_stable_free": spot["stable_free"],
        "futures_total": futures_equity,
        "futures_wallet_display": futures["wallet_balance"],
        "futures_exchange_wallet_balance": futures["wallet_balance"],
        "futures_exchange_margin_balance": futures["margin_balance"],
        "futures_unrealized_pnl": futures["unrealized_pnl"],
        "futures_available_balance": futures["available_balance"],
        "binance_spot": spot,
        "binance_futures": futures,
    }

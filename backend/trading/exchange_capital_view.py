"""Build UI capital numbers strictly from Binance REST account payloads."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Tuple

from config.capital_display_config import TREASURY_DISPLAY_ASSETS


def api_key_fingerprint(api_key: str) -> str:
    raw = (api_key or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


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


def _treasury_assets() -> tuple[str, ...]:
    return tuple(str(asset).upper() for asset in TREASURY_DISPLAY_ASSETS if asset)


def treasury_totals_from_balances(
    balances: dict | None,
    assets: tuple[str, ...] | None = None,
) -> Tuple[float, float, float]:
    """Sum configured treasury assets only (default USDT)."""
    balances = balances or {}
    assets = assets or _treasury_assets()
    usdt = _balance_total(balances, "USDT") if "USDT" in assets else 0.0
    usdc = _balance_total(balances, "USDC") if "USDC" in assets else 0.0
    stable = sum(_balance_total(balances, asset) for asset in assets)
    return usdt, usdc, stable


def _futures_asset_row(futures_account: dict | None, asset: str) -> Dict[str, Any]:
    futures_account = futures_account or {}
    target = str(asset or "USDT").upper()
    for row in futures_account.get("balance_assets") or []:
        if str(row.get("asset", "")).upper() == target:
            return row
    return {}


def _futures_usdt_asset_capital(futures_account: dict | None) -> Dict[str, float]:
    """
    USDT row from `GET /fapi/v2/balance` — matches Binance Demo「資產列表」USDT 列，
    not the account-wide USD total that includes USDC/BTC.
    """
    row = _futures_asset_row(futures_account, "USDT")
    wallet = _safe_float(row.get("balance"))
    cross_wallet = _safe_float(row.get("cross_wallet_balance")) or wallet
    unrealized = _safe_float(row.get("cross_unrealized_pnl"))
    margin = cross_wallet + unrealized
    if not margin and wallet:
        margin = wallet + unrealized
    available = _safe_float(row.get("available_balance"))
    return {
        "wallet_balance": round(wallet, 4),
        "margin_balance": round(margin, 4),
        "unrealized_pnl": round(unrealized, 4),
        "available_balance": round(available, 4),
    }


def build_spot_capital_from_binance(spot_account: dict | None) -> Dict[str, Any]:
    """Spot treasury from Binance Spot testnet `GET /api/v3/account` balances."""
    spot_account = spot_account or {}
    balances = spot_account.get("balances") or {}
    assets = _treasury_assets()

    if balances:
        usdt_total, usdc_total, stable_total = treasury_totals_from_balances(balances, assets)
    else:
        usdt_total = _safe_float(spot_account.get("usdt_total")) if "USDT" in assets else 0.0
        usdc_total = _safe_float(spot_account.get("usdc_total")) if "USDC" in assets else 0.0
        stable_total = usdt_total + usdc_total

    scope = "usdt_only" if assets == ("USDT",) else "treasury_" + "_".join(assets).lower()

    return {
        "source": "binance_spot_rest",
        "display_scope": scope,
        "treasury_assets": list(assets),
        "usdt_total": round(usdt_total, 4),
        "usdc_total": round(usdc_total, 4),
        "stable_total": round(stable_total, 4),
        "stable_free": round(_safe_float(spot_account.get("stable_free")), 4),
        "holdings_total": round(_safe_float(spot_account.get("holdings_total")), 4),
        "update_time": int(spot_account.get("update_time") or 0),
        "sync_status": str(spot_account.get("sync_status") or ""),
        "sync_error": str(spot_account.get("sync_error") or ""),
    }


def futures_equity_from_account(futures_account: dict | None) -> float:
    """Futures treasury equity for configured assets (default USDT asset row only)."""
    assets = _treasury_assets()
    if assets == ("USDT",):
        return _futures_usdt_asset_capital(futures_account)["margin_balance"]

    futures_account = futures_account or {}
    exchange = futures_account.get("exchange_account") or {}
    equity = _safe_float(exchange.get("totalMarginBalance"))
    if equity:
        return equity
    return _safe_float(futures_account.get("exchange_margin_balance"))


def build_futures_capital_from_binance(futures_account: dict | None) -> Dict[str, Any]:
    """Futures capital — USDT-only mode uses per-asset USDT row, not whole-account USD total."""
    futures_account = futures_account or {}
    assets = _treasury_assets()

    if assets == ("USDT",):
        usdt_capital = _futures_usdt_asset_capital(futures_account)
        return {
            "source": "binance_futures_rest",
            "display_scope": "usdt_asset_row_only",
            "market_type": "USDT_M",
            "coin_margined_included": False,
            "treasury_assets": ["USDT"],
            "wallet_balance": usdt_capital["wallet_balance"],
            "margin_balance": usdt_capital["margin_balance"],
            "unrealized_pnl": usdt_capital["unrealized_pnl"],
            "available_balance": usdt_capital["available_balance"],
            "account_total_margin_balance": round(
                _safe_float((futures_account.get("exchange_account") or {}).get("totalMarginBalance")),
                4,
            ),
            "using_exchange_summary": False,
            "update_time": int(futures_account.get("update_time") or 0),
            "sync_status": str(futures_account.get("sync_status") or ""),
            "sync_error": str(futures_account.get("sync_error") or ""),
        }

    exchange = futures_account.get("exchange_account") or {}
    wallet = _safe_float(exchange.get("totalWalletBalance"))
    equity = _safe_float(exchange.get("totalMarginBalance"))
    unrealized = _safe_float(exchange.get("totalUnrealizedProfit"))
    available = _safe_float(exchange.get("availableBalance"))

    if not wallet:
        wallet = _safe_float(futures_account.get("exchange_wallet_balance"))
    if not equity:
        equity = _safe_float(futures_account.get("exchange_margin_balance"))
    if not unrealized:
        unrealized = _safe_float(futures_account.get("unrealized_pnl"))
    if not available:
        available = _safe_float(futures_account.get("available_balance"))

    return {
        "source": "binance_futures_rest",
        "display_scope": "usdt_m_fapi_v2_account_summary",
        "market_type": "USDT_M",
        "coin_margined_included": False,
        "treasury_assets": list(assets),
        "wallet_balance": round(wallet, 4),
        "margin_balance": round(equity, 4),
        "unrealized_pnl": round(unrealized, 4),
        "available_balance": round(available, 4),
        "using_exchange_summary": bool(exchange.get("totalMarginBalance") or exchange.get("totalWalletBalance")),
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
    Capital block for dashboard — treasury totals from Binance REST only.
    Default: USDT only (excludes USDC/BTC from totals; matches Demo 資產列表 USDT 列).
    """
    spot = build_spot_capital_from_binance(spot_account if spot_configured else {})
    futures = build_futures_capital_from_binance(futures_account if futures_configured else {})

    spot_stable = spot["stable_total"] if spot_configured else 0.0
    futures_equity = futures["margin_balance"] if futures_configured else 0.0
    combined = round(spot_stable + futures_equity, 4)

    assets = _treasury_assets()
    scope = "usdt_only_treasury" if assets == ("USDT",) else "multi_asset_treasury"

    return {
        "source": "binance_rest",
        "display_scope": scope,
        "treasury_assets": list(assets),
        "coin_margined_included": False,
        "futures_market_scope": "usdt_m",
        "total": combined,
        "spot_total": spot_stable,
        "spot_stable_total": spot_stable,
        "spot_usdt_total": spot["usdt_total"],
        "spot_usdc_total": spot["usdc_total"],
        "spot_stable_free": spot["stable_free"],
        "spot_holdings_total": spot["holdings_total"],
        "futures_total": futures_equity,
        "futures_wallet_display": futures["wallet_balance"],
        "futures_exchange_wallet_balance": futures["wallet_balance"],
        "futures_exchange_margin_balance": futures["margin_balance"],
        "futures_unrealized_pnl": futures["unrealized_pnl"],
        "futures_available_balance": futures["available_balance"],
        "futures_account_total_margin": futures.get("account_total_margin_balance"),
        "futures_using_exchange_summary": futures.get("using_exchange_summary", False),
        "binance_spot": spot,
        "binance_futures": futures,
    }


def build_account_binding_status(spot_client, futures_client) -> Dict[str, Any]:
    spot_fp = api_key_fingerprint(getattr(spot_client, "api_key", ""))
    futures_fp = api_key_fingerprint(getattr(futures_client, "api_key", ""))
    mismatch = bool(spot_fp and futures_fp and spot_fp != futures_fp)
    futures_base = getattr(futures_client, "base_url", getattr(futures_client, "BASE_URL", ""))
    return {
        "spot_api_key_fp": spot_fp,
        "futures_api_key_fp": futures_fp,
        "same_api_key_pair": spot_fp == futures_fp if (spot_fp and futures_fp) else None,
        "accounts_mismatch": mismatch,
        "spot_base_url": getattr(spot_client, "base_url", ""),
        "futures_base_url": futures_base,
        "futures_scope": "usdt_m",
        "treasury_assets": list(_treasury_assets()),
        "coin_margined_included": False,
        "futures_base_url_is_usdt_m_demo": "demo-fapi.binance.com" in str(futures_base),
    }

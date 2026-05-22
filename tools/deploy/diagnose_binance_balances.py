#!/usr/bin/env python3
"""Print Binance testnet treasury fields (no secrets). Compare with Binance App."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.env_loader import load_env_file

load_env_file()

from backend.trading.binance_futures_testnet_client import BinanceFuturesTestnetClient
from backend.trading.binance_spot_testnet_client import BinanceSpotTestnetClient
from backend.trading.exchange_capital_view import build_ui_capital, treasury_totals_from_balances


def _key_fp(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "MISSING"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _top_balances(balances: dict, limit: int = 12) -> list:
    rows = []
    for asset, payload in (balances or {}).items():
        total = float(payload.get("free", 0) or 0) + float(payload.get("locked", 0) or 0)
        if total > 0.0001:
            rows.append((asset, round(total, 4)))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows[:limit]


def main() -> int:
    spot = BinanceSpotTestnetClient()
    futures = BinanceFuturesTestnetClient()

    print("=== API endpoints ===")
    print(f"spot_base_url: {spot.base_url}")
    print(f"futures_base_url: {futures.base_url}")
    print(f"spot_key_fp: {_key_fp(spot.api_key)}")
    print(f"futures_key_fp: {_key_fp(futures.api_key)}")
    print(f"same_key_pair: {_key_fp(spot.api_key) == _key_fp(futures.api_key)}")

    if not spot.is_configured():
        print("spot: NOT CONFIGURED")
    else:
        account = spot.get_account()
        balances = {
            item["asset"]: {
                "free": float(item.get("free", 0) or 0),
                "locked": float(item.get("locked", 0) or 0),
            }
            for item in account.get("balances", [])
            if float(item.get("free", 0) or 0) or float(item.get("locked", 0) or 0)
        }
        usdt, usdc, stable = treasury_totals_from_balances(balances)
        print("\n=== Spot /api/v3/account (raw) ===")
        print(f"USDT free+locked: {usdt}")
        print(f"USDC free+locked: {usdc}")
        print(f"treasury USDT+USDC: {stable}")
        print(f"top_balances: {json.dumps(_top_balances(balances), ensure_ascii=False)}")

    if not futures.is_configured():
        print("futures: NOT CONFIGURED")
    else:
        info = futures.get_account_information()
        print("\n=== Futures /fapi/v2/account (summary) ===")
        for field in (
            "totalWalletBalance",
            "totalMarginBalance",
            "totalUnrealizedProfit",
            "availableBalance",
            "maxWithdrawAmount",
        ):
            print(f"{field}: {info.get(field)}")
        bal = futures.get_balances()
        top = []
        for item in bal or []:
            b = float(item.get("balance", 0) or 0)
            if b > 0.0001:
                top.append((item.get("asset"), round(b, 4)))
        top.sort(key=lambda x: x[1], reverse=True)
        print(f"top_futures_balances: {json.dumps(top[:8], ensure_ascii=False)}")

    if spot.is_configured() and futures.is_configured():
        spot_account = {"balances": balances, "update_time": 1, "sync_status": "ok"}
        futures_account = {
            "exchange_account": {
                "totalWalletBalance": info.get("totalWalletBalance"),
                "totalMarginBalance": info.get("totalMarginBalance"),
                "totalUnrealizedProfit": info.get("totalUnrealizedProfit"),
                "availableBalance": info.get("availableBalance"),
            },
            "exchange_wallet_balance": float(info.get("totalWalletBalance", 0) or 0),
            "exchange_margin_balance": float(info.get("totalMarginBalance", 0) or 0),
            "unrealized_pnl": float(info.get("totalUnrealizedProfit", 0) or 0),
            "update_time": 2,
            "sync_status": "ok",
        }
        capital = build_ui_capital(spot_account, futures_account)
        print("\n=== UI capital (what dashboard should show) ===")
        print(json.dumps(
            {
                "total": capital["total"],
                "spot_usdt": capital["spot_usdt_total"],
                "spot_usdc": capital["spot_usdc_total"],
                "spot_stable": capital["spot_stable_total"],
                "futures_wallet": capital["futures_wallet_display"],
                "futures_equity": capital["futures_total"],
                "futures_unrealized": capital["futures_unrealized_pnl"],
            },
            indent=2,
        ))

    print("\nNote: NEXUS only queries USDT-M (U本位) demo-fapi — coin-margined (幣本位/dapi) is NEVER included.")
    print("App tabs: compare 'U本位合約' margin balance to futures_equity; ignore '幣本位合約' tab.")
    print("If U本位 in App (~9277) differs from futures_equity here, regenerate API keys from the SAME demo account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

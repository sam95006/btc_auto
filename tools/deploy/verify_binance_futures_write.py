#!/usr/bin/env python3
"""Verify Binance futures demo READ vs WRITE (no secrets printed)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.env_loader import load_env_file

load_env_file()

from backend.trading.binance_futures_testnet_client import BinanceFuturesTestnetClient, BinanceTestnetError
from backend.trading.binance_spot_testnet_client import BinanceSpotTestnetClient


def _key_fp(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "MISSING"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _probe(label, fn):
    try:
        payload = fn()
        return {"ok": True, "label": label, "detail": payload}
    except Exception as exc:
        return {"ok": False, "label": label, "error": str(exc)}


def main() -> int:
    futures = BinanceFuturesTestnetClient()
    spot = BinanceSpotTestnetClient()

    report = {
        "futures_base_url": futures.base_url,
        "futures_key_fp": futures.api_key_fingerprint(),
        "spot_base_url": spot.base_url,
        "spot_key_fp": _key_fp(spot.api_key) if spot.is_configured() else "MISSING",
        "probes": [],
    }

    if not futures.is_configured():
        print(json.dumps({"ok": False, "error": "futures_credentials_missing"}, indent=2))
        return 1

    report["probes"].append(
        _probe(
            "futures_read_account",
            lambda: {
                "canTrade": futures.get_account_information().get("canTrade"),
                "tradeGroupId": futures.get_account_information().get("tradeGroupId"),
                "wallet": futures.get_account_information().get("totalWalletBalance"),
            },
        )
    )
    live = futures.fetch_open_position("ETHUSDT")
    report["open_eth_position"] = live
    report["probes"].append(
        _probe(
            "futures_order_test_endpoint",
            lambda: futures.test_market_order(
                "ETHUSDT",
                "SELL" if live and float(live["position_amt"]) > 0 else "BUY",
                futures.normalize_quantity("ETHUSDT", abs(float(live["position_amt"])) if live else 0.01),
                reduce_only=bool(live),
                position_side="BOTH",
                omit_position_side=False,
            ),
        )
    )
    report["probes"].append(
        _probe(
            "futures_real_post_margin_type",
            lambda: futures.set_margin_type_isolated("ETHUSDT"),
        )
    )
    if live:
        report["probes"].append(
            _probe(
                "futures_real_close_order",
                lambda: futures.close_open_position_market("ETHUSDT", client_order_id="nexus_write_verify"),
            )
        )

    if spot.is_configured():
        report["probes"].append(
            _probe(
                "spot_real_post_order_test",
                lambda: spot._signed_request(
                    "POST",
                    "/v3/order/test",
                    {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001"},
                ),
            )
        )

    read_ok = report["probes"][0]["ok"]
    write_ok = any(
        item.get("ok")
        for item in report["probes"]
        if item.get("label") in {"futures_real_post_margin_type", "futures_real_close_order"}
    )
    report["summary"] = {
        "futures_read_ok": read_ok,
        "futures_write_ok": write_ok,
        "diagnosis": (
            "ok"
            if write_ok
            else (
                "Futures Demo API key can READ but cannot POST trade requests (-1109). "
                "Recreate the key on https://demo.binance.com → API Management with "
                "Enable Reading + Enable Spot & Margin + Enable Futures, copy Secret immediately, "
                "update BINANCE_FUTURES_TESTNET_* in Zeabur, redeploy."
            )
        ),
    }
    report["ok"] = read_ok and write_ok
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Readonly Bybit Demo fee-rate capability probe.

Uses ONLY https://api-demo.bybit.com. Never falls back to mainnet/testnet.
Does not place orders. Does not log secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

DEMO_DOMAIN = "https://api-demo.bybit.com"
FORBIDDEN_DOMAINS = ("api.bybit.com", "api-testnet.bybit.com")
ENDPOINT = "/v5/account/fee-rate"


def _redact(text: str) -> str:
    out = text or ""
    for env_key in ("BYBIT_DEMO_API_KEY", "BYBIT_DEMO_API_SECRET", "ZEABUR_TOKEN"):
        val = (os.environ.get(env_key) or "").strip()
        if val:
            out = out.replace(val, "***REDACTED***")
    out = re.sub(r"[A-Za-z0-9_\-+/=]{40,}", "***REDACTED***", out)
    return out[:500]


def _sign_headers(api_key: str, api_secret: str, payload: str) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    recv = "5000"
    sign = hmac.new(
        api_secret.encode("utf-8"),
        f"{timestamp}{api_key}{recv}{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-BAPI-API-KEY": api_key,
        "X-BAPI-SIGN": sign,
        "X-BAPI-SIGN-TYPE": "2",
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv,
        "User-Agent": "NEXUS-DemoFeeCapabilityProbe/1.0",
    }


def _classify(http_status: int | None, ret_code: Any, ret_msg: str, rows: list) -> dict[str, Any]:
    msg = (ret_msg or "").lower()
    unsupported_tokens = (
        "not support",
        "not supported",
        "unsupported",
        "demo trading does not support",
        "not available for demo",
        "permission denied for demo",
        "invalid request path",
        "404",
    )
    auth_tokens = ("invalid api-key", "api key is invalid", "sign", "permission denied", "unauthorized", "10003", "10004", "10005")

    maker = taker = None
    maker_present = taker_present = False
    if rows and isinstance(rows[0], dict):
        maker_present = rows[0].get("makerFeeRate") is not None
        taker_present = rows[0].get("takerFeeRate") is not None
        try:
            if maker_present:
                maker = float(rows[0].get("makerFeeRate"))
            if taker_present:
                taker = float(rows[0].get("takerFeeRate"))
        except (TypeError, ValueError):
            return {
                "endpoint_supported": True,
                "fee_rate_status": "FEE_RATE_SCHEMA_MISMATCH",
                "maker_fee_rate": "UNAVAILABLE",
                "taker_fee_rate": "UNAVAILABLE",
            }

    if http_status == 200 and str(ret_code) in {"0", "None"} and rows and taker is not None and taker > 0:
        return {
            "endpoint_supported": True,
            "fee_rate_status": "FEE_RATE_LIVE",
            "maker_fee_rate": maker if maker is not None else "UNAVAILABLE",
            "taker_fee_rate": taker,
            "maker_fee_present": maker_present,
            "taker_fee_present": taker_present,
        }

    if http_status == 200 and str(ret_code) in {"0", "None"} and (not rows or taker is None or taker <= 0):
        return {
            "endpoint_supported": True,
            "fee_rate_status": "FEE_RATE_SCHEMA_MISMATCH",
            "maker_fee_rate": maker if maker is not None else "UNAVAILABLE",
            "taker_fee_rate": taker if taker is not None else "UNAVAILABLE",
            "maker_fee_present": maker_present,
            "taker_fee_present": taker_present,
        }

    if any(t in msg for t in unsupported_tokens) or str(ret_code) in {"404", "10001", "10016"}:
        # 10001 often param/path; still may be unsupported on demo — mark unsupported when msg hints demo
        if any(t in msg for t in unsupported_tokens) or "demo" in msg:
            return {
                "endpoint_supported": False,
                "fee_rate_status": "DEMO_FEE_ENDPOINT_UNSUPPORTED",
                "maker_fee_rate": "UNAVAILABLE",
                "taker_fee_rate": "UNAVAILABLE",
            }

    if http_status in {401, 403} or any(t in msg for t in auth_tokens) or str(ret_code) in {"10003", "10004", "10005", "33004"}:
        return {
            "endpoint_supported": "UNKNOWN",
            "fee_rate_status": "FEE_RATE_AUTH_FAILED",
            "maker_fee_rate": "UNAVAILABLE",
            "taker_fee_rate": "UNAVAILABLE",
        }

    if http_status is None:
        return {
            "endpoint_supported": "UNKNOWN",
            "fee_rate_status": "FEE_RATE_UNAVAILABLE",
            "maker_fee_rate": "UNAVAILABLE",
            "taker_fee_rate": "UNAVAILABLE",
        }

    # Non-zero ret on demo with unclear msg: treat as unsupported-or-unavailable, prefer unsupported when path-ish
    if str(ret_code) not in {"0", "None", ""} and http_status == 200:
        return {
            "endpoint_supported": False,
            "fee_rate_status": "DEMO_FEE_ENDPOINT_UNSUPPORTED",
            "maker_fee_rate": "UNAVAILABLE",
            "taker_fee_rate": "UNAVAILABLE",
            "classification_note": "non_zero_ret_on_demo_fee_rate_treated_as_unsupported_pending_docs",
        }

    return {
        "endpoint_supported": "UNKNOWN",
        "fee_rate_status": "FEE_RATE_UNAVAILABLE",
        "maker_fee_rate": "UNAVAILABLE",
        "taker_fee_rate": "UNAVAILABLE",
    }


def probe_symbol(api_key: str, api_secret: str, symbol: str) -> dict[str, Any]:
    params = {"category": "linear", "symbol": symbol.upper()}
    query = urlencode(sorted(params.items()))
    url = f"{DEMO_DOMAIN}{ENDPOINT}?{query}"
    assert all(d not in url for d in FORBIDDEN_DOMAINS)
    headers = _sign_headers(api_key, api_secret, query)
    observed_at = time.time()
    http_status = None
    body: dict[str, Any] = {}
    err = None
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            http_status = int(resp.status)
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        http_status = int(exc.code)
        try:
            body = json.loads(exc.read().decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001
            body = {}
        err = f"HTTPError:{http_status}"
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__

    ret_code = body.get("retCode")
    ret_msg = str(body.get("retMsg") or "")
    rows = ((body.get("result") or {}) if isinstance(body.get("result"), dict) else {}).get("list") or []
    if not isinstance(rows, list):
        rows = []
    classified = _classify(http_status, ret_code, ret_msg, rows)
    return {
        "symbol": symbol.upper(),
        "domain": DEMO_DOMAIN,
        "endpoint": ENDPOINT,
        "category": "linear",
        "http_status": http_status if http_status is not None else "UNAVAILABLE",
        "retCode": ret_code if ret_code is not None else "UNAVAILABLE",
        "retMsg_redacted": _redact(ret_msg),
        "result_list_count": len(rows),
        "response_schema": sorted(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
        "error": err,
        "observed_at": observed_at,
        "credential_mode": "BYBIT_DEMO",
        **classified,
    }


def recommendation_for(results: list[dict[str, Any]]) -> str:
    statuses = {r.get("fee_rate_status") for r in results}
    supported = {r.get("endpoint_supported") for r in results}
    if statuses <= {"FEE_RATE_LIVE"} and supported <= {True}:
        return "DEMO_FEE_RATE_LIVE_VERIFIED"
    if "DEMO_FEE_ENDPOINT_UNSUPPORTED" in statuses and "FEE_RATE_LIVE" not in statuses:
        return "DEMO_FEE_ENDPOINT_UNSUPPORTED_USE_APPROVED_CONSERVATIVE"
    return "DEMO_FEE_RATE_PARTIAL_WITH_BLOCKERS"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    args = ap.parse_args()

    api_key = (os.environ.get("BYBIT_DEMO_API_KEY") or "").strip()
    api_secret = (os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip()
    if not api_key or not api_secret:
        print("missing_demo_credentials")
        return 2

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    results = [probe_symbol(api_key, api_secret, s) for s in symbols]
    rec = recommendation_for(results)
    primary = results[0] if results else {}
    summary = {
        "demo_domain": DEMO_DOMAIN,
        "endpoint": ENDPOINT,
        "category": "linear",
        "symbols_tested": symbols,
        "results": results,
        "endpoint_supported": primary.get("endpoint_supported"),
        "fee_rate_status": primary.get("fee_rate_status"),
        "maker_fee_rate": primary.get("maker_fee_rate"),
        "taker_fee_rate": primary.get("taker_fee_rate"),
        "fee_source": (
            "bybit_demo:/v5/account/fee-rate"
            if primary.get("fee_rate_status") == "FEE_RATE_LIVE"
            else "UNAVAILABLE"
        ),
        "fallback_required": primary.get("fee_rate_status") != "FEE_RATE_LIVE",
        "fallback_honesty": "FEE_RATE_CONFIGURED_CONSERVATIVE_requires_founder_approval",
        "secret_redaction": True,
        "forbidden_domain_fallback_used": False,
        "recommendation": rec,
        "observed_at": time.time(),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "results"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

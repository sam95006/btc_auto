#!/usr/bin/env python3
"""Redacted HTTPS verification for deployed nexus-api-staging."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

RE_DSN = re.compile(r"postgres(?:ql)?://\S+", re.I)


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    raw = RE_DSN.sub("<REDACTED>", raw)
    return json.loads(raw)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_api_staging_deployment.py <base_url>", file=sys.stderr)
        return 2
    base = sys.argv[1].rstrip("/")
    try:
        health = _fetch(f"{base}/health")
        product = _fetch(f"{base}/api/v1/product/health")
        readiness = _fetch(f"{base}/api/v1/product/readiness")
        capabilities = _fetch(f"{base}/api/v1/product/capabilities")
        snapshot = _fetch(f"{base}/api/v1/market/snapshot")
        history = _fetch(f"{base}/api/v1/market/history?symbol=BTCUSDT&interval=1h&limit=2")
        rankings = _fetch(f"{base}/api/v1/market/rankings?metric=gainers&limit=2")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1
    pg = product.get("postgres") or {}
    shadow = product.get("shadow_readonly") or {}
    out = {
        "ok": True,
        "health_status": health.get("status"),
        "postgres_status": pg.get("status"),
        "postgres_configured": pg.get("configured"),
        "postgres_connected": pg.get("connected"),
        "runtime_binding": shadow.get("binding"),
        "readiness_ready": readiness.get("ready"),
        "readiness_checks": readiness.get("checks"),
        "capabilities_ok": (capabilities.get("validation") or {}).get("ok"),
        "market_snapshot_class": snapshot.get("data_class"),
        "market_history_symbol": history.get("symbol"),
        "market_rankings_class": rankings.get("classification"),
    }
    print(json.dumps(out))
    if not readiness.get("ready"):
        return 1
    if shadow.get("binding") != "UNAVAILABLE":
        return 1
    if (capabilities.get("validation") or {}).get("ok") is not True:
        return 1
    if snapshot.get("data_class") != "LIVE_READ_ONLY":
        return 1
    if history.get("symbol") != "BTCUSDT":
        return 1
    if rankings.get("classification") != "LIVE_API":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Remote HTTPS smoke for NEXUS member preview (post Founder Zeabur deploy)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


ROUTES = (
    "/",
    "/opportunities",
    "/scanner",
    "/alerts",
    "/intelligence",
    "/preview/v18_2_1/review",
)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, timeout: float = 30.0) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "nexus-preview-validator/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read(65536).decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, body, headers


def main() -> int:
    p = argparse.ArgumentParser(description="Validate remote NEXUS preview base URL")
    p.add_argument("--base-url", required=True, help="e.g. https://nexus-member-preview-v18-2-1.zeabur.app")
    p.add_argument("--out", default="", help="Optional JSON result path")
    args = p.parse_args()
    base = args.base_url.rstrip("/")
    if not base.startswith("https://"):
        print("FAIL: base-url must be HTTPS", file=sys.stderr)
        return 2

    result: dict[str, Any] = {
        "schema": "nexus_remote_preview_validation_v1",
        "generated_at": utc(),
        "base_url": base,
        "routes": {},
        "health": None,
        "broken_route_count": 0,
        "asset_failure_count": 0,
        "javascript_boot_failure_count": 0,
        "status": "FAIL",
    }

    # Health
    try:
        code, body, _ = fetch(f"{base}/health")
        result["health"] = {"status_code": code, "body_preview": body[:500]}
        if code != 200:
            result["broken_route_count"] += 1
    except urllib.error.URLError as e:
        result["health"] = {"error": str(e)}
        result["broken_route_count"] += 1

    for route in ROUTES:
        url = f"{base}{route}"
        entry: dict[str, Any] = {"url": url}
        try:
            code, body, headers = fetch(url)
            entry["status_code"] = code
            entry["content_type"] = headers.get("content-type", "")
            if code >= 400:
                result["broken_route_count"] += 1
            if "text/html" in entry["content_type"] and len(body) < 200:
                result["javascript_boot_failure_count"] += 1
            if route.endswith("/review") and "member_surface" not in body.lower() and code == 200:
                entry["note"] = "check SPA boot manually"
        except urllib.error.URLError as e:
            entry["error"] = str(e)
            result["broken_route_count"] += 1
        result["routes"][route] = entry

    result["status"] = "PASS" if result["broken_route_count"] == 0 else "FAIL"
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

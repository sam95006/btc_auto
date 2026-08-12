#!/usr/bin/env python3
"""Poll member preview for V18.2.26 founder monitor deploy."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request

BASE = "https://nexus-member-preview-v18-2-1.zeabur.app"
MARKER = "PUBLIC_V18_2_22_CLOSED_BETA_READINESS_HEAD"
NEW_ASSET = "index-BZz1Xiib.js"


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "User-Agent": "v18_2_26_smoke"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def main() -> None:
    last: dict | None = None
    for i in range(40):
        out: dict = {"attempt": i + 1}
        try:
            st, html = get(f"{BASE}/")
            out["index_status"] = st
            m = re.search(r"/assets/(index-[^\"']+\.js)", html)
            out["remote_js"] = m.group(1) if m else None
            out["new_asset"] = out["remote_js"] == NEW_ASSET
            if m:
                _, js = get(f"{BASE}/assets/{m.group(1)}")
                out["demo_monitor_in_js"] = "demo-monitor" in js
                out["marker_in_js"] = MARKER in js
                out["js_sha256"] = hashlib.sha256(js.encode()).hexdigest().upper()
        except Exception as exc:  # noqa: BLE001
            out["index_error"] = str(exc)
        try:
            get(f"{BASE}/api/nexus/founder/demo-monitor")
        except urllib.error.HTTPError as exc:
            out["demo_monitor_status"] = exc.code
            out["demo_monitor_body"] = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception as exc:  # noqa: BLE001
            out["demo_monitor_error"] = str(exc)
        smoke: dict[str, int | str] = {}
        for path in (
            "/overview",
            "/scanner",
            "/account",
            "/watchlist",
            "/api/nexus/ui-build",
            "/api/nexus/public/closed-beta/foundation",
            "/api/nexus/public/closed-beta/ops",
            "/api/nexus/founder/status",
            "/api/nexus/founder/live-ops",
        ):
            try:
                try:
                    st, _ = get(f"{BASE}{path}")
                    smoke[path] = st
                except urllib.error.HTTPError as exc:
                    smoke[path] = exc.code
            except Exception as exc:  # noqa: BLE001
                smoke[path] = f"ERR:{exc}"
        out["smoke"] = smoke
        out["remote_deployed"] = (
            out.get("demo_monitor_status") in (403, 200)
            and out.get("new_asset") is True
        )
        last = out
        print(
            json.dumps(
                {
                    k: out.get(k)
                    for k in (
                        "attempt",
                        "remote_js",
                        "new_asset",
                        "demo_monitor_status",
                        "demo_monitor_in_js",
                        "remote_deployed",
                    )
                }
            )
        )
        if out.get("remote_deployed"):
            break
        time.sleep(15)
    print("FINAL")
    print(json.dumps(last, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Extract first https://*.zeabur.app URL from Zeabur CLI JSON/text (no secrets)."""
from __future__ import annotations

import json
import re
import sys

RAW = sys.stdin.read()
CAND: list[str] = []


def walk(obj: object) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in {"domain", "hostname", "host", "url", "name"} and isinstance(v, str):
                CAND.append(v)
            walk(v)
    elif isinstance(obj, list):
        for item in obj:
            walk(item)


try:
    walk(json.loads(RAW))
except json.JSONDecodeError:
    pass
CAND.extend(re.findall(r"[a-z0-9.-]+\.zeabur\.app", RAW, re.I))

for c in CAND:
    host = c.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
    if "zeabur.app" in host.lower():
        print(f"https://{host}", end="")
        raise SystemExit(0)
raise SystemExit(1)

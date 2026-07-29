#!/usr/bin/env python3
"""Resolve Zeabur service id for nexus-bybit-demo-learning-validation (no secrets printed)."""
from __future__ import annotations

import json
import os
import re
import sys

SERVICE_NAME = os.environ.get("SERVICE_NAME", "nexus-bybit-demo-learning-validation")
FORBIDDEN = os.environ.get("FORBIDDEN_SERVICE_ID", "6a3b81652fdef84a45a2a553")
RAW = sys.stdin.read()


def _rows(data: object) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("services", "data", "items", "nodes"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def main() -> int:
    name = SERVICE_NAME.lower().replace("_", "-")
    sid = ""
    try:
        data = json.loads(RAW)
        for r in _rows(data):
            if not isinstance(r, dict):
                continue
            n = str(r.get("name") or r.get("serviceName") or "").lower().replace("_", "-")
            i = str(r.get("id") or r.get("_id") or r.get("serviceID") or "")
            if name in n and i and i != FORBIDDEN:
                sid = i
                break
    except json.JSONDecodeError:
        if name in RAW.lower().replace("_", "-"):
            for i in re.findall(r"[0-9a-f]{24}", RAW):
                if i != FORBIDDEN:
                    sid = i
                    break
    if not sid or sid == FORBIDDEN:
        print("", end="")
        return 1
    print(sid, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
        # Top-level deploy --json success payload
        for k in ("service_id", "serviceId", "ServiceID"):
            v = data.get(k)
            if isinstance(v, str) and v and v != FORBIDDEN:
                return [{"id": v, "name": SERVICE_NAME}]
        for k in ("services", "data", "items", "nodes"):
            v = data.get(k)
            if isinstance(v, list):
                return v
        edges = data.get("edges")
        if isinstance(edges, list):
            out = []
            for e in edges:
                if isinstance(e, dict) and isinstance(e.get("node"), dict):
                    out.append(e["node"])
            return out
    return []


def _sid(row: dict) -> str:
    for k in ("id", "_id", "ID", "service_id", "serviceId", "serviceID"):
        v = row.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _name(row: dict) -> str:
    for k in ("name", "Name", "serviceName", "service_name"):
        v = row.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def main() -> int:
    name = SERVICE_NAME.lower().replace("_", "-")
    sid = ""
    try:
        data = json.loads(RAW)
        # Prefer explicit deploy JSON key
        if isinstance(data, dict):
            for k in ("service_id", "serviceId"):
                v = data.get(k)
                if isinstance(v, str) and v and v != FORBIDDEN:
                    print(v, end="")
                    return 0
        for r in _rows(data):
            if not isinstance(r, dict):
                continue
            n = _name(r).lower().replace("_", "-")
            i = _sid(r)
            if i and i != FORBIDDEN and (not n or name in n or n in name):
                # Prefer exact name match; keep first non-forbidden otherwise if name empty
                if n == name or name in n:
                    sid = i
                    break
                if not sid and not n:
                    sid = i
        if not sid:
            # last resort: any matching name in nested walk
            for r in _rows(data):
                if isinstance(r, dict) and name in _name(r).lower().replace("_", "-"):
                    i = _sid(r)
                    if i and i != FORBIDDEN:
                        sid = i
                        break
    except json.JSONDecodeError:
        # Deploy success JSON may be mixed with spinner logs — extract service_id=
        m = re.search(r'"service_id"\s*:\s*"([0-9a-f]{24})"', RAW, re.I)
        if m and m.group(1) != FORBIDDEN:
            sid = m.group(1)
        elif name in RAW.lower().replace("_", "-"):
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

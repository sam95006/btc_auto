#!/usr/bin/env python3
"""Migrate .env BYBIT_M0_API_* to BYBIT_DEMO_API_* (local only; no secret output)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

MIGRATIONS = (
    ("BYBIT_M0_API_KEY", "BYBIT_DEMO_API_KEY"),
    ("BYBIT_M0_API_SECRET", "BYBIT_DEMO_API_SECRET"),
)
REMOVE_KEYS = {"BYBIT_M0_API_KEY", "BYBIT_M0_API_SECRET"}


def migrate() -> int:
    if not ENV_PATH.is_file():
        print("missing .env")
        return 1
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    values: dict[str, str] = {}
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        values[k.strip()] = v.strip()

    for old, new in MIGRATIONS:
        if old in values and new not in values:
            values[new] = values[old]

    out: list[str] = []
    seen_new: set[str] = set()
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            out.append(raw if raw.endswith("\n") else raw + "\n")
            continue
        k, _, _ = s.partition("=")
        key = k.strip()
        if key in REMOVE_KEYS:
            continue
        if key in {n for _, n in MIGRATIONS}:
            if key in seen_new:
                continue
            seen_new.add(key)
            out.append(f"{key}={values[key]}\n")
            continue
        out.append(raw if raw.endswith("\n") else raw + "\n")

    present_new = {n for _, n in MIGRATIONS}
    for _, new in MIGRATIONS:
        if new in values and new not in seen_new:
            out.append(f"{new}={values[new]}\n")

    ENV_PATH.write_text("".join(out), encoding="utf-8")
    old_present = any(k in values for k, _ in MIGRATIONS)
    new_present = all(values.get(n, "").strip() for _, n in MIGRATIONS)
    print(f"migration_done old_m0_api_present={old_present} new_demo_api_present={new_present}")
    return 0 if new_present else 1


if __name__ == "__main__":
    raise SystemExit(migrate())

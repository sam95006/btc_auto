#!/usr/bin/env python3
"""
Print SET/MISSING for each variable listed in .env.example (no secret values).

Use locally and compare mentally with Zeabur Variables to avoid Binance / NEXUS misconfig.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv_if_present():
    try:
        from dotenv import load_dotenv
    except Exception:
        load_dotenv = None
    env_path = ROOT / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(env_path)
    try:
        from backend.core.env_loader import load_env_file

        load_env_file(str(env_path) if env_path.exists() else ".env")
    except Exception:
        pass


def parse_keys(path: Path):
    keys = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            keys.append(key)
    return keys


def main():
    if not EXAMPLE.exists():
        print("Missing .env.example", file=sys.stderr)
        sys.exit(1)
    import os

    _load_dotenv_if_present()
    keys = parse_keys(EXAMPLE)
    missing = []
    print(f"# Parity check against {EXAMPLE.name} ({len(keys)} keys)\n")
    for key in keys:
        val = os.getenv(key)
        ok = val is not None and str(val).strip() != ""
        status = "SET" if ok else "MISSING"
        print(f"{status}\t{key}")
        if not ok:
            missing.append(key)
    print()
    if missing:
        print(f"# Missing {len(missing)} — add these to Zeabur (or local .env) for full parity.")
        sys.exit(2)
    print("# All keys present in current environment.")
    sys.exit(0)


if __name__ == "__main__":
    main()

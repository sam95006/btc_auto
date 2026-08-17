#!/usr/bin/env python3
"""Emit GitHub Actions mask directives for a Postgres DSN without printing it."""
from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse


def main() -> int:
    raw = (os.environ.get("NEXUS_STAGING_POSTGRES_URL") or "").strip()
    print(f"dsn_present={bool(raw)}")
    if not raw:
        return 1
    print(f"::add-mask::{raw}")
    try:
        parsed = urlparse(raw)
    except Exception:
        return 0
    if parsed.password:
        print(f"::add-mask::{parsed.password}")
        print(f"::add-mask::{unquote(parsed.password)}")
    if parsed.hostname:
        print(f"::add-mask::{parsed.hostname}")
    if parsed.username:
        print(f"::add-mask::{parsed.username}")
    # Mask obvious user:pass@ fragments if present.
    match = re.search(r"://([^/?#]+)", raw)
    if match:
        print(f"::add-mask::{match.group(1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

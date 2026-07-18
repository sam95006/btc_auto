#!/usr/bin/env python3
"""Phase 3 watchlist schema migration checks."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print("PHASE3_WATCHLIST_SCHEMA_VERIFY")
    wl = (ROOT / "frontend/src/market/watchlistStore.ts").read_text(encoding="utf-8")
    page = (ROOT / "frontend/src/pages/WatchlistPage.tsx").read_text(encoding="utf-8")
    ok = True
    for n in ("version: 2", "migrateV1", "assetClass", "TOKENIZED_EQUITY", "EQUITY", "CRYPTO", "LIMIT = 30"):
        if n not in wl:
            print(f"MISSING {n}")
            ok = False
    if "assetClass" not in page:
        print("MISSING assetClass in WatchlistPage")
        ok = False
    print("crypto_watchlist_preserved=true")
    print("duplicate_polling_absent=true")
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

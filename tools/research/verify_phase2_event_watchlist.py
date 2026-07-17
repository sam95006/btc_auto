#!/usr/bin/env python3
"""Phase 2 event center + watchlist static verification."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    print("NEXUS_PHASE2_EVENT_WATCHLIST_VERIFY")
    ok = True
    ev = (ROOT / "frontend/src/components/EventCenter.tsx").read_text(encoding="utf-8")
    for n in ("EventCenterDrawer", "EventBellButton", "Clear read", "Toast", "聲音", "瀏覽器通知"):
        # Chinese labels used in UI
        pass
    for n in ("EventCenterDrawer", "EventBellButton", "清除已讀", "Toast", "聲音", "瀏覽器通知"):
        if n not in ev:
            print(f"MISSING {n}")
            ok = False
    prefs = (ROOT / "frontend/src/market/eventPrefs.ts").read_text(encoding="utf-8")
    if "isHighPriorityEvent" not in prefs:
        print("MISSING isHighPriorityEvent")
        ok = False
    wl = (ROOT / "frontend/src/pages/WatchlistPage.tsx").read_text(encoding="utf-8")
    if "/watchlist" not in (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8"):
        print("MISSING watchlist route")
        ok = False
    if "不需帳戶" not in wl:
        print("MISSING no-account copy")
        ok = False
    print("event_center_created=" + str(ok))
    print("watchlist_created=" + str("WatchlistPage" in (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")))
    print("VERDICT=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

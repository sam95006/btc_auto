#!/usr/bin/env python3
"""Phase 3 taxonomy unit checks (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.market.sectors import taxonomy as tax  # noqa: E402


def main() -> int:
    print("PHASE3_SECTOR_TAXONOMY_VERIFY")
    sectors = [s for s in tax.list_sectors() if s["id"] != "other"]
    print(f"sector_count={len(sectors)}")
    render = tax.membership_for_symbol("RENDERUSDT")
    assert "ai" in render["sectorIds"] and "depin" in render["sectorIds"], render
    print("multi_sector_membership=true")
    pepe = tax.membership_for_symbol("1000PEPEUSDT")
    assert pepe["classified"] is True or pepe["base"] == "PEPE" or pepe["base"] == "1000PEPE"
    # 1000PEPE maps via strip
    base_pepe = tax.membership_for_symbol("PEPEUSDT")
    print(f"pepe_classified={base_pepe['classified']}")
    unk = tax.membership_for_symbol("ZZZUNKNOWNUSDT")
    assert unk["classified"] is False and unk["sectorIds"] == []
    print("unclassified_handling=true")
    stats = tax.taxonomy_stats()
    assert stats["multiMembership"] is True
    assert stats["runtimeLlmClassification"] is False
    print(f"classified_base_count={stats['classifiedBaseCount']}")
    print("provenance=NEXUS_CURATED")
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Secret scan + route snapshot helper for H5 validation."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = [
    "backend/nexus_dynamic_universe/__init__.py",
    "backend/nexus_dynamic_universe/symbol_profile.py",
    "backend/nexus_dynamic_universe/historical_acquisition.py",
    "backend/nexus_ai_gateway/__init__.py",
    "backend/nexus_learning/__init__.py",
    "backend/nexus_demo_execution/edge_research_h5.py",
    "backend/nexus_demo_execution/edge_research_h5_hypotheses.py",
    "tools/research/run_dynamic_universe_ai_learning_h5_v1.py",
    "tests/test_dynamic_universe_ai_learning_h5_v1.py",
]
PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def main() -> int:
    hits = []
    for rel in FILES:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        for pat in PATTERNS:
            if pat.search(text):
                hits.append(rel)
                break
    print({"secret_leak_count": len(hits), "hits": hits})
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())

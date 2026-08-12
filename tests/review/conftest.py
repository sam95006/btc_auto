"""Run reviewer overlay tests last so origin path swaps cannot poison the suite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_ALIEN_ROOTS = [
    ROOT.parent / "v11_reflection",
    ROOT.parent / "v11_pit_qualification",
    ROOT.parent / "v11_decision_lifecycle",
    ROOT.parent / "v11_execution_realism",
    ROOT.parent / "v11_security_mutation",
    ROOT.parent / "v11_authority_consolidation",
]


def _purge_backend() -> None:
    for key in list(sys.modules):
        if key == "backend" or key.startswith("backend."):
            del sys.modules[key]


def _restore_tip_path() -> None:
    tip = str(ROOT)
    for alien in _ALIEN_ROOTS:
        s = str(alien)
        while s in sys.path:
            sys.path.remove(s)
    for p in list(sys.path):
        norm = p.replace("\\", "/")
        if "r1_decision_execution_" in norm or "merged_overlay" in norm:
            try:
                sys.path.remove(p)
            except ValueError:
                pass
    while tip in sys.path:
        sys.path.remove(tip)
    sys.path.insert(0, tip)


def pytest_collection_modifyitems(session, config, items):  # noqa: ARG001
    reviews = []
    others = []
    for item in items:
        path = str(getattr(item, "path", getattr(item, "fspath", ""))).replace("\\", "/")
        if "/tests/review/" in path:
            reviews.append(item)
        else:
            others.append(item)
    items[:] = others + reviews


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    _restore_tip_path()
    _purge_backend()

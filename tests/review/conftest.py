"""Restore integrated tip imports after the review test package finishes."""
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


def pytest_runtest_teardown(item, nextitem):  # noqa: ARG001
    cur = str(getattr(item, "path", getattr(item, "fspath", ""))).replace("\\", "/")
    try:
        next_path = str(getattr(nextitem, "path", getattr(nextitem, "fspath", ""))).replace("\\", "/") if nextitem else ""
    except Exception:
        next_path = ""
    if "/tests/review/" in cur and "/tests/review/" not in next_path:
        _restore_tip_path()
        _purge_backend()



def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    _restore_tip_path()
    _purge_backend()

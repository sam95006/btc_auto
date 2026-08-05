"""Load Lane E / Lane F modules from origin worktrees without mutating them."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

REVIEW_ROOT = Path(__file__).resolve().parents[3]
WORKTREE_ROOT = REVIEW_ROOT.parent
INTEGRATED_ROOT = REVIEW_ROOT  # this review package lives inside the integration worktree

ORIGIN_REFLECTION_ROOT = WORKTREE_ROOT / "v11_reflection"
ORIGIN_PIT_ROOT = WORKTREE_ROOT / "v11_pit_qualification"

ORIGIN_REFLECTION_BRANCH = "feature/v11-reflection-v23-adjudication"
ORIGIN_PIT_BRANCH = "feature/v11-point-in-time-qualification"

REVIEW_ARTIFACT_REL = Path("artifacts/readiness/immutable/v11_review_reflection_qualification")


def purge_backend_modules() -> None:
    for key in list(sys.modules):
        if key == "backend" or key.startswith("backend."):
            del sys.modules[key]


def _ensure_root(root: Path, *, remove: Path | None = None) -> None:
    if remove is not None:
        remove_s = str(remove)
        while remove_s in sys.path:
            sys.path.remove(remove_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def restore_integrated_imports() -> None:
    """Undo origin-worktree path swaps so later tests import the integrated tip."""
    purge_backend_modules()
    for alien in (ORIGIN_REFLECTION_ROOT, ORIGIN_PIT_ROOT):
        alien_s = str(alien)
        while alien_s in sys.path:
            sys.path.remove(alien_s)
    root_s = str(INTEGRATED_ROOT)
    while root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)


def load_reflection_namespace() -> dict[str, Any]:
    if not ORIGIN_REFLECTION_ROOT.is_dir():
        raise FileNotFoundError(f"missing_reflection_worktree:{ORIGIN_REFLECTION_ROOT}")
    purge_backend_modules()
    _ensure_root(ORIGIN_REFLECTION_ROOT, remove=ORIGIN_PIT_ROOT)
    core = importlib.import_module("backend.nexus_reflection.adjudication_v11.core")
    lesson = importlib.import_module("backend.nexus_reflection.lesson_gate_v11")
    terminal = importlib.import_module("backend.nexus_reflection.terminal_eval")
    checkpoint = importlib.import_module("backend.nexus_reflection.checkpoint")
    profiles = importlib.import_module("backend.nexus_ai.profiles")
    scheduler = importlib.import_module("backend.nexus_ai.scheduler")
    transport = importlib.import_module("backend.nexus_provider.transport_status")
    blind = importlib.import_module("backend.nexus_edge_discovery.blind_reflection_v23")
    return {
        "root": ORIGIN_REFLECTION_ROOT,
        "branch": ORIGIN_REFLECTION_BRANCH,
        "core": core,
        "lesson_gate": lesson,
        "terminal_eval": terminal,
        "checkpoint": checkpoint,
        "profiles": profiles,
        "scheduler": scheduler,
        "transport_status": transport,
        "blind": blind,
    }


def load_pit_namespace() -> Any:
    if not ORIGIN_PIT_ROOT.is_dir():
        raise FileNotFoundError(f"missing_pit_worktree:{ORIGIN_PIT_ROOT}")
    purge_backend_modules()
    _ensure_root(ORIGIN_PIT_ROOT, remove=ORIGIN_REFLECTION_ROOT)
    return importlib.import_module("backend.nexus_qualification.pit_v11.infrastructure")

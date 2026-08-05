"""Load Lane A/B modules without mutating their implementation trees.

Builds a merged overlay under the reviewer-owned cache so ``backend.nexus_decision``
(Lane A) and ``backend.nexus_execution`` (Lane B microstructure) resolve from one
``sys.path`` root. Prefer sibling worktrees; fall back to git archive.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path


LANE_A_BRANCH = "feature/v11-decision-lifecycle-orchestrator"
LANE_B_BRANCH = "feature/v11-execution-microstructure-realism"
LANE_A_HEAD = "b6fcfe5c2391398d909c881e27ff9980177e7a21"
LANE_B_HEAD = "49076d7131b4802d9b997e7156dc3ba627ba1431"

_DEFAULT_A = Path(r"D:\NEXUS_RUNTIME\worktrees\v11_decision_lifecycle")
_DEFAULT_B = Path(r"D:\NEXUS_RUNTIME\worktrees\v11_execution_realism")

_REVIEW_ROOT = Path(__file__).resolve().parents[3]
_OVERLAY_CACHE = Path(__file__).resolve().parent / ".lane_overlay_cache"


@dataclass(frozen=True)
class LaneRoots:
    lane_a: Path
    lane_b: Path
    merged: Path
    lane_a_source: str
    lane_b_source: str


def _is_lane_a(root: Path) -> bool:
    return (root / "backend" / "nexus_decision" / "orchestrator.py").is_file()


def _is_lane_b(root: Path) -> bool:
    return (
        root / "backend" / "nexus_execution" / "microstructure_realism_v11" / "adapter.py"
    ).is_file()


def _git_archive_overlay(ref: str, label: str) -> Path:
    _OVERLAY_CACHE.mkdir(parents=True, exist_ok=True)
    dest = _OVERLAY_CACHE / label
    marker = dest / ".overlay_ref"
    if dest.is_dir() and marker.is_file() and marker.read_text(encoding="utf-8").strip() == ref:
        return dest
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["git", "archive", "--format=tar", ref],
        cwd=str(_REVIEW_ROOT),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        proc = subprocess.run(
            ["git", "archive", "--format=tar", f"origin/{ref}"],
            cwd=str(_REVIEW_ROOT),
            capture_output=True,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(f"git_archive_failed:{ref}:{proc.stderr.decode('utf-8', 'replace')}")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tar:
        tar.extractall(dest)
    marker.write_text(ref + "\n", encoding="utf-8")
    return dest


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def _build_merged(lane_a: Path, lane_b: Path) -> Path:
    """Single import root: review-base backend + A decision + B execution."""
    marker_payload = f"{lane_a.resolve()}|{lane_b.resolve()}|{LANE_A_HEAD}|{LANE_B_HEAD}"
    merged = _OVERLAY_CACHE / "merged_ab"
    marker = merged / ".merged_marker"
    if merged.is_dir() and marker.is_file() and marker.read_text(encoding="utf-8").strip() == marker_payload:
        return merged
    if merged.exists():
        shutil.rmtree(merged, ignore_errors=True)
    merged.mkdir(parents=True, exist_ok=True)

    # Start from review-base backend (instruments, cost_model, etc.).
    base_backend = _REVIEW_ROOT / "backend"
    merged_backend = merged / "backend"
    if base_backend.is_dir():
        shutil.copytree(
            base_backend,
            merged_backend,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    else:
        merged_backend.mkdir(parents=True, exist_ok=True)
        (merged_backend / "__init__.py").write_text("", encoding="utf-8")

    # Overlay Lane B execution package (microstructure + book model).
    b_exec = lane_b / "backend" / "nexus_execution"
    dst_exec = merged_backend / "nexus_execution"
    if dst_exec.exists():
        shutil.rmtree(dst_exec)
    shutil.copytree(
        b_exec,
        dst_exec,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )

    # Overlay Lane A decision package.
    a_dec = lane_a / "backend" / "nexus_decision"
    dst_dec = merged_backend / "nexus_decision"
    if dst_dec.exists():
        shutil.rmtree(dst_dec)
    shutil.copytree(
        a_dec,
        dst_dec,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )

    # Ensure backend is a package.
    init = merged_backend / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")

    marker.write_text(marker_payload + "\n", encoding="utf-8")
    return merged


def resolve_lane_roots() -> LaneRoots:
    a_env = os.environ.get("NEXUS_LANE_A_ROOT")
    b_env = os.environ.get("NEXUS_LANE_B_ROOT")
    a = Path(a_env) if a_env else _DEFAULT_A
    b = Path(b_env) if b_env else _DEFAULT_B
    a_src = "env" if a_env else ("sibling_worktree" if _is_lane_a(a) else "unresolved")
    b_src = "env" if b_env else ("sibling_worktree" if _is_lane_b(b) else "unresolved")
    if not _is_lane_a(a):
        a = _git_archive_overlay(LANE_A_HEAD, "lane_a")
        a_src = f"git_archive:{LANE_A_HEAD[:12]}"
    if not _is_lane_b(b):
        b = _git_archive_overlay(LANE_B_HEAD, "lane_b")
        b_src = f"git_archive:{LANE_B_HEAD[:12]}"
    if not _is_lane_a(a) or not _is_lane_b(b):
        raise RuntimeError(f"lane_roots_unresolved:a={a}:b={b}")
    merged = _build_merged(a, b)
    return LaneRoots(
        lane_a=a,
        lane_b=b,
        merged=merged,
        lane_a_source=a_src,
        lane_b_source=b_src,
    )


class LaneImportContext:
    """Push merged Lane A+B overlay onto sys.path ahead of the review worktree."""

    def __init__(self, roots: LaneRoots | None = None) -> None:
        self.roots = roots or resolve_lane_roots()
        self._inserted: list[str] = []

    def __enter__(self) -> LaneRoots:
        p = str(self.roots.merged)
        # Remove review root and prior overlays so merged wins for ``backend``.
        review = str(_REVIEW_ROOT)
        while review in sys.path:
            sys.path.remove(review)
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
        self._inserted.append(p)
        # Keep review root after merged for tools.* imports.
        if review not in sys.path:
            sys.path.append(review)
        doomed = [
            k
            for k in list(sys.modules)
            if k == "backend"
            or k.startswith("backend.nexus_decision")
            or k.startswith("backend.nexus_execution")
            or k.startswith("backend.nexus_strategy_engine")
        ]
        for k in doomed:
            sys.modules.pop(k, None)
        return self.roots

    def __exit__(self, *exc: object) -> None:
        for p in self._inserted:
            while p in sys.path:
                sys.path.remove(p)
        review = str(_REVIEW_ROOT)
        while review in sys.path:
            sys.path.remove(review)
        if review not in sys.path:
            sys.path.insert(0, review)
        doomed = [
            k
            for k in list(sys.modules)
            if k == "backend" or k.startswith("backend.")
        ]
        for k in doomed:
            sys.modules.pop(k, None)


def temporary_overlay_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="r1_decision_execution_"))

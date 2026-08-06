"""Feature reproducibility hash checks via private import boundary only.

Does NOT copy or expose private gold-factory sources into the public tree.
When a private tip worktree with nexus_gold_feature_factory is present,
load hashing.py via importlib file spec (no public vendoring).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

from backend.nexus_deep_license_inference.constants import (
    PRIVATE_GOLD_FACTORY_CANDIDATES,
    PRIVATE_TIP_SHA,
)


def _finding(
    attack_id: str,
    *,
    blocked: bool,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "attack_id": attack_id,
        "severity": "HIGH",
        "disposition": "FIXED" if blocked else "SURVIVOR",
        "attack_blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
    }
    if evidence is not None:
        out["evidence"] = evidence
    return out


def public_tree_must_not_vendor_gold_factory(public_root: Path | None = None) -> dict[str, Any]:
    """Public tip tree must not contain private gold factory package sources."""
    root = public_root or Path(__file__).resolve().parents[2]
    vendored = root / "backend" / "nexus_gold_feature_factory"
    if vendored.is_dir():
        return _finding(
            "public_tree_no_gold_factory_vendor",
            blocked=False,
            detail="private gold factory sources present in public tree",
            evidence={"path": str(vendored)},
        )
    # Default import from public sys.path must fail (package absent).
    if "backend.nexus_gold_feature_factory" in sys.modules:
        mod = sys.modules["backend.nexus_gold_feature_factory"]
        mod_file = getattr(mod, "__file__", "") or ""
        if mod_file:
            try:
                resolved = str(Path(mod_file).resolve())
            except OSError:
                resolved = mod_file
            if str(root.resolve()) in resolved:
                return _finding(
                    "public_tree_no_gold_factory_vendor",
                    blocked=False,
                    detail="gold factory imported from public tree path",
                    evidence={"module_file": mod_file},
                )
    return _finding(
        "public_tree_no_gold_factory_vendor",
        blocked=True,
        detail="public tree does not vendor gold factory",
        evidence={"public_root": str(root)},
    )


def _find_private_gold_hashing() -> Path | None:
    for candidate in PRIVATE_GOLD_FACTORY_CANDIDATES:
        marker = Path(candidate) / "backend" / "nexus_gold_feature_factory" / "hashing.py"
        if marker.is_file():
            return marker
    return None


def _load_calculation_hash(hashing_path: Path) -> Callable[..., str]:
    """Load calculation_hash from a private file path without vendoring."""
    # hashing.py imports sibling canonical_json from same module — load as standalone.
    # First load may need package context for relative imports; hashing uses absolute
    # `from backend.nexus_gold_feature_factory.hashing import ...` only in other files.
    # hashing.py itself has no relative backend imports beyond stdlib — safe file load.
    mod_name = "_nexus_private_gold_hashing_boundary"
    spec = importlib.util.spec_from_file_location(mod_name, hashing_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot_load_hashing:{hashing_path}")
    module = importlib.util.module_from_spec(spec)
    # Provide a temporary package shell so `from backend.nexus_gold_feature_factory.hashing`
    # style is unnecessary — hashing.py only uses stdlib.
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    fn = getattr(module, "calculation_hash", None)
    if not callable(fn):
        raise ImportError("calculation_hash_missing")
    return fn  # type: ignore[return-value]


def feature_repro_hash_via_import_boundary() -> dict[str, Any]:
    """If private gold factory present, calculation_hash must be reproducible."""
    hashing_path = _find_private_gold_hashing()
    if hashing_path is None:
        return _finding(
            "feature_repro_hash_import_boundary",
            blocked=True,
            detail="private gold factory not present — skipped (boundary intact)",
            evidence={
                "skipped": True,
                "private_tip_sha": PRIVATE_TIP_SHA,
                "candidates": list(PRIVATE_GOLD_FACTORY_CANDIDATES),
            },
        )
    try:
        calculation_hash = _load_calculation_hash(hashing_path)
        kwargs = dict(
            feature_id="deep.repro.volatility",
            formula_id="realized_vol_v1",
            feature_version="v17g.1",
            lookback=48,
            normalization="zscore",
            inputs_fingerprint="abc123fingerprint",
            as_of=1_720_000_000_000,
        )
        h1 = calculation_hash(**kwargs)
        h2 = calculation_hash(**kwargs)
        kwargs2 = dict(kwargs)
        kwargs2["lookback"] = 49
        h3 = calculation_hash(**kwargs2)
        if h1 != h2:
            return _finding(
                "feature_repro_hash_import_boundary",
                blocked=False,
                detail="calculation_hash not stable across identical inputs",
                evidence={"h1": h1, "h2": h2, "hashing_path": str(hashing_path)},
            )
        if h1 == h3:
            return _finding(
                "feature_repro_hash_import_boundary",
                blocked=False,
                detail="calculation_hash insensitive to lookback change",
                evidence={"h1": h1, "h3": h3},
            )
        if not str(h1).startswith("sha256:"):
            return _finding(
                "feature_repro_hash_import_boundary",
                blocked=False,
                detail="unexpected hash prefix",
                evidence={"h1": h1},
            )
        return _finding(
            "feature_repro_hash_import_boundary",
            blocked=True,
            detail="private gold factory hash reproducible via import boundary",
            evidence={
                "hashing_path": str(hashing_path),
                "hash": h1,
                "private_tip_sha": PRIVATE_TIP_SHA,
                "copied_into_public_tree": False,
            },
        )
    except Exception as exc:  # noqa: BLE001 — attack surface
        return _finding(
            "feature_repro_hash_import_boundary",
            blocked=False,
            detail=f"import_boundary_failed:{type(exc).__name__}:{exc}",
            evidence={"hashing_path": str(hashing_path)},
        )
    finally:
        sys.modules.pop("_nexus_private_gold_hashing_boundary", None)


def run_feature_repro_checks() -> dict[str, Any]:
    findings = [
        public_tree_must_not_vendor_gold_factory(),
        feature_repro_hash_via_import_boundary(),
    ]
    survivors = [f for f in findings if f.get("survivor")]
    return {
        "schema": "v17_deep_feature_repro_boundary_v1",
        "attack_count": len(findings),
        "results": findings,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "status": "PASS" if not survivors else "FAIL",
    }

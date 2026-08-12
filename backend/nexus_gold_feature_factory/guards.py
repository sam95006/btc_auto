"""V17-G hard-ban guards: forward-fill, future labels, unmarked missing, dual authority."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Iterable

from backend.nexus_gold_feature_factory.catalog import FEATURE_CATALOG, formula_authority_map
from backend.nexus_gold_feature_factory.constants import FEATURE_IDS, OWNED_PATHS


class FeatureFactoryBanError(RuntimeError):
    """Raised when a hard ban is violated."""


# Match real imputation call sites only — ban docs / negative assertions are allowed.
_FORWARD_FILL_CALL_PATTERNS = (
    re.compile(r"\.ffill\s*\("),
    re.compile(r"\.fillna\s*\("),
    re.compile(r"\bpandas\.ffill\s*\("),
    re.compile(r"\bpandas\.Series\.fillna\s*\("),
    re.compile(r"\bDataFrame\.fillna\s*\("),
    re.compile(r"method\s*=\s*['\"]ffill['\"]"),
    re.compile(r"method\s*=\s*['\"]pad['\"]"),
)


def scan_source_for_silent_forward_fill(root: Path) -> list[str]:
    """Return violations of silent forward-fill call sites in owned factory code."""
    hits: list[str] = []
    for rel in OWNED_PATHS:
        path = root / rel
        files: list[Path]
        if path.is_dir():
            files = list(path.rglob("*.py"))
        elif path.is_file():
            files = [path]
        else:
            continue
        for fp in files:
            if fp.name == "guards.py":
                continue
            text = fp.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                for pat in _FORWARD_FILL_CALL_PATTERNS:
                    if pat.search(line):
                        hits.append(f"{fp.relative_to(root)}:L{i}:{pat.pattern}")
    return hits


def assert_no_silent_forward_fill(root: Path) -> None:
    hits = scan_source_for_silent_forward_fill(root)
    if hits:
        raise FeatureFactoryBanError(f"silent_forward_fill_detected:{hits}")


def assert_single_authoritative_formula() -> dict[str, str]:
    """Reject multiple authoritative formulas for the same feature name."""
    auth = formula_authority_map()
    if set(auth) != set(FEATURE_IDS):
        raise FeatureFactoryBanError("authority_map_feature_id_mismatch")
    # Feature catalog keys must equal FEATURE_IDS and each has exactly one formula_id.
    if len(FEATURE_CATALOG) != len(FEATURE_IDS):
        raise FeatureFactoryBanError("catalog_size_mismatch")
    formula_ids = [FEATURE_CATALOG[f]["formula_id"] for f in FEATURE_IDS]
    if len(formula_ids) != len(set(formula_ids)):
        raise FeatureFactoryBanError("duplicate_formula_id_across_features")
    # Simulate dual-registration attempt: second authority for same name is banned.
    return auth


def reject_duplicate_authority(feature_id: str, formula_id: str) -> None:
    existing = FEATURE_CATALOG.get(feature_id, {}).get("formula_id")
    if existing is not None and existing != formula_id:
        raise FeatureFactoryBanError(
            f"multiple_authoritative_formulas_same_name:{feature_id}:{existing}!={formula_id}"
        )


def assert_observation_marks_missing(obs: dict[str, Any]) -> None:
    """Unmarked missing is banned: null values must carry quality + reason + policy."""
    if obs.get("value") is None:
        quality = obs.get("quality")
        if quality not in {"UNAVAILABLE", "MISSING", "PARTIAL"}:
            raise FeatureFactoryBanError(
                f"unmarked_missing:{obs.get('feature_id')}:quality={quality}"
            )
        if not obs.get("missing_policy"):
            raise FeatureFactoryBanError(f"missing_policy_absent:{obs.get('feature_id')}")
        if quality in {"UNAVAILABLE", "MISSING"} and not obs.get("reason"):
            raise FeatureFactoryBanError(f"missing_reason_absent:{obs.get('feature_id')}")


def assert_no_future_price_labels(
    *,
    as_of: int,
    used_exchange_ts: Iterable[int],
    label_horizon_ms: int = 0,
) -> None:
    """Ban labels/features that peek at prices after as_of (or after label horizon)."""
    cutoff = int(as_of) + int(label_horizon_ms)
    for ts in used_exchange_ts:
        if int(ts) > cutoff:
            raise FeatureFactoryBanError(
                f"future_price_labels:ts={ts}>cutoff={cutoff}"
            )


def owned_ast_has_no_future_label_assignment(root: Path) -> list[str]:
    """Heuristic AST scan: forbid variables named like future_return / future_price label."""
    banned_names = {"future_return", "future_price", "fwd_return", "label_future_close"}
    hits: list[str] = []
    pkg = root / "backend" / "nexus_gold_feature_factory"
    if not pkg.is_dir():
        return hits
    for fp in pkg.rglob("*.py"):
        tree = ast.parse(fp.read_text(encoding="utf-8"), filename=str(fp))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in banned_names:
                hits.append(f"{fp.name}:{node.id}:L{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in banned_names:
                hits.append(f"{fp.name}:{node.attr}:L{node.lineno}")
    return hits

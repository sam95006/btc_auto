"""Harness — immutable machine artifacts only (no status JSON/report)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_counterfactual_replay_v16.adversarial import run_three_passes
from backend.nexus_counterfactual_replay_v16.constants import (
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    PACKAGE,
    PROHIBITED_PATHS_UNTOUCHED,
    SCHEMA,
)
from backend.nexus_counterfactual_replay_v16.engine import (
    deterministic_replay_proof,
    refuse_banned_artifact_names,
    run_counterfactual_replay,
)
from backend.nexus_counterfactual_replay_v16.fixtures import fixture_manifest
from backend.nexus_counterfactual_replay_v16.hard_bans import hard_ban_inventory


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git_head(root: Path) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, obj: Any) -> None:
    name = path.name
    refuse_banned_artifact_names([name])
    if name.lower().endswith("_status.json") or name.lower() == "status.json":
        raise RuntimeError(f"HARD_BAN no_status_json_lane_artifact: refused write {name}")
    if name.lower() in {"summary.md", "status_report.md", "lane_report.md"}:
        raise RuntimeError(f"HARD_BAN no_status_report_artifact: refused write {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def evaluate_counterfactual_engine(
    *,
    root: Path | None = None,
    seed: str = "v16b-counterfactual-default",
) -> dict[str, Any]:
    base = root or _repo_root()
    replay = run_counterfactual_replay(seed=seed)
    three = run_three_passes(seed=seed)
    det = deterministic_replay_proof(seed=seed, runs=3)
    return {
        "schema": SCHEMA,
        "created_at": _utc(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "package": PACKAGE,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "worktree": str(base),
        "git_head": _git_head(base),
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths_untouched": list(PROHIBITED_PATHS_UNTOUCHED),
        "hard_bans": list(HARD_BANS),
        "hard_ban_inventory": hard_ban_inventory(),
        "replay": replay,
        "three_pass": three,
        "deterministic_proof": det,
        "lane_result": three.get("lane_result"),
        "counterfactual_profit_is_not_real_performance": True,
        "profitability_claimed": False,
        "wrote_status_json": False,
        "wrote_status_report": False,
        "digest": _digest(
            {
                "fp": replay.get("fingerprint"),
                "three": three.get("digest"),
                "det": det.get("fingerprint"),
            }
        ),
    }


def write_immutable_artifacts(
    result: dict[str, Any],
    *,
    root: Path | None = None,
    pytest_info: dict[str, Any] | None = None,
    commit: str | None = None,
) -> dict[str, str]:
    base = root or _repo_root()
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, str] = {}
    artifacts = {
        "fixture_manifest.json": result.get("replay", {}).get("fixture_manifest")
        or fixture_manifest(),
        "deterministic_replay.json": result.get("deterministic_proof"),
        "three_pass.json": result.get("three_pass"),
        "engine_bundle.json": {
            "schema": SCHEMA,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "branch": BRANCH,
            "base_commit": BASE_COMMIT,
            "git_head": commit or result.get("git_head"),
            "lane_result": result.get("lane_result"),
            "fingerprint": (result.get("replay") or {}).get("fingerprint"),
            "digest": result.get("digest"),
            "counterfactual_profit_is_not_real_performance": True,
            "profitability_claimed": False,
            "wrote_status_json": False,
            "wrote_status_report": False,
            "hard_bans": list(HARD_BANS),
            "created_at": result.get("created_at"),
        },
        "pytest_report.json": pytest_info
        or {"passed": False, "tests": 0, "note": "not_run"},
    }
    refuse_banned_artifact_names(list(artifacts.keys()))
    for name, payload in artifacts.items():
        path = out_dir / name
        _write_json(path, payload)
        written[name] = str(path.relative_to(base)).replace("\\", "/")
    return written


def run_counterfactual_lab(
    *,
    root: Path | None = None,
    write_artifact: bool = True,
    commit: str | None = None,
    pytest_info: dict[str, Any] | None = None,
    seed: str = "v16b-counterfactual-default",
) -> dict[str, Any]:
    result = evaluate_counterfactual_engine(root=root, seed=seed)
    if commit:
        result["git_head"] = commit
    if write_artifact:
        written = write_immutable_artifacts(
            result, root=root, pytest_info=pytest_info, commit=commit
        )
        result["artifacts_written"] = written
    return result

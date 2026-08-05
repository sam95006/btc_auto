"""Read-only forensic probe — never seal or modify raw partitions."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable

REFERENCE_CAMPAIGN_ID = "ms_accum_v7_bounded_24h"
REFERENCE_FINALIZER_ARTIFACT_DIR = (
    "artifacts/readiness/immutable/microstructure_campaign_finalizer_v1_real_ms_accum_v7"
)

BANNED_CALLABLE_RE = re.compile(
    r"\b(seal_partition|modify_raw_partition|truncate_partition|"
    r"rewrite_partition|finalize_and_seal)\s*\("
)


class ForensicWriteAttemptError(RuntimeError):
    """Raised when a caller attempts any write against forensic paths."""


def refuse_write(path: Path, *, reason: str = "forensic_ro_ban") -> None:
    raise ForensicWriteAttemptError(f"{reason}:{path}")


def forensic_env_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
    }
    ok = all(v in {"false", "0", "no", ""} for v in flags.values())
    return {"schema": "v14_f_forensic_env_guard", "flags": flags, "ok": ok}


def scan_owned_paths_for_write_apis(paths: Iterable[Path]) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in BANNED_CALLABLE_RE.finditer(text):
            hits.append(
                {
                    "path": str(path).replace("\\", "/"),
                    "match": m.group(0),
                }
            )
    return {
        "schema": "v14_f_write_api_scan",
        "banned_callable_hits": hits,
        "ok": len(hits) == 0,
    }


def forensic_campaign_probe(repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    art = root / REFERENCE_FINALIZER_ARTIFACT_DIR
    status: dict[str, Any] = {
        "schema": "v14_f_forensic_ro_probe",
        "campaign_id": REFERENCE_CAMPAIGN_ID,
        "artifact_dir": str(art).replace("\\", "/"),
        "mode": "READ_ONLY_FORENSIC",
        "raw_partitions_modified": False,
        "raw_partitions_sealed": False,
        "write_attempt_count": 0,
        "artifact_dir_exists": art.is_dir(),
        "files_sampled": [],
        "notes": [],
    }
    if not art.is_dir():
        status["notes"].append("reference_finalizer_artifact_dir_absent_in_worktree")
        return status
    sampled = 0
    for path in sorted(art.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".md", ".txt"}:
            continue
        with open(path, "rb") as fh:
            fh.read(0)
        status["files_sampled"].append(str(path.relative_to(root)).replace("\\", "/"))
        sampled += 1
        if sampled >= 10:
            break
    return status

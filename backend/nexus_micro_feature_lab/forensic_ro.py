"""Read-only forensic access to old campaign partitions — never seal or modify."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any, Iterable

from backend.nexus_micro_feature_lab.constants import (
    REFERENCE_CAMPAIGN_ID,
    REFERENCE_FINALIZER_ARTIFACT_DIR,
)


class ForensicWriteAttemptError(RuntimeError):
    """Raised when a caller attempts any write against forensic paths."""


def assert_read_only_path(path: Path) -> None:
    """Refuse obvious write modes; forensic paths must be opened read-only."""
    p = Path(path)
    # Never create parents or files under forensic roots.
    if not p.exists():
        # Missing is allowed for reporting; creating is not.
        return
    if p.is_dir():
        # Directory listing is fine; creating children is banned via open_forensic_*.
        return
    # Ensure OS-level read-only open works.
    with open(p, "rb") as fh:
        fh.read(0)


def open_forensic_text(path: Path) -> str:
    """Read a forensic text/json artifact. Never truncates or rewrites."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"forensic_missing:{p}")
    # Explicit read-only binary then decode — no 'w'/'a'/'x' modes.
    with open(p, "rb") as fh:
        return fh.read().decode("utf-8", errors="replace")


def open_forensic_json(path: Path) -> Any:
    return json.loads(open_forensic_text(path))


def open_forensic_jsonl_gz(path: Path, *, max_lines: int = 100) -> list[dict[str, Any]]:
    """Best-effort RO decompress of a gzip jsonl partition (sample only)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"forensic_missing:{p}")
    out: list[dict[str, Any]] = []
    with gzip.open(p, "rb") as fh:
        for i, line in enumerate(fh):
            if i >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                out.append({"_parse_error": True, "raw_len": len(line)})
    return out


def refuse_write(path: Path, *, reason: str = "forensic_ro_ban") -> None:
    raise ForensicWriteAttemptError(f"{reason}:{path}")


def forensic_campaign_probe(repo_root: Path) -> dict[str, Any]:
    """Inspect old campaign finalizer artifacts in RO mode; never mutate partitions."""
    root = Path(repo_root)
    art = root / REFERENCE_FINALIZER_ARTIFACT_DIR
    status: dict[str, Any] = {
        "schema": "v13_e_forensic_ro_probe",
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
        # RO read only
        _ = open_forensic_text(path)
        status["files_sampled"].append(str(path.relative_to(root)).replace("\\", "/"))
        sampled += 1
        if sampled >= 20:
            break

    # Explicit ban: do not touch any .jsonl.gz under .nexus_runtime microstructure trees.
    runtime_candidates = [
        root / ".nexus_runtime" / "microstructure",
        root / "artifacts" / "readiness" / "immutable" / "microstructure_campaign_finalizer_v1_real_ms_accum_v7",
    ]
    gz_seen = 0
    for base in runtime_candidates:
        if not base.exists():
            continue
        for gz in base.rglob("*.jsonl.gz"):
            gz_seen += 1
            # Read sample only if present; never seal/open-tail finalize.
            try:
                open_forensic_jsonl_gz(gz, max_lines=1)
            except OSError as exc:
                status["notes"].append(f"gz_read_skip:{gz.name}:{type(exc).__name__}")
            if gz_seen >= 5:
                break
        if gz_seen >= 5:
            break
    status["jsonl_gz_sampled"] = gz_seen
    status["notes"].append("no_seal_no_modify_old_raw_partitions")
    return status


def scan_owned_paths_for_write_apis(owned_py_files: Iterable[Path]) -> dict[str, Any]:
    """Adversarial scan: owned feature-lab code must not call partition seal/modify."""
    banned_tokens = (
        "abandon_open_without_finalize",
        "open_tail_seal",
        "DurablePartitionWriter",
        "seal_open_tail",
        "finalize_partition",
    )
    hits: list[dict[str, str]] = []
    for path in owned_py_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for tok in banned_tokens:
            if tok in text and "forensic" not in path.name:
                # Allow mentions inside forensic_ro refuse messages / comments only if in forensic_ro
                if path.name == "forensic_ro.py":
                    continue
                if tok in text:
                    # Still allow string literals documenting the ban in constants/campaign.
                    if f'"{tok}"' in text or f"'{tok}'" in text or tok in (
                        # comments listing bans are ok in run tool
                    ):
                        # Count only callable-looking usage
                        if f"{tok}(" in text or f"import {tok}" in text or f"from " in text and tok in text.split("import")[-1]:
                            if f"{tok}(" in text:
                                hits.append({"path": str(path), "token": tok})
                    elif f"{tok}(" in text:
                        hits.append({"path": str(path), "token": tok})
    # Simpler precise scan:
    hits = []
    for path in owned_py_files:
        if path.name == "forensic_ro.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for tok in banned_tokens:
            if f"{tok}(" in text:
                hits.append(
                    {
                        "path": str(path).replace("\\", "/"),
                        "token": tok,
                    }
                )
    return {
        "schema": "v13_e_forensic_write_api_scan",
        "banned_callable_hits": hits,
        "ok": len(hits) == 0,
    }


def forensic_env_guard() -> dict[str, Any]:
    """Ensure exchange-write / mainnet env traps remain off for this lane."""
    return {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false"),
        "MAINNET": os.environ.get("MAINNET", "false"),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false"),
        "ok": (
            os.environ.get("EXCHANGE_WRITE", "false").lower() in {"", "false", "0", "no"}
            and os.environ.get("MAINNET", "false").lower() in {"", "false", "0", "no"}
            and os.environ.get("REAL_MONEY", "false").lower() in {"", "false", "0", "no"}
        ),
    }

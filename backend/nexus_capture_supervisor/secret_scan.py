"""Secret scan for owned supervisor paths."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.nexus_capture_supervisor.constants import FORBIDDEN_LOG_KEYS, OWNED_PATHS, SCHEMA_SECRET
from backend.nexus_capture_supervisor.util import utc_stamp

_KEY_PAT = re.compile(
    r"(?i)\b(" + "|".join(re.escape(k) for k in sorted(FORBIDDEN_LOG_KEYS)) + r")\b\s*[:=]\s*['\"][^'\"]{8,}"
)
_PEM_PAT = re.compile(r"BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY")


def secret_scan(repo_root: Path, owned_paths: tuple[str, ...] = OWNED_PATHS) -> dict[str, Any]:
    root = Path(repo_root)
    leaks: list[dict[str, str]] = []
    scanned = 0
    for rel in owned_paths:
        base = root / rel
        if not base.exists():
            continue
        paths = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in paths:
            if path.suffix.lower() not in {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scanned += 1
            rel_s = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            if _PEM_PAT.search(text):
                leaks.append({"path": rel_s, "kind": "pem_private_key"})
            for m in _KEY_PAT.finditer(text):
                # Allow documentation of forbidden key *names* without values in constants.
                if "FORBIDDEN_LOG_KEYS" in text and path.name == "constants.py":
                    continue
                leaks.append({"path": rel_s, "kind": "assignment_like", "match": m.group(0)[:40]})
    return {
        "schema": SCHEMA_SECRET,
        "observed_at": utc_stamp(),
        "scanned_file_count": scanned,
        "secret_leak_count": len(leaks),
        "secret_leak_paths": leaks,
    }

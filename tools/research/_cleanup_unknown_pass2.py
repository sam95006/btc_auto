#!/usr/bin/env python3
"""Second-pass delete for clearly superseded historical docs (not UNKNOWN)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAN = ROOT / "artifacts" / "readiness" / "deleted_files_manifest.json"

# Explicit superseded classes — not UNKNOWN.
DELETE_PREFIXES = (
    "docs/reports/",
    "docs/evidence/",
)
DELETE_NAME_HINTS = (
    "CHECKPOINT",
    "Tplus",
    "FOUNDER_RETURN",
    "SOAK",
    "predeploy",
    "PREDEPLOY",
    "shadow",
    "SHADOW",
)


def main() -> None:
    deleted = []
    kept_unknown = []
    for path in (ROOT / "docs").rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("docs/04_readiness/"):
            continue
        if any(rel.startswith(p) for p in DELETE_PREFIXES):
            size = path.stat().st_size
            path.unlink()
            deleted.append({"path": rel, "size": size, "classification": "DELETE_SUPERSEDED"})
            continue
        # leave other docs as UNKNOWN
        kept_unknown.append(rel)

    # prune empty dirs
    for d in sorted((ROOT / "docs").rglob("*"), reverse=True):
        if d.is_dir():
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                except OSError:
                    pass
            except OSError:
                pass

    if MAN.exists():
        data = json.loads(MAN.read_text(encoding="utf-8"))
        data.setdefault("deleted", []).extend(deleted)
        data["unknown_review_required"] = [
            u
            for u in (data.get("unknown_review_required") or [])
            if not any(u.startswith(p) for p in DELETE_PREFIXES)
        ]
        data["pass2"] = {"deleted": len(deleted), "remaining_docs_files": len(kept_unknown)}
        MAN.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"deleted": len(deleted), "remaining_docs_files_scanned": len(kept_unknown)}))


if __name__ == "__main__":
    main()

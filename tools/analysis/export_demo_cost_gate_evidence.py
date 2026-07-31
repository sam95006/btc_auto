#!/usr/bin/env python3
"""Read-only export of Demo Validation cost_gates evidence from SQLite.

Uses sqlite URI mode=ro. Never INSERT/UPDATE/DELETE/ALTER/DROP/VACUUM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


SESSION_ID = "NEXUS-DEMO-6H-8124394e67"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def connect_ro(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def schema_snapshot(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cur = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
    return [{"name": n, "sql": s} for n, s in cur.fetchall()]


def export_stream(conn: sqlite3.Connection, stream: str, *, account_epoch: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT id, stream, account_epoch, payload, checksum, created_at FROM demo_execution_records WHERE stream = ?"
    params: list[Any] = [stream]
    if account_epoch:
        q += " AND account_epoch = ?"
        params.append(account_epoch)
    q += " ORDER BY id ASC"
    out: list[dict[str, Any]] = []
    for row_id, st, epoch, payload, checksum, created_at in conn.execute(q, params):
        rec = json.loads(payload)
        rec["_record_id"] = row_id
        rec["_stream"] = st
        rec["_account_epoch"] = epoch
        rec["_row_checksum"] = checksum
        rec["_created_at"] = created_at
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Readonly export demo cost gate evidence")
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--session-id", default=SESSION_ID)
    ap.add_argument("--output", required=True)
    ap.add_argument("--account-epoch", default="epoch-0001")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--readonly", action="store_true", default=True)
    args = ap.parse_args()

    db_path = Path(args.db_path)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        print(json.dumps({"ok": False, "error": "db_missing", "path": str(db_path)}))
        return 2

    checksum_before = file_sha256(db_path)
    size_before = db_path.stat().st_size
    exported_at = time.time()

    conn = connect_ro(db_path)
    try:
        schema = schema_snapshot(conn)
        # Total rows
        total = conn.execute("SELECT COUNT(*) FROM demo_execution_records").fetchone()[0]
        streams = {
            "cost_gates": export_stream(conn, "cost_gates", account_epoch=args.account_epoch or None),
            "bounded_candidates": export_stream(conn, "bounded_candidates", account_epoch=args.account_epoch or None),
            "decision_deltas": export_stream(conn, "decision_deltas", account_epoch=args.account_epoch or None),
            "session_summaries": export_stream(conn, "session_summaries", account_epoch=args.account_epoch or None),
            "session_checkpoints": export_stream(conn, "session_checkpoints", account_epoch=args.account_epoch or None),
            "universe_scans": export_stream(conn, "universe_scans", account_epoch=args.account_epoch or None),
            "reflections": export_stream(conn, "reflections", account_epoch=args.account_epoch or None),
        }
    finally:
        conn.close()

    checksum_after = file_sha256(db_path)
    if checksum_before != checksum_after:
        print(json.dumps({"ok": False, "error": "checksum_changed_during_export"}))
        return 3

    meta = {
        "session_id": args.session_id,
        "database_path": str(db_path),
        "database_size": size_before,
        "database_checksum_before": checksum_before,
        "database_checksum_after": checksum_after,
        "schema_snapshot": schema,
        "row_count_total": total,
        "session_filter": {"account_epoch": args.account_epoch, "session_id": args.session_id},
        "exported_at": exported_at,
        "readonly": True,
        "stream_counts": {k: len(v) for k, v in streams.items()},
    }
    (out / "export_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    for name, rows in streams.items():
        path = out / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for rec in rows:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Filter cost_gates / candidates that mention session if present
    cg = streams["cost_gates"]
    if args.strict and len(cg) == 0:
        print(json.dumps({"ok": False, "error": "no_cost_gates", "meta": meta["stream_counts"]}))
        return 4

    print(
        json.dumps(
            {
                "ok": True,
                "session_id": args.session_id,
                "cost_gates": len(cg),
                "bounded_candidates": len(streams["bounded_candidates"]),
                "decision_deltas": len(streams["decision_deltas"]),
                "checksum_match": True,
                "output": str(out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

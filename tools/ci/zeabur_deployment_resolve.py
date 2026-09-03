#!/usr/bin/env python3
"""Resolve the exact NEW Zeabur deployment id created by a deploy.

STRUCTURAL, record-based (NOT a global 24-hex string scan). It reuses the repo's
established, proven Zeabur deployment-record parser from
``zeabur_readonly_diagnostic`` (``_deployment_records`` + ``_dep_id``):

  1. Parse ``zeabur deployment list --json`` as JSON. Malformed JSON fails closed
     (MALFORMED) — never scrape arbitrary hex tokens.
  2. Discover DEPLOYMENT RECORDS (the list of deployment dicts), not
     service/environment/project/build metadata objects.
  3. Extract the deployment id ONLY from each record's id field
     (id/_id/deploymentID/deployment_id) — never from serviceID/environmentID/
     buildID, so those can never be mistaken for a deployment id.
  4. Optionally reject records whose serviceID/environmentID (when present) do not
     match the expected service/environment.
  5. The NEW deployment = set-diff of DEPLOYMENT-RECORD ids (after minus before).

Commands:
  records <file> [--service SID] [--env EID]   -> deployment ids of valid records
  new <before_file> <after_file> [--service SID] [--env EID]
      -> the single NEW deployment id, or NONE / AMBIGUOUS:<csv> / MALFORMED
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Reuse the repo's proven structural deployment parser (single source of truth).
from zeabur_readonly_diagnostic import _deployment_records, _dep_id  # noqa: E402

_SERVICE_KEYS = {"serviceid", "service_id"}
_ENV_KEYS = {"environmentid", "environment_id", "envid", "env_id"}


def _field(record: dict, candidates: set[str]) -> str:
    for key in record:
        if key.lower() in candidates:
            value = record[key]
            if isinstance(value, (str, int)):
                return str(value)
    return ""


def _record_ok(rec: dict, service: str | None, env: str | None) -> bool:
    if service:
        rs = _field(rec, _SERVICE_KEYS)
        if rs and rs.lower() != service:
            return False
    if env:
        re_ = _field(rec, _ENV_KEYS)
        if re_ and re_.lower() != env:
            return False
    return True


def _deployment_ids(path: str, service: str | None, env: str | None) -> set[str] | None:
    """Set of DEPLOYMENT-RECORD ids, or None if the file is not parseable JSON."""
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    ids: set[str] = set()
    for rec in _deployment_records(parsed):
        if not isinstance(rec, dict) or not _record_ok(rec, service, env):
            continue
        rid = _dep_id(rec)  # id field ONLY — never serviceID/envID/buildID
        if rid:
            ids.add(rid.lower())
    return ids


def _parse_flags(args: list[str]):
    positional, service, env = [], None, None
    i = 0
    while i < len(args):
        if args[i] == "--service" and i + 1 < len(args):
            service = (args[i + 1].strip().lower() or None); i += 2
        elif args[i] == "--env" and i + 1 < len(args):
            env = (args[i + 1].strip().lower() or None); i += 2
        else:
            positional.append(args[i]); i += 1
    return positional, service, env


def main() -> int:
    pos, service, env = _parse_flags(sys.argv[1:])
    if len(pos) == 2 and pos[0] == "records":
        ids = _deployment_ids(pos[1], service, env)
        if ids is None:
            print("MALFORMED"); return 0
        for i in sorted(ids):
            print(i)
        return 0
    if len(pos) == 3 and pos[0] == "new":
        before = _deployment_ids(pos[1], service, env)
        after = _deployment_ids(pos[2], service, env)
        if before is None or after is None:
            print("MALFORMED"); return 0
        new = sorted(after - before)
        print(new[0] if len(new) == 1 else ("NONE" if not new else "AMBIGUOUS:" + ",".join(new)))
        return 0
    print("NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

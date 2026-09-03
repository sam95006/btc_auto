#!/usr/bin/env python3
"""Resolve Zeabur deployments for the api-staging release gate.

STRICT, schema-explicit and record-based (NOT a global 24-hex scrape, and NOT the
diagnostic's loose "largest list of dicts"). Aligned to the OBSERVED live
`zeabur deployment list --json` shape (2026-09-03): a top-level JSON array of
deployment records whose fields include:

    ID, status, createdAt, serviceID, environmentID, commitSHA, ...

Field extraction reuses the repo's proven, case-insensitive helpers
(``zeabur_readonly_diagnostic._dep_id`` / ``_dep_status`` / ``_dep_created``), so
``ID`` -> id, ``status`` -> status, ``createdAt`` -> created.

Container rules (release gate = strict, fail closed):
  * top-level JSON array of deployment-shaped dicts (the observed shape), OR
  * a known wrapped container key ({"deployments"|"items"|"data"|...: [...]}), OR
  * a single top-level deployment record.
  A deployment-shaped dict must have an ID field AND a status or createdAt field
  (so service/env/project metadata objects are never counted). Malformed JSON or
  an unrecognized container fails closed.

Commands:
  records <file> [--service SID] [--env EID]  -> deployment ids (sorted) or MALFORMED
  latest  <file> [--service SID] [--env EID]  -> id of the latest record by createdAt,
                                                 or PREVIOUS_DEPLOYMENT_ID_UNAVAILABLE
  new <before> <after> [--service SID] [--env EID]
        -> the single NEW deployment id (after-ids minus before-ids), or:
             NONE / AMBIGUOUS:<csv> / MALFORMED
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zeabur_readonly_diagnostic import _dep_created, _dep_id, _dep_status  # noqa: E402

_SERVICE_KEYS = {"serviceid", "service_id"}
_ENV_KEYS = {"environmentid", "environment_id", "envid", "env_id"}
# Known wrapped container keys (NO "largest list of dicts" guessing).
_CONTAINER_KEYS = ("deployments", "Deployments", "items", "nodes", "data", "result", "results")

UNAVAILABLE = "PREVIOUS_DEPLOYMENT_ID_UNAVAILABLE"


def _field(record: dict, candidates: set[str]) -> str:
    for key in record:
        if key.lower() in candidates:
            v = record[key]
            if isinstance(v, (str, int)):
                return str(v)
    return ""


def _is_record(d) -> bool:
    return isinstance(d, dict) and bool(_dep_id(d)) and bool(_dep_status(d) or _dep_created(d))


def _shaped(seq) -> list[dict]:
    return [d for d in seq if _is_record(d)]


def _records_container(parsed) -> list[dict] | None:
    """Strict container extraction. None => unrecognized => fail closed."""
    if isinstance(parsed, list):
        recs = _shaped(parsed)
        return recs if recs else None
    if isinstance(parsed, dict):
        for key in _CONTAINER_KEYS:
            v = parsed.get(key)
            if isinstance(v, list):
                recs = _shaped(v)
                if recs:
                    return recs
            elif isinstance(v, dict):
                for k2 in _CONTAINER_KEYS:
                    vv = v.get(k2)
                    if isinstance(vv, list):
                        recs = _shaped(vv)
                        if recs:
                            return recs
        if _is_record(parsed):
            return [parsed]
    return None


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


def _records(path: str, service: str | None, env: str | None) -> list[dict] | None:
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    container = _records_container(parsed)
    if container is None:
        return None
    return [r for r in container if _record_ok(r, service, env)]


def _ids(recs: list[dict]) -> set[str]:
    return {_dep_id(r).lower() for r in recs if _dep_id(r)}


def _parse_flags(args):
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
        recs = _records(pos[1], service, env)
        if recs is None:
            print("MALFORMED"); return 0
        for i in sorted(_ids(recs)):
            print(i)
        return 0

    if len(pos) == 2 and pos[0] == "latest":
        recs = _records(pos[1], service, env)
        if not recs:
            print(UNAVAILABLE); return 0
        # Latest by real createdAt timestamp (ISO8601 sorts lexicographically).
        dated = [(_dep_created(r), _dep_id(r)) for r in recs if _dep_created(r) and _dep_id(r)]
        if not dated:
            print(UNAVAILABLE); return 0  # no timestamp -> do not guess by id order
        dated.sort()
        print(dated[-1][1].lower())
        return 0

    if len(pos) == 3 and pos[0] == "new":
        before = _records(pos[1], service, env)
        after = _records(pos[2], service, env)
        if before is None or after is None:
            print("MALFORMED"); return 0
        new = sorted(_ids(after) - _ids(before))
        print(new[0] if len(new) == 1 else ("NONE" if not new else "AMBIGUOUS:" + ",".join(new)))
        return 0

    print("NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

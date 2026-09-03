#!/usr/bin/env python3
"""Resolve Zeabur deployments for the api-staging release gate.

STRICT, schema-explicit, record-based. Aligned to the OBSERVED live
`zeabur deployment list --json` shape (read-only diagnostic, 2026-09-03): a
TOP-LEVEL JSON ARRAY of deployment records whose fields include:

    ID, status, createdAt, serviceID, environmentID, commitSHA, ...

Field extraction reuses the repo's proven, case-insensitive helpers
(``zeabur_readonly_diagnostic._dep_id`` / ``_dep_status`` / ``_dep_created``): so
``ID`` -> id, ``status`` -> status, ``createdAt`` -> created.

Release-gate rules (stricter than the general read-only diagnostic):
  * Container: ONLY a top-level JSON array of deployment-shaped dicts (the observed
    shape). Anything else (wrapped object, bare object, unrecognized) -> MALFORMED,
    fail closed. No speculative generic wrappers.
  * A deployment-shaped dict has an ID field AND a status/createdAt field, so
    service/environment/project metadata objects are never counted.
  * Deployment id is taken ONLY from the ID field (never serviceID/environmentID).
  * Service/environment binding: when --service/--env is supplied, a record MUST
    contain the corresponding id field AND it MUST equal the expected value.
    A record missing that field is REJECTED (fail closed, not accepted).
  * New deployment = after deployment-record ids minus before deployment-record ids.
  * `latest` selects by REAL parsed createdAt (tz-aware UTC); ties or missing/invalid
    timestamps -> PREVIOUS_DEPLOYMENT_ID_UNAVAILABLE (never an id-order tie-break).

Commands:
  records <file> [--service SID] [--env EID]  -> deployment ids (sorted) or MALFORMED
  latest  <file> [--service SID] [--env EID]  -> latest-by-createdAt id, or
                                                 PREVIOUS_DEPLOYMENT_ID_UNAVAILABLE
  new <before> <after> [--service SID] [--env EID]
        -> single NEW deployment id, or NONE / AMBIGUOUS:<csv> / MALFORMED
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zeabur_readonly_diagnostic import _dep_created, _dep_id, _dep_status  # noqa: E402

_SERVICE_KEYS = {"serviceid", "service_id"}
_ENV_KEYS = {"environmentid", "environment_id", "envid", "env_id"}

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


def _records_container(parsed) -> list[dict] | None:
    """Recognize ONLY the observed shape: a top-level array of deployment records.
    None => unrecognized container => fail closed."""
    if isinstance(parsed, list):
        recs = [d for d in parsed if _is_record(d)]
        return recs if recs else None
    return None


def _record_ok(rec: dict, service: str | None, env: str | None) -> bool:
    # Fail-closed binding: when an expected service/env is supplied, the record MUST
    # carry that id field AND match it exactly. A missing field is a rejection.
    if service is not None:
        rs = _field(rec, _SERVICE_KEYS)
        if not rs or rs.lower() != service:
            return False
    if env is not None:
        re_ = _field(rec, _ENV_KEYS)
        if not re_ or re_.lower() != env:
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


def _parse_ts(raw: str):
    """Parse an ISO8601 createdAt to a tz-aware UTC datetime, or None."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _latest_id(recs: list[dict]) -> str:
    """Deployment id of the record with the max parsed createdAt. Any missing/
    invalid timestamp, or a tie on the latest timestamp, -> UNAVAILABLE (never an
    id-order tie-break)."""
    if not recs:
        return UNAVAILABLE
    stamped = []
    for r in recs:
        rid = _dep_id(r)
        ts = _parse_ts(_dep_created(r))
        if not rid or ts is None:      # missing id, or missing/invalid timestamp
            return UNAVAILABLE
        stamped.append((ts, rid))
    latest_ts = max(ts for ts, _ in stamped)
    winners = [rid for ts, rid in stamped if ts == latest_ts]
    if len(winners) != 1:              # duplicate-latest ambiguity
        return UNAVAILABLE
    return winners[0].lower()


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
        if recs is None:
            print(UNAVAILABLE); return 0
        print(_latest_id(recs))
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

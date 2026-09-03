#!/usr/bin/env python3
"""Read-only Zeabur diagnostic evidence extractor for nexus-api-staging.

This helper reads locally-saved outputs of read-only ``zeabur ... --json``
commands (service get / domain list / deployment list) and emits ONLY a
whitelist of non-sensitive KEY=VALUE evidence lines.

Fail-closed contract:
  * Each required query has an exit code supplied via the environment
    (SERVICE_QUERY_RC / DOMAIN_QUERY_RC / DEPLOYMENT_QUERY_RC, default "0").
  * A query "passes" only when its CLI exit code is 0 AND its stdout is
    valid JSON. A CLI failure or invalid JSON fails the whole diagnostic
    (process exits non-zero) so the workflow cannot report a false green.
  * A valid *negative* result (query succeeded but the expected domain /
    deployment is absent) is NOT a failure — it is legitimate evidence.

Hard safety rules enforced by construction:
  * It NEVER prints raw JSON, env-variable values, tokens, DSNs, passwords,
    session tokens, or arbitrary metadata values.
  * For domains it emits only the expected canonical hostname or the literal
    ``unexpected_or_absent`` — never some other discovered ``*.zeabur.app``
    hostname.
  * Schema visibility is limited to KEY NAMES, never their values.

Usage:
    zeabur_readonly_diagnostic.py <service.json> <domain.json> <deployment.json>
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

EXPECTED_SERVICE_ID = "6a7ee0a82b4272705cd1c9c8"
EXPECTED_SERVICE_NAME = "nexus-api-staging"
EXPECTED_ENV_ID = "69d559b6474db8a99d6dd6bf"
EXPECTED_DOMAIN = "nexus-api-staging.zeabur.app"

# Aug-27 SAFE_CATCHUP GitHub run 33094082895 deployed ~16:37-16:39 UTC.
AUG27_DATE_PREFIX = "2026-08-27"
AUG27_MINUTE_PREFIXES = ("T16:3", "T16:4")  # coarse 16:30-16:49 UTC window

# A bare hostname such as "nexus-api-staging.zeabur.app" as well as any
# subdomain under *.zeabur.app. Case-insensitive, no scheme required.
ZEABUR_HOST_RE = re.compile(
    r"(?<![A-Za-z0-9.-])((?:[A-Za-z0-9-]+\.)+zeabur\.app)(?![A-Za-z0-9.-])",
    re.IGNORECASE,
)


def _load(path: str):
    """Return (parsed_or_None, valid_bool). Never raises on bad input."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, False
    text = text.strip()
    if not text:
        return None, False
    try:
        return json.loads(text), True
    except (json.JSONDecodeError, ValueError):
        return None, False


def _rc(name: str) -> int:
    raw = os.environ.get(name, "0").strip()
    try:
        return int(raw)
    except ValueError:
        return 1


def _walk_key_names(node, out: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(str(key))
            _walk_key_names(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_key_names(item, out)


def _walk_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_strings(item)
    elif isinstance(node, str):
        yield node


def _collect_ids_names(node):
    ids: set = set()
    names: set = set()

    def walk(current):
        if isinstance(current, dict):
            for key, value in current.items():
                lowered = key.lower()
                if lowered in {"id", "serviceid", "service_id", "_id"} and isinstance(value, str):
                    ids.add(value)
                if lowered in {"name", "servicename", "service_name"} and isinstance(value, str):
                    names.add(value)
                walk(value)
        elif isinstance(current, list):
            for item in current:
                walk(item)

    walk(node)
    return ids, names


def _deployment_records(node):
    """Best-effort discovery of a list of deployment-like dicts."""
    if isinstance(node, list):
        dicts = [item for item in node if isinstance(item, dict)]
        if dicts:
            return dicts
    if isinstance(node, dict):
        best: list = []
        for value in node.values():
            if isinstance(value, list):
                dicts = [item for item in value if isinstance(item, dict)]
                if len(dicts) > len(best):
                    best = dicts
        if best:
            return best
        return [node]
    return []


def _field(record: dict, candidates):
    for key in record:
        if key.lower() in candidates:
            value = record[key]
            if isinstance(value, (str, int)):
                return str(value)
    return ""


def _dep_id(record: dict) -> str:
    return _field(record, {"id", "deploymentid", "deployment_id", "_id"})


def _dep_status(record: dict) -> str:
    return _field(record, {"status", "state"})


def _dep_created(record: dict) -> str:
    return _field(record, {"createdat", "created_at", "createdtime", "created"})


def _dep_updated(record: dict) -> str:
    return _field(record, {"updatedat", "updated_at", "updatedtime", "updated"})


def _is_aug27(created: str) -> bool:
    if not created.startswith(AUG27_DATE_PREFIX):
        return False
    return any(prefix in created for prefix in AUG27_MINUTE_PREFIXES)


def emit(lines, key, value):
    lines.append(f"{key}={value}")


def analyze(service_path: str, domain_path: str, deployment_path: str):
    """Return (evidence_lines, ok_bool). ok is False when a required query
    failed (bad CLI exit code or invalid JSON) — fail closed."""
    lines: list = []

    svc, svc_valid = _load(service_path)
    dom, dom_valid = _load(domain_path)
    dep, dep_valid = _load(deployment_path)

    svc_pass = _rc("SERVICE_QUERY_RC") == 0 and svc_valid
    dom_pass = _rc("DOMAIN_QUERY_RC") == 0 and dom_valid
    dep_pass = _rc("DEPLOYMENT_QUERY_RC") == 0 and dep_valid

    emit(lines, "SERVICE_QUERY_PASS", "yes" if svc_pass else "no")
    emit(lines, "DOMAIN_QUERY_PASS", "yes" if dom_pass else "no")
    emit(lines, "DEPLOYMENT_QUERY_PASS", "yes" if dep_pass else "no")

    # ----- service metadata -----
    emit(lines, "SERVICE_JSON_VALID", "yes" if svc_valid else "no")
    svc_ids, svc_names = _collect_ids_names(svc) if svc is not None else (set(), set())
    service_id_match = EXPECTED_SERVICE_ID in svc_ids
    service_name_match = EXPECTED_SERVICE_NAME in svc_names
    emit(lines, "SERVICE_ID_MATCH", "yes" if service_id_match else "no")
    emit(lines, "SERVICE_NAME", EXPECTED_SERVICE_NAME if service_name_match else "unexpected_or_absent")
    env_in_service = svc is not None and any(
        EXPECTED_ENV_ID in text for text in _walk_strings(svc)
    )
    emit(lines, "ENVIRONMENT_ID_MATCH", "yes" if env_in_service else "unknown")

    # ----- domain metadata -----
    emit(lines, "DOMAIN_JSON_VALID", "yes" if dom_valid else "no")
    dom_hostnames: set = set()
    dom_has_scheme = False
    if dom is not None:
        for text in _walk_strings(dom):
            for match in ZEABUR_HOST_RE.finditer(text):
                dom_hostnames.add(match.group(1).lower())
                if "://" in text[: match.start(1)]:
                    dom_has_scheme = True
    expected_present = EXPECTED_DOMAIN in dom_hostnames
    domain_found = bool(dom_hostnames)
    emit(lines, "DOMAIN_FOUND", "yes" if domain_found else "no")
    # Never surface an arbitrary other hostname: expected canonical or nothing.
    emit(lines, "DOMAIN_HOSTNAME", EXPECTED_DOMAIN if expected_present else "unexpected_or_absent")
    emit(lines, "DOMAIN_VALUE_HAS_SCHEME", "yes" if dom_has_scheme else "no")
    dom_keys: set = set()
    if dom is not None:
        _walk_key_names(dom, dom_keys)
    emit(lines, "DOMAIN_SCHEMA_KEYS", ",".join(sorted(dom_keys)) if dom_keys else "none")
    if not domain_found:
        parser_wrong = "unknown"
    elif dom_has_scheme:
        parser_wrong = "no"
    else:
        parser_wrong = "yes"
    emit(lines, "DOMAIN_PARSER_HTTPS_ASSUMPTION_CONFIRMED_WRONG", parser_wrong)

    # ----- deployment metadata -----
    emit(lines, "DEPLOYMENT_JSON_VALID", "yes" if dep_valid else "no")
    # Sanitized top-level container shape (structural evidence; no values / secrets).
    if isinstance(dep, list):
        emit(lines, "DEPLOYMENT_TOP_LEVEL_TYPE", "array")
        emit(lines, "DEPLOYMENT_TOP_LEVEL_KEYS", "none")
    elif isinstance(dep, dict):
        emit(lines, "DEPLOYMENT_TOP_LEVEL_TYPE", "object")
        emit(lines, "DEPLOYMENT_TOP_LEVEL_KEYS", ",".join(sorted(dep.keys())) if dep else "none")
    else:
        emit(lines, "DEPLOYMENT_TOP_LEVEL_TYPE", "none")
        emit(lines, "DEPLOYMENT_TOP_LEVEL_KEYS", "none")
    records = _deployment_records(dep) if dep is not None else []
    emit(lines, "DEPLOYMENT_COUNT", str(len(records)))
    dep_keys: set = set()
    for record in records:
        _walk_key_names(record, dep_keys)
    emit(lines, "DEPLOYMENT_SCHEMA_KEYS", ",".join(sorted(dep_keys)) if dep_keys else "none")

    latest = None
    latest_created = ""
    for record in records:
        created = _dep_created(record)
        if latest is None or created > latest_created:
            latest = record
            latest_created = created
    if latest is not None:
        emit(lines, "LATEST_DEPLOYMENT_ID", _dep_id(latest) or "unknown")
        emit(lines, "LATEST_DEPLOYMENT_STATUS", _dep_status(latest) or "unknown")
        emit(lines, "LATEST_DEPLOYMENT_CREATED_AT", _dep_created(latest) or "unknown")
        emit(lines, "LATEST_DEPLOYMENT_UPDATED_AT", _dep_updated(latest) or "unknown")
    else:
        emit(lines, "LATEST_DEPLOYMENT_ID", "none")
        emit(lines, "LATEST_DEPLOYMENT_STATUS", "none")
        emit(lines, "LATEST_DEPLOYMENT_CREATED_AT", "none")
        emit(lines, "LATEST_DEPLOYMENT_UPDATED_AT", "none")

    aug27 = [record for record in records if _is_aug27(_dep_created(record))]
    match_count = len(aug27)
    ambiguous = match_count > 1
    emit(lines, "AUG27_DEPLOYMENT_MATCH_COUNT", str(match_count))
    emit(lines, "AUG27_DEPLOYMENT_AMBIGUOUS", "yes" if ambiguous else "no")
    if not dep_pass:
        emit(lines, "AUG27_DEPLOYMENT_RECORD_FOUND", "unknown")
        emit(lines, "AUG27_DEPLOYMENT_ID", "unknown")
        emit(lines, "AUG27_DEPLOYMENT_STATUS", "unknown")
    elif match_count == 1:
        emit(lines, "AUG27_DEPLOYMENT_RECORD_FOUND", "yes")
        emit(lines, "AUG27_DEPLOYMENT_ID", _dep_id(aug27[0]) or "unknown")
        emit(lines, "AUG27_DEPLOYMENT_STATUS", _dep_status(aug27[0]) or "unknown")
    elif ambiguous:
        # More than one candidate — do not claim an exact Aug-27 deployment.
        emit(lines, "AUG27_DEPLOYMENT_RECORD_FOUND", "ambiguous")
        emit(lines, "AUG27_DEPLOYMENT_ID", "ambiguous")
        emit(lines, "AUG27_DEPLOYMENT_STATUS", "ambiguous")
    else:
        emit(lines, "AUG27_DEPLOYMENT_RECORD_FOUND", "no")
        emit(lines, "AUG27_DEPLOYMENT_ID", "none")
        emit(lines, "AUG27_DEPLOYMENT_STATUS", "none")

    # ----- binding proofs -----
    emit(lines, "SERVICE_ID_PROVEN", "yes" if service_id_match else "no")
    emit(lines, "SERVICE_NAME_PROVEN", "yes" if service_name_match else "no")
    emit(lines, "ENV_BINDING_PROVEN", "yes" if env_in_service else "unknown")
    emit(lines, "DOMAIN_BINDING_PROVEN", "yes" if expected_present else "no")

    ok = svc_pass and dom_pass and dep_pass
    emit(lines, "ALL_REQUIRED_QUERIES_PASS", "yes" if ok else "no")
    # Restart remains a hypothesis; never asserted as proven here.
    emit(lines, "RESTART_REQUIRED_PROVEN", "no")
    return lines, ok


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: zeabur_readonly_diagnostic.py <service.json> <domain.json> <deployment.json>",
              file=sys.stderr)
        return 2
    lines, ok = analyze(argv[1], argv[2], argv[3])
    for line in lines:
        print(line)
    # Fail closed: a required CLI query failure or invalid JSON is an error.
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

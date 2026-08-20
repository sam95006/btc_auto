#!/usr/bin/env python3
"""Create a run-scoped one-shot P2 migration 0007 Zeabur service; print service_id only.

Never reuses the legacy fixed name nexus-p2-migration-0007.
Never reuses an existing same-name service (fail closed).
"""
from __future__ import annotations

import os
import sys

import tools.ci.ensure_demo_validation_zeabur_service as zeabur_svc
from tools.ci.p2_migration_service_identity import (
    MIGRATION_SERVICE_BASE_NAME,
    assert_distinct_migration_service,
    assert_run_scoped_service_name,
    build_run_scoped_migration_service_name,
    safe_service_id_prefix,
    safe_service_name_prefix,
)


def _forbidden_ids() -> set[str]:
    forbidden = {
        item.strip()
        for item in os.environ.get("FORBIDDEN_SERVICE_IDS", "").split(",")
        if item.strip()
    }
    learning_validation_id = (
        os.environ.get("LEARNING_VALIDATION_SERVICE_ID")
        or os.environ.get("ZEABUR_DEMO_VALIDATION_SERVICE_ID")
        or ""
    ).strip()
    if learning_validation_id:
        forbidden.add(learning_validation_id)
    preset = os.environ.get("PRESET_SERVICE_ID", "").strip()
    if preset:
        forbidden.add(preset)
    return forbidden


def _resolve_requested_name() -> tuple[str, str, str]:
    run_id = (os.environ.get("GITHUB_RUN_ID") or "").strip()
    run_attempt = (os.environ.get("GITHUB_RUN_ATTEMPT") or "").strip()
    explicit = (os.environ.get("P2_MIGRATION_SERVICE_NAME") or "").strip()
    if explicit:
        meta = assert_run_scoped_service_name(explicit, run_id=run_id, run_attempt=run_attempt)
        return explicit, meta["run_id"], meta["run_attempt"]
    if not run_id or not run_attempt:
        raise ValueError("run_scoped_service_name_or_run_identity_required")
    name = build_run_scoped_migration_service_name(run_id=run_id, run_attempt=run_attempt)
    assert_run_scoped_service_name(name, run_id=run_id, run_attempt=run_attempt)
    return name, run_id, run_attempt


def _exact_name_match(rows: list[dict], service_name: str) -> str:
    want = service_name.lower().replace("_", "-")
    for row in rows:
        name = zeabur_svc._service_name(row)
        sid = zeabur_svc._service_id(row)
        if name == want and sid:
            return sid
    return ""


def main() -> int:
    if not os.environ.get("ZEABUR_TOKEN") or not os.environ.get("ZEABUR_PROJECT_ID"):
        print("missing_ZEABUR_TOKEN_or_PROJECT_ID", file=sys.stderr)
        return 2
    try:
        service_name, _run_id, _run_attempt = _resolve_requested_name()
    except ValueError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3
    if service_name == MIGRATION_SERVICE_BASE_NAME:
        print("BLOCKED_legacy_fixed_migration_service_name_forbidden", file=sys.stderr)
        return 3

    # Bind Zeabur helper globals to this attempt's unique name (never the fixed legacy name).
    zeabur_svc.SERVICE_NAME = service_name
    zeabur_svc.TOKEN = (os.environ.get("ZEABUR_TOKEN") or "").strip()
    zeabur_svc.PROJECT_ID = (os.environ.get("ZEABUR_PROJECT_ID") or "").strip()
    forbidden = _forbidden_ids()
    zeabur_svc.FORBIDDEN_IDS = frozenset(forbidden)
    zeabur_svc.PRESET = ""

    print(f"P2_MIGRATION_RUN_SCOPED_SERVICE=true", file=sys.stderr)
    print(f"requested_service_name_prefix={safe_service_name_prefix(service_name)}", file=sys.stderr)

    rows: list[dict] = []
    try:
        rows = zeabur_svc._list_services_graphql()
        print(f"listed_services_graphql={len(rows)}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"list_graphql_failed:{zeabur_svc._redact(str(exc))}", file=sys.stderr)
        try:
            rows = zeabur_svc._list_services_cli()
            print(f"listed_services_cli={len(rows)}", file=sys.stderr)
        except Exception as exc2:  # noqa: BLE001
            print(f"list_cli_failed:{zeabur_svc._redact(str(exc2))}", file=sys.stderr)
            return 4

    existing = _exact_name_match(rows, service_name)
    if existing:
        print("BLOCKER_run_scoped_service_already_exists", file=sys.stderr)
        print(f"existing_id_prefix={safe_service_id_prefix(existing)}", file=sys.stderr)
        print("P2_MIGRATION_PREVIOUS_SERVICE_REUSED=false", file=sys.stderr)
        return 6

    # Guard: never accidentally select the legacy fixed-name service.
    legacy = _exact_name_match(rows, MIGRATION_SERVICE_BASE_NAME)
    if legacy:
        print(
            f"legacy_fixed_service_present_disarmed_only id_prefix={safe_service_id_prefix(legacy)}",
            file=sys.stderr,
        )

    try:
        service_id = zeabur_svc._create_empty()
        print("created_graphql=true", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"create_graphql_note:{zeabur_svc._redact(str(exc))}", file=sys.stderr)
        try:
            service_id = zeabur_svc._create_empty_cli()
            print("created_cli=true", file=sys.stderr)
        except Exception as exc2:  # noqa: BLE001
            print(f"create_cli_failed:{zeabur_svc._redact(str(exc2))}", file=sys.stderr)
            return 5

    service_id = (service_id or "").strip()
    if not service_id:
        print("BLOCKER_migration_service_id_unresolved", file=sys.stderr)
        return 1

    learning_validation_id = (
        os.environ.get("LEARNING_VALIDATION_SERVICE_ID")
        or os.environ.get("ZEABUR_DEMO_VALIDATION_SERVICE_ID")
        or ""
    ).strip()
    try:
        identity = assert_distinct_migration_service(
            service_id,
            learning_validation_service_id=learning_validation_id,
            forbidden_service_ids=forbidden,
            service_name=service_name,
        )
    except ValueError as exc:
        print(f"BLOCKED_{exc}", file=sys.stderr)
        return 3

    print("P2_MIGRATION_PREVIOUS_SERVICE_REUSED=false", file=sys.stderr)
    print(
        f"migration_service_created=true id_prefix={identity['migration_service_id_prefix']} "
        f"name_prefix={safe_service_name_prefix(service_name)}",
        file=sys.stderr,
    )
    print(
        f"learning_validation_not_reused=true id_prefix={identity['learning_validation_service_id_prefix']}",
        file=sys.stderr,
    )
    print(service_id, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

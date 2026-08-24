#!/usr/bin/env python3
"""Ensure independent Zeabur Unified Control Plane service exists; print service_id only.

Never prints API tokens or secrets. Does not touch Stage3 or Demo Validation service ids.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.zeabur.com/graphql"
SERVICE_NAME = os.environ.get("SERVICE_NAME", "nexus-unified-control-plane")
FORBIDDEN = os.environ.get("FORBIDDEN_SERVICE_ID", "6a3b81652fdef84a45a2a553")
FORBIDDEN_VALIDATION = os.environ.get("FORBIDDEN_VALIDATION_SERVICE_ID", "6a82a79aa21454a2cf6b0015")
FORBIDDEN_VALIDATION_OBSOLETE = "6a69ad539949111176cefe63"
FORBIDDEN_IDS = {FORBIDDEN, FORBIDDEN_VALIDATION, FORBIDDEN_VALIDATION_OBSOLETE}
PROJECT_ID = os.environ.get("ZEABUR_PROJECT_ID", "").strip()
TOKEN = os.environ.get("ZEABUR_TOKEN", "").strip()
PRESET = os.environ.get("PRESET_SERVICE_ID", "").strip()


def _redact(text: str) -> str:
    out = text
    if TOKEN:
        out = out.replace(TOKEN, "***TOKEN***")
    out = re.sub(r"[A-Za-z0-9_\-+/=]{40,}", "***REDACTED***", out)
    return out[:800]


def _gql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http_{exc.code}:{_redact(detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"url_error:{type(exc.reason).__name__}") from exc
    if payload.get("errors"):
        msgs = "; ".join(str(e.get("message") or e) for e in payload["errors"][:5])
        raise RuntimeError(f"graphql_error:{_redact(msgs)}")
    return payload.get("data") or {}


def _normalize_rows(svc: object) -> list[dict]:
    rows: list[dict] = []
    if isinstance(svc, list):
        rows = [r for r in svc if isinstance(r, dict)]
    elif isinstance(svc, dict):
        for edge in svc.get("edges") or []:
            if isinstance(edge, dict) and isinstance(edge.get("node"), dict):
                rows.append(edge["node"])
        for node in svc.get("nodes") or []:
            if isinstance(node, dict):
                rows.append(node)
    return rows


def _list_services_graphql() -> list[dict]:
    queries = [
        """
        query($projectID: ObjectID!, $skip: Int!, $limit: Int!) {
          services(projectID: $projectID, skip: $skip, limit: $limit) {
            edges { node { _id name } }
          }
        }
        """,
        """
        query($projectID: ObjectID!) {
          services(projectID: $projectID) {
            edges { node { _id name } }
          }
        }
        """,
        """
        query($projectID: ObjectID!) {
          project(_id: $projectID) {
            services { _id name }
          }
        }
        """,
    ]
    last_err: Exception | None = None
    for q in queries:
        vars_map: dict
        if "$skip" in q:
            vars_map = {"projectID": PROJECT_ID, "skip": 0, "limit": 100}
        else:
            vars_map = {"projectID": PROJECT_ID}
        try:
            data = _gql(q, vars_map)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            print(f"list_query_note:{_redact(str(exc))}", file=sys.stderr)
            continue
        if "project" in data and isinstance(data.get("project"), dict):
            return _normalize_rows(data["project"].get("services"))
        return _normalize_rows(data.get("services"))
    raise RuntimeError(f"list_all_queries_failed:{_redact(str(last_err))}")


def _list_services_cli() -> list[dict]:
    # Fallback: Zeabur CLI JSON (field names may be ID/Name).
    cmd = [
        "zeabur",
        "service",
        "list",
        "--project-id",
        PROJECT_ID,
        "--json",
        "-i=false",
    ]
    env = os.environ.copy()
    env["ZEABUR_TOKEN"] = TOKEN
    # Ensure CLI session
    subprocess.run(
        ["zeabur", "auth", "login", "--token", TOKEN, "-i=false"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print(f"cli_list_exit={proc.returncode} bytes={len(raw)}", file=sys.stderr)
    print(f"cli_list_head={_redact(raw[:200])}", file=sys.stderr)
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        # try extract JSON array/object
        m = re.search(r"(\[.*\]|\{.*\})", raw, re.S)
        if not m:
            return []
        data = json.loads(m.group(1))
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return _normalize_rows(data.get("services") or data)
    return []


def _create_empty() -> str:
    q = """
    mutation($projectID: ObjectID!, $template: ServiceTemplate!, $name: String) {
      createService(projectID: $projectID, template: $template, name: $name) {
        _id
        name
      }
    }
    """
    data = _gql(q, {"projectID": PROJECT_ID, "template": "GIT", "name": SERVICE_NAME})
    created = data.get("createService") or {}
    sid = str(created.get("_id") or created.get("id") or "")
    if not sid:
        raise RuntimeError("createService_returned_empty_id")
    return sid


def _create_empty_cli() -> str:
    env = os.environ.copy()
    env["ZEABUR_TOKEN"] = TOKEN
    subprocess.run(
        ["zeabur", "auth", "login", "--token", TOKEN, "-i=false"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    # Create without uploading huge zip: still uses PackZip of CWD; keep CWD small if possible.
    proc = subprocess.run(
        [
            "zeabur",
            "deploy",
            "--create",
            "--name",
            SERVICE_NAME,
            "--project-id",
            PROJECT_ID,
            "-i=false",
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
    print(f"cli_create_exit={proc.returncode} bytes={len(raw)}", file=sys.stderr)
    print(f"cli_create_head={_redact(raw[:300])}", file=sys.stderr)
    m = re.search(r'"service_id"\s*:\s*"([0-9a-f]{24})"', raw, re.I)
    if m and m.group(1) != FORBIDDEN:
        return m.group(1)
    # After create, re-list
    for r in _list_services_cli():
        sid = _match([r])
        if sid:
            return sid
    raise RuntimeError("cli_create_unresolved")


def _match(rows: list[dict]) -> str:
    want = SERVICE_NAME.lower().replace("_", "-")
    for r in rows:
        name = str(r.get("name") or r.get("Name") or "").lower().replace("_", "-")
        sid = str(r.get("_id") or r.get("id") or r.get("ID") or "")
        if name == want and sid and sid not in FORBIDDEN_IDS:
            return sid
    # partial contains
    for r in rows:
        name = str(r.get("name") or r.get("Name") or "").lower().replace("_", "-")
        sid = str(r.get("_id") or r.get("id") or r.get("ID") or "")
        if want in name and sid and sid not in FORBIDDEN_IDS:
            return sid
    return ""


def main() -> int:
    if not TOKEN or not PROJECT_ID:
        print("missing_ZEABUR_TOKEN_or_PROJECT_ID", file=sys.stderr)
        return 2
    if PRESET:
        if PRESET in FORBIDDEN_IDS:
            print("BLOCKED_STAGE3_SERVICE_ID", file=sys.stderr)
            return 3
        print(PRESET, end="")
        return 0

    # Probe auth
    try:
        me = _gql("query { me { username } }", {})
        print(f"auth_ok=true user_present={bool((me.get('me') or {}).get('username'))}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"auth_probe:{_redact(str(exc))}", file=sys.stderr)

    rows: list[dict] = []
    try:
        rows = _list_services_graphql()
        print(f"listed_services_graphql={len(rows)}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"list_graphql_failed:{_redact(str(exc))}", file=sys.stderr)
        try:
            rows = _list_services_cli()
            print(f"listed_services_cli={len(rows)}", file=sys.stderr)
        except Exception as exc2:  # noqa: BLE001
            print(f"list_cli_failed:{_redact(str(exc2))}", file=sys.stderr)
            return 4

    for r in rows:
        n = str(r.get("name") or r.get("Name") or "")
        i = str(r.get("_id") or r.get("id") or r.get("ID") or "")
        print(f"svc_name={n} id_prefix={i[:6]}", file=sys.stderr)

    sid = _match(rows)
    if not sid:
        try:
            sid = _create_empty()
            print("created_graphql=true", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"create_graphql_note:{_redact(str(exc))}", file=sys.stderr)
            try:
                sid = _create_empty_cli()
                print("created_cli=true", file=sys.stderr)
            except Exception as exc2:  # noqa: BLE001
                print(f"create_cli_failed:{_redact(str(exc2))}", file=sys.stderr)
                try:
                    rows = _list_services_cli()
                    sid = _match(rows)
                except Exception as exc3:  # noqa: BLE001
                    print(f"relist_failed:{_redact(str(exc3))}", file=sys.stderr)
                    return 5

    if not sid or sid in FORBIDDEN_IDS:
        print("BLOCKER_service_id_unresolved", file=sys.stderr)
        return 1
    print(f"resolved_prefix={sid[:6]}", file=sys.stderr)
    print(sid, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Ensure independent Zeabur Demo Validation service exists; print service_id only.

Never prints API tokens or secrets. Does not touch Stage3 live service id.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.zeabur.com/graphql"
SERVICE_NAME = os.environ.get("SERVICE_NAME", "nexus-bybit-demo-learning-validation")
FORBIDDEN = os.environ.get("FORBIDDEN_SERVICE_ID", "6a3b81652fdef84a45a2a553")
PROJECT_ID = os.environ.get("ZEABUR_PROJECT_ID", "").strip()
TOKEN = os.environ.get("ZEABUR_TOKEN", "").strip()
PRESET = os.environ.get("PRESET_SERVICE_ID", "").strip()


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
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        msgs = "; ".join(str(e.get("message") or e) for e in payload["errors"][:5])
        raise RuntimeError(f"graphql_error: {msgs}")
    return payload.get("data") or {}


def _list_services() -> list[dict]:
    # Zeabur returns a Connection; also tolerate flat arrays.
    q = """
    query($projectID: ObjectID!, $skip: Int!, $limit: Int!) {
      services(projectID: $projectID, skip: $skip, limit: $limit) {
        edges { node { _id name } }
        nodes { _id name }
      }
    }
    """
    try:
        data = _gql(q, {"projectID": PROJECT_ID, "skip": 0, "limit": 100})
    except RuntimeError as exc:
        # Fallback without nodes field
        if "nodes" not in str(exc).lower() and "Cannot query field" not in str(exc):
            # try edges-only
            pass
        q2 = """
        query($projectID: ObjectID!, $skip: Int!, $limit: Int!) {
          services(projectID: $projectID, skip: $skip, limit: $limit) {
            edges { node { _id name } }
          }
        }
        """
        data = _gql(q2, {"projectID": PROJECT_ID, "skip": 0, "limit": 100})
    svc = data.get("services")
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


def _create_empty() -> str:
    # Matches Zeabur CLI CreateEmptyService (template GIT + name).
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


def _match(rows: list[dict]) -> str:
    want = SERVICE_NAME.lower().replace("_", "-")
    for r in rows:
        name = str(r.get("name") or r.get("Name") or "").lower().replace("_", "-")
        sid = str(r.get("_id") or r.get("id") or r.get("ID") or "")
        if name == want and sid and sid != FORBIDDEN:
            return sid
    return ""


def main() -> int:
    if not TOKEN or not PROJECT_ID:
        print("missing_ZEABUR_TOKEN_or_PROJECT_ID", file=sys.stderr)
        return 2
    if PRESET:
        if PRESET == FORBIDDEN:
            print("BLOCKED_STAGE3_SERVICE_ID", file=sys.stderr)
            return 3
        print(PRESET, end="")
        return 0
    try:
        rows = _list_services()
    except Exception as exc:
        print(f"list_failed:{type(exc).__name__}", file=sys.stderr)
        return 4
    print(f"listed_services={len(rows)}", file=sys.stderr)
    for r in rows:
        n = str(r.get("name") or "")
        i = str(r.get("_id") or r.get("id") or "")
        print(f"svc_name={n} id_prefix={i[:6]}", file=sys.stderr)
    sid = _match(rows)
    if not sid:
        try:
            sid = _create_empty()
            print("created=true", file=sys.stderr)
        except Exception as exc:
            # Race: another create may have won; re-list.
            print(f"create_note:{type(exc).__name__}", file=sys.stderr)
            try:
                rows = _list_services()
                sid = _match(rows)
            except Exception as exc2:
                print(f"relist_failed:{type(exc2).__name__}", file=sys.stderr)
                return 5
    if not sid or sid == FORBIDDEN:
        print("BLOCKER_service_id_unresolved", file=sys.stderr)
        return 1
    print(f"resolved_prefix={sid[:6]}", file=sys.stderr)
    print(sid, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

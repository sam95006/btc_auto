#!/usr/bin/env python3
"""Suspend Stage3 + Unified Control Plane on Zeabur; never touch Validation.

Uses Zeabur GraphQL. Prints only redacted operational status (no secrets).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.zeabur.com/graphql"
TOKEN = os.environ.get("ZEABUR_TOKEN", "").strip()
ENV_ID = os.environ.get("ZEABUR_ENV_ID", "69d559b6474db8a99d6dd6bf").strip()
VALIDATION_ID = os.environ.get("VALIDATION_SERVICE_ID", "6a82a79aa21454a2cf6b0015").strip()
STAGE3_ID = os.environ.get("STAGE3_SERVICE_ID", "6a3b81652fdef84a45a2a553").strip()
CONTROL_PLANE_ID = os.environ.get(
    "CONTROL_PLANE_SERVICE_ID", "6a6bf638ffb4fc697c8a7b1f"
).strip()
DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes"}

FORBIDDEN_TOUCH = {VALIDATION_ID}

# Prefer suspend (scale-to-zero equivalent). Never delete.
# Signature mirrors documented restartService(serviceID, environmentID).
MUTATIONS = [
    (
        "suspendServiceEnv",
        "mutation($serviceID: ObjectID!, $environmentID: ObjectID!) { "
        "suspendService(serviceID: $serviceID, environmentID: $environmentID) }",
        lambda sid: {"serviceID": sid, "environmentID": ENV_ID},
    ),
    (
        "suspendService",
        "mutation($serviceID: ObjectID!) { suspendService(serviceID: $serviceID) }",
        lambda sid: {"serviceID": sid},
    ),
    (
        "pauseServiceEnv",
        "mutation($serviceID: ObjectID!, $environmentID: ObjectID!) { "
        "pauseService(serviceID: $serviceID, environmentID: $environmentID) }",
        lambda sid: {"serviceID": sid, "environmentID": ENV_ID},
    ),
    (
        "stopServiceEnv",
        "mutation($serviceID: ObjectID!, $environmentID: ObjectID!) { "
        "stopService(serviceID: $serviceID, environmentID: $environmentID) }",
        lambda sid: {"serviceID": sid, "environmentID": ENV_ID},
    ),
    (
        "cancelDeploymentEnv",
        "mutation($serviceID: ObjectID!, $environmentID: ObjectID!) { "
        "cancelDeployment(serviceID: $serviceID, environmentID: $environmentID) }",
        lambda sid: {"serviceID": sid, "environmentID": ENV_ID},
    ),
]


def _introspect_suspend_fields() -> list[str]:
    q = (
        "{ __schema { mutationType { fields { name } } } }"
    )
    try:
        payload = _gql(q, {})
    except Exception as exc:  # noqa: BLE001
        return [f"introspect_error:{_redact(str(exc))}"]
    fields = (
        (((payload.get("data") or {}).get("__schema") or {}).get("mutationType") or {}).get("fields")
        or []
    )
    names = [str(f.get("name") or "") for f in fields if isinstance(f, dict)]
    keys = ("suspend", "pause", "stop", "cancel", "scale", "disable")
    return [n for n in names if any(k in n.lower() for k in keys)]


def _redact(text: str) -> str:
    out = text or ""
    if TOKEN:
        out = out.replace(TOKEN, "***TOKEN***")
    out = re.sub(r"[A-Za-z0-9_\-+/=]{40,}", "***REDACTED***", out)
    return out[:1200]


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
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"http_{exc.code}:{_redact(detail)}") from exc
    return payload


def _try_suspend(service_id: str, label: str) -> dict:
    if service_id in FORBIDDEN_TOUCH:
        return {"label": label, "service_id": service_id, "ok": False, "error": "FORBIDDEN_VALIDATION"}
    if DRY_RUN:
        return {"label": label, "service_id": service_id, "ok": True, "dry_run": True, "method": "dry_run"}
    errors: list[str] = []
    for name, query, vars_fn in MUTATIONS:
        try:
            payload = _gql(query, vars_fn(service_id))
        except Exception as exc:  # noqa: BLE001 ??collect attempts
            errors.append(f"{name}:exc:{_redact(str(exc))}")
            continue
        if payload.get("errors"):
            msgs = "; ".join(str(e.get("message") or e) for e in payload["errors"][:3])
            errors.append(f"{name}:gql:{_redact(msgs)}")
            continue
        data = payload.get("data") or {}
        return {
            "label": label,
            "service_id": service_id,
            "ok": True,
            "method": name,
            "data_keys": sorted(data.keys()),
        }
    return {"label": label, "service_id": service_id, "ok": False, "errors": errors[:8]}


def main() -> int:
    if not TOKEN:
        print("missing ZEABUR_TOKEN", file=sys.stderr)
        return 2
    targets = [
        (STAGE3_ID, "nexus-stage3-bybit-demo-learning"),
        (CONTROL_PLANE_ID, "nexus-unified-control-plane"),
    ]
    mutation_hints = _introspect_suspend_fields() if TOKEN and not DRY_RUN else []
    results = [_try_suspend(sid, name) for sid, name in targets]
    report = {
        "validation_untouched": VALIDATION_ID,
        "dry_run": DRY_RUN,
        "mutation_hints": mutation_hints[:40],
        "results": results,
        "all_ok": all(r.get("ok") for r in results),
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

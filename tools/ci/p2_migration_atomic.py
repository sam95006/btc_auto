"""P2 migration atomic same-exec current-pod gate + authoritative stdout evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

MIGRATION_HELPER_REL = "tools/ci/p2_staging_migration_0007.py"
MIGRATION_HELPER_PATH = f"/app/{MIGRATION_HELPER_REL}"

STALE_POD_MARKER = "P2_MIGRATION_EXEC_POD_NOT_CURRENT=true"
PYTHON_STARTED_MARKER = "P2_MIGRATION_PYTHON_STARTED=true"
GATES_PASS_MARKER = "P2_MIGRATION_CURRENT_POD_GATES_PASS=true"
STALE_POD_EXIT = 42
MAX_STALE_ATTEMPTS = 36
STALE_RETRY_INTERVAL_SEC = 5.0
FORBIDDEN_SECRET_MARKERS = (
    "postgres://",
    "postgresql://",
    "NEXUS_POSTGRES_URL=",
    "password",
    "secret",
)

ATOMIC_REMOTE_SH = r"""
set -eu
echo P2_MIGRATION_ATOMIC_EXEC=true
echo P2_MIGRATION_PYTHON_STARTED=false
EXPECTED="${EXPECTED:-}"
APP_ROOT="${APP_ROOT:-/app}"
BAKED=""
SOURCE=""
HELPER_PRESENT=false
if [ -f "$APP_ROOT/DEPLOYMENT_COMMIT" ]; then
  BAKED=$(tr -d '\r\n' < "$APP_ROOT/DEPLOYMENT_COMMIT")
fi
if [ -f "$APP_ROOT/SOURCE_COMMIT" ]; then
  SOURCE=$(tr -d '\r\n' < "$APP_ROOT/SOURCE_COMMIT")
fi
if [ -f "$APP_ROOT/tools/ci/p2_staging_migration_0007.py" ]; then
  HELPER_PRESENT=true
fi
echo "expected_sha_prefix=$(printf '%s' "$EXPECTED" | cut -c1-12)"
echo "baked_sha_prefix=$(printf '%s' "$BAKED" | cut -c1-12)"
echo "source_sha_prefix=$(printf '%s' "$SOURCE" | cut -c1-12)"
echo "helper_present=$HELPER_PRESENT"
current=true
if [ -z "$EXPECTED" ] || [ -z "$BAKED" ] || [ -z "$SOURCE" ]; then
  current=false
fi
if [ "$BAKED" != "$EXPECTED" ] || [ "$SOURCE" != "$EXPECTED" ] || [ "$BAKED" != "$SOURCE" ]; then
  current=false
fi
if [ "$HELPER_PRESENT" != true ]; then
  current=false
fi
if [ "$current" != true ]; then
  echo P2_MIGRATION_EXEC_POD_NOT_CURRENT=true
  echo P2_MIGRATION_PYTHON_STARTED=false
  exit 42
fi
if [ -z "${NEXUS_POSTGRES_URL:-}" ]; then
  echo P2_MIGRATION_ATOMIC_GATE_FAIL=dsn_missing
  echo P2_MIGRATION_PYTHON_STARTED=false
  exit 1
fi
if [ "${MAINNET:-}" != false ] || [ "${REAL_MONEY:-}" != false ] || [ "${DEMO_AUTONOMOUS_ENABLED:-}" != false ] || [ "${AUTONOMOUS_SEND:-}" != false ] || [ "${EXCHANGE_WRITE:-}" != false ]; then
  echo P2_MIGRATION_ATOMIC_GATE_FAIL=safety_flags
  echo P2_MIGRATION_PYTHON_STARTED=false
  exit 1
fi
echo P2_MIGRATION_CURRENT_POD_GATES_PASS=true
export PYTHONPATH="${PYTHONPATH:-/app}"
export MAINNET=false
export REAL_MONEY=false
export DEMO_AUTONOMOUS_ENABLED=false
export AUTONOMOUS_SEND=false
export EXCHANGE_WRITE=false
export NEXUS_ENV="${NEXUS_ENV:-STAGING}"
export NEXUS_PG_RUNTIME_ENABLED="${NEXUS_PG_RUNTIME_ENABLED:-true}"
python - <<'PY'
import json
import sys
try:
    import backend.nexus_persistence_pg.migrate  # noqa: F401
    import backend.nexus_persistence_pg.pool  # noqa: F401
    import tools.ci.p2_staging_migration_0007  # noqa: F401
except Exception as exc:
    print(
        json.dumps(
            {
                "P2_MIGRATION_PREBOOTSTRAP_FAILURE": True,
                "stage": "import",
                "exception_type": type(exc).__name__,
                "helper_present": True,
                "python_started": False,
                "create_order_calls": 0,
                "exchange_write_call_count": 0,
            }
        )
    )
    sys.exit(1)
PY
echo P2_MIGRATION_PYTHON_STARTED=true
exec python -m tools.ci.p2_staging_migration_0007
"""


def current_pod_shell_gates_pass(
    *,
    expected: str,
    baked: str | None,
    source: str | None,
    helper_present: bool,
    postgres_url: str | None,
    mainnet: str,
    real_money: str,
    demo_autonomous_enabled: str,
    autonomous_send: str,
    exchange_write: str,
) -> dict[str, Any]:
    expected_s = (expected or "").strip()
    baked_s = (baked or "").strip()
    source_s = (source or "").strip()
    sha_ok = bool(
        expected_s
        and baked_s
        and source_s
        and baked_s == expected_s
        and source_s == expected_s
        and baked_s == source_s
    )
    current = sha_ok and bool(helper_present)
    if not current:
        return {
            "current_pod": False,
            "stale_pod": True,
            "python_may_start": False,
            "marker": STALE_POD_MARKER,
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
        }
    if not (postgres_url or "").strip():
        return {
            "current_pod": True,
            "stale_pod": False,
            "python_may_start": False,
            "marker": "P2_MIGRATION_ATOMIC_GATE_FAIL=dsn_missing",
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
        }
    flags_ok = (
        mainnet == "false"
        and real_money == "false"
        and demo_autonomous_enabled == "false"
        and autonomous_send == "false"
        and exchange_write == "false"
    )
    if not flags_ok:
        return {
            "current_pod": True,
            "stale_pod": False,
            "python_may_start": False,
            "marker": "P2_MIGRATION_ATOMIC_GATE_FAIL=safety_flags",
            "create_order_calls": 0,
            "exchange_write_call_count": 0,
        }
    return {
        "current_pod": True,
        "stale_pod": False,
        "python_may_start": True,
        "marker": GATES_PASS_MARKER,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def classify_atomic_exec_output(raw: str) -> dict[str, Any]:
    text = raw or ""
    python_started = PYTHON_STARTED_MARKER in text
    stale_pod = STALE_POD_MARKER in text and not python_started
    return {
        "python_started": python_started,
        "stale_pod": stale_pod,
        "retry_allowed": stale_pod and not python_started,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def run_atomic_migration_with_stale_retry(
    *,
    exec_attempt: Callable[[int], dict[str, Any]],
    max_attempts: int = MAX_STALE_ATTEMPTS,
    interval_sec: float = STALE_RETRY_INTERVAL_SEC,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    sleeper = sleep or (lambda _seconds: None)
    history: list[dict[str, Any]] = []
    last_stdout = ""
    python_starts = 0
    attempt = 0
    for attempt in range(1, max_attempts + 1):
        result = exec_attempt(attempt)
        stdout = str(result.get("stdout") or "")
        last_stdout = stdout
        classified = classify_atomic_exec_output(stdout)
        history.append({"attempt": attempt, "exit_code": result.get("exit_code"), **classified})
        if classified["python_started"]:
            python_starts += 1
            if python_starts > 1:
                raise RuntimeError("migration_python_rerun_forbidden")
            return {
                "migration_started": True,
                "python_starts": 1,
                "retry_after_python_start": False,
                "attempts": attempt,
                "history": history,
                "stdout": stdout,
                "create_order_calls": 0,
                "exchange_write_call_count": 0,
            }
        if classified["retry_allowed"]:
            sleeper(interval_sec)
            continue
        break
    stale_only = bool(history) and all(item.get("stale_pod") for item in history)
    return {
        "migration_started": False,
        "python_starts": 0,
        "retry_after_python_start": False,
        "attempts": attempt,
        "history": history,
        "stdout": last_stdout,
        "error": "stale_pod_retry_exhausted" if stale_only else "pre_bootstrap_failure",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def _iter_json_objects(raw: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = 0
    text = raw or ""
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        index = end if end > index else index + 1
    return found


def _secret_leak(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, default=str).lower()
    return any(marker in text for marker in FORBIDDEN_SECRET_MARKERS)


def extract_authoritative_migration_stdout(raw: str) -> dict[str, Any]:
    migration: dict[str, Any] | None = None
    prebootstrap: dict[str, Any] | None = None
    for obj in _iter_json_objects(raw):
        if _secret_leak(obj):
            continue
        if obj.get("P2_MIGRATION_PREBOOTSTRAP_FAILURE"):
            prebootstrap = obj
            continue
        if "P2_MIGRATION_0007_APPLIED_PASS" in obj:
            migration = obj
    if migration is not None:
        return {
            "authoritative": True,
            "kind": "migration",
            "decision": "PASS" if migration.get("P2_MIGRATION_0007_APPLIED_PASS") is True else "HOLD",
            "payload": migration,
            "file_channel_authoritative": False,
        }
    if prebootstrap is not None:
        return {
            "authoritative": True,
            "kind": "prebootstrap",
            "decision": "HOLD",
            "payload": prebootstrap,
            "file_channel_authoritative": False,
        }
    return {
        "authoritative": False,
        "kind": "missing",
        "decision": "HOLD",
        "payload": None,
        "file_channel_authoritative": False,
    }


def sanitize_prebootstrap_failure(raw: str) -> dict[str, Any]:
    text = raw or ""
    out: dict[str, Any] = {
        "python_started": PYTHON_STARTED_MARKER in text,
        "stale_pod": STALE_POD_MARKER in text,
        "helper_present": "helper_present=true" in text,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }
    for line in text.splitlines():
        if line.startswith("expected_sha_prefix="):
            out["expected_sha_prefix"] = line.split("=", 1)[1]
        elif line.startswith("baked_sha_prefix="):
            out["baked_sha_prefix"] = line.split("=", 1)[1]
        elif line.startswith("source_sha_prefix="):
            out["source_sha_prefix"] = line.split("=", 1)[1]
        elif line.startswith("P2_MIGRATION_ATOMIC_GATE_FAIL="):
            out["stage"] = line.split("=", 1)[1]
    auth = extract_authoritative_migration_stdout(text)
    if auth.get("kind") == "prebootstrap" and isinstance(auth.get("payload"), dict):
        payload = auth["payload"]
        out["stage"] = payload.get("stage") or out.get("stage")
        out["exception_type"] = payload.get("exception_type")
    if "Traceback" in text and "exception_type" not in out:
        import re

        match = re.search(r"^([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))(?::|$)", text, re.MULTILINE)
        if match:
            out["exception_type"] = match.group(1)
    if STALE_POD_MARKER in text and not out["python_started"]:
        out["stage"] = out.get("stage") or "stale_pod"
    return out


def control_decision_from_channels(
    *,
    stdout_result: dict[str, Any],
    file_http_status: int | None = None,
    file_bytes: int | None = None,
    file_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del file_http_status, file_bytes, file_payload
    if stdout_result.get("authoritative") and stdout_result.get("kind") == "migration":
        decision = stdout_result.get("decision") or "HOLD"
    else:
        decision = "HOLD"
    return {
        "decision": decision,
        "authoritative_channel": "stdout" if stdout_result.get("authoritative") else "none",
        "file_channel_authoritative": False,
        "file_channel_override": False,
    }


def write_authoritative_artifact(result: dict[str, Any], destination: Path) -> Path | None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    control = {
        "authoritative_stdout": bool(result.get("authoritative")),
        "kind": result.get("kind"),
        "control_decision": result.get("decision") or "HOLD",
        "file_channel_authoritative": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }
    (destination.parent / "p2_migration_control_decision.json").write_text(
        json.dumps(control, indent=2), encoding="utf-8"
    )
    payload = result.get("payload")
    if not result.get("authoritative") or not isinstance(payload, dict):
        (destination.parent / "p2_migration_stdout_missing.json").write_text(
            json.dumps({"control_decision": "HOLD", "reason": "stdout_evidence_missing"}, indent=2),
            encoding="utf-8",
        )
        return None
    if result.get("kind") == "prebootstrap":
        prebootstrap_path = destination.parent / "p2_migration_prebootstrap_failure.json"
        prebootstrap_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return prebootstrap_path
    destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return destination


def print_remote_script() -> str:
    return ATOMIC_REMOTE_SH.lstrip("\n")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--print-remote-script" in args:
        script = print_remote_script()
        sys.stdout.write(script)
        if not script.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

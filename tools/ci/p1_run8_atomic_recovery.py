"""Run #8 atomic same-exec current-pod gate + authoritative stdout evidence.

Identity and Python bootstrap must share one remote shell. A stale-pod hit
retries only before bootstrap starts. File download is never the control
authority.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p1_zeabur_transport import (  # noqa: E402
    parse_run8_accounting_recovery_evidence,
    parse_run8_bootstrap_failure_evidence,
)

STALE_POD_MARKER = "P1_RUN8_EXEC_POD_NOT_CURRENT=true"
BOOTSTRAP_STARTED_MARKER = "P1_RUN8_PYTHON_BOOTSTRAP_STARTED=true"
GATES_PASS_MARKER = "P1_RUN8_CURRENT_POD_GATES_PASS=true"
STALE_POD_EXIT = 42
MAX_STALE_ATTEMPTS = 36
STALE_RETRY_INTERVAL_SEC = 5.0
FORBIDDEN_SECRET_MARKERS = (
    "postgres://",
    "postgresql://",
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
)

ATOMIC_REMOTE_SH = r"""
set -eu
echo P1_RUN8_ATOMIC_EXEC=true
echo P1_RUN8_PYTHON_BOOTSTRAP_STARTED=false
EXPECTED="${EXPECTED:-}"
APP_ROOT="${APP_ROOT:-/app}"
BAKED=""
SOURCE=""
SCRIPT_PRESENT=false
if [ -f "$APP_ROOT/DEPLOYMENT_COMMIT" ]; then
  BAKED=$(tr -d '\r\n' < "$APP_ROOT/DEPLOYMENT_COMMIT")
fi
if [ -f "$APP_ROOT/SOURCE_COMMIT" ]; then
  SOURCE=$(tr -d '\r\n' < "$APP_ROOT/SOURCE_COMMIT")
fi
if [ -f "$APP_ROOT/p1_run8_baked_identity_probe.sh" ]; then
  SCRIPT_PRESENT=true
fi
echo "expected_sha_prefix=$(printf '%s' "$EXPECTED" | cut -c1-12)"
echo "baked_sha_prefix=$(printf '%s' "$BAKED" | cut -c1-12)"
echo "source_sha_prefix=$(printf '%s' "$SOURCE" | cut -c1-12)"
echo "probe_script_present=$SCRIPT_PRESENT"
current=true
if [ -z "$EXPECTED" ] || [ -z "$BAKED" ] || [ -z "$SOURCE" ]; then
  current=false
fi
if [ "$BAKED" != "$EXPECTED" ] || [ "$SOURCE" != "$EXPECTED" ] || [ "$BAKED" != "$SOURCE" ]; then
  current=false
fi
if [ "$SCRIPT_PRESENT" != true ]; then
  current=false
fi
if [ "$current" != true ]; then
  echo P1_RUN8_EXEC_POD_NOT_CURRENT=true
  echo P1_RUN8_PYTHON_BOOTSTRAP_STARTED=false
  exit 42
fi
if [ -z "${NEXUS_POSTGRES_URL:-}" ]; then
  echo P1_RUN8_ATOMIC_GATE_FAIL=dsn_missing
  echo P1_RUN8_PYTHON_BOOTSTRAP_STARTED=false
  exit 1
fi
if [ "${MAINNET:-}" != false ] || [ "${REAL_MONEY:-}" != false ] || [ "${DEMO_AUTONOMOUS_ENABLED:-}" != false ] || [ "${AUTONOMOUS_SEND:-}" != false ] || [ "${EXCHANGE_WRITE:-}" != false ]; then
  echo P1_RUN8_ATOMIC_GATE_FAIL=safety_flags
  echo P1_RUN8_PYTHON_BOOTSTRAP_STARTED=false
  exit 1
fi
echo P1_RUN8_CURRENT_POD_GATES_PASS=true
echo P1_RUN8_PYTHON_BOOTSTRAP_STARTED=true
export PYTHONPATH="${PYTHONPATH:-/app}"
export MAINNET=false
export REAL_MONEY=false
export DEMO_AUTONOMOUS_ENABLED=false
export AUTONOMOUS_SEND=false
export EXCHANGE_WRITE=false
export NEXUS_ENV="${NEXUS_ENV:-STAGING}"
export NEXUS_PG_RUNTIME_ENABLED="${NEXUS_PG_RUNTIME_ENABLED:-true}"
export NEXUS_EXPECTED_SHA="${NEXUS_EXPECTED_SHA:-$EXPECTED}"
exec python -m backend.nexus_demo_execution.p1_run8_accounting_recovery_bootstrap
"""


def current_pod_shell_gates_pass(
    *,
    expected: str,
    baked: str | None,
    source: str | None,
    script_present: bool,
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
    current = sha_ok and bool(script_present)
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
            "marker": "P1_RUN8_ATOMIC_GATE_FAIL=dsn_missing",
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
            "marker": "P1_RUN8_ATOMIC_GATE_FAIL=safety_flags",
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
    bootstrap_started = BOOTSTRAP_STARTED_MARKER in text
    stale_pod = STALE_POD_MARKER in text and not bootstrap_started
    return {
        "bootstrap_started": bootstrap_started,
        "stale_pod": stale_pod,
        "retry_allowed": stale_pod and not bootstrap_started,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def run_atomic_recovery_with_stale_retry(
    *,
    exec_attempt: Callable[[int], dict[str, Any]],
    max_attempts: int = MAX_STALE_ATTEMPTS,
    interval_sec: float = STALE_RETRY_INTERVAL_SEC,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Retry the whole atomic exec only for pre-bootstrap stale-pod hits."""
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
        history.append(
            {
                "attempt": attempt,
                "exit_code": result.get("exit_code"),
                **classified,
            }
        )
        if classified["bootstrap_started"]:
            python_starts += 1
            if python_starts > 1:
                raise RuntimeError("recovery_bootstrap_rerun_forbidden")
            return {
                "recovery_started": True,
                "python_bootstrap_starts": 1,
                "retry_after_bootstrap": False,
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
        "recovery_started": False,
        "python_bootstrap_starts": 0,
        "retry_after_bootstrap": False,
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
    text = json.dumps(payload, default=str)
    return any(marker in text for marker in FORBIDDEN_SECRET_MARKERS)


def extract_authoritative_run8_stdout(raw: str) -> dict[str, Any]:
    """Scan wrapper noise and validate with existing Run8 parsers. Never infers PASS."""
    recovery: dict[str, Any] | None = None
    bootstrap: dict[str, Any] | None = None
    for obj in _iter_json_objects(raw):
        dumped = json.dumps(obj)
        try:
            parsed = parse_run8_accounting_recovery_evidence(dumped)
        except ValueError:
            parsed = None
        if parsed is not None:
            if not _secret_leak(parsed):
                recovery = parsed
            continue
        try:
            parsed_b = parse_run8_bootstrap_failure_evidence(dumped)
        except ValueError:
            continue
        if not _secret_leak(parsed_b):
            bootstrap = parsed_b
    if recovery is not None:
        verdict = str(recovery.get("BYBIT_DEMO_SINGLE_TRADE_E2E_PASS") or "HOLD")
        decision = "PASS" if verdict == "PASS" else "HOLD"
        return {
            "authoritative": True,
            "kind": "recovery",
            "decision": decision,
            "payload": recovery,
            "file_channel_authoritative": False,
        }
    if bootstrap is not None:
        return {
            "authoritative": True,
            "kind": "bootstrap",
            "decision": "HOLD",
            "payload": bootstrap,
            "file_channel_authoritative": False,
        }
    return {
        "authoritative": False,
        "kind": "missing",
        "decision": "HOLD",
        "payload": None,
        "file_channel_authoritative": False,
    }


def control_decision_from_channels(
    *,
    stdout_result: dict[str, Any],
    file_http_status: int | None = None,
    file_bytes: int | None = None,
    file_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stdout is the only control channel. File hits cannot create or override PASS."""
    del file_http_status, file_bytes, file_payload
    if stdout_result.get("authoritative"):
        decision = stdout_result.get("decision") or "HOLD"
    else:
        decision = "HOLD"
    if decision not in {"PASS", "HOLD"}:
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
    (destination.parent / "p1_run8_control_decision.json").write_text(
        json.dumps(control, indent=2), encoding="utf-8"
    )
    payload = result.get("payload")
    if not result.get("authoritative") or not isinstance(payload, dict):
        (destination.parent / "p1_run8_stdout_missing.json").write_text(
            json.dumps({"control_decision": "HOLD", "reason": "stdout_evidence_missing"}, indent=2),
            encoding="utf-8",
        )
        return None
    destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    if result.get("kind") == "bootstrap":
        (destination.parent / "p1_run8_bootstrap_failure.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
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

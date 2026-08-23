"""P2 migration operational readiness — service-exec SHA + safety proof (authoritative)."""
from __future__ import annotations

from typing import Any, Callable

CURRENT_IMAGE_PROBE_PASS_MARKER = "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true"
OPERATIONAL_READINESS_PASS_MARKER = "P2_MIGRATION_OPERATIONAL_READINESS_PASS=true"
BOOTSTRAP_READINESS_PASS_MARKER = "P2_MIGRATION_BOOTSTRAP_OPERATIONAL_READINESS_PASS=true"
ACTIVATION_READINESS_PASS_MARKER = "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=true"
SERVICE_NOT_RUNNING_MARKER = "P2_MIGRATION_SERVICE_NOT_RUNNING_YET=true"

NOT_RUNNING_MARKERS = (
    "NOT_RUNNING_SERVICE",
    "Inactive service",
    "This service is not in the running state",
)
CLI_TRANSPORT_WAIT_MARKERS = (
    "execute command failed",
    *NOT_RUNNING_MARKERS,
)

# Remote probe: SHA + helper + disarmed safety flags. Never print secret values.
INLINE_CURRENT_IMAGE_PROBE_SH = r"""
set -eu
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
echo "expected_sha=$EXPECTED"
echo "baked_sha=$BAKED"
echo "source_sha=$SOURCE"
echo "expected_sha_prefix=$(printf '%s' "$EXPECTED" | cut -c1-12)"
echo "baked_sha_prefix=$(printf '%s' "$BAKED" | cut -c1-12)"
echo "source_sha_prefix=$(printf '%s' "$SOURCE" | cut -c1-12)"
echo "helper_present=$HELPER_PRESENT"
SAFETY_OK=true
for flag in MAINNET REAL_MONEY DEMO_AUTONOMOUS_ENABLED AUTONOMOUS_SEND EXCHANGE_WRITE; do
  eval "val=\${$flag:-}"
  if [ "$val" != "false" ]; then
    SAFETY_OK=false
    echo "safety_flag_bad=$flag"
  fi
done
echo "safety_flags_ok=$SAFETY_OK"
if [ -z "$EXPECTED" ] || [ -z "$BAKED" ] || [ -z "$SOURCE" ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  echo "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_BOOTSTRAP_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=false"
  exit 1
fi
if [ "$BAKED" != "$EXPECTED" ] || [ "$SOURCE" != "$EXPECTED" ] || [ "$BAKED" != "$SOURCE" ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  echo "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_BOOTSTRAP_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=false"
  exit 1
fi
if [ "$HELPER_PRESENT" != true ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  echo "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_BOOTSTRAP_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=false"
  exit 1
fi
if [ "$SAFETY_OK" != true ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  echo "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_BOOTSTRAP_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=false"
  exit 1
fi
echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true"
echo "P2_MIGRATION_OPERATIONAL_READINESS_PASS=true"
echo "P2_MIGRATION_BOOTSTRAP_OPERATIONAL_READINESS_PASS=true"
"""

INLINE_ACTIVATION_READINESS_PROBE_SH = INLINE_CURRENT_IMAGE_PROBE_SH + r"""
DSN_PRESENT=false
if [ -n "${NEXUS_POSTGRES_URL:-}" ]; then
  DSN_PRESENT=true
fi
echo "dsn_present=$DSN_PRESENT"
if [ "$DSN_PRESENT" != true ]; then
  echo "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=false"
  echo "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false"
  exit 1
fi
echo "P2_MIGRATION_ACTIVATION_OPERATIONAL_READINESS_PASS=true"
"""


def _field(raw: str, key: str) -> str:
    prefix = f"{key}="
    for line in (raw or "").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def classify_readiness_probe_output(
    raw: str,
    *,
    expected_sha: str | None = None,
    transport_exit_code: int | None = None,
    phase: str = "bootstrap",
) -> dict[str, Any]:
    """Classify one Zeabur service-exec operational readiness capture.

    NOT_RUNNING / inactive → wait (never PASS).
    Wrong SHA / missing helper / safety flag true → hard fail closed.
    Activation phase additionally requires NEXUS_POSTGRES_URL presence (never print value).
    """
    del transport_exit_code
    phase_norm = (phase or "bootstrap").strip().lower()
    if phase_norm not in {"bootstrap", "activation", "legacy"}:
        raise ValueError("readiness_phase_unsupported")
    text = raw or ""
    not_running = any(marker in text for marker in NOT_RUNNING_MARKERS)
    transport_wait = any(marker in text for marker in CLI_TRANSPORT_WAIT_MARKERS)
    pass_marker = (
        OPERATIONAL_READINESS_PASS_MARKER in text
        or CURRENT_IMAGE_PROBE_PASS_MARKER in text
        or (phase_norm == "bootstrap" and BOOTSTRAP_READINESS_PASS_MARKER in text)
        or (phase_norm == "activation" and ACTIVATION_READINESS_PASS_MARKER in text)
    )
    expected = (expected_sha or "").strip() or _field(text, "expected_sha")
    baked = _field(text, "baked_sha")
    source = _field(text, "source_sha")
    helper_present = _field(text, "helper_present") == "true"
    safety_ok = _field(text, "safety_flags_ok")
    safety_line_present = "safety_flags_ok=" in text
    safety_flags_ok = safety_ok == "true" if safety_line_present else False
    dsn_line_present = "dsn_present=" in text
    dsn_present = _field(text, "dsn_present") == "true" if dsn_line_present else phase_norm != "activation"
    expected_prefix = _field(text, "expected_sha_prefix")
    baked_prefix = _field(text, "baked_sha_prefix")
    source_prefix = _field(text, "source_sha_prefix")
    sha_ok = bool(
        expected
        and baked
        and source
        and baked == expected
        and source == expected
        and baked == source
        and helper_present
    )
    prefixes_present = bool(expected_prefix and baked_prefix and source_prefix)
    probe_body_ran = bool(_field(text, "expected_sha") or _field(text, "helper_present") or safety_line_present)

    ready = bool(
        pass_marker
        and sha_ok
        and prefixes_present
        and safety_flags_ok
        and dsn_present
        and not not_running
        and not (transport_wait and not pass_marker)
    )

    hard_fail = False
    if not not_running and probe_body_ran and not ready:
        if safety_line_present and not safety_flags_ok:
            hard_fail = True
        elif phase_norm == "activation" and dsn_line_present and not dsn_present:
            hard_fail = True
        elif baked or source or _field(text, "helper_present"):
            if not sha_ok or not helper_present or not prefixes_present:
                hard_fail = True

    phase_pass_marker = {
        "bootstrap": BOOTSTRAP_READINESS_PASS_MARKER,
        "activation": ACTIVATION_READINESS_PASS_MARKER,
        "legacy": OPERATIONAL_READINESS_PASS_MARKER,
    }[phase_norm]

    return {
        "ready": ready,
        "operational_ready": ready,
        "phase": phase_norm,
        "not_running_yet": not_running and not ready,
        "hard_fail": hard_fail,
        "cli_error": transport_wait and not ready and not hard_fail,
        "pass_marker_present": pass_marker,
        "helper_present": helper_present,
        "safety_flags_ok": safety_flags_ok,
        "dsn_present": dsn_present,
        "expected_sha_prefix": expected_prefix,
        "baked_sha_prefix": baked_prefix,
        "source_sha_prefix": source_prefix,
        "sha_ok": sha_ok,
        "SERVICE_NOT_RUNNING_MARKER": SERVICE_NOT_RUNNING_MARKER if not_running else "",
        phase_pass_marker: "true" if ready else "false",
        "P2_MIGRATION_OPERATIONAL_READINESS_PASS": "true" if ready else "false",
        "P2_MIGRATION_DEPLOY_OUTPUT_DEPLOYMENT_ID_AUTHORITY": False,
        "P2_MIGRATION_DEPLOYMENT_LIST_AUTHORITY": False,
        "OPERATIONAL_RUNTIME_SHA_AUTHORITY": ready,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def wait_for_current_image_streak(
    *,
    probe: Callable[[int], dict[str, Any]],
    max_attempts: int = 12,
    consecutive_needed: int = 3,
    retry_interval_sec: float = 5.0,
    consecutive_gap_sec: float = 2.0,
    sleep: Callable[[float], None] | None = None,
    phase: str = "bootstrap",
) -> dict[str, Any]:
    sleeper = sleep or (lambda _seconds: None)
    phase_norm = (phase or "bootstrap").strip().lower()
    streak = 0
    history: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        result = probe(attempt)
        classified = classify_readiness_probe_output(
            str(result.get("stdout") or ""),
            expected_sha=str(result.get("expected_sha") or "") or None,
            transport_exit_code=result.get("exit_code"),  # type: ignore[arg-type]
            phase=phase_norm,
        )
        row = {"attempt": attempt, "exit_code": result.get("exit_code"), **classified}
        history.append(row)
        if classified.get("hard_fail"):
            return {
                "converged": False,
                "streak": 0,
                "attempts": attempt,
                "history": history,
                "hard_fail": True,
                "fail_closed": True,
                "create_order_calls": 0,
                "exchange_write_call_count": 0,
            }
        if classified["ready"]:
            streak += 1
            row["current_image_streak"] = streak
            if streak >= consecutive_needed:
                return {
                    "converged": True,
                    "streak": streak,
                    "attempts": attempt,
                    "history": history,
                    "P2_MIGRATION_OPERATIONAL_READINESS_PASS": True,
                    "P2_MIGRATION_DEPLOYMENT_CONVERGED": True,
                    "hard_fail": False,
                    "create_order_calls": 0,
                    "exchange_write_call_count": 0,
                }
            sleeper(consecutive_gap_sec)
            continue
        streak = 0
        sleeper(retry_interval_sec)
    return {
        "converged": False,
        "streak": 0,
        "attempts": max_attempts,
        "history": history,
        "hard_fail": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def print_remote_script(*, phase: str = "bootstrap") -> str:
    phase_norm = (phase or "bootstrap").strip().lower()
    if phase_norm == "activation":
        return INLINE_ACTIVATION_READINESS_PROBE_SH.lstrip("\n")
    return INLINE_CURRENT_IMAGE_PROBE_SH.lstrip("\n")


def main(argv: list[str] | None = None) -> int:
    import json
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    phase = "bootstrap"
    if "--phase" in args:
        phase = args[args.index("--phase") + 1]
    if "--print-remote-script" in args:
        script = print_remote_script(phase=phase)
        sys.stdout.write(script)
        if not script.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    if "--classify-file" in args:
        idx = args.index("--classify-file")
        path = Path(args[idx + 1])
        expected = ""
        if "--expected" in args:
            expected = args[args.index("--expected") + 1]
        exit_code = None
        if "--exit-code" in args:
            exit_code = int(args[args.index("--exit-code") + 1])
        classified = classify_readiness_probe_output(
            path.read_text(encoding="utf-8", errors="replace"),
            expected_sha=expected or None,
            transport_exit_code=exit_code,
            phase=phase,
        )
        print(json.dumps(classified, sort_keys=True))
        if classified.get("hard_fail"):
            return 3
        return 0 if classified["ready"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

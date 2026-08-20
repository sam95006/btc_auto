"""P2 migration baked-image rollout readiness — positive proof only, never exit-code alone."""
from __future__ import annotations

from typing import Any, Callable

CURRENT_IMAGE_PROBE_PASS_MARKER = "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true"
SERVICE_NOT_RUNNING_MARKER = "P2_MIGRATION_SERVICE_NOT_RUNNING_YET=true"

NOT_RUNNING_MARKERS = (
    "NOT_RUNNING_SERVICE",
    "Inactive service",
    "This service is not in the running state",
)
CLI_ERROR_MARKERS = (
    "execute command failed",
    *NOT_RUNNING_MARKERS,
)

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
if [ -z "$EXPECTED" ] || [ -z "$BAKED" ] || [ -z "$SOURCE" ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  exit 1
fi
if [ "$BAKED" != "$EXPECTED" ] || [ "$SOURCE" != "$EXPECTED" ] || [ "$BAKED" != "$SOURCE" ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  exit 1
fi
if [ "$HELPER_PRESENT" != true ]; then
  echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false"
  exit 1
fi
echo "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true"
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
) -> dict[str, Any]:
    """Classify one Zeabur service-exec readiness capture.

    Transport exit code is advisory only. Positive proof requires the exact
    PASS marker and absence of known CLI/application error text.
    """
    del transport_exit_code
    text = raw or ""
    not_running = any(marker in text for marker in NOT_RUNNING_MARKERS)
    cli_error = any(marker in text for marker in CLI_ERROR_MARKERS)
    pass_marker = CURRENT_IMAGE_PROBE_PASS_MARKER in text
    expected = (expected_sha or "").strip() or _field(text, "expected_sha")
    baked = _field(text, "baked_sha")
    source = _field(text, "source_sha")
    helper_present = _field(text, "helper_present") == "true"
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
    # Prefixes are display-only; empty prefixes still block if full SHAs missing.
    prefixes_present = bool(expected_prefix and baked_prefix and source_prefix)
    ready = bool(pass_marker and sha_ok and prefixes_present and not not_running and not cli_error)
    return {
        "ready": ready,
        "not_running_yet": not_running and not ready,
        "cli_error": cli_error and not ready,
        "pass_marker_present": pass_marker,
        "helper_present": helper_present,
        "expected_sha_prefix": expected_prefix,
        "baked_sha_prefix": baked_prefix,
        "source_sha_prefix": source_prefix,
        "sha_ok": sha_ok,
        "SERVICE_NOT_RUNNING_MARKER": SERVICE_NOT_RUNNING_MARKER if not_running else "",
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
) -> dict[str, Any]:
    sleeper = sleep or (lambda _seconds: None)
    streak = 0
    history: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        result = probe(attempt)
        classified = classify_readiness_probe_output(
            str(result.get("stdout") or ""),
            expected_sha=str(result.get("expected_sha") or "") or None,
            transport_exit_code=result.get("exit_code"),  # type: ignore[arg-type]
        )
        row = {"attempt": attempt, "exit_code": result.get("exit_code"), **classified}
        history.append(row)
        if classified["ready"]:
            streak += 1
            if streak >= consecutive_needed:
                return {
                    "converged": True,
                    "streak": streak,
                    "attempts": attempt,
                    "history": history,
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
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def print_remote_script() -> str:
    return INLINE_CURRENT_IMAGE_PROBE_SH.lstrip("\n")


def main(argv: list[str] | None = None) -> int:
    import json
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    if "--print-remote-script" in args:
        script = print_remote_script()
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
        )
        print(json.dumps(classified, sort_keys=True))
        return 0 if classified["ready"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

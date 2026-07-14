#!/usr/bin/env python3
"""Robust Stage 4 cloud dry-run wait helper.

Fixes known P2D-R1 wait failures:
1. Avoid fragile f-string / brace escaping when building remote python one-liners.
2. Treat expected tick_count reached + summary present as completed_needs_finalize
   even when dry_run_completed remains false (do not poll forever).

Does NOT mutate trading state, order path, or Stage 4.19 gates.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_SERVICE_ID = "6a3b81652fdef84a45a2a553"
DEFAULT_ENV_ID = "69d559b6474db8a99d6dd6bf"

STATUS_COMPLETED = "completed"
STATUS_COMPLETED_NEEDS_FINALIZE = "completed_needs_finalize"
STATUS_PARTIAL_COMPLETION_OR_FINALIZE_NEEDED = "partial_completion_or_finalize_needed"
STATUS_WAITING = "waiting"
STATUS_TIMEOUT = "timeout"
STATUS_MISSING_SUMMARY = "missing_summary"


@dataclass
class WaitSnapshot:
    tick_count: int = 0
    effective_decision_count: int = 0
    parse_error_count: int = 0
    mock_ai_used_count: int = 0
    order_sent_count: int = 0
    dry_run_completed: bool = False
    cloud_dry_run_completed: bool = False
    technical_valid: Optional[bool] = None
    raw: Dict[str, Any] | None = None


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Parse first JSON object from possibly noisy CLI/npm output."""
    if not text:
        return None
    # Prefer lines that look like JSON objects
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
    if not m:
        # broader fallback
        m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def evaluate_wait_status(
    *,
    snapshot: WaitSnapshot | Dict[str, Any] | None,
    expected_tick_count: int = 6,
    summary_present: bool = True,
) -> Dict[str, Any]:
    """Pure status evaluator — no I/O, no trading side effects."""
    if isinstance(snapshot, dict):
        snap = WaitSnapshot(
            tick_count=int(snapshot.get("tick_count") or 0),
            effective_decision_count=int(snapshot.get("effective_decision_count") or 0),
            parse_error_count=int(snapshot.get("parse_error_count") or 0),
            mock_ai_used_count=int(snapshot.get("mock_ai_used_count") or 0),
            order_sent_count=int(snapshot.get("order_sent_count") or 0),
            dry_run_completed=bool(snapshot.get("dry_run_completed")),
            cloud_dry_run_completed=bool(snapshot.get("cloud_dry_run_completed")),
            technical_valid=snapshot.get("technical_valid"),
            raw=snapshot,
        )
    elif snapshot is None:
        snap = WaitSnapshot()
        summary_present = False
    else:
        snap = snapshot

    result: Dict[str, Any] = {
        "status": STATUS_WAITING,
        "summary_present": summary_present,
        "tick_count": snap.tick_count,
        "expected_tick_count": expected_tick_count,
        "effective_decision_count": snap.effective_decision_count,
        "dry_run_completed": snap.dry_run_completed,
        "cloud_dry_run_completed": snap.cloud_dry_run_completed,
        "partial_completion_or_finalize_needed": False,
        "action": "keep_waiting",
        "stage_419_triggered": False,
        "trading_state_mutated": False,
        "order_path_touched": False,
        "snapshot": asdict(snap) if snap.raw is None else snap.raw,
    }

    if not summary_present and snap.tick_count <= 0:
        result["status"] = STATUS_MISSING_SUMMARY
        result["action"] = "keep_waiting_for_summary"
        return result

    done_flag = bool(snap.dry_run_completed or snap.cloud_dry_run_completed)
    ticks_ok = snap.tick_count >= int(expected_tick_count)

    if done_flag and ticks_ok:
        result["status"] = STATUS_COMPLETED
        result["action"] = "proceed_to_post_run_reset_and_analysis"
        return result

    if ticks_ok and summary_present:
        # Known P2D-R1 failure mode: ticks reached but dry_run_completed stayed false
        result["status"] = STATUS_COMPLETED_NEEDS_FINALIZE
        result["partial_completion_or_finalize_needed"] = True
        result["action"] = (
            "treat_as_complete_for_operator_workflow;"
            "run_post_reset_and_analysis;"
            "inspect_why_dry_run_completed_false"
        )
        # Alias for report wording
        result["status_alias"] = STATUS_PARTIAL_COMPLETION_OR_FINALIZE_NEEDED
        return result

    result["status"] = STATUS_WAITING
    result["action"] = "keep_waiting"
    return result


def build_summary_poll_command(output_dir: str) -> str:
    """Build a remote one-liner WITHOUT embedding braces inside Python f-strings."""
    # Use single-quoted remote python -c carefully; return path-literal only.
    # Caller should prefer uploading a tiny poll script; this string is syntax-safe.
    path = output_dir.rstrip("/") + "/stage4_ai_decision_summary.json"
    # Avoid f-string with dict braces entirely
    parts = [
        "python -c '",
        "import json,pathlib;",
        "p=pathlib.Path(\"" + path + "\");",
        "print(\"MISSING\") if not p.is_file() else print(json.dumps(",
        "{",
        '"tick_count":json.loads(p.read_text()).get("tick_count"),',
        '"effective_decision_count":json.loads(p.read_text()).get("effective_decision_count"),',
        '"parse_error_count":json.loads(p.read_text()).get("parse_error_count"),',
        '"mock_ai_used_count":json.loads(p.read_text()).get("mock_ai_used_count"),',
        '"order_sent_count":json.loads(p.read_text()).get("order_sent_count"),',
        '"dry_run_completed":json.loads(p.read_text()).get("dry_run_completed"),',
        '"cloud_dry_run_completed":json.loads(p.read_text()).get("cloud_dry_run_completed"),',
        '"technical_valid":json.loads(p.read_text()).get("technical_valid")',
        "}",
        ", default=str))",
        "'",
    ]
    return "".join(parts)


def poll_local_summary(summary_path: Path) -> tuple[Optional[Dict[str, Any]], bool]:
    if not summary_path.is_file():
        return None, False
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, True
    return (data if isinstance(data, dict) else None), True


def wait_local(
    *,
    output_dir: str | Path,
    expected_tick_count: int = 6,
    poll_seconds: float = 1.0,
    max_polls: int = 5,
    initial_sleep_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Local wait loop for unit tests / offline simulation."""
    out = Path(output_dir)
    summary_path = out / "stage4_ai_decision_summary.json"
    if initial_sleep_seconds > 0:
        time.sleep(initial_sleep_seconds)

    last: Dict[str, Any] = {
        "status": STATUS_TIMEOUT,
        "partial_completion_or_finalize_needed": False,
        "stage_419_triggered": False,
        "trading_state_mutated": False,
    }
    for _ in range(max(1, int(max_polls))):
        data, present = poll_local_summary(summary_path)
        evaluated = evaluate_wait_status(
            snapshot=data,
            expected_tick_count=expected_tick_count,
            summary_present=present and data is not None,
        )
        last = evaluated
        if evaluated["status"] in {
            STATUS_COMPLETED,
            STATUS_COMPLETED_NEEDS_FINALIZE,
        }:
            return evaluated
        time.sleep(max(0.0, float(poll_seconds)))
    last["status"] = STATUS_TIMEOUT
    last["action"] = "timeout_no_tick_progress"
    last["stage_419_triggered"] = False
    last["trading_state_mutated"] = False
    return last


def zeabur_exec(
    shell_cmd: str,
    *,
    service_id: str = DEFAULT_SERVICE_ID,
    env_id: str = DEFAULT_ENV_ID,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    esc = shell_cmd.replace('"', '\\"')
    cmd = (
        f"npx zeabur@latest -i=false service exec "
        f'--id {service_id} --env-id {env_id} -- sh -lc "{esc}"'
    )
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def wait_remote(
    *,
    output_dir: str,
    expected_tick_count: int = 6,
    poll_seconds: float = 45.0,
    max_polls: int = 40,
    initial_sleep_seconds: float = 0.0,
    service_id: str = DEFAULT_SERVICE_ID,
    env_id: str = DEFAULT_ENV_ID,
    log_path: str | Path | None = None,
) -> Dict[str, Any]:
    log_file = Path(log_path) if log_path else None

    def _log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
        print(line, flush=True)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    if initial_sleep_seconds > 0:
        _log(f"WAIT_START sleep {initial_sleep_seconds}s")
        time.sleep(initial_sleep_seconds)

    last: Dict[str, Any] = {"status": STATUS_TIMEOUT}
    poll_cmd = build_summary_poll_command(output_dir)
    for i in range(max(1, int(max_polls))):
        r = zeabur_exec(poll_cmd, service_id=service_id, env_id=env_id)
        text = (r.stdout or "") + (r.stderr or "")
        _log(f"POLL{i} {text.replace(chr(10), ' | ')[:2000]}")
        data = extract_json_object(text)
        present = data is not None and "MISSING" not in text.split("POLL", 1)[0]
        if "MISSING" in text and data is None:
            present = False
        evaluated = evaluate_wait_status(
            snapshot=data,
            expected_tick_count=expected_tick_count,
            summary_present=present,
        )
        last = evaluated
        if evaluated["status"] in {STATUS_COMPLETED, STATUS_COMPLETED_NEEDS_FINALIZE}:
            _log(f"DONE status={evaluated['status']}")
            return evaluated
        time.sleep(max(0.0, float(poll_seconds)))

    last["status"] = STATUS_TIMEOUT
    last["action"] = "timeout_no_tick_progress"
    last["stage_419_triggered"] = False
    last["trading_state_mutated"] = False
    _log("TIMEOUT")
    return last


def main() -> int:
    ap = argparse.ArgumentParser(description="Wait for Stage 4 cloud dry-run completion (robust)")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--expected-tick-count", type=int, default=6)
    ap.add_argument("--poll-seconds", type=float, default=45.0)
    ap.add_argument("--max-polls", type=int, default=40)
    ap.add_argument("--initial-sleep-seconds", type=float, default=0.0)
    ap.add_argument("--local", action="store_true", help="Poll local filesystem instead of Zeabur")
    ap.add_argument("--log-path", default="")
    args = ap.parse_args()

    if args.local:
        result = wait_local(
            output_dir=args.output_dir,
            expected_tick_count=args.expected_tick_count,
            poll_seconds=args.poll_seconds,
            max_polls=args.max_polls,
            initial_sleep_seconds=args.initial_sleep_seconds,
        )
    else:
        result = wait_remote(
            output_dir=args.output_dir,
            expected_tick_count=args.expected_tick_count,
            poll_seconds=args.poll_seconds,
            max_polls=args.max_polls,
            initial_sleep_seconds=args.initial_sleep_seconds,
            log_path=args.log_path or None,
        )
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") in {STATUS_COMPLETED, STATUS_COMPLETED_NEEDS_FINALIZE}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

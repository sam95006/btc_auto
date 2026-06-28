#!/usr/bin/env python3
"""Stage 4 AI Decision Layer — local dry-run loop (no orders)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_client import BybitDemoClient  # noqa: E402
from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_ai_decision_agent import (  # noqa: E402
    MOCK_MODEL_NAME,
    Stage4AIDecisionAgent,
    resolve_stage4_output_dir,
    write_decision,
)
from tools.research.stage4_llm_client import (  # noqa: E402
    RealLLMRequiredError,
    mock_fallback_allowed,
    real_llm_preflight,
    require_real_llm_enabled,
)

READINESS = ROOT / "data/external_alpha/reports/stage4_ai_decision_dry_run_readiness.json"


@contextmanager
def _stage4_output_dir_env(output_dir: Optional[Path]) -> Iterator[Optional[Path]]:
    """Sync --output-dir to STAGE4_OUTPUT_DIR for LLM debug + default path resolution."""
    if output_dir is None:
        yield None
        return
    resolved = output_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    previous = os.environ.get("STAGE4_OUTPUT_DIR")
    os.environ["STAGE4_OUTPUT_DIR"] = str(resolved)
    try:
        yield resolved
    finally:
        if previous is None:
            os.environ.pop("STAGE4_OUTPUT_DIR", None)
        else:
            os.environ["STAGE4_OUTPUT_DIR"] = previous


def _resolve_run_log_path(output_dir: Path, duration_minutes: float) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    name = "stage4_30m_dry_run.log" if duration_minutes >= 5 else "stage4_short_run.log"
    return output_dir / name


def _append_run_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{utc_now_iso()} {message}\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _write_fail_summary(
    out: Path,
    *,
    failed_reason: str,
    duration_minutes: float,
    poll_interval_seconds: float,
    symbols: List[str],
    mode: str,
    use_real_llm: bool,
    log_path: Path | None = None,
) -> Dict[str, Any]:
    log_path = log_path or _resolve_run_log_path(out, duration_minutes)
    summary = {
        "record_type": "stage4_ai_decision_summary",
        "generated_at_utc": utc_now_iso(),
        "phase": "4",
        "mode": mode,
        "duration_minutes": duration_minutes,
        "poll_interval_seconds": poll_interval_seconds,
        "symbols": symbols,
        "dry_run_completed": False,
        "failed_reason": failed_reason,
        "real_llm_required": require_real_llm_enabled(),
        "mock_fallback_allowed": mock_fallback_allowed(use_real_llm=use_real_llm),
        "decision_count": 0,
        "real_llm_used_count": 0,
        "mock_ai_used_count": 0,
        "tick_count": 0,
        "output_dir": str(out),
        "model_name": None,
        "is_mock_ai": False,
        "real_llm_used": False,
        "fallback_to_mock": False,
        "all_order_sent_false": True,
        "order_sent_count": 0,
        "provider_health_check_passed": False,
        "run_log_path": str(log_path),
        "decisions": [],
    }
    write_json(out / "stage4_ai_decision_summary.json", summary)
    _append_run_log(
        log_path,
        f"FAIL reason={failed_reason} real_llm_required={summary['real_llm_required']} "
        f"mock_fallback_allowed={summary['mock_fallback_allowed']} order_sent_count=0",
    )
    return summary


def preflight_real_llm(
    *,
    use_real_llm: bool,
    output_dir: Path | None = None,
    duration_minutes: float = 0.0,
    poll_interval_seconds: float = 0.0,
    symbols: List[str] | None = None,
    mode: str = "dry_run",
    write_fail: bool = True,
) -> tuple[bool, str, Dict[str, Any] | None]:
    symbols = symbols or []
    with _stage4_output_dir_env(output_dir) as synced:
        out = synced or resolve_stage4_output_dir()
        ok, reason = real_llm_preflight(use_real_llm=use_real_llm)
        if ok:
            return True, "", None
        summary = None
        if write_fail:
            summary = _write_fail_summary(
                out,
                failed_reason=reason,
                duration_minutes=duration_minutes,
                poll_interval_seconds=poll_interval_seconds,
                symbols=symbols,
                mode=mode,
                use_real_llm=use_real_llm,
            )
        return False, reason, summary


def _fetch_market(symbol: str) -> Dict[str, Any]:
    from tools.research.stage4_market_context import build_market_context

    try:
        client = BybitDemoClient("dry-run", allow_demo_order=False)
        return build_market_context(symbol, client=client)
    except Exception as exc:
        from tools.research.stage4_market_context import _empty_context

        ctx = _empty_context(symbol.upper(), limitations=[f"fetch_error:{str(exc)[:80]}"])
        return ctx


def _fetch_account() -> Dict[str, Any]:
    try:
        client = BybitDemoClient("dry-run", allow_demo_order=False)
        snap = client.get_account_balance()
        return {
            "total_equity": snap.get("total_equity"),
            "available_balance": snap.get("available_balance"),
            "wallet_balance": snap.get("wallet_balance"),
            "balance_read_ok": bool(snap.get("balance_read_ok")),
            "open_positions": client.count_open_positions(),
        }
    except Exception as exc:
        return {
            "total_equity": 5000.0,
            "available_balance": 5000.0,
            "wallet_balance": 5000.0,
            "balance_read_ok": True,
            "open_positions": 0,
            "fallback": True,
            "error": str(exc)[:120],
        }


def run_dry_run(
    *,
    duration_minutes: float,
    poll_interval_seconds: float,
    symbols: List[str],
    mode: str = "dry_run",
    output_dir: Path | None = None,
    use_real_llm: bool = False,
) -> Dict[str, Any]:
    with _stage4_output_dir_env(output_dir) as synced:
        out = synced or resolve_stage4_output_dir()
        return _run_dry_run_inner(
            duration_minutes=duration_minutes,
            poll_interval_seconds=poll_interval_seconds,
            symbols=symbols,
            mode=mode,
            output_dir=out,
            use_real_llm=use_real_llm,
        )


def _run_dry_run_inner(
    *,
    duration_minutes: float,
    poll_interval_seconds: float,
    symbols: List[str],
    mode: str,
    output_dir: Path,
    use_real_llm: bool,
) -> Dict[str, Any]:
    out = output_dir
    log_path = _resolve_run_log_path(out, duration_minutes)

    ok, reason, fail_summary = preflight_real_llm(
        use_real_llm=use_real_llm,
        output_dir=out,
        duration_minutes=duration_minutes,
        poll_interval_seconds=poll_interval_seconds,
        symbols=symbols,
        mode=mode,
        write_fail=True,
    )
    if not ok:
        return fail_summary or _write_fail_summary(
            out,
            failed_reason=reason,
            duration_minutes=duration_minutes,
            poll_interval_seconds=poll_interval_seconds,
            symbols=symbols,
            mode=mode,
            use_real_llm=use_real_llm,
            log_path=log_path,
        )

    provider_health_check_passed: bool | None = None
    if use_real_llm and require_real_llm_enabled():
        from tools.research.check_stage4_llm_provider import run_health_check

        provider = os.environ.get("STAGE4_LLM_PROVIDER", "groq").strip().lower() or "groq"
        model = os.environ.get("STAGE4_LLM_MODEL", "llama-3.3-70b-versatile").strip()
        health = run_health_check(provider=provider, model=model)
        provider_health_check_passed = bool(health.get("provider_health_check_passed"))
        if not provider_health_check_passed:
            failed = str(health.get("error") or "provider_health_check_failed")
            return _write_fail_summary(
                out,
                failed_reason=failed,
                duration_minutes=duration_minutes,
                poll_interval_seconds=poll_interval_seconds,
                symbols=symbols,
                mode=mode,
                use_real_llm=use_real_llm,
                log_path=log_path,
            )

    try:
        agent = Stage4AIDecisionAgent(use_real_llm=use_real_llm)
    except RealLLMRequiredError as exc:
        return _write_fail_summary(
            out,
            failed_reason=exc.reason,
            duration_minutes=duration_minutes,
            poll_interval_seconds=poll_interval_seconds,
            symbols=symbols,
            mode=mode,
            use_real_llm=use_real_llm,
            log_path=log_path,
        )

    if use_real_llm and not mock_fallback_allowed(use_real_llm=True) and (
        agent.fallback_to_mock or agent.is_mock_ai or agent.model_name == MOCK_MODEL_NAME
    ):
        return _write_fail_summary(
            out,
            failed_reason="mock_fallback_blocked",
            duration_minutes=duration_minutes,
            poll_interval_seconds=poll_interval_seconds,
            symbols=symbols,
            mode=mode,
            use_real_llm=use_real_llm,
            log_path=log_path,
        )

    _append_run_log(
        log_path,
        f"START mode={mode} duration_minutes={duration_minutes} symbols={','.join(symbols)} "
        f"use_real_llm={use_real_llm} model={agent.model_name}",
    )
    started = time.time()
    end = started + duration_minutes * 60.0
    decisions: List[Dict[str, Any]] = []
    tick = 0

    while time.time() < end:
        tick += 1
        account = _fetch_account()
        open_positions = int(account.get("open_positions") or 0)
        for symbol in symbols:
            market = _fetch_market(symbol)
            decision = agent.decide(
                symbol=symbol,
                mode=mode,
                market_context=market,
                account_context=account,
                open_positions=open_positions,
            )
            write_decision(out, decision)
            decisions.append(decision)
            _append_run_log(
                log_path,
                f"TICK={tick} symbol={decision.get('symbol')} final={decision.get('final_decision')} "
                f"parse_error={decision.get('parse_error')} order_sent={decision.get('order_sent')}",
            )
        if duration_minutes <= 0.05:
            break
        if time.time() >= end:
            break
        time.sleep(poll_interval_seconds)

    summary = {
        "record_type": "stage4_ai_decision_summary",
        "generated_at_utc": utc_now_iso(),
        "phase": "4",
        "mode": mode,
        "duration_minutes": duration_minutes,
        "poll_interval_seconds": poll_interval_seconds,
        "symbols": symbols,
        "dry_run_completed": True,
        "decision_count": len(decisions),
        "real_llm_used_count": sum(1 for d in decisions if d.get("real_llm_used")),
        "mock_ai_used_count": sum(1 for d in decisions if d.get("is_mock_ai")),
        "tick_count": tick,
        "output_dir": str(out),
        "model_name": agent.model_name,
        "is_mock_ai": agent.is_mock_ai,
        "real_llm_used": agent.real_llm_used,
        "fallback_to_mock": agent.fallback_to_mock,
        "all_order_sent_false": all(not d.get("order_sent") for d in decisions),
        "order_sent_count": sum(1 for d in decisions if d.get("order_sent")),
        "provider_health_check_passed": provider_health_check_passed,
        "run_log_path": str(log_path),
        "decisions": [{"decision_id": d["decision_id"], "symbol": d["symbol"], "final_decision": d["final_decision"]} for d in decisions],
    }
    write_json(out / "stage4_ai_decision_summary.json", summary)
    _append_run_log(
        log_path,
        f"END decision_count={len(decisions)} tick_count={tick} all_order_sent_false={summary['all_order_sent_false']}",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 AI decision dry-run (no orders)")
    parser.add_argument("--duration-minutes", type=float, default=30.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=60.0)
    parser.add_argument("--symbols", default="ETHUSDT,BTCUSDT")
    parser.add_argument("--mode", default="dry_run")
    parser.add_argument("--fast-test", action="store_true", help="Single tick, no sleep")
    parser.add_argument("--use-real-llm", action="store_true")
    parser.add_argument("--preflight-only", action="store_true", help="Real LLM preflight; write fail summary and exit")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    out = Path(args.output_dir) if args.output_dir else None
    duration = 0.01 if args.fast_test else args.duration_minutes
    poll = 0.0 if args.fast_test else args.poll_interval_seconds

    if args.preflight_only:
        ok, reason, summary = preflight_real_llm(
            use_real_llm=args.use_real_llm,
            output_dir=out,
            duration_minutes=duration,
            poll_interval_seconds=max(0.0, poll),
            symbols=symbols,
            mode=args.mode,
            write_fail=True,
        )
        payload = {"preflight_passed": ok, "failed_reason": reason or None, "summary": summary}
        print(json.dumps(payload, indent=2))
        return 0 if ok else 1

    summary = run_dry_run(
        duration_minutes=duration,
        poll_interval_seconds=max(0.0, poll),
        symbols=symbols,
        mode=args.mode,
        output_dir=out,
        use_real_llm=args.use_real_llm,
    )

    from tools.research.validate_stage4_ai_decision_outputs import validate  # noqa: E402

    validation = validate(out or resolve_stage4_output_dir())
    write_json(
        READINESS,
        {
            "record_type": "stage4_ai_decision_dry_run_readiness",
            "generated_at_utc": utc_now_iso(),
            "summary": summary,
            "validation": validation,
        },
    )
    print(json.dumps({"summary": summary, "validation": validation}, indent=2))
    return 0 if validation.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

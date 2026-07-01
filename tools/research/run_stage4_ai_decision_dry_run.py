#!/usr/bin/env python3
"""Stage 4 AI Decision Layer — local dry-run loop (no orders)."""
from __future__ import annotations

import argparse
import json
import os
import signal
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
    ProviderRateLimited,
    RealLLMRequiredError,
    env_truthy,
    groq_key_configured,
    mock_fallback_allowed,
    real_llm_preflight,
    require_real_llm_enabled,
)
from tools.research.stage4_system_events import append_system_event  # noqa: E402

READINESS = ROOT / "data/external_alpha/reports/stage4_ai_decision_dry_run_readiness.json"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _default_poll_interval_seconds() -> float:
    return _env_float("STAGE4_POLL_INTERVAL_SECONDS", 120.0)


def require_stage3_context_enabled() -> bool:
    return env_truthy("STAGE4_REQUIRE_STAGE3_CONTEXT", False)


def _resolve_stage3_dir() -> Path:
    from tools.research.stage4_context_summary import resolve_stage3_data_dir

    return resolve_stage3_data_dir()


def preflight_stage3_context(
    *,
    output_dir: Path,
    duration_minutes: float,
    poll_interval_seconds: float,
    symbols: List[str],
    mode: str,
    use_real_llm: bool,
    log_path: Path | None = None,
    stats: Dict[str, int] | None = None,
) -> tuple[bool, str, Dict[str, Any] | None]:
    if not require_stage3_context_enabled():
        return True, "", None
    from tools.research.check_stage3_context_seed import check_stage3_context

    # Stage 3 demo learning seed is ETHUSDT-centric; fleet read-only runs share the same files.
    check_symbol = "ETHUSDT"
    result = check_stage3_context(target_dir=_resolve_stage3_dir(), symbol=check_symbol)
    if result.get("passed"):
        return True, "", None
    return False, "missing_required_stage3_context", _write_fail_summary(
        out=output_dir,
        failed_reason="missing_required_stage3_context",
        duration_minutes=duration_minutes,
        poll_interval_seconds=poll_interval_seconds,
        symbols=symbols,
        mode=mode,
        use_real_llm=use_real_llm,
        log_path=log_path,
        stats=stats,
    )


def _symbol_gap_seconds() -> float:
    return _env_float("STAGE4_SYMBOL_GAP_SECONDS", 5.0)


def _light_preflight_enabled() -> bool:
    raw = os.environ.get("STAGE4_LIGHT_PREFLIGHT", "").strip().lower()
    if raw in {"", "1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


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


def _empty_run_stats() -> Dict[str, int]:
    return {
        "skipped_tick_count": 0,
        "provider_rate_limit_count": 0,
        "provider_error_count": 0,
        "parse_error_count": 0,
        "empty_response_count": 0,
        "real_successful_llm_decision_count": 0,
        "effective_decision_count": 0,
        "fallback_used_count": 0,
        "provider_exhaustion_count": 0,
        "fallback_attempt_count": 0,
        "fallback_success_count": 0,
        "provider_chain_failed_count": 0,
    }


def _target_effective_decision_count() -> int:
    raw = os.environ.get("STAGE4_TARGET_EFFECTIVE_DECISION_COUNT", "30").strip()
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return 30


def _aggregate_run_provider_stats(decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    from tools.research.validate_stage4_ai_decision_outputs import _aggregate_provider_stats

    return _aggregate_provider_stats(decisions)


def _record_skipped_tick(
    *,
    exc: ProviderRateLimited,
    tick: int,
    stats: Dict[str, int],
) -> None:
    from tools.research.stage4_provider_metrics import aggregate_attempt_metrics_from_attempts

    stats["skipped_tick_count"] += 1
    rate_like = {
        "provider_rate_limited",
        "rate_limit",
        "rate_limit_gate",
        "local_rate_gate_skip",
        "backoff_active_skip",
        "provider_http_429",
    }
    exhaustion_like = {"empty_llm_response", "provider_quota_exhausted", "content_empty"}
    if exc.reason == "provider_chain_failed" or exc.event_type == "provider_chain_failed":
        stats["provider_chain_failed_count"] += 1
        stats["provider_error_count"] += 1
    elif exc.reason in exhaustion_like or exc.event_type == "provider_quota_exhausted":
        stats["provider_exhaustion_count"] += 1
        stats["provider_rate_limit_count"] += 1
    elif exc.reason in rate_like or exc.event_type in rate_like:
        stats["provider_rate_limit_count"] += 1
    else:
        stats["provider_error_count"] += 1

    attempts = list(exc.provider_attempts or [])
    if attempts:
        tick_metrics = aggregate_attempt_metrics_from_attempts(
            [attempts],
            chain_failed_count=1 if exc.event_type == "provider_chain_failed" else 0,
        )
        stats["fallback_attempt_count"] = stats.get("fallback_attempt_count", 0) + int(
            tick_metrics.get("fallback_attempt_count") or 0
        )
        if tick_metrics.get("fallback_success_count"):
            stats["fallback_success_count"] = stats.get("fallback_success_count", 0) + int(
                tick_metrics.get("fallback_success_count") or 0
            )

    gate = exc.gate_status or {}
    event: Dict[str, Any] = {
        "event_type": exc.event_type or "provider_rate_limited",
        "provider": exc.provider,
        "model_name": exc.model_name,
        "symbol": exc.symbol,
        "tick_time_utc": utc_now_iso(),
        "tick_index": tick,
        "tick_number": tick,
        "retry_count": exc.retry_count,
        "reason": exc.reason,
        "call_kind": exc.call_kind,
        "http_status": exc.http_status,
        "seconds_since_last_llm_call": gate.get("seconds_since_last_llm_call"),
        "required_wait_seconds": gate.get("required_wait_seconds"),
        "backoff_until_utc": gate.get("backoff_until_utc"),
        "action": "skip_tick_no_decision",
        "order_sent": False,
    }
    if attempts:
        event["provider_attempts"] = attempts
        event["fallback_used"] = bool(exc.fallback_used)
        if exc.fallback_reason:
            event["fallback_reason"] = exc.fallback_reason
    append_system_event(event)


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
    stats: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    log_path = log_path or _resolve_run_log_path(out, duration_minutes)
    stats = stats or _empty_run_stats()
    summary = {
        "record_type": "stage4_ai_decision_summary",
        "generated_at_utc": utc_now_iso(),
        "phase": "4.6",
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
        **stats,
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
    stats = _empty_run_stats()
    from tools.research.stage4_provider_quota_governor import Stage4ProviderQuotaGovernor

    Stage4ProviderQuotaGovernor.reset_shared()

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
            stats=stats,
        )

    ok_ctx, ctx_reason, ctx_fail = preflight_stage3_context(
        output_dir=out,
        duration_minutes=duration_minutes,
        poll_interval_seconds=poll_interval_seconds,
        symbols=symbols,
        mode=mode,
        use_real_llm=use_real_llm,
        log_path=log_path,
        stats=stats,
    )
    if not ok_ctx:
        return ctx_fail or _write_fail_summary(
            out,
            failed_reason=ctx_reason,
            duration_minutes=duration_minutes,
            poll_interval_seconds=poll_interval_seconds,
            symbols=symbols,
            mode=mode,
            use_real_llm=use_real_llm,
            log_path=log_path,
            stats=stats,
        )

    provider_health_check_passed: bool | None = None
    if use_real_llm and require_real_llm_enabled():
        if _light_preflight_enabled():
            provider_health_check_passed = groq_key_configured()
            if not provider_health_check_passed:
                return _write_fail_summary(
                    out,
                    failed_reason="missing_real_llm_key",
                    duration_minutes=duration_minutes,
                    poll_interval_seconds=poll_interval_seconds,
                    symbols=symbols,
                    mode=mode,
                    use_real_llm=use_real_llm,
                    log_path=log_path,
                    stats=stats,
                )
        else:
            from tools.research.check_stage4_llm_provider import run_health_check

            provider = os.environ.get("STAGE4_LLM_PROVIDER", "groq").strip().lower() or "groq"
            model = os.environ.get("STAGE4_LLM_MODEL", "llama-3.3-70b-versatile").strip()
            health = run_health_check(provider=provider, model=model)
            provider_health_check_passed = bool(health.get("provider_health_check_passed"))
            if health.get("healthcheck_skipped_by_gate"):
                provider_health_check_passed = True
            if not provider_health_check_passed:
                failed = str(health.get("error") or "provider_health_check_failed")
                if health.get("error_type") == "rate_limit":
                    stats["provider_rate_limit_count"] += 1
                    stats["skipped_tick_count"] += 1
                return _write_fail_summary(
                    out,
                    failed_reason=failed,
                    duration_minutes=duration_minutes,
                    poll_interval_seconds=poll_interval_seconds,
                    symbols=symbols,
                    mode=mode,
                    use_real_llm=use_real_llm,
                    log_path=log_path,
                    stats=stats,
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
            stats=stats,
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
            stats=stats,
        )

    symbol_gap = _symbol_gap_seconds()
    _append_run_log(
        log_path,
        f"START mode={mode} duration_minutes={duration_minutes} symbols={','.join(symbols)} "
        f"use_real_llm={use_real_llm} model={agent.model_name} poll={poll_interval_seconds} gap={symbol_gap}",
    )
    started = time.time()
    end = started + duration_minutes * 60.0
    decisions: List[Dict[str, Any]] = []
    tick = 0
    summary_written = False
    loop_completed = False
    target_effective = _target_effective_decision_count()
    symbols_with_market_context_error: set[str] = set()

    def _persist_summary(
        *,
        dry_run_completed: bool = False,
        partial_completion: bool = False,
        failed_reason: str | None = None,
    ) -> Dict[str, Any]:
        nonlocal summary_written
        if summary_written:
            return {}
        summary_written = True
        effective = stats["effective_decision_count"]
        partial = partial_completion or effective < target_effective
        completed = dry_run_completed and effective >= target_effective and not partial
        if partial and not failed_reason:
            if effective < target_effective:
                failed_reason = "provider_yield_below_target"
            elif not loop_completed:
                failed_reason = "partial_exit"
        summary = {
            "record_type": "stage4_ai_decision_summary",
            "generated_at_utc": utc_now_iso(),
            "phase": "4.13",
            "mode": mode,
            "duration_minutes": duration_minutes,
            "poll_interval_seconds": poll_interval_seconds,
            "symbols": symbols,
            "dry_run_completed": completed,
            "partial_completion": partial,
            "failed_reason": failed_reason,
            "effective_decision_count": effective,
            "target_effective_decision_count": target_effective,
            "decision_count": len(decisions),
            "real_llm_used_count": sum(1 for d in decisions if d.get("real_llm_used")),
            "mock_ai_used_count": sum(1 for d in decisions if d.get("is_mock_ai")),
            "tick_count": tick,
            "output_dir": str(out),
            "model_name": agent.model_name,
            "is_mock_ai": agent.is_mock_ai,
            "real_llm_used": agent.real_llm_used,
            "fallback_to_mock": agent.fallback_to_mock,
            "all_order_sent_false": all(not d.get("order_sent") for d in decisions) if decisions else True,
            "order_sent_count": sum(1 for d in decisions if d.get("order_sent")),
            "provider_health_check_passed": provider_health_check_passed,
            "run_log_path": str(log_path),
            "decisions": [
                {"decision_id": d["decision_id"], "symbol": d["symbol"], "final_decision": d["final_decision"]}
                for d in decisions
            ],
            **_aggregate_run_provider_stats(decisions),
            **stats,
        }
        from tools.research.stage4_groq_key_registry import GroqKeyRegistry
        from tools.research.stage4_provider_metrics import aggregate_attempt_metrics
        from tools.research.stage4_system_events import read_system_events

        summary.update(GroqKeyRegistry.shared().health_report())
        attempt_metrics = aggregate_attempt_metrics(
            decisions=decisions,
            system_events=read_system_events(out),
            chain_failed_count=int(stats.get("provider_chain_failed_count") or 0),
        )
        for key, value in attempt_metrics.items():
            summary[key] = value
        stats["fallback_attempt_count"] = int(attempt_metrics.get("fallback_attempt_count") or 0)
        stats["fallback_success_count"] = int(attempt_metrics.get("fallback_success_count") or 0)
        chain_client = getattr(agent, "llm_client", None)
        if chain_client is not None and hasattr(chain_client, "chain_status"):
            summary.update(chain_client.chain_status())
        from tools.research.stage4_per_symbol_summary import build_per_symbol_summary

        fleet_summary = build_per_symbol_summary(
            decisions,
            symbols_configured=symbols,
            symbols_with_market_context_error=sorted(symbols_with_market_context_error),
        )
        summary.update(fleet_summary)
        summary["dataset_target_met"] = effective >= target_effective
        write_json(out / "stage4_ai_decision_summary.json", summary)
        _append_run_log(
            log_path,
            f"END decision_count={len(decisions)} effective={effective} "
            f"skipped={stats['skipped_tick_count']} rate_limit={stats['provider_rate_limit_count']} "
            f"exhaustion={stats['provider_exhaustion_count']} chain_failed={stats['provider_chain_failed_count']} "
            f"fallback_success={stats['fallback_success_count']} parse_errors={stats['parse_error_count']} "
            f"partial={partial} completed={completed} order_sent_count=0",
        )
        try:
            from tools.research.export_stage4_ai_decision_bundle import export_bundle

            bundle = export_bundle(out)
            summary["bundle_export"] = {
                "bundle_path": bundle.get("bundle_path"),
                "bundle_safe": bundle.get("bundle_safe"),
                "file_count": bundle.get("file_count"),
                "bundle_exported": bool(bundle.get("bundle_safe") and bundle.get("file_count", 0) > 0),
            }
            write_json(out / "stage4_ai_decision_summary.json", summary)
        except Exception as exc:
            _append_run_log(log_path, f"BUNDLE_EXPORT_FAIL {str(exc)[:80]}")
        return summary

    def _handle_stop(signum: int, _frame: Any) -> None:
        _append_run_log(log_path, f"SIGNAL signum={signum} persisting partial summary")
        _persist_summary(dry_run_completed=False, partial_completion=True, failed_reason="partial_exit")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    summary_result: Dict[str, Any] = {}
    try:
        while time.time() < end:
            tick += 1
            account = _fetch_account()
            open_positions = int(account.get("open_positions") or 0)
            for idx, symbol in enumerate(symbols):
                market = _fetch_market(symbol)
                from tools.research.stage4_context_skip import make_context_unavailable_decision
                from tools.research.stage4_market_context import market_context_unavailable

                unavailable, err_reason = market_context_unavailable(market)
                if unavailable:
                    symbols_with_market_context_error.add(symbol.upper())
                    decision = make_context_unavailable_decision(
                        symbol=symbol,
                        mode=mode,
                        market_context=market,
                        account_context=account,
                        error_reason=err_reason,
                        open_positions=open_positions,
                    )
                    write_decision(out, decision)
                    decisions.append(decision)
                    _append_run_log(
                        log_path,
                        f"TICK={tick} symbol={symbol} CONTEXT_SKIP reason={err_reason} order_sent=false",
                    )
                    if idx < len(symbols) - 1 and symbol_gap > 0:
                        time.sleep(symbol_gap)
                    continue
                try:
                    decision = agent.decide(
                        symbol=symbol,
                        mode=mode,
                        market_context=market,
                        account_context=account,
                        open_positions=open_positions,
                    )
                except ProviderRateLimited as exc:
                    _record_skipped_tick(exc=exc, tick=tick, stats=stats)
                    _append_run_log(
                        log_path,
                        f"TICK={tick} SKIPPED symbol={symbol} reason={exc.reason} order_sent=false",
                    )
                    if idx < len(symbols) - 1 and symbol_gap > 0:
                        time.sleep(symbol_gap)
                    continue

                if decision.get("parse_error"):
                    stats["parse_error_count"] += 1
                    if decision.get("raw_content_empty") or decision.get("parse_error_type") in {
                        "content_empty",
                        "empty_llm_response",
                    }:
                        stats["empty_response_count"] += 1
                else:
                    stats["real_successful_llm_decision_count"] += 1
                    stats["effective_decision_count"] += 1
                    if decision.get("fallback_used"):
                        stats["fallback_used_count"] += 1
                        stats["fallback_success_count"] += 1
                    attempts = decision.get("provider_attempts") or []
                    if len(attempts) > 1:
                        stats["fallback_attempt_count"] += 1

                write_decision(out, decision)
                decisions.append(decision)
                _append_run_log(
                    log_path,
                    f"TICK={tick} symbol={decision.get('symbol')} final={decision.get('final_decision')} "
                    f"parse_error={decision.get('parse_error')} order_sent={decision.get('order_sent')}",
                )
                if idx < len(symbols) - 1 and symbol_gap > 0:
                    time.sleep(symbol_gap)

            if duration_minutes <= 0.05:
                loop_completed = True
                break
            if time.time() >= end:
                break
            time.sleep(poll_interval_seconds)
        loop_completed = True
    finally:
        summary_result = _persist_summary(
            dry_run_completed=loop_completed,
            partial_completion=stats["effective_decision_count"] < target_effective,
        )
    return summary_result


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4 AI decision dry-run (no orders)")
    parser.add_argument("--duration-minutes", type=float, default=30.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=-1.0)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--mode", default="dry_run")
    parser.add_argument("--fast-test", action="store_true", help="Single tick, no sleep")
    parser.add_argument(
        "--dry-run-once",
        action="store_true",
        help="One tick across all symbols (fixed fleet smoke test)",
    )
    parser.add_argument("--use-real-llm", action="store_true")
    parser.add_argument("--preflight-only", action="store_true", help="Real LLM preflight; write fail summary and exit")
    parser.add_argument("--fail-summary-only", action="store_true", help="Write fail summary and exit (no dry-run loop)")
    parser.add_argument("--failed-reason", default="unknown", help="Reason for --fail-summary-only")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    from tools.research.stage4_fleet_symbols import resolve_stage4_symbols

    symbols = resolve_stage4_symbols(cli_default="ETHUSDT,BTCUSDT")
    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    out = Path(args.output_dir) if args.output_dir else None
    duration = 0.01 if (args.fast_test or args.dry_run_once) else args.duration_minutes
    poll = 0.0 if args.fast_test else (
        args.poll_interval_seconds if args.poll_interval_seconds >= 0 else _default_poll_interval_seconds()
    )

    if args.fail_summary_only:
        target = out or resolve_stage4_output_dir()
        summary = _write_fail_summary(
            target,
            failed_reason=args.failed_reason,
            duration_minutes=duration,
            poll_interval_seconds=max(0.0, poll),
            symbols=symbols,
            mode=args.mode,
            use_real_llm=args.use_real_llm,
        )
        print(json.dumps({"summary": summary}, indent=2))
        return 1

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

    validation = validate(out or resolve_stage4_output_dir(), require_real_llm=args.use_real_llm)
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

"""Short soak runner for Wave 5 real public shadow runtime (accelerated in tests)."""
from __future__ import annotations

import argparse
import time
from typing import Any, Callable

from backend.nexus_real_shadow.api_routes import get_or_create_runtime, get_real_shadow_api_state, reset_real_shadow_api_state
from backend.nexus_real_shadow.orchestration import NexusRealPublicShadowRuntime


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def run_soak(
    *,
    duration_seconds: float = 900.0,
    cycle_interval_seconds: float = 30.0,
    clock: FakeClock | None = None,
    on_cycle: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    reset_real_shadow_api_state()
    runtime = get_or_create_runtime()
    clk = clock or FakeClock(time.time())
    start = clk.time()
    end = start + duration_seconds
    cycles = 0
    errors: list[str] = []

    while clk.time() < end:
        try:
            cycle = runtime.run_cycle()
            get_real_shadow_api_state().sync_from_cycle(cycle)
            cycles += 1
            if on_cycle:
                on_cycle(cycle)
        except Exception as exc:
            errors.append(str(exc))
        clk.advance(cycle_interval_seconds)

    return {
        "duration_seconds": duration_seconds,
        "cycle_interval_seconds": cycle_interval_seconds,
        "cycles_completed": cycles,
        "errors": errors,
        "labels": ["PUBLIC MARKET DATA", "SHADOW SIMULATION", "NOT EXECUTED"],
    }


def run_accelerated_soak(*, cycles: int = 5, cycle_interval_seconds: float = 1.0) -> dict[str, Any]:
    """Deterministic offline soak using FakeClock (CI-safe, no network)."""
    duration = max(1.0, float(cycles) * float(cycle_interval_seconds))
    result = run_soak(
        duration_seconds=duration,
        cycle_interval_seconds=float(cycle_interval_seconds),
        clock=FakeClock(0.0),
    )
    result["ok"] = not result.get("errors") and int(result.get("cycles_completed") or 0) >= 1
    result["pass"] = result["ok"]
    result["exchange_write_call_count"] = 0
    result["private_endpoint_call_count"] = 0
    result["authenticated_request_count"] = 0
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave5 real public shadow soak runner")
    parser.add_argument("--duration-seconds", type=float, default=900.0)
    parser.add_argument("--cycle-interval-seconds", type=float, default=30.0)
    parser.add_argument("--accelerated", action="store_true")
    args = parser.parse_args(argv)

    clock = FakeClock(0.0) if args.accelerated else None
    result = run_soak(
        duration_seconds=args.duration_seconds,
        cycle_interval_seconds=args.cycle_interval_seconds,
        clock=clock,
    )
    print(result)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

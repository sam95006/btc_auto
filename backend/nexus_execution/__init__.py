"""NEXUS Execution Realism V1.1 package.

Founder-only Autonomous Execution Simulator components.

Execution mode invariant:
  SIMULATED_NO_EXCHANGE_WRITE

Every module in this package MUST refuse to instantiate an authenticated
exchange-write client. The `security_boundary` module publishes a global
counter which is expected to remain zero for the lifetime of any process
that imports this package under test or under readiness generation.

The `contracts` module defines the versioned execution contract shared
between Agent A (execution) and Agent B (session orchestration). Changes
to that contract require a new version file, never in-place mutation of
the current file's public dataclasses.
"""
from __future__ import annotations

from backend.nexus_execution.security_boundary import (  # noqa: F401
    EXECUTION_MODE,
    ExchangeWriteAttempted,
    assert_no_exchange_write,
    exchange_write_attempt_count,
    install_exchange_write_traps,
    record_exchange_write_attempt,
)
from backend.nexus_execution.orchestrator_adapter_v1 import (  # noqa: F401
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
    NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1,
    build_session_execution_adapter,
)

__all__ = [
    "EXECUTION_MODE",
    "ExchangeWriteAttempted",
    "assert_no_exchange_write",
    "exchange_write_attempt_count",
    "install_exchange_write_traps",
    "record_exchange_write_attempt",
    "ADAPTER_ID",
    "CANONICAL_EXECUTION_ENGINE",
    "CANONICAL_EXECUTION_ENGINE_COUNT",
    "NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1",
    "build_session_execution_adapter",
]

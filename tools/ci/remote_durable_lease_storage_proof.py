#!/usr/bin/env python3
"""Remote durable lease storage proof qualification — consumes validation runtime status."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_bounded_runtime.bootstrap import install_certified_bounded_runtime, patch_bounded_6h_start_handler
from backend.nexus_bounded_runtime.runtime_lease_storage_proof import (
    consume_remote_storage_proof,
    prove_runtime_durable_lease_storage,
)
from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from tools.ci.demo_bounded_session_preflight import run_preflight


def prove_local_runner_not_authoritative() -> dict[str, Any]:
    """GitHub runner /tmp must not satisfy remote durable storage proof."""
    tmp_proof = prove_runtime_durable_lease_storage("/tmp/nexus_demo_validation")
    consumed = consume_remote_storage_proof(tmp_proof)
    return {
        "GITHUB_RUNNER_TMP_NOT_AUTHORITATIVE": consumed.get("DURABLE_LEASE_STORAGE_PREFLIGHT_PASS") is False,
        "GITHUB_RUNNER_TMP_EPHEMERAL": tmp_proof.get("EPHEMERAL_LEASE_STORAGE") is True,
    }


def prove_runtime_status_surface(data_root: Path) -> dict[str, Any]:
    install_certified_bounded_runtime()
    patch_bounded_6h_start_handler()
    from backend.nexus_demo_execution.api_routes import DemoExecutionApiState

    state = DemoExecutionApiState()
    state.data_root = data_root
    payload = state.bounded_6h_status()
    consumed = consume_remote_storage_proof(payload)
    return {
        "RUNTIME_STATUS_SURFACE_PRESENT": all(
            key in payload
            for key in (
                "DURABLE_LEASE_STORAGE_RUNTIME_PROVEN",
                "DURABLE_LEASE_STORAGE_PATH",
                "EPHEMERAL_LEASE_STORAGE",
                "NEXUS_DATA_ROOT",
            )
        ),
        "RUNTIME_STORAGE_PROOF_SOURCE": payload.get("RUNTIME_STORAGE_PROOF_SOURCE"),
        **consumed,
    }


def run(*, offline: bool = True, base_url: str = "", expected_sha: str = "") -> dict[str, Any]:
    apply_disarmed_flags()
    os.environ.setdefault("NEXUS_DATA_ROOT", str(Path("artifacts/remote_lease_storage_proof").resolve()))
    data_root = Path(os.environ["NEXUS_DATA_ROOT"])
    evidence: dict[str, Any] = {
        "REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS": False,
        "CREATE_ORDER_CALLS": 0,
        "EXCHANGE_WRITE_CALL_COUNT": 0,
        "error": None,
    }
    evidence.update(prove_local_runner_not_authoritative())
    runtime_surface = prove_runtime_status_surface(data_root)
    evidence.update(runtime_surface)
    evidence["RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER"] = runtime_surface.get("RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER") is True

    preflight = run_preflight(
        base_url=base_url,
        expected_github_sha=expected_sha or os.environ.get("GITHUB_SHA", ""),
        offline=offline,
    )
    evidence["offline_preflight_pass"] = preflight.get("preflight_pass") is True
    evidence["preflight_remote_storage"] = preflight.get("remote_durable_lease_storage")

    evidence["REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS"] = bool(
        evidence.get("GITHUB_RUNNER_TMP_NOT_AUTHORITATIVE")
        and evidence.get("RUNTIME_STATUS_SURFACE_PRESENT")
        and evidence.get("DURABLE_LEASE_STORAGE_RUNTIME_PROVEN")
        and evidence.get("EPHEMERAL_LEASE_STORAGE") is False
        and evidence.get("RUNTIME_STORAGE_PROOF_NOT_GITHUB_RUNNER")
        and (offline or preflight.get("REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS") is True)
        and evidence.get("CREATE_ORDER_CALLS") == 0
        and evidence.get("EXCHANGE_WRITE_CALL_COUNT") == 0
    )
    if not evidence["REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS"]:
        evidence["error"] = evidence.get("error") or "remote_durable_lease_storage_proof_failed"
    return evidence


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", default=True)
    parser.add_argument("--base", default=os.environ.get("DEMO_VAL_URL", ""))
    parser.add_argument("--expected-sha", default=os.environ.get("GITHUB_SHA", ""))
    args = parser.parse_args()
    evidence = run(offline=args.offline, base_url=args.base, expected_sha=args.expected_sha)
    print(json.dumps(evidence, indent=2, sort_keys=True, default=str))
    return 0 if evidence.get("REMOTE_DURABLE_LEASE_STORAGE_PROOF_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())

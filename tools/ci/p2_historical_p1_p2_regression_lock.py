"""Historical P1→P2 offline regression lock — existing certified contracts only."""
from __future__ import annotations

# Immutable offline suite: do not invent new product behavior here.
HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES: tuple[str, ...] = (
    # P1 Run8 / recovery / transport
    "tests/test_p1_run8_atomic_recovery.py",
    "tests/test_p1_run8_postgres_accounting_recovery.py",
    "tests/test_p1_run8_rollout_convergence.py",
    "tests/test_p1_run8_posix_identity_probe.py",
    "tests/test_p1_run8_predispatch_static.py",
    "tests/test_p1_closed_at_timestamptz.py",
    "tests/test_p1_validation_runtime.py",
    "tests/test_p1_zeabur_transport.py",
    "tests/test_p1_staging_migration_0006.py",
    "tests/test_bybit_demo_durable_order_foundation.py",
    "tests/test_phase61b_durable_ledger.py",
    # P2 learning / evidence / qualification / migration
    "tests/test_p2_run8_learning_closure.py",
    "tests/test_p2_durable_learning_closure.py",
    "tests/test_p2_run8_evidence_truth.py",
    "tests/test_p2_1_postgres_qualification.py",
    "tests/test_p2_staging_migration_0007.py",
    "tests/test_p2_migration_atomic.py",
    "tests/test_p2_migration_service.py",
    "tests/test_p2_migration_file_channel_audit.py",
    "tests/test_p2_migration_rollout_readiness.py",
    "tests/test_p2_migration_bootstrap.py",
    "tests/test_p2_migration_deployment_diagnostics.py",
    "tests/test_p2_migration_image_contract.py",
    "tests/test_p2_certified_surface_freeze.py",
    "tests/test_p2_migration_operational_readiness_control.py",
    "tests/test_p2_migration_lifecycle_command.py",
    "tests/test_p2_migration_deployment_phase.py",
    "tests/test_p2_migration_deployment_discovery.py",
    "tests/test_p2_git_bound_migration_architecture.py",
    "tests/test_p2_durable_learning_closure_qualification.py",
    "tests/test_p2_zeabur_pinned_cli_contract.py",
)


def pytest_argv() -> list[str]:
    return ["-m", "pytest", *HISTORICAL_P1_P2_REGRESSION_LOCK_MODULES, "-q", "--tb=line"]


def main() -> int:
    import subprocess
    import sys

    cmd = [sys.executable, *pytest_argv()]
    print("HISTORICAL_P1_P2_REGRESSION_LOCK=RUNNING")
    print(" ".join(cmd))
    proc = subprocess.run(cmd, check=False)
    if proc.returncode == 0:
        print("HISTORICAL_P1_P2_REGRESSION_LOCK=PASS")
        return 0
    print("HISTORICAL_P1_P2_REGRESSION_LOCK=FAIL")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

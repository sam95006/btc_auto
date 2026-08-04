"""Private Core Security Boundary V1 — automated adversarial proofs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_autonomy.security_boundary_v1 import (  # noqa: E402
    evaluate_security_boundary,
    run_boundary,
    write_immutable_status,
)
from backend.nexus_autonomy.security_credential_boundary_v1 import (  # noqa: E402
    DEMO_ENV_KEY,
    DEMO_ENV_SECRET,
    MAINNET_ENV_KEY,
    MAINNET_ENV_SECRET,
    resolve_exchange_profile,
)
from backend.nexus_autonomy.security_exceptions_v1 import (  # noqa: E402
    CredentialBoundaryError,
    ExchangeWriteForbidden,
    NetworkEgressForbidden,
    PersistenceSecurityError,
    PublicPrivateBoundaryError,
)
from backend.nexus_autonomy.security_import_graph_v1 import (  # noqa: E402
    assert_import_graph_clean,
    build_import_graph,
    classify_module,
)
from backend.nexus_autonomy.security_network_traps_v1 import network_egress_traps  # noqa: E402
from backend.nexus_autonomy.security_persistence_v1 import (  # noqa: E402
    assert_ledger_event_safe,
    assert_safe_relative_path,
    assert_schema_migration_trusted,
    fail_closed_json_loads,
    run_persistence_security_self_test,
)
from backend.nexus_autonomy.security_public_private_v1 import (  # noqa: E402
    assert_public_schema,
    prove_lesson_not_publicly_serializable,
    prove_strategy_params_not_public,
    redact_account_identifiers,
)
from backend.nexus_autonomy.security_write_traps_v1 import (  # noqa: E402
    WriteTrapRegistry,
    exchange_write_traps,
)


ROOT = Path(__file__).resolve().parents[1]


def test_public_route_classification():
    assert classify_module("backend.api.market_public_routes") == "PUBLIC_ROUTE"
    assert classify_module("backend.nexus_demo_execution.demo_write_client") == "EXECUTION_WRITE"
    assert classify_module("backend.nexus_autonomy.execution_simulator_v1") == "SIMULATION"


def test_import_graph_public_cannot_import_execution_write():
    report = build_import_graph(root=ROOT)
    public_write = [
        v
        for v in report.violations
        if v.get("rule") == "public_route_imports_execution_write"
    ]
    assert public_write == []
    assert report.node_count > 0
    assert report.edge_count > 0


def test_import_graph_simulation_clean():
    report = build_import_graph(root=ROOT)
    sim_write = [v for v in report.violations if v.get("rule") == "simulation_imports_execution_write"]
    assert sim_write == []
    assert_import_graph_clean(root=ROOT)


def test_write_trap_create_order_forbidden():
    with exchange_write_traps() as counters:
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

        client = DemoWriteClient(api_key="k" * 16, api_secret="s" * 16)
        with pytest.raises(ExchangeWriteForbidden):
            client.create_market_order(
                symbol="BTCUSDT", side="Buy", qty="0.001", order_link_id="t1"
            )
        assert counters.exchange_write_attempt_count >= 1
        assert counters.order_write_attempt_count >= 1


def test_write_trap_cancel_and_leverage():
    registry = WriteTrapRegistry()
    counters = registry.install()
    try:
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

        client = DemoWriteClient(api_key="k" * 16, api_secret="s" * 16)
        with pytest.raises(ExchangeWriteForbidden):
            client.cancel_order(symbol="BTCUSDT", order_id="1")
        with pytest.raises(ExchangeWriteForbidden):
            client.set_leverage("BTCUSDT", 2)
        assert counters.order_write_attempt_count >= 1
        assert counters.position_mutation_attempt_count >= 1
    finally:
        registry.uninstall()


def test_withdrawal_and_transfer_traps():
    registry = WriteTrapRegistry()
    counters = registry.install()
    try:
        with pytest.raises(ExchangeWriteForbidden):
            registry.trap_callable("withdraw")()
        with pytest.raises(ExchangeWriteForbidden):
            registry.trap_callable("transfer")()
        assert counters.withdrawal_attempt_count == 1
        assert counters.transfer_attempt_count == 1
        assert "EXCHANGE_WRITE_FORBIDDEN" in str(ExchangeWriteForbidden("withdraw"))
    finally:
        registry.uninstall()


def test_missing_env_fail_closed():
    result = resolve_exchange_profile({}, requested_profile="demo")
    assert result.fail_closed is True
    assert result.ok is False
    assert result.writes_enabled is False
    assert "demo_credentials_missing" in result.reasons


def test_no_mainnet_credential_fallback():
    env = {
        MAINNET_ENV_KEY: "mainnetkey123456",
        MAINNET_ENV_SECRET: "mainnetsecret123456",
    }
    result = resolve_exchange_profile(env, requested_profile="demo")
    assert result.mainnet_fallback_used is True
    assert result.writes_enabled is False
    assert result.fail_closed is True


def test_demo_mainnet_cannot_be_confused():
    env = {
        DEMO_ENV_KEY: "demokey12345678",
        DEMO_ENV_SECRET: "demosecret123456",
    }
    result = resolve_exchange_profile(
        env, requested_profile="demo", base_url="https://api.bybit.com"
    )
    assert result.demo_mainnet_confused is True
    assert result.writes_enabled is False


def test_mainnet_profile_blocked():
    result = resolve_exchange_profile({}, requested_profile="mainnet")
    assert result.ok is False
    assert result.writes_enabled is False


def test_malformed_keys_cannot_enable_writes():
    env = {
        DEMO_ENV_KEY: "short",
        DEMO_ENV_SECRET: "short",
        "NEXUS_FOUNDER_EXCHANGE_WRITE": "true",
    }
    result = resolve_exchange_profile(
        env, requested_profile="demo", base_url="https://api-demo.bybit.com"
    )
    assert result.writes_enabled is False
    assert "malformed_credentials" in result.reasons


def test_public_readonly_requires_no_secret():
    result = resolve_exchange_profile({}, requested_profile="public_readonly")
    assert result.profile == "public_readonly"
    assert result.writes_enabled is False


def test_lesson_serialization_blocked_from_public():
    with pytest.raises(PublicPrivateBoundaryError):
        assert_public_schema(
            {
                "lesson_id": "L1",
                "process_classification": "BAD_PROCESS",
                "immediate_safe_actions": ["block"],
            },
            context="public",
        )
    prove_lesson_not_publicly_serializable()


def test_strategy_params_blocked_from_public():
    with pytest.raises(PublicPrivateBoundaryError):
        assert_public_schema({"strategy_parameters": {"entry_threshold": 1}}, context="public")
    prove_strategy_params_not_public()


def test_redaction_of_secrets_and_accounts():
    out = redact_account_identifiers(
        {"api_key": "ABC", "account_id": "9", "order_id": "O1", "symbol": "ETHUSDT"}
    )
    assert out["api_key"] == "***"
    assert out["account_id"] == "***"
    assert out["order_id"] == "***"
    assert out["symbol"] == "ETHUSDT"


def test_snapshot_path_traversal_blocked(tmp_path: Path):
    with pytest.raises(PersistenceSecurityError):
        assert_safe_relative_path("../secret.json", root=tmp_path)
    with pytest.raises(PersistenceSecurityError):
        assert_safe_relative_path("..\\windows\\system32", root=tmp_path)


def test_malicious_ledger_and_corrupt_schema():
    with pytest.raises(PersistenceSecurityError):
        fail_closed_json_loads("{bad")
    with pytest.raises(PersistenceSecurityError):
        assert_ledger_event_safe({"api_secret": "leakleakleakleak"})
    with pytest.raises(PersistenceSecurityError):
        assert_ledger_event_safe({"payload": {"raw_provider_response": "sk-test"}})
    with pytest.raises(PersistenceSecurityError):
        assert_schema_migration_trusted("drop_all", {"private_event_ledger_v1"})
    persistence = run_persistence_security_self_test(tmp_root=ROOT)
    assert persistence["passed"] is True
    assert persistence["secret_leak_count"] == 0


def test_network_egress_blocks_write_and_unexpected_domain():
    with network_egress_traps(allow_public_market=True, allow_demo_host=False) as counters:
        import urllib.request

        with pytest.raises(NetworkEgressForbidden):
            urllib.request.urlopen("https://api-demo.bybit.com/v5/order/create")
        with pytest.raises(NetworkEgressForbidden):
            urllib.request.urlopen("https://evil.example/x")
    assert counters.write_blocked_count >= 1
    assert counters.unexpected_domain_count >= 1


def test_secret_looking_value_in_evidence_fails():
    with pytest.raises(PersistenceSecurityError):
        assert_ledger_event_safe(
            {"type": "EVIDENCE", "note": "api_secret=supersecretvalue999"}
        )


def test_full_boundary_pass_and_immutable_artifact(tmp_path: Path):
    # Evaluate against real repo root for import graph; write artifact to tmp via monkeypatch path
    status = evaluate_security_boundary(root=ROOT)
    assert status["recommendation"] == "NEXUS_PRIVATE_SECURITY_BOUNDARY_V1_PASS"
    assert status["violations"]["exchange_write_attempt_count"] == 0
    assert status["violations"]["withdrawal_attempt_count"] == 0
    assert status["violations"]["transfer_attempt_count"] == 0
    assert status["violations"]["mainnet_client_created_count"] == 0
    assert status["violations"]["private_route_public_exposure_count"] == 0
    assert status["violations"]["private_lesson_public_exposure_count"] == 0
    assert status["violations"]["private_strategy_public_exposure_count"] == 0
    assert status["violations"]["secret_leak_count"] == 0
    assert status["findings"]["unresolved_critical_count"] == 0
    assert status["audit"]["write_method_trap_count"] >= 1
    assert status["audit"]["import_graph_node_count"] > 0

    out = write_immutable_status(root=ROOT, status=status)
    assert out.exists()
    assert "NEXUS_PRIVATE_SECURITY_BOUNDARY_V1_PASS" in out.read_text(encoding="utf-8")


def test_run_boundary_cli_path():
    status = run_boundary(write_artifact=True, root=ROOT)
    assert status["Security_Boundary_status"] == "NEXUS_PRIVATE_SECURITY_BOUNDARY_V1_PASS"
    assert status["exchange_write_attempt_count"] == 0
    assert status["secret_leak_count"] == 0


def test_credential_assert_no_secret_echo():
    from backend.nexus_autonomy.security_credential_boundary_v1 import assert_no_secret_in_text

    assert_no_secret_in_text("all clear evidence")
    with pytest.raises(CredentialBoundaryError):
        assert_no_secret_in_text("leak", secrets=["leak"])

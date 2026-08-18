import importlib.util
from pathlib import Path

from backend.nexus_demo_execution.p1_validation_runtime import (
    apply_disarmed_flags,
    code_identity_matches,
    load_valid_json_object,
    unique_remote_path,
    write_json_file,
)


def test_disarmed_flags_and_unique_paths():
    env: dict[str, str] = {}
    flags = apply_disarmed_flags(env)
    assert flags["MAINNET"] == "false"
    assert env["EXCHANGE_WRITE"] == "false"
    path = unique_remote_path(kind="p1_run8_accounting_recovery", run_id="12", run_attempt="1")
    assert path.endswith("p1_run8_accounting_recovery_12_1.json")


def test_write_and_reject_empty_json(tmp_path: Path):
    target = tmp_path / "evidence.json"
    assert write_json_file(target, {"recovery_stage": "MODULE_IMPORT"}) is True
    assert load_valid_json_object(target)["recovery_stage"] == "MODULE_IMPORT"
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    assert load_valid_json_object(empty) is None


def test_code_identity_and_run8_stdout_parser():
    assert code_identity_matches(expected_sha="abcdef123", loaded_sha="abcdef1xyz") is True
    spec = importlib.util.spec_from_file_location(
        "p1_parse_run8_stdout",
        Path("tools/ci/p1_parse_run8_stdout.py"),
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parsed = mod.parse_run8_stdout(
        'noise\n{"recovery_stage":"CLOSED_PNL_READ","BYBIT_DEMO_SINGLE_TRADE_E2E_PASS":"HOLD"}\n'
    )
    assert parsed["runner_json_detected"] is True
    assert parsed["recovery_stage"] == "CLOSED_PNL_READ"
    assert mod.parse_run8_stdout("no json here")["runner_json_detected"] is False

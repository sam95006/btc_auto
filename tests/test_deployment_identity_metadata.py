"""Deployment identity must never report a hardcoded historical commit."""
from __future__ import annotations

import os
from pathlib import Path

from backend.nexus_demo_execution import v2_policy


def test_resolve_runtime_deployment_commit_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_DEPLOYMENT_COMMIT", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    monkeypatch.setenv("GITHUB_SHA", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    assert v2_policy.resolve_runtime_deployment_commit().startswith("aaaa")


def test_resolve_runtime_deployment_commit_rejects_historical_pr24(monkeypatch) -> None:
    stale = "81b0d14e2ffb6c5b5e92eeedd7962ed60dd00bc0"
    monkeypatch.setenv("NEXUS_DEPLOYMENT_COMMIT", stale)
    monkeypatch.delenv("NEXUS_SOURCE_COMMIT", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    assert v2_policy.resolve_runtime_deployment_commit() == "UNKNOWN"


def test_runtime_deployment_commit_sot_is_dynamic(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "cccccccccccccccccccccccccccccccccccccccc")
    monkeypatch.delenv("NEXUS_DEPLOYMENT_COMMIT", raising=False)
    monkeypatch.delenv("NEXUS_SOURCE_COMMIT", raising=False)
    assert v2_policy.RUNTIME_DEPLOYMENT_COMMIT_SOT.startswith("cccc")


def test_resolve_runtime_deployment_commit_accepts_zeabur_git_sha(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_DEPLOYMENT_COMMIT", raising=False)
    monkeypatch.delenv("NEXUS_SOURCE_COMMIT", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setenv("ZEABUR_GIT_COMMIT_SHA", "dddddddddddddddddddddddddddddddddddddddd")
    assert v2_policy.resolve_runtime_deployment_commit().startswith("dddd")


def test_demo_founder_gate_defaults_are_not_live_approvals() -> None:
    text = Path("deploy/zeabur_bybit_demo_validation/demo_founder_gate.env").read_text(encoding="utf-8")
    assert "FOUNDER_GATE=DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION" in text
    assert "FOUNDER_6H_APPROVED=false" in text
    assert "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2=false" in text
    assert "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3=false" in text
    assert "MAINNET=false" in text
    assert "REAL_MONEY=false" in text
    assert "EXCHANGE_WRITE=false" in text
    assert "DEMO_AUTONOMOUS_ENABLED=false" in text
    assert "FOUNDER_6H_APPROVED=true" not in text

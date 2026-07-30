"""Service registry for Control Plane federation."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from backend.nexus_control_plane import (
    EXECUTION_OWNER_DEMO_VALIDATION,
    ROLE_CONTROL_PLANE,
    ROLE_DEMO_EXECUTION,
    ROLE_LEARNING_ENGINE,
    ROLE_MARKET_INTELLIGENCE,
)


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ServiceRecord:
    service_name: str
    service_role: str
    service_url: str
    runtime_identity: str = "UNKNOWN"
    deployment_commit: str = "UNKNOWN"
    code_sha: str = "UNKNOWN"
    policy_version: str = "UNKNOWN"
    schema_version: str = "UNKNOWN"
    health: str = "UNKNOWN"
    freshness: str = "UNKNOWN"
    last_success_at: float | None = None
    execution_owner: bool = False
    exchange_write_capability: bool = False
    mainnet_capability: bool = False
    real_money_capability: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "service_role": self.service_role,
            "service_url": self.service_url,
            "runtime_identity": self.runtime_identity,
            "deployment_commit": self.deployment_commit,
            "code_sha": self.code_sha,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
            "health": self.health,
            "freshness": self.freshness,
            "last_success_at": self.last_success_at,
            "execution_owner": self.execution_owner,
            "exchange_write_capability": self.exchange_write_capability,
            "mainnet_capability": self.mainnet_capability,
            "real_money_capability": self.real_money_capability,
        }


@dataclass
class ServiceRegistry:
    """Backend-configured hosts only — never hardcode in browser."""

    records: dict[str, ServiceRecord] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "ServiceRegistry":
        market_url = (
            os.environ.get("NEXUS_MARKET_INTELLIGENCE_URL")
            or os.environ.get("NEXUS_STAGE3_URL")
            or "https://nexus-stage3-bybit-demo-learning.zeabur.app"
        ).rstrip("/")
        demo_url = (
            os.environ.get("NEXUS_DEMO_EXECUTION_URL")
            or os.environ.get("NEXUS_DEMO_VALIDATION_URL")
            or "https://nexus-bybit-demo-val.zeabur.app"
        ).rstrip("/")
        control_url = (os.environ.get("NEXUS_CONTROL_PLANE_URL") or "local://control-plane").rstrip("/")

        # Stage3 must never be execution owner in the unified contract.
        stage3_exec = False
        if _truthy("STAGE3_EXECUTION_OWNER"):
            stage3_exec = False  # hard override — contract forbids

        reg = cls()
        reg.records[ROLE_MARKET_INTELLIGENCE] = ServiceRecord(
            service_name="nexus-stage3-bybit-demo-learning",
            service_role=ROLE_MARKET_INTELLIGENCE,
            service_url=market_url,
            execution_owner=stage3_exec,
            exchange_write_capability=False,
            mainnet_capability=False,
            real_money_capability=False,
            policy_version="stage3-market-gateway",
        )
        reg.records[ROLE_DEMO_EXECUTION] = ServiceRecord(
            service_name="nexus-bybit-demo-learning-validation",
            service_role=ROLE_DEMO_EXECUTION,
            service_url=demo_url,
            execution_owner=True,
            exchange_write_capability=True,  # capability exists; Control Plane never proxies writes
            mainnet_capability=False,
            real_money_capability=False,
            policy_version="demo-autonomous-6h-bounded-v1",
        )
        reg.records[ROLE_LEARNING_ENGINE] = ServiceRecord(
            service_name="nexus-bybit-demo-learning-validation",
            service_role=ROLE_LEARNING_ENGINE,
            service_url=demo_url,
            execution_owner=False,
            exchange_write_capability=False,
            mainnet_capability=False,
            real_money_capability=False,
            policy_version="demo-learning-evidence",
        )
        reg.records[ROLE_CONTROL_PLANE] = ServiceRecord(
            service_name="nexus-web-control-plane",
            service_role=ROLE_CONTROL_PLANE,
            service_url=control_url,
            execution_owner=False,
            exchange_write_capability=False,
            mainnet_capability=False,
            real_money_capability=False,
            policy_version="control-plane-v1",
        )
        return reg

    def allowed_hosts(self) -> set[str]:
        hosts: set[str] = set()
        for rec in self.records.values():
            if rec.service_url.startswith("local://"):
                continue
            host = urlparse(rec.service_url).hostname
            if host:
                hosts.add(host.lower())
        return hosts

    def get(self, role: str) -> ServiceRecord | None:
        return self.records.get(role)

    def summary(self) -> dict[str, Any]:
        return {
            "execution_owner": EXECUTION_OWNER_DEMO_VALIDATION,
            "stage3_execution_owner": False,
            "stage3_exchange_write": False,
            "stage3_auto_send": False,
            "services": {k: v.to_dict() for k, v in self.records.items()},
            "allowed_hosts": sorted(self.allowed_hosts()),
        }

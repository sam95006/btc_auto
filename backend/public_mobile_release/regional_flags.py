"""Regional feature flag evaluation with global hard bans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.public_mobile_release.yaml_lite import load_simple_yaml


GLOBAL_BAN_KEYS = (
    "live_billing_enabled",
    "real_iap_products_enabled",
    "automated_customer_trading",
    "copy_trading",
    "custodial_wallet",
)


@dataclass(frozen=True)
class FlagDecision:
    region: str
    flags: dict[str, Any]
    banned: bool
    ban_reasons: tuple[str, ...]


class RegionalFlagEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.regions = config.get("regions") or {}
        self.global_overrides = config.get("global_overrides") or {}

    @classmethod
    def from_package(cls, package_root: Path) -> "RegionalFlagEngine":
        data = load_simple_yaml(package_root / "regional" / "feature_flags.yaml")
        return cls(data)

    def evaluate(self, region: str) -> FlagDecision:
        base = dict(self.regions.get("ZZ") or {})
        specific = dict(self.regions.get(region) or {})
        merged = {**base, **specific}
        ban_reasons: list[str] = []
        for key in GLOBAL_BAN_KEYS:
            # global overrides win when False
            if key in self.global_overrides:
                merged[key] = self.global_overrides[key]
            if merged.get(key) is True:
                ban_reasons.append(f"{key}=true_forbidden")
                merged[key] = False
        # subscription UI cannot enable while billing banned
        if not merged.get("live_billing_enabled", False):
            merged["subscription_purchase_ui"] = False
        banned = bool(ban_reasons)
        return FlagDecision(region=region, flags=merged, banned=banned, ban_reasons=tuple(ban_reasons))

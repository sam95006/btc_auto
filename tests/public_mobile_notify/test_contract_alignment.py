"""Contract alignment between Python constants and Dart prototypes."""

from __future__ import annotations

from pathlib import Path

from backend.nexus_public_mobile_notify.constants import (
    ALERT_KINDS,
    DEEP_LINK_ROUTES,
    PRIVATE_FIELD_DENYLIST,
)

ROOT = Path(__file__).resolve().parents[2]
DART_ALERT = ROOT / "mobile" / "nexus_notify_prototypes" / "lib" / "src" / "alert_kinds.dart"
DART_DEEP = ROOT / "mobile" / "nexus_notify_prototypes" / "lib" / "src" / "deep_link.dart"


def test_dart_alert_kinds_cover_python_set():
    text = DART_ALERT.read_text(encoding="utf-8")
    for kind in ALERT_KINDS:
        assert f"'{kind}'" in text or f'"{kind}"' in text


def test_dart_routes_cover_python_set():
    text = DART_DEEP.read_text(encoding="utf-8")
    for route in DEEP_LINK_ROUTES:
        assert f"'{route}'" in text


def test_dart_denylist_covers_critical_private_fields():
    text = DART_ALERT.read_text(encoding="utf-8")
    for field in ("strategy_id", "orders", "wallet", "api_key", "checkpoint_path"):
        assert field in PRIVATE_FIELD_DENYLIST
        assert f"'{field}'" in text

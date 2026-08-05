"""Preference store tests."""

from __future__ import annotations

from backend.nexus_public_mobile_notify.preferences import InMemoryPreferenceStore


def test_default_preferences_and_channel_gate():
    store = InMemoryPreferenceStore()
    prefs = store.get_or_default("member_1")
    assert prefs.push_enabled is True
    assert prefs.allows(kind="RISK", priority="HIGH") is True

    store.update_channel("member_1", "RISK", enabled=False)
    prefs2 = store.get_or_default("member_1")
    assert prefs2.allows(kind="RISK", priority="CRITICAL") is False
    assert prefs2.version == 2

    store.update_channel("member_1", "DATA_STALE", min_priority="HIGH")
    prefs3 = store.get_or_default("member_1")
    assert prefs3.allows(kind="DATA_STALE", priority="NORMAL") is False
    assert prefs3.allows(kind="DATA_STALE", priority="HIGH") is True


def test_global_push_disable():
    store = InMemoryPreferenceStore()
    prefs = store.get_or_default("m2")
    prefs.push_enabled = False
    store.save(prefs)
    assert store.get_or_default("m2").allows(kind="DECISION_STATUS", priority="CRITICAL") is False

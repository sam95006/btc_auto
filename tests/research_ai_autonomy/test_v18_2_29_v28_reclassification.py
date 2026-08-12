from __future__ import annotations

from backend.nexus_research_ai_autonomy.reflection_v29_reclassify import reclassify_v28_bluaiusdt_loss


def test_v28_reclassification_outputs_original_and_new_class():
    out = reclassify_v28_bluaiusdt_loss()
    assert out["symbol"] == "BLUAIUSDT"
    assert "V28_original_class" in out
    assert "V28_reclassified_as" in out
    assert out["V28_reclassified_as"]["new_diagnostic_classification"] is not None
    assert 0.0 <= out["V28_reclassified_as"]["confidence"] <= 1.0


def test_v28_unavoidable_downgraded_if_direction_ambiguity_supported():
    out = reclassify_v28_bluaiusdt_loss()
    orig = out["V28_original_class"]
    new = out["V28_reclassified_as"]["new_diagnostic_classification"]
    tie_supported = bool(out["diagnostics"]["tie"]["direction_ambiguity_supported"])

    if orig == "UNAVOIDABLE_MARKET_OUTCOME" and tie_supported:
        assert new != "UNAVOIDABLE_MARKET_OUTCOME"


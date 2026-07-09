# Stage 4.18-P1 — BTC Dual-Provider Shadow Mode Implementation

**Date:** 2026-07-09 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** code-only — **default off, no soak, no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18P1_PASS`**

| Layer | Result |
|-------|--------|
| Shadow config + runner | **PASS** |
| Dry-run integration (default off) | **PASS** |
| Paper/calibration/graduation guards | **PASS** |
| Validator shadow safety checks | **PASS** |
| Unit tests | **PASS** (25/25 related) |
| Offline diagnostics probe (O3 map) | **PASS** |
| Stage 4.19 | **BLOCKED** |

BTC dual-provider shadow mode implemented with **both env flags default false**. Actual decisions unchanged; shadow writes only to `btc_shadow_provider_decisions.jsonl`.

**Do not** auto-run P1-R1 30m. **Do not** enable shadow flags without operator approval.

---

## 2. P design summary

| Field | Value |
|-------|-------|
| Recommended option | Option 3 — BTC dual-provider shadow |
| P1 scope | diagnostic-only shadow mode |
| Routing changes applied | **none** (design preserved) |

---

## 3. Config flags and defaults

| Env flag | Default | Required for shadow |
|----------|---------|---------------------|
| `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED` | **false** | yes |
| `STAGE4_BTC_DUAL_PROVIDER_SHADOW` | **false** | yes |

`shadow_mode_active=false` unless **both** flags are true.

---

## 4. Shadow decision schema

Output file: `btc_shadow_provider_decisions.jsonl`

Key fields per row:
- `actual_provider` / `shadow_provider` (opposite pair)
- `shadow_decision_intent`, `shadow_confidence`, `shadow_directional_bias`
- `shadow_would_be_valid_watch_under_current_rules`
- `provider_divergence_detected`
- `shadow_diagnostic_only=true`
- All exclusion flags `true`
- `order_sent=false`

---

## 5. Actual decision path unchanged

- `agent.decide()` unchanged in behavior
- Actual rows still written to `ai_decisions.jsonl` only
- `effective_decision_count` excludes shadow
- Provider chain fallback state not modified by shadow (direct `Stage4LLMClient`, `SHADOW_BYPASSES_PROVIDER_CHAIN`)

---

## 6–9. Shadow exclusions

| Path | Excluded |
|------|----------|
| Paper logger | **yes** — `is_shadow_decision_row` filter |
| Calibration | **yes** — analyzer reads actual only |
| Graduation | **yes** — shadow never in calibration inputs |
| Stage 4.19 readiness | **yes** — validator fails if shadow drives readiness |

---

## 10. Tests result

```
tests.test_stage4_btc_dual_provider_shadow — 10/10 OK
tests.test_stage4_btc_shadow_diagnostics — 3/3 OK
tests.test_stage4_provider_routing_design — 6/6 OK
tests.test_stage4_controlled_provider_probe — 6/6 OK
```

---

## 11. Offline diagnostics probe (O3 map, no LLM)

```
python tools/research/stage4_btc_shadow_diagnostics.py \
  --input-dir /data/stage4_18o3_controlled_provider_probe \
  --output-dir /data/stage4_18p1_shadow_diagnostics_probe
```

| Metric | Value |
|--------|-------|
| `shadow_decision_count` | 6 (mapped from O3 probe) |
| `shadow_valid_watch_count` | 1 |
| `provider_divergence_count` | 1 |
| `recommendation` | collect more shadow samples |

---

## 12. Whether P1-R1 30m is recommended

**Not auto-run.** Operator may enable both flags and run **P1-R1 30m** after explicit approval to collect live shadow JSONL — not proposed automatically.

---

## 13. Safety confirmation

| Check | Value |
|-------|-------|
| `shadow_mode_active` (default) | **false** |
| `routing_changes_applied` | **false** |
| `order_sent_count` | **0** |
| Soak (30m/60m) | **not run** |
| Stage 4.19 | **not started** |

---

## 14. Files added/modified

**Added:** `stage4_provider_routing_config.py`, `stage4_btc_dual_provider_shadow.py`, `stage4_btc_shadow_diagnostics.py`, tests

**Modified:** `run_stage4_ai_decision_dry_run.py`, `stage4_ai_decision_agent.py`, `stage4_provider_chain.py`, `stage4_paper_event_logger.py`, `stage4_watchlist_followup_simulator.py`, `stage4_paper_entry_failure_analyzer.py`, `validate_stage4_ai_decision_outputs.py`

---

## 15. Final verdict

**`STAGE_4_18P1_PASS`**

Shadow machinery ready, **default off**. Remain at gate until operator approves P1-R1.

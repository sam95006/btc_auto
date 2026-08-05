# NEXUS Public V1 UI Data Contract and Traceability (PUB-G)

**Status:** Foundation / LOCAL+STAGING verification only  
**Lane:** PUB-G  
**Branch:** `feature/public-v1-ui-data-traceability`  
**Schema:** `public.intelligence.v1`

## Purpose

Machine-verifiable mapping from every Member Platform UI surface —

- card
- table
- chart
- gauge
- chip
- notification
- Decision summary

— to a **public DTO** field path. Private intelligence fields are denied.

## Required LIVE counters

| Counter | Required |
|---------|----------|
| `visible_mock_value_count` | 0 |
| `unmapped_live_component_count` | 0 |
| `private_field_binding_count` | 0 |
| `stale_without_indicator` | 0 |
| `unavailable_fabrication` | 0 |

## Rules

1. **LIVE mode** must not render MOCK/DEMO values as live facts.
2. Every LIVE-required component must have ≥1 public DTO binding.
3. Bindings may only use allow-listed public fields (aligned with PUB-A).
4. STALE values must expose a stale indicator.
5. UNAVAILABLE must not fabricate substitute numbers/labels.
6. DEMO/fixture mode (PUB-D) remains allowed only when labeled DEMO — never as LIVE.

## Package layout

- `backend/nexus_public_ui_trace/` — catalog, DTO registry, bindings, verifier, two-pass runner
- `tools/public_v1/run_ui_data_traceability_gate.py` — stdout JSON gate (no `*_status.json`)
- `tests/public_ui_trace/` — positive + negative counter tests
- `frontend/src/public_ui_trace/` — TypeScript contract mirror

## Hard bans

No PR26/27 merge, no production deploy, no production public API, no live billing, no exchange writes, no mainnet, no real money, no private-core trading imports, no `*_status.json` artifacts from this lane.

## Verify

```bash
python tools/public_v1/run_ui_data_traceability_gate.py
python -m pytest tests/public_ui_trace -q
```

TWO PASSES: gate runs verification twice; counters must match and equal zero.

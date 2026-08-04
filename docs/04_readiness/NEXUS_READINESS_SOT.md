# NEXUS Readiness Source of Truth

Updated: 2026-08-04T04:20:00Z

## Current system stage

`BLIND_REFLECTION_V2_3_CONTINUITY_V4_IN_PROGRESS`

Canonical workspace: `G:\我的雲端硬碟\btc_bot`

Private Core PR: `#24` (Draft, unmerged)

## Calibration progress (checkpoint; not a terminal package)

- Groq Reflection successes: see `.nexus_runtime/blind_reflection_v23_checkpoint.json`
- Do **not** mint Git commits or immutable packages for partial batches (37/80, 42/80, …)
- Terminal package only after 80/80 + Critic adjudication (or formal quality fail)

## Disagreement accounting

While SambaNova Critic is blocked/unresolved:

- `unadjudicated_disagreement_count`
- `provider_blocked_disagreement_count` (when provider-blocked)

Root-cause fields remain `NOT_YET_ADJUDICATED` (not confirmed zero):

- AI_misclassification_count
- deterministic_baseline_too_coarse_count
- evidence_packet_ambiguous_count
- taxonomy_ambiguous_count
- outcome_process_mapping_error_count

## Hard risk semantics

- `hard_risk_static_ban_status=PASS` (bans held)
- `hard_risk_override_path_test_status=NOT_EXECUTED` until Learning Prevention exercises a prohibited request path

## VWAP

`VWAP_RESEARCH_LINE_TERMINAL_CURRENT_EXECUTION_MODEL`

## Microstructure Data Foundation V1

Approved capture foundation only (no strategies):

- `AGGRESSIVE_TRADE_FLOW`
- `LIQUIDATION_EVENTS`

Package: `artifacts/readiness/immutable/microstructure_data_foundation_v1/`

Raw events: `.nexus_runtime/microstructure/` (not committed)

## Formal blockers

Demo/WF/OOS/Shadow/deploy/mainnet/real money blocked.

Public product PR `#26` frozen pending Founder-led ICP recruitment.

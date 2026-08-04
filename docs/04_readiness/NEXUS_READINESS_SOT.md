# NEXUS Readiness Source of Truth

Updated: 2026-08-04T03:45:00Z

## Current system stage

`BLIND_REFLECTION_V2_3_PROVIDER_SPLIT_CONTINUITY_V3`

Canonical workspace: `G:\我的雲端硬碟\btc_bot`

Private Core PR: `#24` (Draft, unmerged)

## Evidence delivery metrics (do not conflate)

| Metric | Meaning |
| --- | --- |
| `evidence_packet_constructible_ratio` | Frozen packets can be serialized (80/80) |
| `reflection_prompt_delivery_ratio_on_attempts` | Attempted Reflection calls included the packet |
| `full_calibration_completion_ratio` | Successful Reflection / 80 |
| `critic_prompt_delivery_ratio_on_attempts` | Attempted Critic calls included the packet |

Pending cases are **not** Provider-delivered.

## Provider-specific transport

Separate counters/stages for:

- `GROQ_REFLECTION_REASONER`
- `SAMBANOVA_INDEPENDENT_CRITIC`
- `CEREBRAS_RESEARCH_NORMALIZER`
- `GROQ_MAIN_REASONER`

A SambaNova 429 must not increment Groq counters.

`INVOCATION_BATCH_LIMIT_REACHED` is not a Provider rate limit.

Critic `0/N` under SambaNova transport block → `SAMBANOVA_PROVIDER_BLOCKED` (not ordinary `VALID`).

## Interpretation correction (preserved)

Prior all-429 run is **not** model-quality failure.

`V2_3_RESULT_INTERPRETATION = CALIBRATION_INCOMPLETE_PROVIDER_CAPACITY`

## VWAP terminal taxonomy

Sealed confirmation preserved. Non-mutating correction:

- `VWAP_RAW_EDGE_PRESENT_BUT_COST_DESTROYED`
- `VWAP_DEVELOPMENT_COST_DESTROYED`
- `VWAP_RESEARCH_LINE_TERMINAL_CURRENT_EXECUTION_MODEL`

Do not keep `DISCOVERY_NO_GROSS_EDGE` as primary when gross expectancy > 0 and net < 0.

No VWAP retune / formal WF / OOS.

## Next alpha research gate

`NEXUS_ALPHA_DATA_FAMILY_FEASIBILITY_V1` — research-source decision only.

Selected proposal (Founder approval before acquisition):

- `LIQUIDATION_EVENTS`
- `AGGRESSIVE_TRADE_FLOW`

No paid purchase, no prohibited scrape, no new candle strategies in this stage.

## Runtime / packages

- Checkpoint: `.nexus_runtime/blind_reflection_v23_checkpoint.json` (not committed)
- Prior packages preserved under `artifacts/readiness/immutable/`
- Final immutable continuation package only after full V2.3 + learning-prevention evaluation

## Formal blockers preserved

Demo/WF/OOS/Shadow/deploy/mainnet/real money remain blocked.

Public product PR `#26` remains frozen pending real Founder-led ICP recruitment.

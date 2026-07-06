# Stage 4.18-K — Diagnostics After 4.18-J-R1

**Date:** 2026-07-06 (UTC+8)  
**Trigger:** 4.18-J-R1 **PARTIAL** — technical PASS, quality FAIL, 0 graduations  
**Input:** `/data/stage4_ai_decisions_418j_r1_schema_enforced_regression_30m`  
**Analyzer output:** `/data/stage4_18k_j_r1_failure_analysis`

---

## 1. J-R1 failure summary

| Gate | Result |
|------|--------|
| Runtime / technical | PASS |
| `within_cap > above_cap` | **FAIL** (2 vs 13) |
| Graduations (BTC/ETH) | **0** |
| Stage 4.19 | **blocked** |

418-J enforcement works as designed — it **surfaces** failures rather than masking them. Graduation did not increase because root causes remain in LLM output quality, not missing enforcement.

---

## 2. Primary failure causes (ranked)

| Rank | Cause | J-R1 count | Notes |
|------|-------|------------|-------|
| 1 | **MAE above symbol cap** | 13 | BTC avg ~2.17%, SOL ~2.5%, ETH mixed (one low 0.008% outlier) |
| 2 | **Missing paper fields** | 12 | `entry_trigger` / `invalidation` gaps on watch intents |
| 3 | **Directional bias without candidate_side** | 14 | Blocks graduation even when watch logged |
| 4 | **MAE vs invalidation inconsistent** | 1 | Improved vs I-R1 (4) |
| 5 | **Confirmation window** | 0 consecutive graduations | `watchlist_confirmed=0` in calibration |

---

## 3. Why prompt-only tuning is insufficient (confirmed on J-R1)

- Enforcement correctly sets `block_reason=mae_above_symbol_cap` — logger shows **12 hypothetical_skip** vs **1** pending watchlist.
- ETH **one** within-cap watch proves examples can work, but **2/3** ETH watches still above cap.
- LLM still emits `candidate_side=NONE` with LONG/SHORT bias on majority of paper intents.
- 30m / 6-tick sample rarely yields 2 consecutive compliant BTC+ETH watches with side + MAE + fields.

---

## 4. Code-only recommendations (no RG loosening)

### 4.1 Prompt / schema (418-L candidate)

- Add **worked `candidate_side` examples** paired with `directional_bias` (not only bias without side).
- Require `entry_trigger.type != none` in examples for every watch sample.
- Repeat ETH **0.30%** reference→invalidation math in per-symbol instruction block.

### 4.2 Diagnostics (done in 418-K)

- New tool: `tools/research/stage4_paper_entry_failure_analyzer.py` — offline failure breakdown by block_reason / symbol / intent.

### 4.3 Sample size (recommendation only)

- Consider **60m read-only** sample (12 ticks) **only after** next prompt iteration — not in this step.
- Do **not** relax formal confirmation threshold or RG caps.

### 4.4 Mechanical paper sandbox (future)

- If 418-L prompt iteration still fails `within_cap > above_cap`, evaluate **mechanical MAE from invalidation price** as paper-only display field (not order path) — design gate only.

---

## 5. Watchlist confirmation regression

| Bucket | J-R1 |
|--------|------|
| `mae_above_cap` | 13 |
| `quality_incomplete` | (enforcement) |
| `side_missing_on_confirmation` | elevated vs G-R1 |
| `no_consecutive_tick` | primary graduation blocker |
| `confidence_decreasing` | minor |

G-R1 BTC graduation (`beb61bde…`) required trend SHORT @ conf 0.62, MAE 0.30%, but **`entry_trigger.type=none`** — would fail 418-J `missing_paper_fields` today.

---

## 6. ETH diagnostic

| Metric | J-R1 | I-R1 |
|--------|------|------|
| ETH watches | 3 | 2 |
| Within cap | **1** | 0 |
| Above cap | 2 | 2 |
| Graduation | 0 | 0 |

**Partial ETH improvement** but insufficient for Stage 4.19 operator gate.

---

## 7. Stage 4.19 status

**NOT started.** Operator gate requires BTC **and** ETH graduation > 0, `recommended_mode_for_419 != none`, `within_cap > above_cap`.

---

## 8. Safety

| Check | Value |
|-------|-------|
| Orders / demo / ARM / production | **not touched** |
| RG thresholds | **unchanged** |
| Second 30m soak in 418-K | **not run** |

---

## 9. Verdict

**`STAGE_4_18K_CODE_PASS`** — diagnostics + analyzer delivered; stopped at gate.

**Next:** Stage 4.18-L — `candidate_side` + `entry_trigger` prompt iteration (code-only), then optional 60m read-only sample if approved.

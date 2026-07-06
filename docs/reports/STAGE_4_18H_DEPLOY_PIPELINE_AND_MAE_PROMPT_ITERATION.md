# Stage 4.18-H — Deploy Pipeline Fix + MAE Prompt Iteration

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Prior report:** `ea95616` (4.18-G-R1 PARTIAL)  
**Mode:** tooling + prompt only — **no soak, no orders, no RG changes**

---

## 1. Executive summary

Stage 4.18-H addresses two blockers before the next 30m regression:

**Part A — Deploy pipeline:** Added `check_stage4_runtime_version.py`, entrypoint patch re-apply from `/data/stage4_418f_runtime_patch/`, and dry-run gate when runtime is stale.

**Part B — Prompt iteration:** Extended `stage4_prompt_builder.py` with 418-H rules tying MAE to invalidation distance (not ATR/vol), explicit BTC/ETH 0.28%/0.35% targets, SOL/PEPE caps, and ETH paper-field yield guidance.

**Verdict: CODE PASS — stopped at gate (no 30m soak, no Stage 4.19).**

---

## 2. 4.18-G-R1 result summary

| Metric | Value |
|--------|-------|
| Runtime gate | PASS (manual sync) |
| Technical soak | PASS (6/6, 22 effective) |
| `within_cap` / `above_cap` | 7 / 22 |
| BTC graduation | 1 (`major_mae_100_llm_mae`) |
| ETH graduation | 0 |
| Stage 4.19 | **blocked** |

First BTC paper graduation proved the pipeline can work; ETH + cap alignment remain gaps.

---

## 3. Deploy drift root cause

| Finding | Detail |
|---------|--------|
| Zeabur `npx deploy` | Reports success but `/app` often stays on stale image |
| Restart | Wipes ephemeral `/app` manual sync |
| Local package | `deploy/zeabur_stage3_demo_learning` already had 418F files |
| Likely causes | Service not bound to fresh GitHub build; cached image; deploy root mismatch |

**4.18-G failed** because soak ran pre-418F code. **4.18-G-R1** succeeded only via manual base64 sync.

---

## 4. Deploy pipeline fix plan (minimal runtime changes)

### Immediate (implemented)

1. **`check_stage4_runtime_version.py`** — JSON gate before cloud regression.
2. **Entrypoint patch re-apply** — on idle start, copy `/data/stage4_418f_runtime_patch/*.py` → `/app/tools/research/` when `STAGE4_APPLY_RUNTIME_PATCH=true` (default).
3. **Dry-run hard gate** — entrypoint + `run_stage4_ai_decision_dry_run.py` block when `STAGE4_REQUIRE_RUNTIME_VERSION_CHECK` enabled (default on when `STAGE4_REQUIRE_REAL_LLM=true`).
4. **Persist patch after manual sync** — operator copies 418F/H files to `/data/stage4_418f_runtime_patch/` (survives restart).

### Recommended (operator / infra — not code)

1. Verify Zeabur service binds to `stage3-demo-learning` branch and `deploy/zeabur_stage3_demo_learning` root.
2. Force rebuild (no cache) after each Stage4 research commit.
3. Compare `STAGE3_DEPLOY_VERSION.json` commit vs expected git SHA before soak.
4. Pre-soak ritual: `python tools/research/check_stage4_runtime_version.py --gate --apply-patch-dir /data/stage4_418f_runtime_patch`

### Not done (by design)

- No RG threshold changes
- No automatic GitHub Actions deploy wiring (out of scope)
- No 30m soak in this step

---

## 5. Runtime version check design

**Path:** `tools/research/check_stage4_runtime_version.py`

**Checks:**

- 11 required research files exist under `tools/research/`
- 418F + 418H prompt hint strings in `stage4_prompt_builder.py`
- `build_mae_calibration_metrics` in `stage4_paper_readiness.py` (size + import)
- `get_paper_mae_pct` in `stage4_paper_guard_inputs.py`
- `main` in `stage4_mae_calibration_analysis.py`
- Stale detection: missing files, small `stage4_paper_readiness.py`, missing hints

**Output:**

```json
{
  "runtime_version_check_passed": true,
  "prompt_hints_present": true,
  "mae_analysis_script_present": true,
  "build_mae_metrics_present": true,
  "paper_guard_inputs_present": true,
  "get_paper_mae_pct_present": true,
  "app_file_stale_suspected": false
}
```

**Gate:** `runtime_version_check_passed=false` → dry-run returns `failed_reason=stage4_runtime_version_check_failed`.

---

## 6. Prompt iteration changes (418-H)

**File:** `tools/research/stage4_prompt_builder.py`

| Rule | Change |
|------|--------|
| MAE semantics | Not ATR / vol forecast; = adverse move reference → invalidation |
| BTC/ETH | Survival ≤0.28%, graduation ≤0.35%; above → skip |
| SOL | Cap 0.25%; don't use chop as MAE |
| PEPE | Cap 0.20%; watchlist/skip; no deflating MAE for entry |
| ETH | Skip if no direction; if bias exists, require paper fields |
| Anti-gaming | Do not underestimate MAE; uncertain → skip; `mae_risk_too_high` block |

Paper-readiness validator rules **unchanged** — above-cap MAE still `decision_quality_incomplete`.

---

## 7. ETH graduation issue analysis

4.18-G-R1 ETH distribution: **hard_skip=4, soft_skip=2**, no MAE-bearing paper-ready watches.

Likely causes (not mutually exclusive):

1. **Market/regime** — ETH ticks lacked clear directional edge in 30m window.
2. **Prompt conservatism** — pre-418H rules did not require paper fields when bias exists; model defaulted to skip without structured output.
3. **Provider mix** — heavy Cerebras fallback after Groq TPM cooldown may change skip bias.
4. **Not RG** — formal thresholds unchanged; blocker is upstream decision quality + MAE scale.

418-H adds explicit ETH guidance: if `directional_bias` is LONG/SHORT, must emit `entry_trigger`, `invalidation`, `mae_risk_estimate_pct`. Next regression will show if ETH yield improves without forcing `enter_candidate`.

---

## 8. Why Stage 4.19 is still blocked

- Only **1 BTC** graduation; **ETH=0**
- `within_cap (7) < above_cap (22)`
- Operator gate: **both** BTC and ETH graduation required
- No RG loosening

---

## 9. Next regression plan (418-H-R1 or 418-I)

1. Deploy/rebuild package with 418-H code **or** sync + persist to `/data/stage4_418f_runtime_patch/`
2. **`check_stage4_runtime_version.py --gate` must PASS** before soak
3. 30m fixed-fleet read-only dry-run (same env as 4.18-G-R1)
4. Success targets:
   - `within_cap > above_cap`
   - BTC **and** ETH graduation > 0
   - BTC/SOL avg MAE closer to caps (not deflated)
5. Only then consider Stage 4.19 offline paper exit evaluation

---

## 10. Safety confirmation

| Check | Value |
|-------|-------|
| Orders sent | 0 |
| Mock AI | 0 |
| Exchange private API | not called |
| RG thresholds | unchanged |
| Production / btc-auto / ARM / radar | not touched |
| Stage 4.19 auto-started | **NO** |
| 30m soak auto-started | **NO** |

---

## 11. Tests

```bash
python -m unittest tests.test_stage4_ai_decision_layer tests.test_stage4_paper_event_logger tests.test_stage4_watchlist_followup_simulator -q
```

**Result:** 259/259 passed (+16 new 418-H tests).

---

**final_verdict:** `STAGE_4_18H_CODE_PASS` — deploy gate + prompt iteration complete; **next 30m regression required before Stage 4.19 gate.**

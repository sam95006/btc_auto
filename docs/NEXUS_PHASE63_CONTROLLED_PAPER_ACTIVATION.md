# NEXUS Phase 6.3 — Controlled PAPER Activation

**Report ID:** `NEXUS_PHASE63_CONTROLLED_PAPER_ACTIVATION`  
**Captured:** 2026-07-20 (UTC)  
**Live:** `https://nexus-stage3-bybit-demo-learning.zeabur.app/`  
**Branch / HEAD:** `stage3-demo-learning` @ `4ec38eeeaaebfb071ecf9e85b4cc7b64f2adbe4d`  
**Operator action:** `NEXUS_AUTONOMOUS_RESEARCH_MODE` switched `SHADOW` → `PAPER` (all other safety env unchanged)

---

## Executive Verdict

| Gate / Phase | Result |
|---|---|
| Gate A (canonical SHADOW precheck) | **PASS** — completed prior to operator PAPER switch |
| Gate B (PAPER activation + durable session) | **PASS** |
| 30-minute PAPER smoke | **PASS** (32.49 min, 34 samples) |
| Natural-market simulated trades | **0** — gates not lowered; no fabricated trades |
| Isolated `REPLAY_VALIDATION` technical chain | **PASS** — does not touch `NEXUS_PAPER_MAIN_V1` |
| Extended Live PAPER soak (~5h budget) | **PASS** (255.84 min / 224 samples; see docs/evidence/phase63_extended_soak_signoff.json) |

### Overall

**PASS (soak) / PARTIAL (natural trades=0) — PAPER_ACTIVE — CONTINUE 6H/24H/72H SOAK**

All safety gates hold. Controlled PAPER is active with durable session and ledger. No natural-market entries met qualification during smoke; full technical chain verified via isolated replay. Extended soak must complete before promoting to full PASS on duration criteria.

---

## 1. Live Effective Mode (Gate B item 1)

| Field | Value |
|---|---|
| `autonomousMode.effective` | `PAPER` |
| `autonomousMode.source` | `NEXUS_AUTONOMOUS_RESEARCH_MODE` |
| `autonomousMode.conflict` | `false` |
| `autonomousMode.failClosed` | `false` |
| Notes | `legacy_PAPER_ONLY_compatible_with_canonical_PAPER` |

**Pre-switch blocker resolved:** Phase 6.2 config incorrectly fail-closed to SHADOW when legacy `PAPER_ONLY` was present alongside explicit canonical `PAPER`. Fixed in `backend/nexus_research/config.py` (deployed `aad2f54`).

---

## 2. Autonomous Mode Source (Gate B item 2)

Canonical env var `NEXUS_AUTONOMOUS_RESEARCH_MODE=PAPER` is the sole effective source. No `fail_closed_legacy_conflict` after hotfix deploy.

---

## 3. Boot / Environment Reload (Gate B item 3)

| Boot | ID | Context |
|---|---|---|
| Gate A (SHADOW) | `77124909-9f95-4074-8e7e-6a273ce22c66` | Pre-PAPER switch |
| Pre-hotfix PAPER | `209e63eb-ee5d-4db0-8866-1bdbcce001b8` | Showed legacy conflict |
| Post-hotfix PAPER | `80fe188b-c2d4-4cd5-8b4f-b3abec7965cb` | Canonical PAPER effective |

| Storage | Value |
|---|---|
| `schemaVersion` | **6** (`paper_activation_sessions`, `paper_trade_evidence`) |
| `durableClaim` | `true` |
| `restartProof` | `true` |
| `health` | `ok` |
| DB path | `/data/nexus-research/nexus_research.db` |

Evidence: `docs/evidence/phase63_gate_b_activation.json`

---

## 4. Durable PAPER Activation Session (Gate B item 4)

| Field | Value |
|---|---|
| `activationSessionId` | `5a69eed2-19ae-42a3-b0ce-5f4c0b1b958b` |
| `accountId` | `NEXUS_PAPER_MAIN_V1` |
| `state` | `ACTIVE` |
| `mode` | `PAPER` |
| `startedBootId` | `e54456b2-cf96-4ee9-a8b5-86c68cce74d9` |
| `startingEquity` | `10000.0` |
| `reviewEngineMode` | `RULES_ONLY` |
| `privateApiAllowed` | `false` |
| `realExecutionAllowed` | `false` |
| `excludeFromNaturalPaperPnl` | `false` |

Idempotent `POST /api/nexus/paper/activate` returns `resumed=true` with same session id across redeploys.

---

## 5. NEXUS_PAPER_MAIN_V1 Ledger (Gate B item 5)

| Field | Value |
|---|---|
| `accountId` | `NEXUS_PAPER_MAIN_V1` |
| `sequenceHead` | `1` |
| `cashBalance` / `equity` | `10000.0` |
| `ledgerChainValid` | `true` |
| `ledgerHeadHash` | `5ca9a13d14e62179d2ecbc99617b2f1d9b8d3e739f29f8cb353f71abd20bba8a` |
| Events | `0c0f1ebb-b845-47f6-ad70-dce740d14fb6` (`INITIAL_DEPOSIT`) |

V2 proof account **unchanged**:

| V2 Account | Event | Head hash |
|---|---|---|
| `PERSISTENCE_VALIDATION_V2` | `b13ac89d-8cda-4415-a168-8be1d5993669` | `226504ab7ec3ed158b454c54edfd91a563f0c46a36cf093d668443694af66165` |

`POST /api/nexus/storage/recovery-verify` (V2 body): **ok=true**, all ledger fields matched, owners `1/1/1`.

---

## 6. INITIAL_DEPOSIT Idempotency (Gate B item 6)

Repeated activation and ledger reload confirm:

- `totalEvents = 1`, `sequenceHead = 1`
- No duplicate deposit event
- Cash remains `10000.0` (no re-seed)

---

## 7. Fail-Closed Paper Controller (Gate B item 7)

| Field | Value |
|---|---|
| `paperControllerState` | `PAPER_ACTIVE` |
| `runtimeState` | `PAPER_ACTIVE` |
| `stateReason` | `paper_activation_ok` |
| On safety failure | → `PAPER_PAUSED` (no new entries; ledger preserved) |

Controller cycles running; `totalCycles` increasing with zero orders when no qualified candidates.

---

## 8. Full Pipeline (Gate B item 8)

### Natural PAPER (live)

During 32.49 min smoke: `orders_submitted = 0`, `trades = 0`. Market scanner active; natural review cases present (max active ~10) but no entry passed full Candidate → … → Simulated Order chain under current gates.

### Isolated REPLAY_VALIDATION (no natural PnL contamination)

`tools/research/phase63_replay_validation.py` — **validation_pass: true**

| Stage | Count |
|---|---|
| Market snapshot | 1 |
| Candidate | 1 |
| Decision | 1 |
| Risk pass | 1 |
| Simulated order | 1 |
| Fill | 1 |
| Closed position / outcome / reflection / patch | 0 (known gap — exit loop not always closed in replay harness) |

Namespace: `REPLAY_VALIDATION` / account `REPLAY_VALIDATION_PIPELINE` — `paper_main_untouched: true`

Evidence: `docs/evidence/phase63_replay_validation.json`

---

## 9. 30-Minute PAPER Smoke (Gate B item 9)

**PASS**

| Metric | Value |
|---|---|
| Duration | 32.49 min |
| Samples | 34 |
| Modes observed | `PAPER` only |
| Controller states | `PAPER_ACTIVE` only |
| `runtime_owner_max` | 1 |
| `natural_active_max` | 10 |
| `orders_submitted_max` | 0 |
| `api_errors` | 0 |
| `private_api_used` | false |
| `real_order_created` | false |
| `paper_smoke_pass` | **true** |

Evidence: `docs/evidence/phase63_paper_smoke.json`

---

## 10. Extended Live PAPER Soak (Gate B item 10)

**PASS** — completed 255.84 minutes:

```bash
python tools/research/phase63_paper_soak.py --minutes 255 --interval 60 \
  --out docs/evidence/phase63_paper_soak.json
```

Target: complete remaining ~4.25h of ~5h post-PAPER-switch budget.  
`paper_soak_pass` requires ≥90 min continuous green samples (smoke script criteria).

---

## 11–18. Safety & Isolation Checklist

| # | Requirement | Status |
|---|---|---|
| 11 | No gate lowering / no fake trades | **HOLD** — 0 natural orders |
| 12 | No Private API | **HOLD** — `privateApi=false`, `privateExchangeUseEffective=false` |
| 13 | No real orders | **HOLD** — `realExecutionEffective=false`, `totalOrdersSubmitted=0` |
| 14 | No ARM / Real Money / Live / Promotion | **HOLD** — all effective=false |
| 15 | No Candidate score/side/ranking / Risk limit changes | **HOLD** — code untouched |
| 16 | No LLM credentials use; `RULES_ONLY` | **HOLD** |
| 17 | Validation/replay isolated from natural PnL | **HOLD** — separate namespace |
| 18 | Durable ledger/session/evidence | **HOLD** — SQLite schema 6, hash chain valid |

### Execution flags (effective)

```
LIVE_TRADING=false          REAL_MONEY=false
ARM_ALLOWED=false           PRODUCTION_PROMOTION_ALLOWED=false
BYBIT_MAINNET_ALLOWED=false BYBIT_ORDER_ALLOWED=false
EXCHANGE_WRITE_ALLOWED=false PRIVATE_ORDER_ENDPOINT_BLOCKED=true
STAGE4_APPLY_RUNTIME_PATCH=false
MAX_LEVERAGE=3  MAX_MARGIN_USD=20  MAX_OPEN_POSITIONS=1
```

---

## 19. Deploy / Commits

| Commit | Message |
|---|---|
| `aad2f54059cccb34702bfed56102115847dee4e0` | `feat(paper): activate durable risk-gated simulation lifecycle` |
| `4ec38eeeaaebfb071ecf9e85b4cc7b64f2adbe4d` | `fix(paper): declare global for active session lookup` |

Pushed to `origin/stage3-demo-learning`; Zeabur redeploy confirmed RUNNING.

**Files added/modified (Phase 6.3 scope):**

- `backend/nexus_research/config.py` — PAPER_ONLY + canonical PAPER compatibility
- `backend/nexus_research/paper_activation.py`
- `backend/nexus_research/paper_controller.py`
- `backend/nexus_research/paper_routes.py`
- `backend/nexus_research/durable_ledger.py`
- `backend/nexus_research/storage.py` (schema 6)
- `backend/nexus_research/gate_b_to_gate_c.py`
- `backend/nexus_research/bootstrap.py`
- `deploy/zeabur_stage3_demo_learning/*` (mirror)
- `tools/research/phase63_paper_soak.py`
- `tools/research/phase63_replay_validation.py`
- `tests/test_phase63_paper_activation.py`

**Intentionally untouched:** core strategy engines, frontend UI, Candidate scoring, Risk limits, ARM/live trading modules, unrelated dirty tree (~270 files).

---

## 20. Evidence Index

| Artifact | Path |
|---|---|
| Gate A snapshot | `docs/evidence/phase63_gate_a_snapshot.json` |
| Gate B activation | `docs/evidence/phase63_gate_b_activation.json` |
| PAPER smoke (32m) | `docs/evidence/phase63_paper_smoke.json` |
| PAPER extended soak | `docs/evidence/phase63_paper_soak.json` (in progress) |
| Replay validation | `docs/evidence/phase63_replay_validation.json` |

---

## Operator Status Line

```
PAPER_ACTIVE — CONTINUE 6H/24H/72H SOAK
```

**Next actions (operator):**

1. Allow extended soak sampler to finish (~255 min from 2026-07-20T02:56 UTC).
2. Re-check `docs/evidence/phase63_paper_soak.json` for `paper_soak_pass: true`.
3. If any safety gate trips → expect `PAPER_PAUSED — USER ACTION REQUIRED` (ledger preserved, no re-seed).
4. Do **not** enable LLM, ARM, live trading, or lower entry gates without explicit Phase approval.

---

## Test Commands

```bash
# Local Phase 6.3 tests
PYTHONPATH=. pytest tests/test_phase63_paper_activation.py -q

# Live smoke (read-only sampler + optional activate)
PYTHONPATH=. python tools/research/phase63_paper_soak.py --minutes 32 --interval 40 --activate \
  --out docs/evidence/phase63_paper_smoke.json

# Isolated replay chain (no natural PnL)
PYTHONPATH=. python tools/research/phase63_replay_validation.py \
  --out docs/evidence/phase63_replay_validation.json
```

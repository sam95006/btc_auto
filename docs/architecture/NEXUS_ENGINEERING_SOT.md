# NEXUS / EATI Engineering Source of Truth
**Handoff date:** 2026-08-24  
**Purpose:** persistent engineering continuity for Codex / future agents.

> The root `AGENTS.md` is the operational contract. This document is the long-form historical and architectural context.
> Current verified GitHub `main` always overrides stale historical notes.

## Executive summary

NEXUS / EATI is a long-running trading, learning, risk, evidence, and market-intelligence system.

It has progressed far beyond a single auto-trading bot. The project includes:
- market discovery and scanning;
- decision candidates;
- evidence;
- risk controls;
- bounded Demo execution;
- protection and reconciliation;
- outcome classification;
- reflection and mistake memory;
- P1/P2/OOS validation;
- public/member intelligence surfaces;
- enterprise product planning;
- GitHub-native Zeabur deployment.

The current engineering objective is NOT real-money trading.

The current objective is to prove, in a controlled Bybit Demo lane, a repeatable learning closure:

market observation
→ signal/candidate
→ decision
→ bounded Demo execution
→ close
→ accounting
→ outcome classification
→ reflection
→ mistake memory / penalty
→ measurable changed future decision
→ evidence review.

The next immediate step is final review of PR #34. The previously documented public URL is no longer treated as the current live Validation URL, and there is currently no bound public domain.

## Latest authoritative handoff state

GitHub:
- repository: `sam95006/btc_auto`
- branch: `main`
- handoff / verified deployment commit: `b0c952ca2eb994c7fe514c1ac1d7c5f93be600d3`
- source-of-truth rule: the current source of truth is always latest verified GitHub `main` plus verified live deployment identity, not a permanent historical SHA.
- current PR: PR #34, base `main`, head `codex/nexus-handoff`, not merged and not deployed.

Zeabur Validation:
- service: `nexus-bybit-demo-learning-validation`
- service id: `6a82a79aa21454a2cf6b0015`
- verified deployment identity during handoff: `b0c952ca2eb994c7fe514c1ac1d7c5f93be600d3`
- current public domain status: Zeabur CLI confirmed `Domains=[]` and `domain list=[]`; there is currently no public domain.
- legacy URL `https://nexus-bybit-demo-val.zeabur.app` is no longer treated as the current live Validation URL.

Current full-engine deploy definition:
`deploy/zeabur_bybit_demo_validation/Dockerfile.full_engine`

Current code safety defaults:
- demo only
- mainnet false
- real money false
- exchange write false
- autonomous disabled until an explicit bounded Founder-gated session.

Current security handoff branch:
- branch: `codex/nexus-handoff`
- lineage includes `d02d97e5886874628cdc974785a26624ccf6b370`
- current handoff branch SHA includes `9be8965bf350d4330f66ba3a314680b72dfb180e`
- future merge must replace PR/branch SHA references with the new verified `main` commit.

Validation public HTTP guard:
- guard env: `NEXUS_VALIDATION_PUBLIC_GUARD`
- control token env: `NEXUS_VALIDATION_CONTROL_TOKEN`
- unauthenticated public GET allowlist:
  - `/health`
  - `/api/nexus/fee-policy`
  - `/api/nexus/market/status`
  - `/api/nexus/demo-execution/account`
  - `/api/nexus/control-plane/overview`
  - `/api/nexus/demo-execution/status`

Public Exposure Security Audit:
- completed during handoff.
- original code surface had unauthenticated state-changing routes.
- validation public HTTP hardening is completed on `codex/nexus-handoff`.
- actual production Flask `url_map` security proof: 92 state-changing routes, 92/92 guarded.

Historical P1/P2 evidence remains preserved.

Real Money / Mainnet / Production ARM remain forbidden.

## Why current architecture must not be rolled back

Over several months, the project accumulated evidence and fixes for:
- startup interference;
- network/DNS failure;
- weak-window quality gates;
- dynamic blocklists;
- residual positions;
- VERIFYING stalls;
- reflection and penalty application;
- OOS/walk-forward;
- deployment and identity problems;
- UI/public/private boundary;
- single-service / validation-service separation.

Rolling back to make an old workflow simpler would discard learned constraints and reintroduce known failure modes.

Therefore current `main` is authoritative.

## Validation philosophy

The system should not be promoted because:
- one trade won;
- one session had positive PnL;
- win rate looks high.

Promotion requires evidence that:
- process quality improves;
- repeated mistakes decrease;
- risk remains bounded;
- cost/funding/slippage are accounted;
- behavior changes for evidence-backed reasons;
- behavior remains stable across restarts, sessions, and market regimes;
- out-of-sample behavior remains acceptable.

## Product philosophy

Public NEXUS should not expose or sell the private automatic execution engine as the primary subscription product.

Public/member value:
- market intelligence;
- opportunities;
- risk;
- evidence;
- historical similarity;
- AI explanation;
- decision support;
- alerts;
- research.

Private NEXUS/EATI:
- execution;
- internal learning;
- validation;
- private risk/capital/execution controls.

Enterprise direction:
- private/controlled AI;
- RBAC;
- audit;
- internal data integration;
- knowledge graph / agents;
- API/reporting;
- privacy and non-leakage.

Future product direction, deferred and out of scope for this Security PR:
- Private Auto Trading may use Fed / US macro intelligence as external AI trading intelligence.
- Member Intelligence may include Social / News / Global Financial Intelligence with per-score Evidence Ledger.
- These are product-spec directions only and do not expand the current runtime, validation, or security branch scope.

## DataHunterX competitive direction

The project should learn from DataHunterX's usability and product storytelling without becoming a clone.

Target:
**NEXUS should explain not only what the market is doing, but why a decision is credible, what can invalidate it, what risks exist, what similar history says, and what the system learned from prior outcomes.**

That is the intended differentiation:
Market Intelligence
→ Decision Intelligence
→ Evidence Intelligence.

## Current validation sequence

1. PR #34 final review.
2. Merge hardened security branch to `main`.
3. Deploy hardened Validation Full Engine.
4. Confirm live deployment commit matches merged `main`.
5. Confirm Validation guard active.
6. Create/bind public domain.
7. GET `/health`.
8. Verify unauthenticated protected route is denied.
9. GET-only observational preflight.
10. Confirm fresh Demo account.
11. Confirm `open_positions=0`.
12. Confirm `open_orders=0`.
13. Confirm `MAINNET=false`.
14. Confirm `REAL_MONEY=false`.
15. Confirm `EXCHANGE_WRITE=false`.
16. Founder review.
17. Short bounded validation.
18. Review learning closure.
19. 6H.
20. Review.
21. 12H.
22. 24H.
23. Multi-day / multi-regime.
24. Cross-session learning validation.
25. Promotion Review.

No step implies real-money authorization.
No step authorizes real money.

## Learning boundary

Current bounded `SessionMistakeMemory` is session-local.

This is sufficient to prove:
trade 1 outcome
→ memory
→ trade 2 candidate changed/blocked/penalized.

It is NOT yet sufficient to claim durable long-term cross-session learning.

Cross-session persistence and long-horizon improvement remain explicit validation targets.

## Historical validation status

Stage 1:
- 14/14 paper days complete;
- 11 would-enter;
- 3 would-skip;
- data limitation issue corrected;
- context similarity evidence available.

Tier B:
- two qualifying micro cases achieved historically;
- multiple failures were documented rather than hidden.

P1:
behavior-change evidence cleared historically.

P2:
performance evidence cleared historically.

OOS/walk-forward:
clear_candidate historically.

Production:
denied.

This distinction is essential:
“P1/P2 clear”
does NOT mean
“safe for real money”.

## UI history

Many UI versions existed. Old MVP commit labels are historical only.

Current product direction is:
- simple first screen;
- conclusion before details;
- beginner/intermediate/pro/enterprise adaptation;
- evidence/risk explanations;
- no fake live values;
- mobile eventually designed like a real exchange app, not desktop shrinkage.

## Agent behavior expected

Codex should behave like a senior systems engineer inheriting a high-risk, evidence-driven codebase:
- inspect before editing;
- trace dependencies;
- prefer small patches;
- preserve validation evidence;
- never “solve” a blocker by removing safety;
- never fabricate runtime evidence;
- stop when an external fact such as live URL cannot be proven locally;
- report exact next action.

## Human collaboration loop

The Founder intends to use:
Codex locally for implementation/audit
→ bring Codex output back to ChatGPT
→ discuss architecture/safety/next step
→ return a precise task to Codex.

Therefore Codex outputs should be concise, structured, and easy to review.

The preferred final report pattern is:
current head
→ what was inspected
→ what changed
→ tests
→ safety state
→ blockers
→ next safe step.

## End-state vision

The desired system is an adaptive, auditable capital-intelligence engine whose value comes from:
- learning from outcomes;
- not repeating bad process;
- increasing decision quality;
- maintaining strict risk control;
- proving improvement with evidence;
- compounding only if long-term net expectancy is actually positive.

No document should promise guaranteed win-rate growth or guaranteed capital growth.

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

The next immediate blocker is network/service reachability for the live Validation HTTP endpoints, because the documented public URL returned 404 from the latest observational preflight host.

## Latest authoritative handoff state

GitHub:
- repository: `sam95006/btc_auto`
- branch: `main`
- authoritative HEAD at handoff: `b0c952ca2eb994c7fe514c1ac1d7c5f93be600d3`

Zeabur Validation:
- service: `nexus-bybit-demo-learning-validation`
- service id: `6a82a79aa21454a2cf6b0015`

Current full-engine deploy definition:
`deploy/zeabur_bybit_demo_validation/Dockerfile.full_engine`

Current code safety defaults:
- demo only
- mainnet false
- real money false
- exchange write false
- autonomous disabled until an explicit bounded Founder-gated session.

Historical P1/P2 evidence remains preserved.

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

## DataHunterX competitive direction

The project should learn from DataHunterX's usability and product storytelling without becoming a clone.

Target:
**NEXUS should explain not only what the market is doing, but why a decision is credible, what can invalidate it, what risks exist, what similar history says, and what the system learned from prior outcomes.**

That is the intended differentiation:
Market Intelligence
→ Decision Intelligence
→ Evidence Intelligence.

## Current validation sequence

1. Full Engine live boot — achieved historically in this handoff sequence.
2. Confirm actual live public domain.
3. Confirm deployment identity.
4. GET-only observational preflight.
5. Short bounded validation.
6. Verify closed-loop learning evidence.
7. 6H bounded validation.
8. Review.
9. 12H.
10. 24H.
11. Multi-day / multi-regime.
12. restart/recovery/API failure/weak-market/volatility/loss-streak tests.
13. Promotion review.

No step implies real-money authorization.

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

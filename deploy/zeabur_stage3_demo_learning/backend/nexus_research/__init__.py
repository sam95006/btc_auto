"""NEXUS Phase 5 Gate B + Gate C + Phase 6 Gate C + Gate D — Research Package.

Phase 5 Gate B:  AI Review Cycle, Review Cases, Role Analysts.
Phase 5 Gate C:  Simulator, Risk Engine, Capital Allocator, Reflection, Soak, Replay.
Phase 6 Gate C:  Continuous Autonomous Paper Runtime (paper_controller, exit_policies,
                 simulation_policy, bootstrap, paper_routes).
Phase 6 Gate D:  AI-assisted Review, Performance Validation, Live Soak Framework.
                 reasoning_provider.py — RULES_ONLY / LLM_ASSISTED / LLM_UNAVAILABLE / DEGRADED
                 performance_service.py — per-stream metrics (LIVE_PAPER/SHADOW/REPLAY/MANUAL)
                 review_engine.py — review mode exposed to UI (honest, non-fabricated)
                 live_soak.py — 30m smoke checklist + phased markers (6h/24h/72h)

Research-only: no real orders, no private API, no fleet execution.
Mode: NEXUS_AUTONOMOUS_RESEARCH_MODE ∈ {OFF, SHADOW, PAPER} (default: SHADOW)
LLM providers: openai, anthropic, azure_openai (allowlisted Western only).
"""
__version__ = "6.0.0-gate-d"
PHASE = "6-GATE-D"
RESEARCH_ONLY = True

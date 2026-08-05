# Authority Consolidation V1 — Lane H Summary

Generated: 2026-08-05T03:56:54Z

## Graph summary

- Domains with duplicates: `['checkpoint', 'cost', 'execution', 'fill', 'lifecycle', 'provider_retry', 'risk']`
- Authority claims: 62
- Circular SCC count: 3
- Critical graph findings: 5

## Critical findings

- **registry_critical_competitor**: {"kind": "registry_critical_competitor", "domain": "fill", "module": "backend.nexus_autonomy.execution_simulator_v1_1", "symbol": "AutonomousExecutionSimulatorV1_1", "notes": "Embedded fill policy duplicates fill_engine semantics.", "recommended_action": "migrate_callers"}
- **registry_critical_competitor**: {"kind": "registry_critical_competitor", "domain": "cost", "module": "backend.nexus_strategy_engine.cost_semantics", "symbol": "COST_MODEL_VERSION", "notes": "Divergent COST_MODEL_VERSION string (NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1 vs founder-conservative-v1-1-*). Contract drift risk for strateg
- **registry_critical_competitor**: {"kind": "registry_critical_competitor", "domain": "lifecycle", "module": "backend.nexus_private_control.state_machine", "symbol": "CANONICAL_STATES", "notes": "Founder control-plane lifecycle uses a different state vocabulary (IDLE/STARTING/.../KILLED) vs Session SM. Dual lifecycle authorities.", "
- **registry_critical_competitor**: {"kind": "registry_critical_competitor", "domain": "provider_retry", "module": "backend.nexus_edge_discovery.provider_transport_v23", "symbol": "exponential_backoff_with_jitter", "notes": "Reflection V2.3 transport implements its own backoff/retry rather than importing backend.nexus_provider.retry_p
- **circular_import_scc**: {"kind": "circular_import_scc", "severity": "high", "sccs": [["backend.nexus_execution", "backend.nexus_execution.execution_simulator_v1_1", "backend.nexus_execution.orchestrator_adapter_v1"], ["backend.nexus_demo_execution.geometry_event_sim", "backend.nexus_demo_execution.structural_geometry_quali

## Blockers

- [critical] `COST_MODEL_VERSION_DIVERGENCE` domain=cost — Align strategy cost_semantics versioning with execution cost_model or explicitly namespace as research-proxy (not Session cost authority).
- [critical] `DUAL_LIFECYCLE_VOCABULARY` domain=lifecycle — Keep scoped (session vs control-plane). Block any code that maps states by identical name without an explicit adapter contract.
- [critical] `PARALLEL_RETRY_IMPLEMENTATION` domain=provider_retry — Import parse_retry_after / backoff_with_jitter from backend.nexus_provider.retry_policy; deprecate local copy.
- [critical] `MULTI_SCOPE_AUTHORITY` domain=lifecycle — Domain lifecycle has multiple legitimate scoped authorities; requires explicit adapter contracts before deletion waves.
- [critical] `MULTI_SCOPE_AUTHORITY` domain=checkpoint — Domain checkpoint has multiple legitimate scoped authorities; requires explicit adapter contracts before deletion waves.

## Pass delta

- Pass1 blockers: 5
- Pass2 blockers: 5
- CI gate passed: True

## Policy

- No mass-delete of compatibility modules.
- No merge/deploy from this lane.
- Removals are recommendations only.

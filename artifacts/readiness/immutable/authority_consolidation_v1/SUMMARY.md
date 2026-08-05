# Authority Consolidation V1 — Lane H Summary

Generated: 2026-08-05T03:35:56Z  
Branch: `feature/v11-repository-authority-consolidation`  
Base: `e4f30f9b8abaaade6151a75ef5ac6face53d5135`  
Passes: 2  
CI duplicate-authority gate: **PASSED** (known competitors baselined; new unregistered claimants fail)

## Graph summary

| Metric | Value |
|--------|------:|
| Domains scanned | 7 |
| Authority claims | 60 |
| Claimant modules (nodes) | 38 |
| Import edges | 3865 |
| Domains with duplicates | 7 (all) |
| Circular import SCCs | 3 |
| Critical graph findings | 5 |

### Canonical authorities

| Domain | Canonical |
|--------|-----------|
| execution | `backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11` |
| fill | `backend.nexus_execution.fill_engine.try_fill` |
| cost | `backend.nexus_execution.cost_model.COST_MODEL_VERSION` |
| risk | `backend.nexus_execution.risk_gates.RiskLimits` |
| lifecycle | `backend.nexus_autonomy.session_state_machine` (Session scope) |
| checkpoint | `backend.nexus_recovery.crash_recovery.recover_from_checkpoint` (Session recovery) |
| provider_retry | `backend.nexus_provider.retry_policy` |

### Domains with non-canonical claimants

- **execution** (5): autonomy V1/V1.1 shims, paper + Binance testnet engines
- **fill** (4): autonomy simulators/models, shadow `simulate_fill`
- **cost** (3): strategy `cost_semantics`, demo `trade_geometry`, taxonomy audit
- **risk** (5): product `risk_control_engine`, research/demo risk, autonomy shims
- **lifecycle** (5): control-plane SM, demo SMs, qualification promotion SM
- **checkpoint** (4): control-plane store, reflection v23/v10, edge-discovery helpers
- **provider_retry** (4): edge-discovery transport, shadow HTTP, Stage4 breaker, research supervisor

## Critical findings

1. **Fill duplication** — `nexus_autonomy.execution_simulator_v1_1` still embeds full fill policy (compat shim, not Session authority).
2. **Cost contract divergence** — `COST_MODEL_VERSION` differs between execution (`founder-conservative-v1-1-2026-08-05`) and strategy (`NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1`).
3. **Dual lifecycle vocabularies** — Session SM vs Private Control Plane SM share some names (`RUNNING`/`PAUSED`/`RECOVERING`/`FAILED_SAFE`) with incompatible full sets.
4. **Parallel provider retry** — `nexus_edge_discovery.provider_transport_v23` implements local backoff instead of `nexus_provider.retry_policy`.
5. **Circular import SCCs (3)** — execution package self-cycle; demo geometry pair; research features seed/registry.

## Blockers (5)

1. `COST_MODEL_VERSION_DIVERGENCE` (cost)
2. `DUAL_LIFECYCLE_VOCABULARY` (lifecycle)
3. `PARALLEL_RETRY_IMPLEMENTATION` (provider_retry)
4. `MULTI_SCOPE_AUTHORITY` (lifecycle) — needs explicit adapter before delete waves
5. `MULTI_SCOPE_AUTHORITY` (checkpoint) — session / control-plane / reflection schemas must not cross-resume

## Future removals (recommend only — no deletes)

See `removal_recommendations.json`. Highest priority `future_remove` / `migrate_callers`:

- `backend.nexus_autonomy.execution_simulator_v1` (+ fill/risk constants)
- Migrate callers off `execution_simulator_v1_1` compat shim → `orchestrator_adapter_v1`
- Align or namespace strategy `cost_semantics` vs execution `cost_model`
- Point edge-discovery / Stage4 retry at `backend.nexus_provider`

## How to re-run

```bash
python tools/architecture/run_authority_consolidation.py --passes 2
python tools/architecture/ci_gate_duplicate_authorities.py
python -m pytest tests/architecture -q
```

## Policy

- Owned paths only: `backend/nexus_contracts/`, `tools/architecture/`, `tests/architecture/`, `artifacts/readiness/immutable/authority_consolidation_v1/`
- No mass-delete of compatibility modules
- No merge/deploy from this lane
- Agents A–G paths untouched

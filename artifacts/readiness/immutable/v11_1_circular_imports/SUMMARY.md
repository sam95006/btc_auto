# FOUNDER C6 — Circular Import Remediation

Generated: 2026-08-05T04:08:48Z

## Gate

- circular_SCC_count: **0**
- import_smoke_status: **PASS**
- runtime_startup_status: **PASS**
- typecheck_status: **PASS**
- two-pass: pass1=PASS pass2=PASS
- overall: **PASS**

## Baseline SCCs (3 → 0)

1. Execution package self-cycle (`nexus_execution` ↔ simulator ↔ orchestrator_adapter)
2. Demo geometry cycle (`geometry_event_sim` ↔ `structural_geometry_qualify`)
3. Research features cycle (`feature_seed` ↔ `registry`)

## Techniques

- Shared contracts / leaf modules
- Composition-root extraction
- DI + Protocol (`FeatureRegistryProtocol`)
- Submodule imports (no package `__init__` back-edge)
- TYPE_CHECKING edges ignored by SCC graph extractor

## Blockers

None.

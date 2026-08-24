# Phase A — Safe Folder Classification

Date: 2026-08-24  
Commit baseline at classification start: `a3a7bb8cebc70d6b850507660a306398aaccc9ba` (then advanced by this Phase A commit).

## Decision

**No bulk move of `backend/`, `tests/`, or root entrypoints in Phase A.**

Reason: imports, Docker COPY paths, pytest paths, and GitHub Actions assume current roots (`backend.*`, `config/`, `app.py`, `run.py`).

## What Phase A creates

| Path | Purpose |
|------|---------|
| `nexus/README.md` | Pointer to current NEXUS core under `backend/` |
| `eati/README.md` | Pointer to learning / validation surfaces |
| `integrations/README.md` | Pointer to exchange adapters |
| `configs/README.md` | Pointer to `config/` + demo templates |
| `docs/architecture/` | Repository map + this note |
| `deploy/README.md` | Deployment catalog |

## Phase B (later)

Migrate packages only when:

1. Import graph audited
2. Dockerfile / workflow COPY paths updated in the same change
3. Regression lock still green
4. No Real Money / ARM / Stage3 / member-preview side effects

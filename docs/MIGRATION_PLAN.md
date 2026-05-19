# MIGRATION_PLAN

Last planned: 2026-05-11

## Scope
This plan does **not** move files yet. It identifies where things should go later and the risk of doing so.

## Legend
- `Active runtime`: used by the currently verified running system.
- `Direct move`: can be moved without code changes.
- `Needs import/path changes`: any runtime or reference updates would be required.
- `Risk`: `LOW`, `MEDIUM`, `HIGH`

## Top-level items

| Current location | Suggested new location | Active runtime | Direct move | Needs import/path changes | Risk | Suggested action |
|---|---|---:|---:|---:|---|---|
| `run.py` | keep at root | Yes | No | N/A | HIGH | 保留 |
| `requirements.txt` | keep at root | Yes | No | N/A | MEDIUM | 保留 |
| `Procfile` | keep at root or `tools/deploy/Procfile` later | Yes/Deploy | No | Possibly | MEDIUM | 先保留 |
| `.env` | keep at root | Yes | No | N/A | HIGH | 保留 |
| `.env.example` | keep at root or `docs/examples/` later | Yes/Support | Not now | Maybe | MEDIUM | 先保留 |
| `trading.db*` | keep at root | Yes | No | N/A | HIGH | 保留 |
| `AGENTS.md` | `docs/AGENTS.md` | Yes (instructional) | No | Yes, external references may assume root | MEDIUM | 後續搬移 |
| `ACTIVE_SYSTEM_MAP.md` | `docs/ACTIVE_SYSTEM_MAP.md` | Support | Yes | Low | LOW | 後續搬移 |
| `TARGET_STRUCTURE.md` | `docs/TARGET_STRUCTURE.md` | Support | Yes | Low | LOW | 後續搬移 |
| `MIGRATION_PLAN.md` | `docs/MIGRATION_PLAN.md` | Support | Yes | Low | LOW | 後續搬移 |
| `NEXUS_MASTER.md` | `docs/NEXUS_MASTER.md` | Support | Yes | Low | LOW | 後續搬移 |
| `DEPLOY_NOW.bat` | `tools/deploy/DEPLOY_NOW.bat` | No active runtime | Likely yes | Low | LOW | 後續搬移 |
| `FIX_DEPLOY.bat` | `tools/deploy/FIX_DEPLOY.bat` | No active runtime | Likely yes | Low | LOW | 後續搬移 |
| `fix_versions.ps1` | `tools/deploy/fix_versions.ps1` | No active runtime | Likely yes | Low | LOW | 後續搬移 |

## Runtime directories

| Current location | Suggested new location | Active runtime | Direct move | Needs import/path changes | Risk | Suggested action |
|---|---|---:|---:|---:|---|---|
| `backend/` | keep | Yes | No | N/A | HIGH | 保留 |
| `config/` | keep | Yes | No | N/A | HIGH | 保留 |
| `templates/` | keep | Yes | No | N/A | HIGH | 保留 |
| `static/` | keep | Yes | No | N/A | HIGH | 保留 |
| `static/nexus/` | keep | Yes | No | N/A | HIGH | 保留 |
| `tests/` | keep or `qa/tests/` later | Yes/Support | Not now | Maybe | MEDIUM | 先保留 |
| `logs/` | keep | Yes | Yes | No | LOW | 保留 |

## Candidate archive / non-runtime directories

| Current location | Suggested new location | Active runtime | Direct move | Needs import/path changes | Risk | Suggested action |
|---|---|---:|---:|---:|---|---|
| `legacy/` | `archives/legacy/` | No confirmed | Yes | No known active imports | LOW | 歸檔 |
| `scratch/` | `archives/scratch/` | No active runtime | Yes | `scratch/start_local_server.py` may need operator awareness only | LOW | 歸檔 |
| `_cleanup_candidate/` | `archives/cleanup_candidate/` | No active runtime | Yes | No | LOW | 歸檔 |
| `shared/` | `archives/shared/` or keep as `shared/` until understood | No confirmed | Probably | Unknown future references | MEDIUM | 人工判斷 |
| `assets/` | `archives/assets/` or keep | No confirmed in active chain | Probably | Unknown non-code consumers | MEDIUM | 人工判斷 |

## Environment / dependency directories

| Current location | Suggested new location | Active runtime | Direct move | Needs import/path changes | Risk | Suggested action |
|---|---|---:|---:|---:|---|---|
| `node_modules/` | keep | Tooling only | No | Tooling would break | HIGH | 保留 |
| `venv/` | keep | Environment | No | Runtime would break | HIGH | 保留 |
| `.vscode/` | keep or `tools/editor/` later | No runtime | Yes | Editor-only | LOW | 後續搬移/保留 |
| `.git/` | keep | Repo metadata | No | Repo breaks | HIGH | 保留 |

## Folder-specific notes

### `legacy/`
- Contents look like previous architecture:
  - `legacy/main.py`
  - `legacy/simulator.py`
  - `legacy/webhook.py`
  - `legacy/agents/`
  - `legacy/core/`
  - `legacy/sensors/`
  - `legacy/strategy/`
- Not referenced by the current verified runtime chain.
- Suggested handling: archive as a whole, do not selectively rewrite.

### `scratch/`
- Most temporary files already removed.
- Remaining file:
  - `scratch/start_local_server.py`
- Suggested handling:
  - either move to `tools/local/start_local_server.py`
  - or archive under `archives/scratch/`
- Risk is low because it is not part of active runtime.

### `shared/`
- Current visible content is minimal, but intent is unclear.
- Not confirmed active.
- Suggested handling: keep until a dedicated dependency scan or human decision confirms purpose.

### `assets/`
- Separate from `static/nexus/assets/`
- Not part of the currently verified Flask frontend chain.
- Suggested handling: keep for now; later archive only after visual/content owner review.

## Safest executable next moves
1. Move documentation files into `docs/`
   - Low risk
   - No runtime effect if references are updated later or left as duplicates first
2. Move deployment/helper scripts into `tools/deploy/`
   - Low risk
   - No active runtime imports
3. Move `legacy/`, `scratch/`, `_cleanup_candidate/` under `archives/`
   - Low risk
   - But do it in a dedicated pass with startup verification

## High-risk items
- `backend/`
- `templates/`
- `static/nexus/`
- `config/`
- `run.py`
- `.env`
- `trading.db*`
- `venv/`
- `node_modules/`

## Recommendation
- Next migration pass should start with **docs + tools + archive folders only**.
- Do **not** move runtime code folders until a later dedicated refactor phase is approved.

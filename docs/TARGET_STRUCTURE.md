# TARGET_STRUCTURE

Last planned: 2026-05-11

## Planning goals
- Keep the current active runtime working.
- Reduce top-level clutter without changing runtime behavior.
- Separate runtime code, developer tools, archives, and environment state.
- Preserve Flask `templates/` and `static/` locations until an explicit migration step is approved.

## Recommended final structure

```text
btc_bot/
├─ run.py
├─ requirements.txt
├─ Procfile
├─ .env
├─ .env.example
├─ trading.db
├─ trading.db-wal
├─ trading.db-shm
├─ backend/
│  ├─ api/
│  ├─ audit/
│  ├─ config/
│  ├─ core/
│  ├─ decision/
│  ├─ fleets/
│  ├─ market/
│  ├─ news/
│  ├─ risk/
│  ├─ security/
│  ├─ services/
│  ├─ trading/
│  ├─ wallet/
│  └─ worker/
├─ config/
├─ templates/
├─ static/
│  └─ nexus/
│     ├─ app.js
│     ├─ api_client.js
│     ├─ state_store.js
│     ├─ layout_state.js
│     ├─ assets/
│     ├─ components/
│     ├─ scenes/
│     ├─ utils/
│     └─ animation/
├─ tests/
├─ docs/
│  ├─ AGENTS.md
│  ├─ ACTIVE_SYSTEM_MAP.md
│  ├─ TARGET_STRUCTURE.md
│  ├─ MIGRATION_PLAN.md
│  └─ NEXUS_MASTER.md
├─ tools/
│  ├─ local/
│  ├─ cleanup/
│  └─ deploy/
├─ archives/
│  ├─ legacy/
│  ├─ scratch/
│  └─ cleanup_candidate/
├─ logs/
├─ assets/
├─ shared/
├─ node_modules/
└─ venv/
```

## Folder purposes

### Active runtime
- `run.py`
  - Flask/web bootstrap entry.
- `backend/`
  - Active backend runtime modules.
- `config/`
  - Active root-level configuration shims and security config.
- `templates/`
  - Active Flask templates.
- `static/nexus/`
  - Active frontend application code and assets.
- `tests/`
  - Automated verification for active code.
- `trading.db*`
  - Active SQLite runtime state.
- `.env`, `.env.example`
  - Runtime environment and template.
- `logs/`
  - Runtime and audit logs.

### Tools
- `tools/local/`
  - Local launch helpers such as `start_local_server.py` after future migration.
- `tools/deploy/`
  - Deployment scripts such as `DEPLOY_NOW.bat`, `FIX_DEPLOY.bat`, `fix_versions.ps1`.
- `tools/cleanup/`
  - Cleanup helpers or reports if needed in future.

### Docs
- `docs/`
  - All project documentation and planning markdown should eventually live here.

### Legacy / archive
- `archives/legacy/`
  - Historical system code that is not part of active runtime.
- `archives/scratch/`
  - Disposable screenshots, DOM dumps, local debug outputs, temporary browser profiles.
- `archives/cleanup_candidate/`
  - Temporary quarantine area for future conservative cleanup passes.

### Keep but treat carefully
- `assets/`
  - Not currently part of the confirmed active runtime chain; likely historical or auxiliary material.
- `shared/`
  - Present but not currently confirmed active; may become a utility/archive bucket later.
- `node_modules/`
  - Local tooling dependency area, not active Python runtime.
- `venv/`
  - Python environment, never treat as regular project content.

## Active runtime summary

### Current backend active chain
- `run.py`
- `backend/api/server.py`
- `backend/worker/runner.py`
- runtime modules documented in [ACTIVE_SYSTEM_MAP.md](./ACTIVE_SYSTEM_MAP.md)

### Current frontend active chain
- `templates/nexus_command.html`
- `static/nexus/app.js`
- `static/nexus/api_client.js`
- `static/nexus/state_store.js`
- active components/scenes/assets documented in [ACTIVE_SYSTEM_MAP.md](./ACTIVE_SYSTEM_MAP.md)

## Legacy / archive candidates
- `legacy/`
- `scratch/`
- `_cleanup_candidate/`

## Cannot-touch areas
- `backend/` runtime modules
- `templates/`
- `static/nexus/`
- `config/`
- `trading.db`, `trading.db-wal`, `trading.db-shm`
- `.env`
- `venv/`
- `node_modules/`

## Recommended migration order
1. Move markdown docs into `docs/` only after all references are reviewed.
2. Move helper scripts into `tools/` without changing runtime imports.
3. Move `legacy/`, `scratch/`, `_cleanup_candidate/` under `archives/`.
4. Only then consider whether `assets/` and `shared/` should be archived or repurposed.


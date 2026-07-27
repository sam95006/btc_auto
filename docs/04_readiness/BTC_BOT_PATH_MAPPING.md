# BTC_BOT 遷移後路徑對照（Path Mapping）

**產生時間：** 2026-07-27  
**正式 Repo Root：** `G:\我的雲端硬碟\btc_bot`（顯示名 BTC_BOT）

## 原則

- `docs/evidence` **不是**全部搬到 `docs/04_readiness`
- 永久證據／事故報告／歷史報告保留原語意
- Active Runtime **不得**依賴 C 槽絕對路徑
- `archives/**` 僅封存，不得當正式 Active Worktree

## Path Mapping

| old_path | new_path | category | active_dependency | action |
|---|---|---|---|---|
| `C:\Users\user\.cursor\projects\g-btc-bot\nexus-6h-autonomous-demo\` | `archives/worktrees/nexus-6h-autonomous-demo/` | ARCHIVE_ONLY | false | 保留；不改歷史 |
| `...\nexus-6h-autonomous-demo\docs\evidence\NEXUS_CLEAN_24H_VALIDATION_INTEGRITY_INCIDENT_REPORT.md` | `archives/worktrees/nexus-6h-autonomous-demo/docs/evidence/...` | Incident Report / HISTORICAL | false | 頂部可加 relocated 註記；不改寫結論 |
| `...\nexus-clean24h-local\docs\evidence\NEXUS_WAVE1_DEPLOYMENT_READINESS_CHECK_UPDATED.md` | `archives/worktrees/nexus-clean24h-local/docs/evidence/...` | Readiness / HISTORICAL | false | 保留 HOLD 結論 |
| `docs/evidence/*`（主倉） | 仍為 `docs/evidence/`；索引見 `docs/03_evidence/` | 永久 Evidence | 部分工具會寫入 | **不強制搬移**；新 Readiness 寫 `docs/04_readiness/` |
| `docs/04_readiness/` | `docs/04_readiness/` | Readiness Evidence | true | Clean 24H Zeabur-only／遷移報告 |
| `_wt_*`（根目錄） | `archives/orphan_checkouts/` | ARCHIVE_ONLY | false | Git worktree metadata 仍可能 prunable |
| C 槽 `agent-transcripts`／`terminals` | `archives/cursor_project/`（舊）+ Cursor 可能再生成於 C | ARCHIVE_ONLY | false | IDE 快取屬預期 |

## Active 引用檢查（本輪）

- Active `backend/`／`frontend/`／`Dockerfile`／`Procfile`：**無** C 槽 `g-btc-bot` 絕對路徑
- `tools/` 仍有 `docs/evidence` 寫入路徑 → **ACTIVE_SCRIPT**，語意正確（永久證據目錄），非遷移回歸
- Live 運行碼 `demo_autonomous`：曾不在 HEAD `a06fab2`；本輪已自 Live commit `2761718` 還原至正式樹並套用 Runtime Stall 修復

## 相容性

| 項目 | compatibility_required |
|---|---|
| Zeabur Dockerfile COPY `.` | 是；相對路徑 |
| `.dockerignore` 排除 `archives/` | 是 |
| 本機 Clean 24H JSONL | **否**（已 DEPRECATED） |
| archives worktree 當 Active | **否** |

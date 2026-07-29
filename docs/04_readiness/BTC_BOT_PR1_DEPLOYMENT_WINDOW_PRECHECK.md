# BTC_BOT PR #1 Deployment Window Precheck

**Recommendation**：`PR1_DEPLOYMENT_READY_AWAITING_FOUNDER_APPROVAL`  
**merge=false · deploy=false · observer=false · clean24h=false · exchange_write=false**

本文件僅供 Founder 批准前的獨立部署前驗證。**不建立自動部署 Workflow。不執行 Deploy。**

---

## 1. Current Live SHA／Unknown State

- Live 服務：`nexus-stage3-bybit-demo-learning.zeabur.app`
- Live 部署 Commit：以 Zeabur 現況為準（本輪未強制取得 deploymentCommit；部署後 Smoke 必須驗證）
- Live 倉位狀態（本輪三次唯讀）：**position=0／orders=0**

## 2. Target RC SHA

- `rc_head`：`c2b3c9504bbd011e677e2cfe9ccb707e9944a5ff`
- Branch：`rc/runtime-stall-zeabur-observer`
- Draft PR：[#1](https://github.com/sam95006/btc_auto/pull/1)

## 3. Base SHA

- Base branch：`stage3-demo-learning`
- Base SHA：`2761718d510f35728e5c108003ceb59ab8039dbc`

## 4. Triple 0／0 Snapshot

| Label | captured_at (UTC) | position | orders | ambiguous_intent | lastCycle_send | mainnet | real_money |
|-------|-------------------|----------|--------|------------------|----------------|---------|------------|
| T+0 | 2026-07-29T01:22:31Z | 0 | 0 | false | false | false | false |
| T+60 | 2026-07-29T01:24:03Z | 0 | 0 | false | false | false | false |
| T+180 | 2026-07-29T01:26:33Z | 0 | 0 | false | false | false | false |

證據：`docs/04_readiness/NEXUS_WAVE5_LIVE_TRIPLE_FLAT_SNAPSHOT.json`  
`triple_pass=true` → `deployment_window=AVAILABLE_FOR_PR1_INDEPENDENT_VALIDATION`

## 5. PR Changed Files

- changed_files=**32**
- ahead_by=12／behind_by=0（相對 `stage3-demo-learning`）
- **Wave 2／3／4／5 套件洩漏檔數=0**（無 `nexus_global_shadow`／`nexus_adaptive_policy`／`nexus_real_shadow`／Wave4 UI）
- 範圍：runtime stall／singleton／protection observability／validation observer／RC docs／tests

## 6. CI Runs

| Head | Run | Conclusion |
|------|-----|------------|
| `c2b3c95` | 30321287376 | success |
| `7d01643`（保護觀測） | 30320925228 | success |

Workflow：`rc_runtime_stall_validation.yml`

## 7. Environment Safety（部署時必須維持）

- `AUTONOMOUS_SEND=false`（或等效 Auto Send 關閉）
- `EXCHANGE_WRITE=false`
- `MAINNET=false`
- `REAL_MONEY=false`
- `ARM=false`
- `NEXUS_ZEABUR_CLEAN_OBSERVER=false`
- 不得載入／啟用 Mainnet 金鑰路徑

## 8. Pre-deploy Backup／Snapshot

部署前（Founder 批准後執行，本輪不做）：

1. 記錄目前 Zeabur deploymentCommit／image
2. 再拍一次 Account／Status 唯讀 Snapshot
3. 確認仍為 0／0 且無 ambiguous intent

## 9. Rollback Target

- 回滾至部署前 Zeabur 映像／Commit（記錄於部署當下）
- 程式碼回滾參考：`stage3-demo-learning` @ `2761718d…`（或部署前實際 Live SHA）

## 10. Rollback Procedure

1. Zeabur 將服務指回上一成功部署
2. 等待 `/health` 200
3. 唯讀確認 position／orders／Auto Send／Observer
4. 若仍異常：維持 Observer=false、Auto Send=false，停止進一步操作並回報 Founder

## 11. Deployment Trigger

- **僅 Founder 手動批准後**於 Zeabur 操作
- 禁止本 Repo 自動部署 Workflow
- 禁止 Force Push／自動 Merge

## 12. Read-only Smoke（部署後；本輪不執行）

1. Verify deploymentCommit == `c2b3c95…`（或批准的 RC Head）
2. `/health`
3. `/`
4. `/overview`
5. `/api/nexus/ui-build`
6. Runtime owner count（singleton）
7. Reconciliation
8. Position count == 0（或預期）
9. Open order count
10. Auto Send == false
11. Observer == false
12. Mainnet == false
13. Real money == false
14. No startup order
15. No duplicate controller
16. No unprotected position

任一異常 → **立即 Rollback**。Smoke 階段不得啟用 Observer／Auto Send／Clean24H／Exchange Write。

## 13. Failure Conditions

- 任一次 Snapshot ≠ 0／0
- ambiguous_intent=true
- lastCycle_send=true（非預期）
- mainnet_used 或 real_money_used
- Wave 2～5 範圍混入
- Secret 外洩
- Container／Health 失敗

→ `deployment_window=CLOSED` 或 `PR1_DEPLOYMENT_PRECHECK_PARTIAL_WITH_BLOCKERS`

## 14. Observer State

`observer=false`（預設關閉；本輪不得啟用）

## 15. Auto Send State

`lastCycle_send=false`／Auto Send 預設 false（部署後 Smoke 再確認）

## 16. Clean24H State

`clean24h=false`（不得在本窗口自動開始）

## 17. Founder Approval Required

即使 Precheck 全過，仍停在：

**`PR1_DEPLOYMENT_READY_AWAITING_FOUNDER_APPROVAL`**

不得：Merge · Deploy · Ready for Review · 啟用 Observer · 開始 Clean24H

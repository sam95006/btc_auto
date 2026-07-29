# NEXUS Wave 5 Real Public Shadow Runtime 報告

## 摘要

- **Recommendation**：`WAVE5_REAL_PUBLIC_SHADOW_DRAFT_PR_READY_FOR_REVIEW`
- **模式**：PUBLIC MARKET DATA ONLY／SHADOW SIMULATION／NOT EXECUTED
- **固定槓桿**：25x（`leverage_mutable=false`）
- **套件**：`backend/nexus_real_shadow/`
- **分支**：`feature/wave5-real-public-shadow-runtime`
- **Base**：PR #4 Head `dfbaa61b0e26acd2b0de218e003c40a101e1286d`
- **merge=false／deploy=false／exchange_write=false／live_effect=false**

## 邊界（Boundary）

- 僅允許 Bybit 公開 GET 路徑與公開 WS Topic
- 禁止 auth header、私有 API、POST／PUT／PATCH／DELETE、交易所寫入
- CI 使用 sanitized fixture／mock，不注入任何 Bybit Secret
- 違規即 `SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY`

詳見 [Public Data Boundary Report](./NEXUS_WAVE5_PUBLIC_DATA_BOUNDARY_REPORT.md)。

## 架構（端到端循環）

```
Runtime Reconcile
→ Instrument Discovery（動態 USDT Linear Perpetual）
→ Tier 1／2／3 Funnel Scan
→ Market Quality Gate（fail-closed）
→ Regime → Strategy → Intelligence → Candidate Ranking
→ Six-role Review（RULE_BASED 誠實標籤）
→ Risk Critic Veto → Mistake Guard → Portfolio（max 2）
→ Adaptive Policy（固定 25x）
→ Real-price Shadow Lifecycle／Protection／Exit
→ Outcome → Reflection → Champion／Challenger（最高 SHADOW_CHAMPION_CANDIDATE）
→ Persistence／Recovery → Wave 4 UI 真實資料綁定
```

## API（唯讀）

- `/api/nexus/shadow/runtime/status`
- `/api/nexus/shadow/runtime/workers`
- 並透過 `bind_wave5_cycle_to_shadow_api` 刷新既有 Wave 2／4 shadow overview 狀態
- UI：Overview／Universe 優先讀取 Wave 5 runtime funnel；無資料時 `NO_DATA`（不回退合成 128／24／6）

## 測試

| 套件 | 結果 |
|------|------|
| Wave 5 | ≥150（本輪 191 passed） |
| Wave 2／3／4 回歸 | 0 regression（離線驗證） |
| Frontend typecheck | PASS |
| Security scan | violations=0 |

## Soak

短時間 mock／container soak（非 Clean 24H）。見 [Soak Report](./NEXUS_WAVE5_SHADOW_RUNTIME_SOAK_REPORT.md)。

## Live 唯讀證據（Wave 5 起始）

- `position_count=0`、`open_order_count=0`
- 不得因此 Merge／Deploy；僅通知 Founder：PR #1 可進入獨立 Deployment Window 驗證
- 詳見 `NEXUS_WAVE5_LIVE_READONLY_START_SNAPSHOT.json` 與 `BTC_BOT_DEPLOYMENT_WINDOW_STATE.json`

## 繼承 Wave 4 非阻擋債務

- 部分次要 Viewport Screenshot
- axe color-contrast／tablist 排除項
- 部分 Quant Workbench 重用既有 Panel

僅在 Wave 5 精修，不重開 PR #4。

## 固定禁令（本輪維持）

LiveEffect=false · ExchangeWrite=false · Merge=false · Deploy=false · Mainnet=false · RealMoney=false · Observer=false · Clean24H=false · ForcePush=false

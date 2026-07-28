# BTC_BOT Wave 2 — Global Market Six-role Shadow Intelligence

## 1. Started At
2026-07-28T10:30:00+08:00

## 2. Ended At
2026-07-28T12:10:00+08:00（約）

## 3. Actual Duration
約 1.5–2 小時（平行開發線，不含等待 Live 平倉）

## 4. Base SHA
`c2b3c9504bbd011e677e2cfe9ccb707e9944a5ff`

## 5. Branch
`feature/wave2-global-market-six-role`  
Worktree：`C:\Temp\BTC_BOT_WAVE2_GLOBAL_SIX_ROLE`  
Draft PR Base：`rc/runtime-stall-zeabur-observer`

## 6. Commits
見 Checkpoint `commits[]`（依 Work Package 小型 scoped commit）。

## 7. Existing Components Reused
- `demo_autonomous` Universe filter／gate 模式：SELECTIVE_PORT（移除固定 MAJOR_HINTS 作為正式 Universe）
- `nexus_research/roles.py`：EVIDENCE_ONLY（角色命名參考）
- Runtime／Observer／Protection Contract（Base RC）：作為安全邊界沿用，未改 Live 執行路徑

## 8. Provenance
`docs/04_readiness/BTC_BOT_WAVE2_GLOBAL_COMPONENT_PROVENANCE.json`

## 9. Deprecated Four-fleet Components
- `BTC_FLEET`／`ETH_FLEET`／`SOL_FLEET`／`PEPE_FLEET`
- `ShadowFleetCoordinator`
- 固定四市場 Portfolio 配額／固定四市場 API／四艦隊 UI
- 分類：DEPRECATED（不得作為新 Domain Boundary）
- `fleet_id` 僅允許在 compat adapter 讀取後丟棄（`deprecated=true`）

## 10. Global Market Contracts
`backend/nexus_global_shadow/contracts.py` — 無 `fleet_id` 必填欄位；模式僅 SHADOW／REPLAY／FIXTURE／PAPER。

## 11. Dynamic Universe
`DynamicMarketUniverseProvider` + `MarketUniverseBuilder` + `UniverseFilterEngine` — 注入式 Provider，禁止固定四幣正式 Universe。

## 12. Market Quality
`MarketQualityEvaluator` — 缺失／STALE／UNKNOWN 不得自動 PASS。

## 13. Universe Funnel
`total → usdt_perp → trading → fresh → quality_pass → eligible／excluded`；Provider 失敗標記 `UNIVERSE_DEGRADED`／`UNIVERSE_UNAVAILABLE`。

## 14. Regime
正式 Regime 含 UNCERTAIN；證據不足不得猜測。

## 15. Strategy Router
UNCERTAIN 強制 BLOCK；Dynamic Grid／Pairs／Funding DN 標記 Experimental。

## 16. Intelligence
`GlobalMarketIntelligenceComposer`；新聞不可用時 `news_context_availability=UNAVAILABLE`；BTC／ETH 僅 Benchmark Context。

## 17. Candidate Ranking
可重現排序（hash tie-break）；禁止隨機／牆鐘分數／固定市值加分。

## 18. Six Roles
Market Context／Market Structure／Risk Critic／Portfolio Manager／Performance Analyst／Reflection Analyst。

## 19. Risk Critic Veto
BLOCK／UNKNOWN → 強制否決；共識不可覆蓋；無 Feature Flag 略過。

## 20. Portfolio Policy
`max_open_positions=2`，`max_pending_orders=2`，風險與集中度門檻如 Spec。

## 21. Multi-position Shadow
最多 2 個 Shadow Position／2 個 Pending Intent（模擬）。

## 22. Lifecycle
完整狀態機 + `assert_transition`；禁止非法跳轉。

## 23. Exit Simulation
Shadow 模擬 Exit／Protection；不映射 Exchange Write。

## 24. Outcome
完整／不完整欄位誠實標記；禁止假 0 偽裝觀測。

## 25. Reflection
EATI 結構化反思欄位。

## 26. Learning Patch
狀態至 SHADOW_APPLIED；禁止 LIVE_APPLIED／AUTO_PROMOTED。

## 27. Replay
Deterministic harness + 代表性／Fault Fixtures（標記 FIXTURE／NOT_LIVE）。

## 28. Walk-forward
≥ 3 folds；保存 dataset hash 與漏斗計數。

## 29. OOS
與 In-sample 隔離；樣本不足 → `INSUFFICIENT_SAMPLE`。

## 30. Persistence
InMemory／File；Postgres Stub；Evidence append-only + checksum。

## 31. Worker Boundary
Worker Health Registry；不以 `running=true` 單點判斷健康。

## 32. API
唯讀 `GET /api/nexus/shadow/*`（19 端點）；`register_shadow_routes` 軟掛載於 `server.py`。

## 33. UI
`/global-shadow` — Global Market Shadow Intelligence Workspace；3 秒／30 秒／3 分鐘層；保留既有路由。

## 34. Operational Scoreboard
無 `fleet_health` 正式欄位。

## 35. Tests
Wave 2 目標測試 **97 passed**（≥80）：
- `tests/test_wave2_global_market_six_role.py`
- `tests/test_wave2_shadow_api_routes.py`

## 36. Full Suite
本輪未宣稱 Full Suite 全綠；既有 Baseline Debt 保留（RC 已知約 12 failed）。

## 37. Baseline Debt
誠實保留；`release_delta_regression` 以 RC Base 為準，本 Wave 未引入 Live 執行回歸意圖。

## 38. Security
無 Exchange Secret 進入 Wave 2 CI；無 Mainnet／Real Money 能力新增。

## 39. Exchange Write Scan
Wave 2 套件與 API 固定 `exchange_write=false`；無新增寫入路由。

## 40. Four-fleet Violation Scan
`active_architecture_violation_count=0`（`backend/nexus_global_shadow`）。

## 41. Docker／Container
CI workflow 含 docker build + 短時 container smoke（非部署）。

## 42. Live Effect
`live_effect=false`。未改 Live Env／Auto Send／持倉／TP／SL。未 Deploy。未觸碰 PR #1。

## 43. Draft PR
建立 Draft PR：`feature/wave2-global-market-six-role` → `rc/runtime-stall-zeabur-observer`  
`draft=true`／`merge=false`／`deploy=false`

## 44. Known Limitations
- Postgres 為 Stub，本輪不建 Zeabur DB
- Provider 為可注入／測試用；正式 24／7 Bybit 全市場掃描需後續雲端 Worker 部署（本輪禁止部署）
- UI 以 API／Fixture 呈現漏斗；真實長時間掃描需後續啟用 Worker
- Full Suite 技術債未在本輪清零
- 未啟用 Observer／Clean 24H／Mainnet

## 45. Recommendation
**WAVE2_GLOBAL_SIX_ROLE_DRAFT_PR_READY_FOR_REVIEW**

## 46. Next Founder Decision
1. Review Draft PR（不 Merge／不 Deploy）
2. Live 若自然 0／0 → 另開 PR #1 Deployment Window 驗證（與 Wave 2 解耦）
3. 後續再決定是否將 Wave 2 對齊 `stage3-demo-learning` 並規劃雲端 Shadow Worker（仍需獨立批准）

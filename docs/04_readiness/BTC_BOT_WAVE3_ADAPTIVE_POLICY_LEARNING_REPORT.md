# BTC_BOT Wave 3 Adaptive AI Trading Policy — Learning Report

> **狀態**：SHADOW ONLY · 固定 25X · 無交易所寫入 · Draft PR URL：**pending**

---

## 1. 文件目的

本報告記錄 Wave 3「Adaptive AI Trading Policy」在 `feature/wave3-adaptive-policy-learning` 分支上的實作檢查點，基於 PR #2 凍結 HEAD `cd08d07b221e7c01fb15dd1b78d61ad7c0430bac`。

## 2. 工作樹與分支

- 工作樹：`C:\Temp\BTC_BOT_WAVE3_ADAPTIVE_POLICY`
- 分支：`feature/wave3-adaptive-policy-learning`
- 不修改 PR #1 / PR #2 分支

## 3. 安全邊界（硬約束）

| 約束 | 值 |
|------|-----|
| 模式 | SHADOW ONLY |
| 交易所寫入 | false |
| 主網 / 真實資金 | false |
| 固定槓桿 | **25X（不可變）** |
| AI 可改槓桿 | **false** |
| 保證金下限 / 上限 | 20 / 500 USDT |

## 4. 套件根目錄

`backend/nexus_adaptive_policy/`

## 5. 常數匯出（`__init__.py`）

- `FIXED_LEVERAGE = 25`
- `TARGET_NET_OOS_WIN_RATE = 0.60`
- `MIN_MARGIN = 20`
- `MAX_MARGIN = 500`
- `SCHEMA_VERSION = wave3.adaptive_policy.v1`

## 6. 憲章層（`constitution.py`）

- `LeverageConstitution`：拒絕 `leverage != 25` → `IMMUTABLE_LEVERAGE_VIOLATION`
- 拒絕 3x / 10x / 50x / 100x 等禁止槓桿檔
- `ImmutableSafetyPolicy`：`isolated_only`、禁止 cross / martingale / 加倉攤平 / 自動補保證金
- Patch 嘗試修改不可變欄位 → `IMMUTABLE_SAFETY_POLICY`

## 7. 交易案例（`trade_case.py`）

- `TradeCase` + `ProcessQualityVerdict` 五種判決
- **虧損 ≠ 自動 STRATEGY_FAILURE**（僅 BAD_PROCESS_* 或證據不足邏輯分離）

## 8. 失敗分類（`failure_taxonomy.py`）

多因 `FailureClassification`：含 `ENTRY_TOO_EARLY`、`CHASE_ENTRY`、`REPEATED_KNOWN_MISTAKE` 等 18 類。

## 9. 錯誤記憶（`mistake_memory.py`）

- `MistakeMemoryStore`
- `MistakeSimilarityIndex`
- `FailureSignature`（穩定 digest）

## 10. 相似度與進場守衛（`similarity.py`）

- `MistakeSimilarityEngine`
- `PreTradeMistakeGuard`
- `RecurringErrorEscalationPolicy`
- 動作：`ALLOW` … `BLOCK`（共 8 種），**永不改槓桿**

## 11. 深度反思（`reflection.py`）

- `DeepReflectionEngine`
- `CounterfactualAnalyzer`（9 種反事實）
- `LearningProposalGenerator`：**僅可執行提案**（含 action / parameter / value）

## 12. 動態政策（`policy.py`）

- `DynamicTradingPolicy` / `DynamicOrderPolicy` / `DynamicExitPolicy` / `DynamicRiskAllocationPolicy`
- `PolicySnapshot` / `PolicyDecisionTrace`

## 13. 自適應控制器（`adaptive_controller.py`）

- `AdaptivePolicyController` → `ShadowOrderIntent`（槓桿恒 25）
- 保證金 = min(AI 建議, 風險預算, 止損距離, 組合剩餘, 流動性, 滑點, 500)
- `< 20` → `SKIP` + `RISK_BUDGET_BELOW_MINIMUM`

## 14. 進場後不變式（`post_entry.py`）

可：收緊止損 / BE / 追蹤 / 部分平倉 / 體制退出 / 資料品質退出 / 時間止損  
不可：放寬止損、增加最大虧損、攤平、提高槓桿、cross、自動補保證金、取消保護

## 15. 學習 Patch（`patches.py`）

- `LearningPatch` + `ImmutablePatchGuard`
- 狀態：`PROPOSED` / `SHADOW_APPLIED` / `REJECTED`

## 16. 冠軍 / 挑戰者（`champion_challenger.py`）

- 最高狀態：`SHADOW_CHAMPION_CANDIDATE`
- **禁止** `LIVE_APPLIED` / `AUTO_PROMOTED`
- `PromotionGate`：expectancy↑、PF 不惡化、DD 不惡化、錯誤復發↓、樣本足夠、無不可變變更

## 17. 指標（`metrics.py`）

- 成本調整後淨 OOS 勝率、expectancy、PF、回撤、錯誤復發率、劣質流程率
- 目標狀態：`TARGET_NOT_REACHED` / `INSUFFICIENT_SAMPLE` / `PROMISING` / `TARGET_REACHED_SHADOW_ONLY`
- **絕不偽造達標**

## 18. 持久化（`persistence.py`）

- `InMemoryAdaptivePolicyStore`
- `FileAdaptivePolicyStore`（append-only + checksum）
- `PostgresAdaptivePolicyStoreStub`

## 19. 唯讀 API（`api_routes.py`）

前綴：

- `/api/nexus/shadow/learning/*`
- `/api/nexus/shadow/policy/*`

空資料 → `data_status: NO_DATA`（非合成）

## 20. 伺服器軟接線

`backend/api/server.py` 以 try/except 註冊 `register_adaptive_policy_routes`，不影響 live 啟動。

## 21. 前端頁面

- `frontend/src/pages/AiLearningLabPage.tsx`
- 路由 `/ai-learning-lab`
- `SidebarNav` 項目「AI Learning Lab」
- 3s / 30s / 3min 三層；固定 25X；空資料 NO_DATA

## 22. CI 工作流

`.github/workflows/wave3_adaptive_policy_learning_validation.yml`

- 僅 `feature/wave3-adaptive-policy-learning`
- `FIXED_LEVERAGE=25`、`AI_CAN_CHANGE_LEVERAGE=false`
- Wave 3 + Wave 2 測試、槓桿掃描、typecheck、docker（可選）

## 23. 檢查點 JSON

`docs/04_readiness/BTC_BOT_WAVE3_ADAPTIVE_POLICY_CHECKPOINT.json`

## 24. Wave 2 相容性

Wave 2 真實空 API 保持不變；未重新引入預設 fixture funnel。

## 25. 測試覆蓋

| 套件 | 測試檔 | 收集數 |
|------|--------|--------|
| Wave 3 | `tests/test_wave3_adaptive_policy_learning.py` | **139** |
| Wave 2 | `test_wave2_global_market_six_role.py` + `test_wave2_shadow_api_routes.py` | 100 |
| **合計** | | **239 passed** |

## 26. 憲章測試要點

- 25X 通過；3/10/50/100/24/26 拒絕
- Patch 改 leverage / cross / martingale 拒絕

## 27. 流程品質測試要點

- GOOD_PROCESS_LOSS 非 strategy failure
- INCOMPLETE_EVIDENCE 非 strategy failure

## 28. 守衛升級測試要點

- 重複 CHASE_ENTRY 簽名 → occurrence 遞增
- REPEATED_KNOWN_MISTAKE ×2 → BLOCK

## 29. 控制器測試要點

- 正常路徑 margin ∈ [20, 500]、leverage=25
- 低預算 → RISK_BUDGET_BELOW_MINIMUM

## 30. Post-entry 測試要點

- 全部 ALLOWED / FORBIDDEN 枚舉覆蓋
- TIGHTEN_STOP 放寬距離拒絕

## 31. 指標真實性

- 空樣本 → INSUFFICIENT_SAMPLE
- 5 筆全勝 → 不會 TARGET_REACHED_SHADOW_ONLY

## 32. API 空狀態

- `/learning/overview` → NO_DATA、target_status=INSUFFICIENT_SAMPLE
- 無假 60% 勝率欄位

## 33. 持久化 checksum

- append 後 `verify()` 為真
- File store 重載後校驗通過

## 34. 整合流程

case → failure → mistake → reflection → patch → API state → overview OK

## 35. 禁止區域（未觸碰）

- 核心 fleet 策略引擎
- 交易所下單 / live ARM
- PR #1 / PR #2 分支
- 前端交易下單 UI

## 36. 環境變數（CI）

```
FIXED_LEVERAGE=25
AI_CAN_CHANGE_LEVERAGE=false
EXCHANGE_WRITE=false
```

## 37. 操作建議

1. 本地：`python -m pytest tests/test_wave3_adaptive_policy_learning.py tests/test_wave2_*.py -q`
2. 前端：`cd frontend && npm run typecheck`
3. 由 parent agent commit（本子代理不 commit / push / PR）

## 38. 已知限制

- Postgres store 為 stub，無 live DB
- Docker smoke 在 CI 標記 `continue-on-error: true`
- 學習資料預設空；需 runtime 餵入才會 API OK

## 39. 後續 Wave 3 工作（非本 PR）

- Shadow 24h 連續觀測
- Champion 晉升人工審核閘
- 與 Wave 2 pipeline 事件匯流

## 40. 證據路徑

- 檢查點：`docs/04_readiness/BTC_BOT_WAVE3_ADAPTIVE_POLICY_CHECKPOINT.json`
- 本報告：`docs/04_readiness/BTC_BOT_WAVE3_ADAPTIVE_POLICY_LEARNING_REPORT.md`

## 41. 簽核欄（待填）

| 角色 | 姓名 | 日期 | 結果 |
|------|------|------|------|
| 實作 | Agent | 2026-07-28 | IMPLEMENTATION_CHECKPOINT |
| 審核 | pending | — | — |

## 42. Draft PR

- URL：**pending**（由 parent 建立 PR 後更新）

---

*Wave 3 Adaptive Policy · SHADOW ONLY · Fixed 25X · NO_EXCHANGE_WRITE*

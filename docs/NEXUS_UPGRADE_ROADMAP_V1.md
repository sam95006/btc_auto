# NEXUS Upgrade Roadmap v1.0

## 目的
這份文件把 `NEXUS AI Trading System` 從目前的「半自主交易系統」升級到「可持續自學、可治理、可多代理協作、可安全上真實交易」的路線拆成可施工階段。

原則：
- 先補感知，再補學習，再補組合管理，再補代理能力，最後補 live 安全治理
- 每一階段都以 backend 為主
- 不先碰 UI，除非該階段明確需要顯示新狀態
- 所有策略調整都必須先經過 Risk / HQ 審核，不做無約束自我改寫

---

## Stage 1：Perception Upgrade

### 目標
讓系統看到的市場與事件上下文更完整、更可信。

### 要補的能力
- Spot user stream 穩定化
- Spot/Futures order book / spread / liquidity / slippage 感知
- Funding / open interest / liquidation / basis 感知
- 宏觀 / 聯準會 / 加密事件標準化
- 多來源資料交叉驗證
- 資料品質分數

### 建議新增 backend 模組
- `backend/market/orderbook_sync_service.py`
- `backend/market/liquidity_context_engine.py`
- `backend/market/derivatives_context_service.py`
- `backend/news/event_normalization_service.py`
- `backend/market/data_quality_engine.py`

### 建議資料結構
- `market_context_snapshot`
- `orderbook_summary`
- `liquidity_snapshot`
- `derivatives_context`
- `event_registry`
- `data_quality_status`

### 驗收標準
- Spot/Futures stream health 都可機器可讀
- 每個 active symbol 都能輸出 spread / liquidity / slippage 指標
- 能輸出 funding / OI / liquidation / basis 摘要
- 新聞事件可分類成 `macro / fed / crypto / regulatory / exchange / whale`
- `/api/nexus/state` 新增欄位但不破壞舊欄位

---

## Stage 2：Decision Audit Upgrade

### 目標
讓每筆交易決策都可解釋、可追溯、可回放。

### 要補的能力
- decision trace
- signal contribution breakdown
- why-not explanation
- risk override reason
- round table 決策結果機器可讀化強化

### 建議新增 backend 模組
- `backend/decision/decision_trace_store.py`
- `backend/decision/explanation_engine.py`
- `backend/decision/decision_audit_service.py`

### 建議資料結構
- `decision_trace`
- `strategy_explanation`
- `risk_override_log`
- `proposal_rejection_reason`

### 驗收標準
- 每筆新 proposal 都有 trace id
- 可回答「為什麼下這筆」「為什麼不用另一筆」
- 會議決策可被 runtime / learning / risk 直接讀取

---

## Stage 3：Learning Closed Loop

### 目標
從「會記錄輸贏」升級成「會審核地學習」。

### 要補的能力
- confidence calibration 自我修正
- signal weight recommendation 審核落地
- 依 market regime 分開學習
- 高槓桿失敗樣本自動降權
- 各艦隊學習隔離

### 建議新增 backend 模組
- `backend/learning/confidence_calibration_engine.py`
- `backend/learning/regime_memory_store.py`
- `backend/learning/learning_review_queue.py`
- `backend/learning/strategy_weight_reviewer.py`

### 建議資料結構
- `confidence_calibration_store`
- `signal_weight_recommendation_store`
- `regime_learning_memory`
- `learning_review_item`

### 驗收標準
- 每筆交易結果都能回寫 calibration
- recommendation 有審核狀態：`draft / approved / rejected / applied`
- 不同艦隊的學習資料不互相污染

---

## Stage 4：Portfolio Brain

### 目標
讓 HQ 從資金分配器升級成真正的組合管理中樞。

### 要補的能力
- 全局曝險統一盤點
- 跨艦隊 hedge
- correlation / beta 管理
- drawdown-aware capital rebalance
- sector / theme exposure control

### 建議新增 backend 模組
- `backend/portfolio/exposure_aggregator.py`
- `backend/portfolio/hedge_recommendation_engine.py`
- `backend/portfolio/capital_rebalance_engine.py`
- `backend/portfolio/theme_exposure_controller.py`

### 建議資料結構
- `portfolio_exposure_snapshot`
- `fleet_capital_plan`
- `hedge_recommendation`
- `reserve_action_plan`

### 驗收標準
- HQ 可輸出全局曝險矩陣
- 各艦隊的資本分配有明確原因
- 可對高相關曝險發出限制或 hedge 建議

---

## Stage 5：Multi-Agent Deliberation

### 目標
讓各站長與艦隊長從被動規則模組升級成可提案、可辯論、可協調的 agent 組織。

### 要補的能力
- machine-readable 世界頻道 / 站內頻道
- 多代理提案與排序
- conflict resolution
- counterfactual simulation
- task planning / delegation
- 自我檢查與反事實推理

### 建議新增 backend 模組
- `backend/agents/agent_dialogue_bus.py`
- `backend/agents/proposal_ranker.py`
- `backend/agents/conflict_resolution_engine.py`
- `backend/agents/counterfactual_simulator.py`
- `backend/agents/task_planner.py`

### 建議資料結構
- `agent_dialogue_memory`
- `proposal_queue`
- `debate_summary`
- `counterfactual_result`
- `delegated_task_record`

### 驗收標準
- 各站可輸出結構化提案，不只是文字
- 重大衝突下可生成多方案排序
- 系統可追溯哪個 agent 推動了最終決策

---

## Stage 6：Execution Governance

### 目標
提升自治程度，但仍維持硬安全邊界。

### 要補的能力
- proposal -> review -> execute pipeline
- 多級 kill switch
- loss circuit breaker
- anomaly auto-freeze
- manual override
- live shadow mode

### 建議新增 backend 模組
- `backend/governance/execution_governor.py`
- `backend/governance/approval_gate.py`
- `backend/governance/kill_switch_service.py`
- `backend/governance/anomaly_freeze_engine.py`

### 建議資料結構
- `execution_governance_rules`
- `approval_record`
- `kill_switch_state`
- `shadow_mode_status`

### 驗收標準
- 每筆高風險動作都有治理路徑
- 可人工接管
- 可對異常行為自動 freeze

---

## Stage 7：Autonomous Trader

### 目標
在治理前提下，接近真正 autonomous trader。

### 要補的能力
- 自主任務規劃
- 自主 regime adaptation
- 長短期績效平衡
- 自動切換停機 / 觀察 / 減倉模式
- 自主提出策略輪替建議

### 建議新增 backend 模組
- `backend/autonomy/agent_planner.py`
- `backend/autonomy/regime_adaptation_engine.py`
- `backend/autonomy/performance_horizon_balancer.py`
- `backend/autonomy/autonomy_policy_engine.py`

### 建議資料結構
- `autonomy_policy`
- `regime_adaptation_log`
- `strategy_rotation_candidate`
- `system_mode_transition_record`

### 驗收標準
- 可在長時間運行中維持穩定模式切換
- 自治提案不會繞過 governance
- live 仍需人工最高級授權

---

## 大語言模型 API 評估

### 結論
**值得加，但不能放在 execution 最內圈。**

最適合加入 LLM API 的位置：
- Stage 2：Decision Audit Upgrade
- Stage 5：Multi-Agent Deliberation
- Stage 7：Autonomous Trader

### 加入後最有價值的場景
1. **新聞與事件解釋**
- 把原始新聞轉成結構化市場敘事
- 辨識事件衝突、政策語氣、風險級別

2. **決策可解釋化**
- 為每筆 proposal 產出人可讀與機器可讀 explanation
- 幫助 HQ / Risk 審核 learning recommendation

3. **多代理 deliberation**
- 讓 HQ / News / Radar / Fleet 先提出各自結論
- 用 LLM 做提案整合、爭議辨識、方案排序

4. **反事實推演**
- 若不進場、若減倉、若延後 30 分鐘會怎樣

### 不適合直接交給 LLM 的位置
- 下單最終執行
- 最終槓桿決定
- 風控底線
- live 資金額度
- kill switch

### 最安全接法
- `LLM 只做 analysis / proposal / deliberation / explanation`
- 最終執行仍經：
  `Signal -> Risk -> Execution Router -> Exchange`

### 建議模式
- `Deterministic Core + LLM Advisory Layer`

也就是：
- 核心交易與風控仍然是 deterministic backend
- LLM 做高階語義理解與多代理協調
- 任何權重更新都先進 recommendation queue

這樣你會得到：
- 更像「會思考」的 AI
- 但不會失去交易系統最重要的安全控制

---

## 建議施工順序
1. Stage 1：Perception Upgrade
2. Stage 2：Decision Audit Upgrade
3. Stage 3：Learning Closed Loop
4. Stage 4：Portfolio Brain
5. Stage 5：Multi-Agent Deliberation
6. Stage 6：Execution Governance
7. Stage 7：Autonomous Trader

一句話：
先讓系統看得清楚，再讓它學得正確，再讓它管得住全局，最後才給它更高自治權。

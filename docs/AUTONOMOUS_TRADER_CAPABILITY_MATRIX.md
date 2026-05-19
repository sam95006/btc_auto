# Autonomous Trader Capability Matrix

## 目的
這份表把 NEXUS 目前能力、能力缺口、風險、升級優先級整理成可追蹤矩陣。

等級說明：
- `L0` 幾乎沒有
- `L1` 有概念或部分資料
- `L2` 可運行
- `L3` 半自主
- `L4` 高自主
- `L5` 接近真正 autonomous trader

---

## Capability Matrix

| 能力領域 | 目前狀態 | 等級 | 主要缺口 | 風險 | 優先級 |
|---|---|---:|---|---|---|
| Spot/Futures 帳戶同步 | Futures 強，Spot REST 可用，Spot stream 降級補償 | L2-L3 | Spot stream 穩定化、事件對帳 | 錯用舊狀態 | 高 |
| 市場微結構感知 | 只有價格與部分衍生資料 | L1-L2 | order book、spread、liquidity、slippage | 進場品質差 | 高 |
| 衍生品上下文 | funding 有基礎，OI/liquidation/basis 不完整 | L1-L2 | OI、basis、liquidation heat | 高槓桿失真 | 高 |
| 新聞/宏觀感知 | 已有分類與輸入 | L2 | 事件標準化、品質分數、多來源交叉驗證 | 誤判事件 | 高 |
| 決策分數 | confidence / risk / leverage 已有 | L3 | explanation、why-not、trace | 難審核 | 高 |
| 交易執行 | router / idempotency / exchange sync 已有 | L3 | 更強 governance | 錯單風險 | 高 |
| 動態槓桿 | 已完成 confidence + bracket + risk cap | L3 | 長期校正與失敗學習連動 | 高槓桿失控 | 中高 |
| 學習記錄 | journal / result / failure / recommendation 已有 | L2 | calibration、審核後落地、regime memory | 只記錄不進化 | 高 |
| 組合管理 | HQ reserve / fleet allocation 已有 | L1-L2 | portfolio optimizer、hedge、rebalance | 系統只會局部最優 | 高 |
| 多代理協作 | 有站點與角色分工 | L2 | 結構化提案、辯論、衝突解決 | 討論不可計算 | 中高 |
| 反事實推演 | 幾乎沒有 | L0-L1 | counterfactual simulation | 缺替代方案評估 | 中高 |
| 自主規劃 | 幾乎沒有 | L0-L1 | task planning / delegation | 不像真正 agent | 中高 |
| 自治治理 | 有風控與 execution router | L2 | approval gate、kill switch、shadow live | live 風險高 | 高 |
| Live 安全層 | 僅禁止 live | L1 | human override、quota isolation、compliance | 不可碰真錢 | 高 |

---

## 目前已經會自主做的事

- 自動同步 Binance testnet 帳戶與持倉
- 自動抓價格、新聞、部分外部市場資料
- 自動計算 confidence / risk / leverage proposal
- 自動經過 Risk Engine 與 Execution Router
- 自動送 Spot / Futures testnet 單
- 自動寫入 trade_journal / trade_result / failure reason
- 自動生成 round table 機器可讀記憶
- 自動保護 single instance / snapshot write / duplicate order

---

## 目前不能自主做的事

- 不能自由發明新策略
- 不能直接修改核心風控與資金規則
- 不能直接提高最大槓桿上限
- 不能直接切到 live
- 不能繞過 HQ / Risk / Execution Router
- 不能自行批准 learning recommendation 生效
- 不能做成熟的多代理 deliberation
- 不能做長鏈條反事實推演與任務規劃

---

## 距離真正 autonomous trader 還差多少

### 粗估位置
- 目前整體約在 **55% ~ 65%**
- 定位：**L3 半自主交易系統**

### 為什麼不是更低
因為已經有：
- 同步層
- 執行層
- 風控層
- 槓桿控制
- learning 資料模型
- round table 記憶
- 多角色結構

### 為什麼也不是更高
因為還缺：
- 完整感知
- 真正閉環學習
- 組合管理
- 高級代理能力
- live 安全治理

---

## 大語言模型 API 評估矩陣

| 應用位置 | 是否適合加 LLM | 建議程度 | 原因 |
|---|---|---|---|
| 新聞/事件理解 | 是 | 很高 | LLM 對語義、敘事、事件衝突判斷非常有價值 |
| 決策可解釋化 | 是 | 很高 | 可生成 structured explanation 與 why-not |
| 多代理 deliberation | 是 | 很高 | 可做提案整合、衝突辨識、排序 |
| 反事實推演 | 是 | 高 | 適合做 scenario exploration |
| 最終下單 | 否 | 禁止 | 必須由 deterministic core 執行 |
| 最終槓桿 | 否 | 禁止 | 必須受 Risk / bracket 約束 |
| kill switch | 否 | 禁止 | 必須是硬安全規則 |
| live 資金額度 | 否 | 禁止 | 必須受 governance 控制 |

### 建議接法
- **LLM Advisory Layer**
- 不做 `LLM Direct Execution`

即：
- LLM 負責提案、摘要、辯論、解釋
- deterministic backend 負責風控、槓桿、路由、執行

---

## 最值得先做的三件事

1. **Perception Upgrade**
- 因為看不準，後面學習都會歪

2. **Learning Closed Loop**
- 因為現在還只是會記錄，不是真正變準

3. **Portfolio Brain**
- 因為多艦隊交易如果沒有組合腦，很容易局部最佳、全局失控

---

## 最終目標定義

真正的 autonomous trader，不是：
- 想下單就下單
- 讓 LLM 直接碰交易所

而是：
- 能完整感知市場
- 能可解釋地決策
- 能審核地學習
- 能管理整體資本
- 能多代理協作
- 能在嚴格治理下自治

這也是 NEXUS 最合理的最終形態。

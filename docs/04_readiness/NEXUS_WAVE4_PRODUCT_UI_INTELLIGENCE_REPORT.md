# NEXUS Wave 4 Product UI Intelligence 報告

## 摘要

Wave 4 將 NEXUS 前端重組為 7 項主要 IA（總覽／全市場／機會／警報／投資組合／學習／證據），在 **零功能損失** 前提下保留所有既有路由，並以 Shadow／UI-only 方式交付。

## 主要變更

### 1. 資訊架構（IA）

- 側邊欄 7 個主導航：總覽、全市場、機會、警報、投資組合、學習、證據
- 進階／研究連結可折疊，3 次點擊內可達所有舊功能
- 行動端底部導航（768px 以下）

### 2. 新頁面

| 路由 | 說明 |
|------|------|
| `/universe` | 全市場掃描器 + 漏斗標頭 + SIMPLE/PRO/QUANT 欄位預設 |
| `/alerts` | 異常 + 訊號 + 風險合併工作區 |
| `/portfolio` | Shadow 投資組合（固定 25x、最多 2 倉、無 live 操作） |
| `/founder/runtime` | Bybit Demo 營運卡片（自公開總覽移出） |

### 3. 路由別名與棄用

- `/scanner` → 渲染 `UniversePage`（與 `/universe` 相同）
- `/fleets` → 棄用提示 + redirect 至 `/universe`
- 所有其他既有路由 **保留**

### 4. AiCommander

- 單一 FAB／抽屜取代 `FloatingAIAssistant`
- 無 LLM 時顯示 `RULE_BASED_SUMMARY`
- 11 種規則模式（市場脈動、組合摘要、警報 digest 等）

### 5. 總覽強化

- Market Pulse、Decision Funnel（空資料顯示 `NO_DATA`，**不用** 128/24/6 合成預設）
- Top Opportunities、Portfolio/Risk、Critical Alerts、Data Quality Summary
- **公開總覽不再顯示** `BybitDemoAutonomousCard`

### 6. Symbol Workbench

8 分頁：Overview / Structure / Flows / Six Roles / Risk / Plan / Memory / Evidence

## 約束遵守

- Shadow/UI only — 無 exchange write
- 無 Live Trade / ARM / Mainnet 按鈕
- 投資組合固定 25x 標籤
- 誠實 `NO_DATA` 空狀態
- 程式碼英文、文件繁中

## 測試與 CI

- `tests/test_wave4_product_ui_intelligence.py` — 80+ 靜態／契約測試
- `.github/workflows/wave4_product_ui_intelligence_validation.yml` — 僅 `feature/wave4-product-ui-intelligence` 分支

## 視覺回歸

見 `NEXUS_WAVE4_VISUAL_REGRESSION_MANIFEST.json` — 截圖計畫已宣告，瀏覽器擷取待 parent 執行。

## 未觸及區域

- 後端交易／策略／執行邏輯
- PR #1/#2/#3 分支
- 部署與 merge

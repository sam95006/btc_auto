# NEXUS 系統說明（唯一維護文件）

> 本文件取代過去的 `NEXUS_MASTER.md`、`ZEABUR_SETUP`、`ZEABUR_ENV`、`NEXUS_LOCAL_RUN` 等分散說明。  
> 安全階段規則仍以根目錄 [`AGENTS.md`](../AGENTS.md) 為準。

---

## 1. 系統在做什麼

NEXUS 是 **Binance 測試網** 上的指揮艦隊系統：

- **Web + API**：`app.py` / `run.py` → `templates/nexus_command.html`
- **交易迴圈**：`backend/services/nexus_runtime.py`（Zeabur 單服務時可內嵌 worker）
- **持久化**：`trading.db`（會議、聊天、決策審計；路徑由 `NEXUS_DATA_DIR` 決定）

### 艦隊路由（程式強制）

| 類型 | 幣種 |
|------|------|
| 固定艦隊 | BTC、ETH、SOL、PEPE |
| RADAR 雷達站 | XRP、BNB、DOGE 等其餘合約 |

設定見 `config/fleet_routing_config.py`。

### 聊天室緊急指令：整體平倉

在任一頻道（建議 **世界** 或 **風控**）輸入下列文字，系統會**立即**向 Binance U 本位下 `reduceOnly` 市價單，平掉所有合約持倉（不經 LLM 確認）：

- `整體平倉`、`全部平倉`、`全平`、`全部清倉`
- 英文：`close all`、`flatten all`

回覆會顯示成功/失敗筆數。亦可透過 API：`POST /api/nexus/control`，`{"command":"CLOSE_ALL_POSITIONS"}`。

---

## 2. 資金顯示：只跟 Binance 測試帳戶綁定

**儀表板上的總資產、現貨、合約、未實現損益，100% 來自 Binance REST**，標記為 `capital.source = binance_rest`。

| 項目 | API | 欄位 |
|------|-----|------|
| 現貨 USDT/USDC | `GET /api/v3/account` | 各資產 `free + locked` |
| **U 本位** 保證金 / 錢包 | `GET /fapi/v2/account`（`demo-fapi.binance.com`） | `totalMarginBalance`、`totalWalletBalance` |
| 未實現 | 同上 | `totalUnrealizedProfit` |
| **總資產** | — | 現貨 USDT/USDC + **U 本位保證金餘額** |
| **幣本位合約** | 不接入 | App 另一分頁，**永不計入** |

實作：`backend/trading/exchange_capital_view.py` → `nexus_runtime.snapshot()`。

**內部帳本**（HQ 準備金、雷達預算、艦隊分配）僅在 `capital.internal_allocation`，**不計入**畫面上的總資產。  
艦隊可用保證金會依 **合約權益** 在每次 sync 後由 `_apply_live_capital_plan()` 重算（使用 Binance 的 `totalMarginBalance`）。

### 現貨顯示範圍（與 App 對齊）

```env
NEXUS_HQ_SPOT_TRUTH_MODE=stable_only
NEXUS_HQ_SPOT_TRUTH_STABLE_ASSETS=USDT,USDC
```

不含 testnet 空投的其他幣種。

### 部署後對照

```http
GET /api/nexus/connectivity
```

確認：

- `capital_source` = `"binance_rest"`
- `binance_balances` 與 Binance App 一致
- `embedded_worker_started` = `true`（單服務 Zeabur）
- `futures_trading_access.ok` = `true`，且 `dual_side_position` 與 Binance App 的持倉模式一致（單向 / 雙向）
- 啟動後 `startup_exit_check` 會立即檢查既有合約持倉；若 R 止損觸發但一般平倉失敗，會自動以交易所即時 `positionRisk` 重試平倉

若 `last_tick_error` 含 `-1109`：讀取成功但下單失敗，請在 Zeabur 重新複製 **Secret**（建立金鑰時只顯示一次），確認 `BINANCE_FUTURES_BASE_URL=https://demo-fapi.binance.com`，並檢查 `futures_trading_access`。

若數字仍不對，請先查 `/api/nexus/connectivity` 的 `account_binding`：

- `spot_api_key_fp` / `futures_api_key_fp`：金鑰指紋（不含明文金鑰）
- `keys_distinct: true`：代表 spot / futures 的 API key 字串不同（**這是正常現象**，不能用來判定「不同帳戶」）
- 若你看到的 Binance App（或網頁）帳戶與儀表板資金/持倉不一致，最常見原因仍是：**Zeabur 變數裡的四把金鑰不是同一個你正在看的 testnet 帳戶**。請到 [Spot Testnet](https://testnet.binance.vision/) 與 [Futures Demo](https://demo.binance.com/) 用「同一組帳號」分別重建對應金鑰後再部署。

本機可跑（不印金鑰）：

```powershell
python tools/deploy/diagnose_binance_balances.py
```

若要與手機 App 一致：在 Zeabur 填入 **與 App 同一個 testnet 帳戶** 產生的四把金鑰（Spot Testnet + Futures Demo），再 Redeploy。

### 清除舊的本地快取資金

舊版 snapshot 可能曾寫入錯誤的帳本總額。請執行：

```powershell
python tools/deploy/purge_runtime.py   # 請先停止 run.py
python run.py
```

會刪除 `trading.db` 後，啟動時重新向 Binance 拉餘額。

---

## 3. 目錄結構（精簡）

| 路徑 | 用途 | 是否上傳 Zeabur |
|------|------|-----------------|
| `backend/` | API、runtime、交易、風控 | ✅ |
| `config/` | 設定 | ✅ |
| `static/nexus/` | 前端 | ✅ |
| `templates/` | HTML | ✅ |
| `tests/` | 自動測試 | ❌ `.dockerignore` |
| `docs/` | 本文件 | ❌ |
| `tools/deploy/` | 部署/清理腳本 | ❌（僅本機） |
| `tools/autodev/` | 自動化迭代（抓線上狀態 → 測試 → 部署 → 再驗證） | ❌（僅本機） |
| `archives/`、`scratch/` | 歷史/暫存 | ❌ 勿提交 Git |
| `logs/`、`data/`、`trading.db` | 本機狀態 | ❌ Volume 另掛 |

---

## 4. Cursor 全自動化迭代（C：維運 + 策略演化）

> 目標：把「出錯 → 修復 → 部署 → 驗證」變成可重複的一鍵流程。  
> 注意：本機腳本 **不會印出任何金鑰/secret**，只讀取 Zeabur 的公開 API 回傳。

### 4.1 一鍵自動迭代（建議日常使用）

```powershell
powershell -ExecutionPolicy Bypass -File tools/autodev/auto_iterate.ps1
```

流程包含：

- 先抓線上狀態（`/api/nexus/state`、`/api/nexus/pure-ai-status`）並做基本異常判斷
- 跑一組「Pure AI 快速測試」當作 gate
- 上傳 `.env` 並 redeploy Zeabur
- 再抓一次線上狀態確認恢復

### 4.2 只做線上狀態偵錯（不部署）

```powershell
python tools/autodev/triage_remote.py https://btc-auto-bot-2026.zeabur.app
```

常見可直接定位的問題：

- Worker crash / last_tick_error
- snapshot 太慢（UI 卡載入）
- `capital.source != binance_rest`（尚未完成 Binance 同步）
- Pure AI 不 operational

---

## 5. 雲端自動維運（GitHub Actions）

> 目標：不用開 Cursor，也能在雲端每 5 分鐘自動檢查 Zeabur 上的 NEXUS；卡住/報錯就自動 redeploy。  
> 策略演化（learning auto-apply）仍在 Zeabur runtime 內執行；Actions 負責「維運與復原」。

### 5.1 啟用方式

Workflow：`.github/workflows/nexus_cloud_maintainer.yml`

在 GitHub repo 設定 Secrets：

- `NEXUS_BASE_URL`：例如 `https://btc-auto-bot-2026.zeabur.app`
- `ZEABUR_TOKEN`
- `ZEABUR_PROJECT_ID`
- `ZEABUR_SERVICE_ID`

啟用後，每 5 分鐘會跑：

- `GET /api/nexus/state`
- `GET /api/nexus/pure-ai-status`

若偵測到 worker error、last_tick_error、或 state request latency 過高，會自動執行 Zeabur redeploy。

## 6. 合併後自動部署到 Zeabur（GitHub Actions）

Workflow：`.github/workflows/nexus_deploy_zeabur_on_main.yml`

- 觸發：`main` 分支有變更（backend/config/static/templates/.env.example/workflows）或手動 `workflow_dispatch`
- 動作：執行 `zeabur deploy`（使用 repo secrets：`ZEABUR_TOKEN`、`ZEABUR_PROJECT_ID`、`ZEABUR_SERVICE_ID`）

這樣 `nexus-autodev-pr` 產生的 PR **一合併到 main**，會自動部署到 Zeabur。


## 4. 高優先能力（已加入）：「各別艦隊 vs 總站 HQ」

下列四項是你指定的高優先缺口，已全部接進系統；並且明確劃分在「總站 HQ」或「各別艦隊」：

1. **多代理辯論/驗證（Bull/Bear/Risk）**：**總站 HQ**  
   - 位置：`backend/autonomy/pure_ai_debate_gate.py` → `backend/autonomy/pure_ai_orchestrator.py`  
   - 行為：Pure AI 進場提案先經過辯論門（可硬性 veto 或僅附帶衝突標記），再送進下單管線。
   - 開關：`NEXUS_PURE_AI_DEBATE_GATE=1`（預設開啟）

2. **PnL 驅動自我演化（post-mortem / reflection → 自動套用）**：**總站 HQ**  
   - 位置：`backend/services/nexus_runtime.py` + `backend/learning/learning_review_queue.py`  
   - 行為：虧損 trade 會觸發 post-mortem 與 learning review；可用 `NEXUS_LEARNING_AUTO_APPLY=1` 自動套用（仍會經過研究門檻/防呆 clamp）。

3. **ML 適應式「信心輔助」（FreqAI 風格的 prior，不取代 LLM）**：**總站 HQ**  
   - 位置：`backend/analytics/ml_confidence_service.py` → 注入 `ml_confidence_by_symbol` 給 LLM snapshot  
   - 行為：從近期 trade 結果建立 symbol-level prior（0..1），供 LLM 在挑標的/方向時參考，避免在近期明顯失敗的標的反覆追單。

4. **正式績效指標（勝率、MaxDD、Profit Factor…）**：**總站 HQ**  
   - API：`GET /api/nexus/performance-report`（完整報表）  
   - UI：Pure AI 面板會顯示 KPI 摘要（快取 60 秒），並提供完整 JSON 連結。

以上四項全部屬於「總站 HQ」能力：它們在 Pure AI 管線/學習/分析層運作，不會改動任何 `fleet_*_strategy_engine.py` 的艦隊策略邏輯。

---

## 4. 本機啟動

```powershell
Set-Location "g:\我的雲端硬碟\btc_bot"
# 確認 .env 有四把 BINANCE_*_TESTNET_* 
python run.py
```

瀏覽器：`http://127.0.0.1:5000/nexus`

### 本機驗證（無需下單）

| 檢查 | 方式 |
|------|------|
| 連線 / worker | `GET /api/nexus/connectivity` |
| 治理 | `GET /api/nexus/governance-status` |
| 績效 CLI | `python tools/research/performance_report.py` |
| K 線研究 / 研究閘道 | `python tools/research/backtest_runner.py --symbol BTCUSDT --full` |
| 研究閘道 API | `GET /api/nexus/research-gate` |
| TradingView Webhook | `POST /api/nexus/webhook/tradingview`（需 `NEXUS_TRADINGVIEW_WEBHOOK_SECRET`） |
| 環境變數 | `python tools/deploy/check_env_parity.py` |
| 外部市場情報 | `GET /api/nexus/connectivity` → `external_market_intel`（含 fear_greed、binance_macro） |

### 外部數據源（已接入）

| 來源 | 內容 | 金鑰 |
|------|------|------|
| Binance 合約/現貨 | 訂單簿、資金費、OI、K 線、清算、多空比、現貨溢價 | Testnet API |
| CoinGecko | 市值排名、24h 成交量、流動性篩選 | `COINGECKO_API_KEY` |
| CoinMarketCap | BTC 市佔、總市值 | `COINMARKETCAP_API_KEY` |
| CryptoQuant | 交易所流入/流出/淨流、槓桿壓力 | `CRYPTOQUANT_API_KEY` |
| Alternative.me | Fear & Greed 指數 | 無 |
| Binance `/futures/data` | 全球多空帳戶比、主動買賣比、OI 變化、近 1h 清算 | 公開端點 |

---

## 5. Zeabur 部署

### 5.1 平台異常

若 Zeabur 顯示 `nats`、`fluent-bit` 等系統元件異常，先 **重裝 Zeabur 服務**，再 Redeploy NEXUS。

### 5.2 單服務（推薦）

| 變數 | 值 |
|------|-----|
| `NEXUS_EMBEDDED_WORKER` | `1` |
| `WEB_CONCURRENCY` | `1` |
| `NEXUS_DATA_DIR` | `/data`（掛 Volume） |
| `NEXUS_RUNTIME_DB` | `trading.db` |

啟動：`gunicorn -c gunicorn.conf.py app:app`（見 `zbpack.json`）。

若另開獨立 worker 服務，**web** 請設 `NEXUS_WEB_ONLY=1`。

### 5.3 必填金鑰與模式

| 變數 | 說明 |
|------|------|
| `NEXUS_TRADING_MODE` | `binance_testnet` |
| `NEXUS_EXECUTION_MODE` | `binance_mixed_testnet` |
| `BINANCE_SPOT_TESTNET_API_KEY` / `SECRET_KEY` | 現貨 testnet |
| `BINANCE_FUTURES_TESTNET_API_KEY` / `SECRET_KEY` | 合約 testnet |

### 5.4 RADAR / 風控 / Phase 8（建議）

| 變數 | 建議值 |
|------|--------|
| `NEXUS_RADAR_AUTO_TRADE` | `1` |
| `NEXUS_RADAR_LLM_PROPOSALS` | `1` |
| `NEXUS_RADAR_UNIVERSE_MAX` | `50` |
| `NEXUS_AUTONOMY_LEVEL` | `2` |
| `NEXUS_SHADOW_MODE` | `0` |
| `NEXUS_FUTURES_BASELINE_CAPITAL` | 依 testnet 權益調整 |
| `NEXUS_RUNTIME_TICK_SECONDS` | `2` |

LLM：`GROQ_API_KEY_PRIMARY`、`NEXUS_LLM_ENABLE=1` 等（金鑰勿 commit）。

### 5.5 狀態匯出 / 還原（可選）

```powershell
python tools/deploy/nexus_state_sync.py export
python tools/deploy/nexus_state_sync.py import path\to\bundle.zip --data-dir /data
```

僅打包 `trading.db` 與版面 JSON，**不含金鑰**。

### 5.6 部署檢查清單

- [ ] `/health` → `ok`
- [ ] `/api/nexus/connectivity` → 金鑰齊、`capital_source=binance_rest`
- [ ] Volume `/data` 已掛載
- [ ] 頂部資金與 Binance testnet App 一致

---

## 6. Active 程式入口（維護用）

- 啟動：`run.py`、`backend/api/server.py`、`backend/worker/runner.py`
- Runtime：`backend/services/nexus_runtime.py`、`runtime_store.py`
- 前端：`static/nexus/app.js`、`templates/nexus_command.html`
- 交易所：`backend/trading/binance_*_testnet_client.py`

---

## 7. Zeabur 環境變數（P0–P2 合約專用 · 一次貼上）

> **月營收目標** = 合約權益 × `NEXUS_MONTHLY_REVENUE_CAPITAL_FRACTION`（預設 **⅓**）。  
> 例：U 本位權益 3470U → 月目標約 **1157U**。現貨不參與下單（`NEXUS_FUTURES_ONLY_TRADING=1`）。  
> 請把 `你的_*` 換成實際金鑰；**勿**把本檔 commit 到公開 repo。

```env
# --- 執行與資料 ---
NEXUS_DATA_DIR=/data
NEXUS_EMBEDDED_WORKER=1
WEB_CONCURRENCY=1
NEXUS_TRADING_MODE=binance_testnet
NEXUS_EXECUTION_MODE=binance_mixed_testnet
NEXUS_BOOTSTRAP_TRADES=0

# --- Binance 測試網（合約必開）---
BINANCE_FUTURES_TESTNET_API_KEY=你的_futures_key
BINANCE_FUTURES_TESTNET_SECRET_KEY=你的_futures_secret
BINANCE_SPOT_TESTNET_API_KEY=你的_spot_key
BINANCE_SPOT_TESTNET_API_SECRET=你的_spot_secret

# --- LLM ---
NEXUS_LLM_ENABLE=1
GROQ_API_KEY=你的_groq_key
CEREBRAS_API_KEY=你的_cerebras_key
NEXUS_LLM_PROVIDER_AGENT=cerebras
NEXUS_LLM_MODEL_AGENT=llama-3.3-70b
SAMBANOVA_API_KEY=你的_sambanova_key

# --- P0：合約專用 + 提高成交 ---
NEXUS_FUTURES_ONLY_TRADING=1
NEXUS_FUTURES_DEPLOY_FRACTION=0.92
NEXUS_ALWAYS_ON_TRADING=1
NEXUS_SHADOW_MODE=0
NEXUS_AUTONOMY_LEVEL=2
NEXUS_AI_LED_TRADING=1
NEXUS_AI_LED_PRIMARY=1
NEXUS_AI_LED_CORE_FLEETS=1
NEXUS_AI_LED_MIN_CONFIDENCE=0.45
NEXUS_AI_PROPOSAL_MAX_PER_TICK=5
NEXUS_RUNTIME_TICK_SECONDS=2
NEXUS_QUALITY_GATE_ENABLED=1
NEXUS_MIN_TRADE_CONFIDENCE=0.52
NEXUS_TARGET_WIN_RATE=0.55
NEXUS_WALK_FORWARD_MIN_WIN_RATE=0.40
NEXUS_REVENUE_GROWTH_MODE=1
NEXUS_BOLD_TESTNET=1

# --- P0：月營收 KPI（⅓ 合約權益）---
NEXUS_MONTHLY_REVENUE_TARGET_MODE=third_of_futures_capital
NEXUS_MONTHLY_REVENUE_CAPITAL_FRACTION=0.333333
NEXUS_MEETING_TIMEZONE=Asia/Taipei

# --- P1：營運 / Kill-switch ---
NEXUS_OPS_WEBHOOK_URL=
NEXUS_OPS_WEBHOOK_COOLDOWN_SEC=900
NEXUS_KILL_SWITCH_V2=1
NEXUS_KILL_SWITCH_SYNC_STALE_SEC=180
NEXUS_KILL_SWITCH_MAX_CONSECUTIVE_LOSSES=5
NEXUS_KILL_SWITCH_VALIDATION_BLOCK_RATE=0.88
NEXUS_KILL_SWITCH_AUTO_FLATTEN=0

# --- P2：規則訊號 A/B + 多週期 + 出場 ---
NEXUS_RULE_SIGNAL_BRIDGE=1
NEXUS_RULE_SIGNAL_INTERVAL_SEC=60
NEXUS_RULE_SIGNAL_MIN_CONFIDENCE=0.46
NEXUS_RULE_SIGNAL_MOMENTUM_PCT=0.0012
NEXUS_RULE_SIGNAL_MAX_PROPOSALS=2
NEXUS_MULTI_TIMEFRAME=1
NEXUS_TP1_R=0.55
NEXUS_TP2_R=1.0
NEXUS_TP3_R=1.6

# --- P3 策略模組（網格 / Funding / DCA / 月回撤 10%）---
NEXUS_GRID_TRADING=1
NEXUS_FUNDING_ARB=1
NEXUS_DCA_ACCUMULATOR=1
NEXUS_MONTHLY_MAX_DRAWDOWN_PCT=0.10
NEXUS_VOLATILITY_SIZING=1
NEXUS_GRID_INTERVAL_SEC=40
NEXUS_FUNDING_ARB_INTERVAL_SEC=50
NEXUS_DCA_INTERVAL_SEC=3600

# --- 複利（衝月營收時建議關日鎖利，保留樣本）---
NEXUS_COMPOUND_REINVEST=1
NEXUS_DAILY_POSITIVE_MODE=1
NEXUS_LOCK_PROFIT_AFTER_DAILY_TARGET=0
NEXUS_DAILY_PNL_TARGET_PCT=0.008
NEXUS_DAILY_MAX_LOSS_PCT=0.02
NEXUS_LEARNING_AUTO_APPLY=1
NEXUS_LIQUIDATION_PERMANENT_BLACKLIST=0
NEXUS_MATURITY_TARGET_SCORE=90

# --- 現貨僅顯示，不交易 ---
NEXUS_HQ_SPOT_TRUTH_MODE=stable_only
NEXUS_HQ_SPOT_TRUTH_STABLE_ASSETS=USDT,USDC
```

API：`GET /api/nexus/monthly-revenue`、`/api/nexus/decision-funnel`、`/api/nexus/revenue-plan`

---

## 8. 常見問題

| 現象 | 處理 |
|------|------|
| 總資產與 Binance 差很多 | 跑 `purge_runtime.py` 後重啟；確認四把 testnet key 與 App 同帳 |
| UI 報 `updateUIState` | 清瀏覽器快取，確認 `app.js?v=` 為最新 |
| worker 離線 | Zeabur 設 `NEXUS_EMBEDDED_WORKER=1`、`WEB_CONCURRENCY=1` |
| 重啟後聊天/會議不見 | 掛 `/data` Volume |
| `data/` 充滿 `trading_backup_*.db` | 現行 NEXUS 不讀這些檔；先 `--dry-run` 再 prune（見下） |
| 決策拒絕：標的冷卻／歷史劣勢／連虧／強平冷卻 | 見下方「測試網試單」；COMMS 輸入 **清除冷卻** |

### 資料目錄瘦身（不影響後端功能）

**保留：** `trading.db`、`layout_overrides.json`、執行中的 `trading.db-wal` / `trading.db-shm`  
**可刪：** `trading_backup_YYYYMMDD_*.db`（建議只留最新 1～2 個）、`trading_shield_backup.db`、舊 `logs/*.log`

```bash
# 預覽將刪除的備份
python tools/deploy/prune_data_backups.py --dry-run

# 只留最新 2 個 backup，並刪 shield 備份與舊 log
python tools/deploy/prune_data_backups.py --keep 2 --shield --logs

# 完全重置 DB（會從 Binance 重同步，稽核/會議本地紀錄會清空）
python tools/deploy/purge_runtime.py --logs --bundles
```

Zeabur Volume 掛在 `NEXUS_DATA_DIR=/data` 時，在容器或本機對同一目錄執行即可。  
本機 `venv/`、`__pycache__/` 不在 Git 內，可刪除後用 `pip install -r requirements.txt` 重建以縮小雲端同步體積。

### 測試網試單（排除四種拒絕原因）

決策稽核若顯示 **標的冷卻 · 歷史優勢不足 · 連虧紀錄 · 強平冷卻**，代表學習層／回測層在擋試單。請在 **Binance Testnet** 使用：

```env
NEXUS_BOLD_TESTNET=1
NEXUS_TESTNET_SANDBOX=1
NEXUS_SANDBOX_MIN_CONFIDENCE=0.38
NEXUS_SANDBOX_MIN_APPROVAL_SCORE=0.38
NEXUS_SANDBOX_AUTO_RESET=1
NEXUS_SANDBOX_FORCE_LIVE=1
NEXUS_SHADOW_MODE=0
NEXUS_AI_LED_TRADING=1
NEXUS_EMBEDDED_WORKER=1
NEXUS_REVENUE_GROWTH_MODE=1
NEXUS_LEARNING_SYMBOL_COOLDOWN_SECONDS=600
NEXUS_LIQUIDATION_SYMBOL_COOLDOWN_SECONDS=600
```

重啟後會自動執行一次沙盒重置。亦可手動在 COMMS（世界頻道）輸入：

1. **清除冷卻** — 清驗證累積 + 虧損紀錄 + 拒絕稽核 + 恢復交易  
2. **恢復交易** — 若仍顯示暫停  

沙盒模式會放寬上述四項，但仍保留：模擬滑點、日損、**月回撤 10%**、極端行情。  
**上線真實帳戶前請設 `NEXUS_TESTNET_SANDBOX=0` 並關閉 `NEXUS_BOLD_TESTNET`。**

### 防手續費空轉（高頻小虧損）

若 Binance 帳本出現大量 `-0.06U` 等微小已實現損益 + 手續費，代表倉位太小或平倉過快。建議：

```env
NEXUS_FEE_CHURN_GUARD=1
NEXUS_MIN_MARGIN_USD=45
NEXUS_MIN_HOLD_SECONDS=180
NEXUS_SYMBOL_REOPEN_COOLDOWN_SEC=300
NEXUS_RULE_SIGNAL_INTERVAL_SEC=120
```

- 單筆保證金與名義值過小會被拒絕開倉（`fee_churn_*`）。
- AI 強平壓力平倉僅在 **critical** 且持倉超過最短時間才執行。
- 部分止盈需覆蓋約 **3.5× 往返手續費** 才會觸發。
- 畫面「未實現 0」在**無持倉**時屬正常，不是同步錯誤。

---

## 9. 成熟度五維雷達（唯一評分標準）

自 2026-05 起，**只使用一套分數**：`maturity_radar`（每維 0–100，目標 **≥ 80**，進階營運 **≥ 90**）。

| 維度 | 英文鍵 | 衡量內容 |
|------|--------|----------|
| 基礎設施 | `infrastructure` | Worker、Binance 同步、always-on、資料新鮮度 |
| 自動執行 | `auto_execution` | 未暫停、Autonomy≥2、核准/成交、audit 樣本 |
| 風控治理 | `risk_control` | Validation、decision_audit、治理 trace |
| 學習閉環 | `learning` | auto_apply、校準、patch、強平冷卻＋`symbol_lessons`（非永久黑名單） |
| AI 主導 | `ai_led` | LLM 就緒、AI 提案鏈、圓桌綁執行、trade_proposals |

API：`GET /api/nexus/maturity-radar`  
Snapshot 欄位：`maturity_radar`（UI 警報面板會顯示五維百分比）。

建議環境（五維衝 80+）：

```env
NEXUS_EMBEDDED_WORKER=1
NEXUS_ALWAYS_ON_TRADING=1
NEXUS_AI_LED_TRADING=1
NEXUS_AI_LED_PRIMARY=1
NEXUS_AI_LED_CORE_FLEETS=1
NEXUS_LLM_ENABLE=1
NEXUS_LEARNING_AUTO_APPLY=1
NEXUS_AUTONOMY_LEVEL=2
NEXUS_SHADOW_MODE=0
```

`NEXUS_AI_LED_PRIMARY=1`：新倉只走 AI 提案鏈（規則引擎僅管平倉）；`NEXUS_AI_LED_CORE_FLEETS=1`：BTC/ETH/SOL/PEPE 也可由 AI 提案下單。

強平後行為（預設）：`NEXUS_LIQUIDATION_PERMANENT_BLACKLIST=0` → 僅冷卻數小時，再進場需更高信心與較低槓桿（`symbol_lessons`）。  
品質門檻（務實，非保證獲利）：`NEXUS_MIN_TRADE_CONFIDENCE`、`NEXUS_QUALITY_GATE_ENABLED`。  
營運 SLO：`ops_health`；可選 `NEXUS_OPS_WEBHOOK_URL` 發送 degraded 告警。

### 每日復投與正報酬防禦

- `NEXUS_COMPOUND_REINVEST=1`：每日開盤權益 = 昨日收盤權益（`logs/growth_daily_state.json`，Zeabur 請放 `/data/logs`）。
- `NEXUS_DAILY_POSITIVE_MODE=1`：日內虧損擴大時收緊／暫停新倉。
- `NEXUS_LOCK_PROFIT_AFTER_DAILY_TARGET=1`：達日目標後鎖利（`PROFIT_LOCK`），避免獲利回吐。
- Snapshot：`compound_capital`、`growth_mode.daily`、`growth_mode.compound`。

```env
NEXUS_COMPOUND_REINVEST=1
NEXUS_DAILY_POSITIVE_MODE=1
NEXUS_LOCK_PROFIT_AFTER_DAILY_TARGET=1
NEXUS_DAILY_PNL_TARGET_PCT=0.003
NEXUS_MATURITY_TARGET_SCORE=90
NEXUS_DATA_DIR=/data
```

**無法保證**每日正報酬；系統目標是復投 + 虧損日防禦 + 達標鎖利。

---

*最後更新：2026-05-24*

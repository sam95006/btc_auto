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

若數字仍不對，請先查 `/api/nexus/connectivity` 的 `account_binding`：

- `accounts_mismatch: true` → **現貨 API 金鑰與合約 API 金鑰是兩個不同 testnet 帳戶**（儀表板數字對「金鑰綁定的帳戶」是正確的，但不會等於 App 某一個畫面）
- 請到 [Spot Testnet](https://testnet.binance.vision/) 與 [Futures Demo](https://demo.binance.com/) 分別用兩組金鑰登入對帳

本機可跑（不印金鑰）：

```powershell
python tools/deploy/diagnose_binance_balances.py
```

若要與手機 App 一致：在 Zeabur 填入 **與 App 同一 testnet 帳戶** 產生的四把金鑰；現貨與合約建議用**同一帳戶**配對的金鑰。

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
| `archives/`、`scratch/` | 歷史/暫存 | ❌ 勿提交 Git |
| `logs/`、`data/`、`trading.db` | 本機狀態 | ❌ Volume 另掛 |

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
| 環境變數 | `python tools/deploy/check_env_parity.py` |

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

## 7. 常見問題

| 現象 | 處理 |
|------|------|
| 總資產與 Binance 差很多 | 跑 `purge_runtime.py` 後重啟；確認四把 testnet key 與 App 同帳 |
| UI 報 `updateUIState` | 清瀏覽器快取，確認 `app.js?v=` 為最新 |
| worker 離線 | Zeabur 設 `NEXUS_EMBEDDED_WORKER=1`、`WEB_CONCURRENCY=1` |
| 重啟後聊天/會議不見 | 掛 `/data` Volume |

---

## 8. 成熟度五維雷達（唯一評分標準）

自 2026-05 起，**只使用一套分數**：`maturity_radar`（每維 0–100，目標 **≥ 80**）。

| 維度 | 英文鍵 | 衡量內容 |
|------|--------|----------|
| 基礎設施 | `infrastructure` | Worker、Binance 同步、always-on、資料新鮮度 |
| 自動執行 | `auto_execution` | 未暫停、Autonomy≥2、核准/成交、audit 樣本 |
| 風控治理 | `risk_control` | Validation、decision_audit、治理 trace |
| 學習閉環 | `learning` | auto_apply、校準、patch、虧損/黑名單 |
| AI 主導 | `ai_led` | LLM 就緒、AI 提案鏈、圓桌綁執行、trade_proposals |

API：`GET /api/nexus/maturity-radar`  
Snapshot 欄位：`maturity_radar`（UI 警報面板會顯示五維百分比）。

建議環境（五維衝 80+）：

```env
NEXUS_EMBEDDED_WORKER=1
NEXUS_ALWAYS_ON_TRADING=1
NEXUS_AI_LED_TRADING=1
NEXUS_LLM_ENABLE=1
NEXUS_LEARNING_AUTO_APPLY=1
NEXUS_AUTONOMY_LEVEL=2
NEXUS_SHADOW_MODE=0
```

---

*最後更新：2026-05-24*

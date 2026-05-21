# Zeabur 環境變數清單（請在控制台新增）

> **金鑰請自行貼上**，不要 commit 到 Git。其餘可從本機 `.env` 複製（變數名相同、值相同）。

## 必填（沒有就不會交易）

| 變數 | 說明 |
|------|------|
| `NEXUS_TRADING_MODE` | `binance_testnet` |
| `NEXUS_EXECUTION_MODE` | `binance_mixed_testnet` |
| `BINANCE_SPOT_TESTNET_API_KEY` | 現貨 testnet |
| `BINANCE_SPOT_TESTNET_SECRET_KEY` | 現貨 testnet |
| `BINANCE_FUTURES_TESTNET_API_KEY` | 合約 testnet |
| `BINANCE_FUTURES_TESTNET_SECRET_KEY` | 合約 testnet |

## 持久化（必掛 Volume `/data`）

| 變數 | 建議值 |
|------|--------|
| `NEXUS_DATA_DIR` | `/data` |
| `NEXUS_RUNTIME_DB` | `trading.db` |

## Worker（單服務 Zeabur 推薦）

| 變數 | 建議值 |
|------|--------|
| `NEXUS_EMBEDDED_WORKER` | `1` |
| `WEB_CONCURRENCY` | `1`（避免 Gunicorn 多 worker 重複跑交易迴圈） |

若開 **獨立 worker 服務**，web 加 `NEXUS_WEB_ONLY=1`，worker 不要設此項。

部署後請確認 `/api/nexus/connectivity` 的 `embedded_worker_started` 為 `true`，且 `decision_summary.live_position_count` 與 Binance 模擬盤持倉數一致。

## 艦隊與 RADAR（四艦隊固定 + 其餘僅雷達站）

**路由規則（程式強制）**：
- **BTC / ETH / SOL / PEPE** 艦隊：只開/管這四種合約
- **RADAR 雷達站**：XRP、BNB、DOGE 等其餘幣種的開倉與持倉顯示

## 艦隊與 RADAR 參數

| 變數 | 建議值 |
|------|--------|
| `NEXUS_MARKET_TYPE_BTC` | `futures` |
| `NEXUS_MARKET_TYPE_ETH` | `futures` |
| `NEXUS_MARKET_TYPE_SOL` | `futures` |
| `NEXUS_MARKET_TYPE_PEPE` | `futures` |
| `NEXUS_RADAR_AUTO_TRADE` | `1` |
| `NEXUS_RADAR_LLM_PROPOSALS` | `1` |
| `NEXUS_RADAR_LLM_MIN_CONFIDENCE` | `0.55` |
| `NEXUS_RADAR_UNIVERSE_MAX` | `50` |
| `NEXUS_RADAR_MIN_CANDIDATE_SCORE` | `55` |
| `NEXUS_RADAR_MAX_OPEN_POSITIONS` | `3` |
| `NEXUS_RADAR_MAX_LEVERAGE` | `15` |

## 成長 / 風控 / R 出場

| 變數 |
|------|
| `NEXUS_FUTURES_BASELINE_CAPITAL` |
| `NEXUS_CAPITAL_FLOOR` |
| `NEXUS_GROWTH_TARGET` |
| `NEXUS_BOLD_TESTNET` |
| `NEXUS_DAILY_PNL_TARGET_PCT` |
| `NEXUS_DAILY_MAX_LOSS_PCT` |
| `NEXUS_RISK_PCT` |
| `NEXUS_STOP_R` |
| `NEXUS_BREAK_EVEN_AFTER_TP1` |
| `NEXUS_SIGNAL_REVERSE_MIN_CONFIDENCE` |

## Phase 8 自治 / 學習

| 變數 | 建議值 |
|------|--------|
| `NEXUS_AUTONOMY_LEVEL` | `2` |
| `NEXUS_LEARNING_AUTO_APPLY` | `1` |
| `NEXUS_LEARNING_AUTO_APPROVE` | `1` |
| `NEXUS_SHADOW_MODE` | `0` |
| `NEXUS_AI_PROPOSAL_MAX_PER_TICK` | `3` |
| `NEXUS_STRATEGY_VERSION` | `v1.0.0-core` |

## 執行與新聞

| 變數 |
|------|
| `NEXUS_RUNTIME_TICK_SECONDS` |
| `NEXUS_BOOTSTRAP_TRADES` |
| `BINANCE_TESTNET_VALIDATE_ON_BOOT` |
| `BINANCE_TESTNET_RECV_WINDOW` |
| `NEXUS_HQ_SPOT_THRESHOLD` |
| `NEXUS_HQ_SPOT_COOLDOWN_SECONDS` |
| `NEXUS_NEWS_PAUSE_SECONDS` |
| `NEXUS_MEETING_TIMEZONE` |

## 每日戰報（聊天室）

| 變數 | 建議值 |
|------|--------|
| `NEXUS_DAILY_REPORT_ENABLE` | `1` |
| `NEXUS_DAILY_REPORT_SLOTS` | `00:00,12:00` |

## LLM（金鑰自行貼）

| 變數 |
|------|
| `NEXUS_LLM_ENABLE` |
| `GROQ_API_KEY_PRIMARY` |
| `GROQ_API_KEY_SECONDARY` |
| `SAMBANOVA_API_KEY` |
| `NEXUS_LLM_PROVIDER_NEWS` |
| `NEXUS_LLM_PROVIDER_RADAR` |
| `NEXUS_LLM_PROVIDER_RADAR_PROPOSAL` |
| `NEXUS_LLM_MODEL_RADAR_PROPOSAL` |
| `NEXUS_LLM_PROVIDER_ROUNDTABLE` |
| `NEXUS_LLM_PROVIDER_REFLECTION` |
| `NEXUS_LLM_PROVIDER_CHAT` |
| `NEXUS_LLM_MODEL_CHAT` |
| `NEXUS_LLM_PROVIDER_AGENT` |
| `NEXUS_LLM_MODEL_AGENT` |

## 檢查

部署後開：`https://你的網域/api/nexus/connectivity`  
本機對照：`python tools/deploy/check_env_parity.py`

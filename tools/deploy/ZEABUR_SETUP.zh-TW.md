# Zeabur 部署與本地無縫銜接

## 一、先修 Zeabur 伺服器（你的截圖問題）

若看到 **「9 個系統元件中有 4 個異常」**（`nats`、`fluent-bit`、`vector-aggregator`、`zeabur-kube-watch`），這是 **Zeabur 平台本身壞掉**，不是 NEXUS 程式碼問題。此時重啟 App 也無法正常部署。

請依序操作：

1. 點截圖中的 **「重裝 Zeabur 服務」**（橘色按鈕）
2. 等待 5–15 分鐘，直到系統健康警告消失（9/9 正常）
3. 再對 NEXUS 的 web / worker 服務按 **Redeploy**

若重裝後仍異常：Zeabur 控制台 → 伺服器 → 查看日誌，或聯繫 Zeabur 支援（自建節點常需重裝系統元件）。

---

## 二、Web 與 Worker（二選一即可）

### 方案 A：只開一個 Zeabur 服務（推薦新手）

Zeabur 只部署 **web** 時，程式會偵測 Zeabur 注入的 `ZEABUR_SERVICE_ID` / `ZEABUR_PROJECT_ID` 等變數，**自動在同一容器內啟動內嵌 worker 執行緒**，負責連幣安與寫入 `trading.db` 快照。此時儀表板不會再顯示「工作節點離線」。

- 若使用 **Gunicorn 且 worker 數 > 1**，請改為 `-w 1`，或改設 `NEXUS_EMBEDDED_WORKER=1` 才啟用內嵌（避免多進程重複下單）。
- 若你**另外**開了獨立 worker 服務，請在 **web** 服務加上 `NEXUS_WEB_ONLY=1`，關閉內嵌 worker，只讓獨立 worker 跑交易迴圈（避免雙迴圈重複下單）。

### 方案 B：Web + Worker 兩個服務

| 服務 | 啟動方式 | 作用 |
|------|----------|------|
| **web** | 預設（`app.py` / Gunicorn） | 儀表板 + API（請設 `NEXUS_WEB_ONLY=1`） |
| **worker** | `python -m backend.worker.runner` | 交易引擎 |

兩個服務請使用 **同一個 Git repo**（`sam95006/btc_auto`），環境變數盡量複製相同。

### 診斷 API（不含機密）

部署後在瀏覽器開：

`https://你的網域/api/nexus/connectivity`

可看到：`testnet_credentials_missing`、`embedded_worker_started`、`snapshot_system_health` 等，用來確認是缺金鑰還是沒跑 worker。

---

## 三、與本地「無縫銜接」的關鍵

### 1. 同一組 Binance Testnet 金鑰

雲端與本地使用 **相同四把 testnet key**，帳戶持倉、餘額會由 `nexus_runtime` 自動同步，無需複製持倉狀態。

### 2. 共用持久化磁碟（會議紀錄、聊天、決策審計）

`trading.db` 與 UI 版面存在 SQLite / JSON。Zeabur 容器重啟會清空預設目錄，必須掛載 Volume：

1. Zeabur → **web 服務** → Volumes → 新增掛載路徑 `/data`
2. **worker 服務** → 掛載 **同一個** Volume 到 `/data`
3. 兩個服務都設定環境變數：

```env
NEXUS_DATA_DIR=/data
NEXUS_RUNTIME_DB=trading.db
```

（不必手動設 `ZEABUR=1`；Zeabur 會注入 `ZEABUR_SERVICE_ID` 等，程式會辨識。）

### 3. 從本機匯出狀態再上傳

在本機專案根目錄：

```powershell
python tools/deploy/nexus_state_sync.py export
```

會產生 `archives/state_bundles/nexus_state_YYYYMMDD_HHMMSS.zip`。

上傳到 Zeabur（擇一）：

- **方式 A**：用 Zeabur 檔案管理 / SFTP 將 zip 解壓到 Volume 的 `/data`（含 `trading.db`、`layout_overrides.json`）
- **方式 B**：在可 SSH 的環境執行  
  `python tools/deploy/nexus_state_sync.py import /path/to/nexus_state_xxx.zip --data-dir /data`

### 4. 環境變數與本地 `.env` 對齊

複製本地 `.env` 到 Zeabur（**不要** commit 到 Git）。至少包含 `.env.example` 中所有 `NEXUS_*`、`BINANCE_*`、`GROQ_*` 變數。

本機可先跑（**不會印出金鑰內容**，只顯示 SET / MISSING）：

```powershell
python tools/deploy/check_env_parity.py
```

Zeabur 控制台變數補齊後，雲端與本地對幣安的後端行為才會一致。

---

## 四、部署成功檢查清單

- [ ] Zeabur 系統健康 9/9 正常
- [ ] web 服務 `/health` 回 `{"status":"ok"}`，且單服務時 `embedded_worker` 為 `true`
- [ ] `/api/nexus/connectivity` 中 `testnet_credentials_missing` 為空陣列
- [ ] 若用獨立 worker：其日誌有 tick / sync；若用內嵌：web 日誌有 `NEXUS embedded worker thread started`
- [ ] web（與獨立 worker 若有）共用 `/data` Volume
- [ ] `NEXUS_TRADING_MODE=binance_testnet`
- [ ] 儀表板頂部資金與 testnet 帳戶一致

---

## 五、常見錯誤

| 現象 | 原因 | 處理 |
|------|------|------|
| Build 成功但立刻 Crash | 缺 testnet 金鑰 | 補齊四把 `BINANCE_*_TESTNET_*` |
| 有 UI 但不交易 | 沒開 worker | 新增 worker 服務 |
| 重啟後會議/聊天清空 | 沒掛 Volume | 掛 `/data` 並設 `NEXUS_DATA_DIR` |
| 部署一直失敗 | Zeabur 元件異常 | 先「重裝 Zeabur 服務」 |

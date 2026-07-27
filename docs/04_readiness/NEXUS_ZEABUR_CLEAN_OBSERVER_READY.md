# Zeabur-only Clean 24H — Observer 就緒說明

**狀態：** 架構已落地於程式碼；**尚未**啟用、**尚未**開始新 Clean 24H  
**預設：** `NEXUS_ZEABUR_CLEAN_OBSERVER` 未開 → Observer 不啟動

## 模組

- `backend/nexus_research/demo_autonomous/validation_observer.py`
- API：`GET /api/nexus/demo/autonomous/observer`
- 證據目錄：`research_data_dir()/zeabur_clean_validation_observer/samples.jsonl`（Zeabur Volume）

## 行為

- 每 60 秒唯讀 snapshot
- 單一 Owner；第二次 `start()` 拒絕
- 不寫交易所、不發 Session、不改 Auto Send
- Boot／Commit 變更 → fail-closed
- Controller Owner ≠ 1 → fail
- Runtime STALLED → fail
- Mainnet／Real-money → fail
- Observer 自身 heartbeat；停滯可判 FAILED／STALLED

## 啟用條件（需 Founder 批准 Push／Deploy 後）

1. Scoped Runtime Fix 已部署到 Zeabur  
2. 帳戶 0 倉／0 單／對帳 MATCH  
3. 設定 `NEXUS_ZEABUR_CLEAN_OBSERVER=true`（僅在批准後）  
4. 確認 `observer_owner_count=1`、`observer_health=HEALTHY`  
5. 才開始**全新** Clean 24H 計時

## 禁止

- 本機 JSONL 當 Primary Recorder  
- 從失敗的本機 Clean 24H 繼續計時  
- 未批准前 Push／Deploy／改 Zeabur env

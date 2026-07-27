# NEXUS Clean 24H — Zeabur Only

**生效日：** 2026-07-27  
**規則等級：** 強制

## 唯一驗證場地

Clean／Reliability 24H（與後續 72H）**必須在 Zeabur 伺服器上運行**，不是本機 Python 監視器。

- Live 服務：`https://nexus-stage3-bybit-demo-learning.zeabur.app`
- 本機只允許：**唯讀 GET**（status／account／position／health）
- 本機**禁止**再充當「唯一乾淨 24H 監視器」

## 為何改規則

本機 `run_clean_autonomous_24h_validation.py` 曾被當成主監視器，後來出現：

- JSONL 採樣中斷
- Scanner／Controller 停滯
- 監視器行程存在但不健康

且使用者原意是 **在 Zeabur 上跑 24H**，不是本地。

既有本機 Integrity 調查結論保留為失敗證據，**不洗成 PASS**：

- `archives/worktrees/nexus-6h-autonomous-demo/docs/evidence/NEXUS_CLEAN_24H_VALIDATION_INTEGRITY_INCIDENT_REPORT.md`

## DEPRECATED（本機）

以下腳本若仍存在，僅供唯讀／除錯，**不得**作為 Clean 24H 過關依據：

- `tools/research/run_clean_autonomous_24h_validation.py`
- 任何本機無限迴圈寫 JSONL 的「乾淨 24H」監視器

## 正確做法（之後）

1. 確保 Zeabur Demo Runtime／Controller 在雲端持續健康  
2. 本機可用排程做 **read-only probe** 彙整證據（可選）  
3. 證據寫入 `docs/evidence/` 或 `docs/04_readiness/`  
4. Wave 1 部署仍另需安全視窗 + 明確批准  

## 固定

- Push／Deploy：不因本文件自動執行  
- 不為製造視窗而干預 Live（無人工平倉／續期／Restart）

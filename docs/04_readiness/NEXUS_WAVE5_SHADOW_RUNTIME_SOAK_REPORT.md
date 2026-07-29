# NEXUS Wave 5 Shadow Runtime Soak Report

## 範圍

- **非** Clean 24H／Clean 72H／Production Stable
- 本輪：加速 mock soak＋CI container smoke
- 未來可於 Zeabur 執行較長公開資料 soak（仍禁 private／write／deploy 除非 Founder 另批）

## 驗證項

- Universe／Snapshot 前進
- Worker 無 Stall（mock 路徑）
- Candidate 無重複開倉
- Risk Critic Veto 有效
- Portfolio ≤2、Pending ≤2
- 固定 25x
- Shadow Lifecycle 前進
- Persistence 可重啟恢復
- UI 可讀 runtime status
- No Exchange Write

## 標籤

`PUBLIC_DATA_CAPTURE` · `SHADOW_ONLY` · `NOT_EXECUTED` · `NOT_PROFIT_PROOF`

## 結果

- 模組：`backend/nexus_real_shadow/soak.py`
- 測試覆蓋：加速 mock cycles（pytest）
- Container smoke：CI `wave5-docker`／`wave5-container-soak`
- **不得**宣稱 Clean 24H 或 TARGET_REACHED

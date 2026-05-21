# NEXUS 本機啟動與驗證（Phase 8）

## 啟動

```powershell
Set-Location "g:\我的雲端硬碟\btc_bot"
python run.py
```

瀏覽器：`http://127.0.0.1:5000/nexus`

## 驗證管線（無需金鑰）

| 檢查 | URL / 指令 |
|------|------------|
| 連線與 worker | `GET /api/nexus/connectivity` |
| 治理狀態 | `GET /api/nexus/governance-status` |
| 決策 trace | `GET /api/nexus/decision-traces` |
| 學習審核 | `GET /api/nexus/learning-reviews` |
| 虧損反思 | `GET /api/nexus/loss-review` |
| 績效報告 | `GET /api/nexus/performance-report` |
| CLI 報告 | `python tools/research/performance_report.py` |

## 本機 .env 重點（非金鑰）

- `NEXUS_AUTONOMY_LEVEL=2`：治理通過後可下 testnet 單
- `NEXUS_SHADOW_MODE=0`：關閉僅記錄不下單
- `NEXUS_LEARNING_AUTO_APPLY=1`：虧損建議自動落地到風控參數
- `NEXUS_RADAR_UNIVERSE_MAX=50`：RADAR 掃描流動性前 N 幣

## Zeabur

複製本機 `.env` 變數到 Zeabur（金鑰自行貼上），並設：

- `NEXUS_DATA_DIR=/data` + Volume
- `NEXUS_MEETING_TIMEZONE=Asia/Taipei`

詳見 `tools/deploy/ZEABUR_SETUP.zh-TW.md`。

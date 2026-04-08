## 🚀 Zeabur 持久化部署指南 - `/app/data` 硬碟

### 📌 核心概念

每次上傳新版本時，Zeabur 會：
1. ✅ **保留** `/app/data` 持久硬碟中的所有文件
   - 所有交易成交記錄
   - 所有失敗數據和分析
   - AI 所有學習到的資料
   - 自動備份
2. ❌ **更新** 應用代碼（拉取最新版本）

結果：**新代碼 + 完整歷史數據 = 連續學習改進**

---

## 🔧 硬碟配置（已完成）

### ✅ 您的 Zeabur 設置

```
硬碟 ID: db-storage
掛載目錄: /app/data
用量: 無限
狀態: ✅ 已掛載
```

### 備份路徑

系統會自動在同一硬碟上創建備份：

```
/app/data/
├── trading.db                          ← 當前實時數據庫
├── trading_backup_20260408_100000.db   ← 自動備份 1
├── trading_backup_20260408_110000.db   ← 自動備份 2
└── trading_backup_20260408_120000.db   ← 自動備份 3
```

**當前應用自動檢測**：
```python
# storage.py 中的優先級檢測
優先級順序：
1. /app/data    ← Zeabur 持久硬碟（最優）
2. /data        ← Zeabur 持久卷（備用）
3. ./           ← 本地開發環境（備用）
```

---

### 2️⃣ Zeabur 環境配置

無需手動配置，系統自動處理：

✅ 應用啟動時自動檢測 `/app/data` 是否可用
✅ 優先使用 `/app/data` 持久硬碟
✅ 備用方案 `/data` 持久卷
✅ 數據庫自動創建在對應位置

### 3️⃣ 應用啟動流程

每次應用啟動時（包括部署新版本）：

```
【應用啟動】
  ↓
【檢測存儲路徑】
  ├─ 是否有 /app/data? ✓
  ├─ 是否可寫入? ✓
  └─ 使用: /app/data
  ↓
【連接數據庫】
  └─ /app/data/trading.db
  ↓
【驗證數據完整性】
  ├─ PRAGMA integrity_check
  ├─ 自動備份
  └─ 恢復失敗的備用方案
  ↓
【顯示歷史統計】
  ├─ 📊 生涯交易總筆數
  ├─ 💰 累計盈虧
  ├─ 🧠 AI 學習參數
  └─ 📋 失敗記錄和反思
  ↓
【開始交易】
  └─ 使用保留的所有歷史數據持續運行
```

**啟動日誌示例**：
```
╔════════════════════════════════════════╗
  🗄️  數據持久化系統
╚════════════════════════════════════════╝
📍 存儲類型: Zeabur 持久硬碟 (/app/data)
📍 數據庫路徑: /app/data/trading.db
📊 用途: 交易記錄 + AI 學習 + 失敗分析

✅ 數據庫連接成功
✅ 數據庫完整性檢查通過
✅ 數據庫備份成功: /app/data/trading_backup_20260408_092323.db

【📈 歷史累計統計】
✅ 生涯交易總筆數: 42
✅ 生涯累計盈虧: $1,234.56
✅ 歷史學習資料: 已保留
✅ 失敗記錄: 已保留
✅ AI 反思分析: 已保留
```

---

## 💾 數據結構 - Zeabur `/app/data` 中保存的所有內容

### 交易記錄表
```
trades 表:
  ├─ id, timestamp, symbol
  ├─ signal_type, entry_price, exit_price
  ├─ qty, pnl, total_pnl
  ├─ direction (LONG/SHORT)
  ├─ win_loss (WIN/LOSS/BREAK)
  └─ market_context (JSON: RSI, EMA, ATR, 波動率等)
```

### AI 學習數據
```
lessons 表 (AI 反思和失敗記錄):
  ├─ symbol, timestamp
  ├─ pnl, reason (虧損原因)
  ├─ market_context (當時市場狀況)
  ├─ signal_type
  └─ is_learned (是否已從中學習)
```

### 信號統計表
```
signal_stats 表 (AI 優化參數基礎):
  ├─ symbol, signal_type
  ├─ total_trades, winning_trades, losing_trades
  ├─ win_rate, avg_pnl
  └─ last_updated (最後更新時間)
```

### 自適應參數
```
performance_optimizer 跟蹤:
  ├─ RSI 買點/賣點的自動調整歷史
  ├─ 布林帶參數優化歷史
  ├─ 每個幣種的最優參數
  └─ 市場制度識別結果
```

### 市場制度記錄
```
market_regime_detector 記錄:
  ├─ 每次檢測的市場制度 (UPTREND/DOWNTREND/etc)
  ├─ 趨勢強度分佈
  ├─ 波動率變化
  └─ 適應性交易建議調整
```

---

## 🔄 部署流程 - 保留所有數據

### 每次上傳新版本

```bash
# 1. 本地開發和測試
git commit -m "新功能/改進"
python main.py  # 本地測試

# 2. 推送到 GitHub
git push origin main

# 3. Zeabur 自動部署流程
# ✅ 拉取新代碼
# ✅ 保留 /app/data 硬碟中的所有文件
#    ├─ trading.db (當前數據庫)
#    ├─ trading_backup_*.db (所有備份)
#    ├─ 所有交易記錄
#    ├─ 所有失敗記錄
#    └─ 所有 AI 學習數據
# ✅ 重啟應用

# 4. 應用自動識別和使用舊數據庫
```

### 結果

```
新代碼版本: v1.0 → v1.1 ✨
數據庫: trading.db (保留所有記錄)
✅ 新代碼 + 舊數據 = 連續改進的 AI
```

---

## 🛡️ 數據安全機制

### 自動完整性檢查
```
每次啟動時：
✅ PRAGMA integrity_check - 驗證數據庫完整性
✅ 若發現損壞 - 自動建立時間戳備份
✅ 若無法修復 - 從最新備份恢復
```

### 多層備份策略
```
層級 1: 當前運行的數據庫
        /app/data/trading.db

層級 2: 一小時內的備份
        /app/data/trading_backup_202604081100xx.db

層級 3: 每日檔案
        /app/data/trading_backup_20260408_*.db

層級 4: GitHub 代碼備份
        ✅ 所有交易邏輯和策略都在 Git 中
        ✅ 可隨時恢復應用代碼
```

### 防誤操作
```
✅ 數據庫永不顯示在 Git 倉庫
   .gitignore 已配置: *.db, trading_backup_*.db

✅ 每次啟動自動備份
   防止上一次異常關閉導致的損壞

✅ 自動恢復機制
   無需手動干預
```

---

## ✅ 驗證清單

### 部署前檢查
- [ ] 確認 storage.py 優先檢查 `/app/data`
- [ ] 確認 `.gitignore` 包含 `trading.db`
- [ ] 確認備份邏輯已開啟
- [ ] 本地測試通過

### 部署後檢查
- [ ] 啟動日誌顯示「Zeabur 持久硬碟 (/app/data)」
- [ ] 數據庫完整性檢查通過
- [ ] 歷史交易記錄正確顯示
- [ ] LINE 機器人查詢返回完整歷史
- [ ] 新部署後生涯數單筆數和盈虧未清零

### 數據驗證
```bash
# 查看數據庫位置
ls -lah /app/data/

# 驗證完整性
sqlite3 /app/data/trading.db "PRAGMA integrity_check;"

# 查詢交易筆數
sqlite3 /app/data/trading.db "SELECT COUNT(*) FROM trades;"

# 查詢失敗記錄
sqlite3 /app/data/trading.db "SELECT COUNT(*) FROM lessons;"

# 查詢信號統計
sqlite3 /app/data/trading.db "SELECT * FROM signal_stats LIMIT 5;"
```

---

## 📊 預期結果

每次部署新版本時：
```
代碼版本: v1.0 → v1.1 → v1.2 ...... ✨ 持續改進
═════════════════════════════════════
數據庫:   ✅ 完全保留
  ├─ 交易記錄: 42 筆 → 45 筆 → 48 筆 (累積)
  ├─ 失敗記錄: 已保留用於反思
  ├─ 學習參數: 持續優化中
  └─ 市場分析: 經驗不斷增加

AI 反思: 
  ✅ 能夠回顧過去失敗
  ✅ 學習到的規則永不丟失
  ✅ 策略參數自動優化
  ✅ 24/7 連續改進
```

---

## 🎯 最終架構

```
┌─────────────────────────────────────┐
│      GitHub (代碼倉庫)              │
│  • main.py, strategy.py, etc.      │
│  • 定期推送新版本                  │
└──────────────┬──────────────────────┘
               │ git push
               ↓
┌─────────────────────────────────────┐
│      Zeabur (應用服務)              │
│  【應用目錄】 【數據硬碟】          │
│  • 代碼文件  │ /app/data/         │
│  • 配置文件  │ ├─ trading.db      │
│  • 啟動腳本  │ ├─ backup_*.db    │
│             │ ├─ 交易記錄        │
│             │ ├─ 失敗分析        │
│             │ └─ AI 學習數據      │
└─────────────────────────────────────┘
               │
               ↓
      【每次部署】
      • 更新應用代碼
      • ✅ 保留 /app/data 所有數據
      • 重啟應用
      • 自動識別舊數據庫
      • 繼續交易和學習
```

---

## 🚀 總結

✅ **代碼更新** - 通過 GitHub 推送新版本
✅ **數據永存** - 所有交易/學習/失敗記錄在 Zeabur 硬碟
✅ **AI 記憶** - 永不遺失，持續進化
✅ **自動恢復** - 損壞時自動從備份恢復
✅ **無人守護** - 24/7 自主交易和學習

🎉 **完全自主的 AI 交易機器人** 正式上線！


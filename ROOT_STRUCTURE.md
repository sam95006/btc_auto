# Root Structure Guide

本文件說明目前專案根目錄保留內容、不可亂動區域，以及後續新增檔案的放置規則。

## 1. 根目錄保留清單

### `backend/`
- 後端主程式與 runtime 核心
- 包含 API、worker、services、market、news、security、audit、wallet、trading 等模組

### `config/`
- 系統設定與安全設定
- 例如 security config、資金配置等集中設定檔

### `templates/`
- Flask/Jinja 模板
- 前端主 HTML 模板由這裡提供

### `static/`
- 前端靜態檔
- 目前 active frontend 主要在 `static/nexus/`

### `assets/`
- 非 active runtime 主鏈的素材區
- 先保留，不要隨意清理或搬移

### `tests/`
- 自動化測試
- 放置驗證腳本與單元測試

### `docs/`
- 專案文件與規劃文件
- 包含系統地圖、結構規劃、遷移計畫、主說明文件

### `tools/`
- 工具腳本、部署腳本、本機輔助腳本
- 目前部署腳本在 `tools/deploy/`

### `archives/`
- 歷史檔案、舊版檔案、清理候選區、暫存歸檔區
- `legacy/`、`scratch/`、`_cleanup_candidate/` 已歸檔到此處

### `logs/`
- 執行紀錄與 audit log
- 用於診斷、驗證與安全追蹤

### `venv/`
- Python 虛擬環境
- 屬於執行環境，不是一般專案檔案

### `node_modules/`
- 前端或工具鏈依賴
- 不屬於 active Python runtime，但也不要手動亂動

### `.git/`
- Git 版本控制資料

### `.vscode/`
- 本機編輯器設定

## 2. 不可亂動清單

以下內容屬於 active runtime 或核心配置，未經明確規劃不要直接搬移、刪除、改路徑：

- `backend/`
- `config/`
- `templates/`
- `static/nexus/`
- `run.py`
- `trading.db`
- `.env`

## 3. 可歸檔區

`archives/` 的用途：

- 放舊版檔案
- 放歷史保留檔
- 放已移出的清理候選
- 放暫存驗證資料

規則：

- 不要再從 `archives/` 引用 active runtime
- `archives/` 不應成為新的 import 來源
- 若未來需要比對舊版，可從這裡人工查閱，但不要掛回執行鏈

## 4. 開發規則

未來新增檔案請遵守以下放置規則：

- 新文件放 `docs/`
- 工具腳本放 `tools/`
- 舊版檔案放 `archives/`
- 前端 active 檔案只放 `static/nexus/`
- 後端 active 檔案只放 `backend/`
- 不准再把暫存檔、截圖、臨時 log、一次性驗證腳本丟在根目錄

補充原則：

- 根目錄只保留「啟動、核心、設定、文件入口、依賴環境」
- 非核心內容優先收進 `docs/`、`tools/`、`archives/`

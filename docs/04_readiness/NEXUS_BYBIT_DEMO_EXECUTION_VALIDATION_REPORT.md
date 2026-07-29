# NEXUS Bybit Demo Execution Validation 報告

**狀態：** DEMO_AUTONOMOUS_DISABLED  
**分支：** `feature/bybit-demo-execution-validation`  
**服務：** `nexus-bybit-demo-learning-validation`（獨立 Zeabur 服務，尚未部署）

## 摘要

本套件為 **Bybit Demo 專用** 執行驗證邊界，與 Wave5 公開 Shadow、主網、真實資金完全隔離。資金來源僅允許 Bybit Demo Private API 的 `available_balance`，禁止虛擬帳本與硬編碼 5000U。

## 模組

| 模組 | 用途 |
|------|------|
| `backend/nexus_demo_execution/__init__.py` | 常數：BYBIT_DEMO、FIXED_LEVERAGE=25、風險上限 |
| `capital_constitution.py` | 資金憲章 — 拒絕 fake balance |
| `demo_domain.py` | 僅允許 `api-demo.bybit.com` |
| `account_reader.py` | 帳戶讀取介面 + 測試用 FakeReader |
| `account_epoch.py` | 資金重置偵測 → 新 epoch，保留舊交易資料 |
| `allocation.py` | 從 available_balance 分配保證金 |
| `safety_gate.py` | 七階段安全閘門 |
| `order_adapter.py` | 訂單 stub（閘門通過前禁止寫入） |
| `reconciliation.py` | MATCH / MISMATCH / AMBIGUOUS |
| `kill_switch.py` | 緊急停止 → DEMO_AUTONOMOUS_DISABLED |
| `persistence.py` | SQLite append-only |
| `export_tool.py` | 匯出 summary / trades / reflections / manifest |
| `api_routes.py` | 唯讀 API `/api/nexus/demo-execution/*` |

## 安全閘門（順序）

1. READ_ONLY  
2. ACCOUNT_RECONCILED  
3. DRY_RUN_INTENT  
4. DEMO_ORDER_SMOKE  
5. PROTECTION_VERIFIED  
6. FOUNDER_CONFIRMATION  
7. DEMO_AUTONOMOUS_ENABLED  

任一失敗 → **DEMO_AUTONOMOUS_DISABLED**

## 當前狀態

| 項目 | 值 |
|------|-----|
| autonomous_mode | DEMO_AUTONOMOUS_DISABLED |
| current_stage | READ_ONLY |
| next_gate | FOUNDER_CONFIRMATION_AFTER_SMOKE |
| first_demo_smoke_order_ready | **false** |

## 阻礙項（Blockers）

1. 安全閘門尚未逐級通過  
2. 首次 Demo Smoke 訂單未就緒（需 DEMO_ORDER_SMOKE 以上）  
3. 需 Founder 於 Smoke 測試後手動確認  
4. 禁止未經批准之 Zeabur 部署或合併  

## API 端點（唯讀）

- `GET /api/nexus/demo-execution/status`
- `GET /api/nexus/demo-execution/gate`
- `GET /api/nexus/demo-execution/constitution`
- `GET /api/nexus/demo-execution/domain`
- `GET /api/nexus/demo-execution/kill-switch`
- `GET /api/nexus/demo-execution/persistence`
- `GET /api/nexus/demo-execution/epoch`

## CI

`.github/workflows/bybit_demo_execution_validation.yml`

- security-scan（禁止 mainnet）
- python-tests（≥40 測試）
- typecheck-optional

## 測試

```bash
python -m pytest tests/test_bybit_demo_execution_validation.py -q
```

## 禁止事項

- 主網（api.bybit.com）端點  
- 真實資金交易  
- virtual_balance / hardcoded 5000U  
- 自動資金重置  
- 未經 Founder 批准之部署  

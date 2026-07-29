# NEXUS Bybit Demo Execution Validation 報告

**狀態：** FOUNDER_CONFIRMATION_REQUIRED / DEMO_AUTONOMOUS_DISABLED  
**分支：** `feature/bybit-demo-execution-validation`  
**服務：** `nexus-bybit-demo-learning-validation`（獨立 Zeabur 服務）

## 摘要

本套件為 **Bybit Demo 專用** 執行驗證邊界。本輪 Founder 已批准 `CREATE_AND_DEPLOY_INDEPENDENT_DEMO_VALIDATION_SERVICE`，但 **未批准** 首次 Demo 訂單。閘門鏈最高止於 `FOUNDER_CONFIRMATION_REQUIRED`；不得到達 `DEMO_ORDER_SMOKE_EXECUTED` 或 `DEMO_AUTONOMOUS_ENABLED`。

## 模組

| 模組 | 用途 |
|------|------|
| `safety_gate.py` | 十階段安全閘門（本輪終點 FOUNDER_CONFIRMATION_REQUIRED） |
| `orchestration.py` | DemoValidationOrchestrator — 唯讀驗證週期 |
| `order_payload.py` | Demo 訂單 payload 結構驗證（永不 POST） |
| `protection_payload.py` | 保護鏈 entry→fill→position→SL→TP→verified |
| `http_demo_reader.py` | 真實 Bybit Demo GET reader（api-demo.bybit.com） |
| `export_tool.py` | 匯出 summary / epochs / snapshots / dry_run_intents 等 |
| `kill_switch.py` | Founder 觸發清單緊急停止 |
| `api_routes.py` | 唯讀 API + run-readonly-cycle |

## 安全閘門（順序）

1. READ_ONLY  
2. ACCOUNT_RECONCILED  
3. DRY_RUN_INTENT  
4. DEMO_ORDER_PAYLOAD_VALIDATED  
5. PROTECTION_PAYLOAD_VALIDATED  
6. RESTART_RECOVERY_VERIFIED  
7. PERSISTENCE_VERIFIED  
8. EXPORT_VERIFIED  
9. PROTECTION_VERIFIED  
10. **FOUNDER_CONFIRMATION_REQUIRED** ← 本輪終點  

任一失敗 → **DEMO_AUTONOMOUS_DISABLED**

## 當前狀態

| 項目 | 值 |
|------|-----|
| autonomous_mode | DEMO_AUTONOMOUS_DISABLED |
| current_stage | **FOUNDER_CONFIRMATION_REQUIRED** |
| next_gate | NONE |
| first_demo_smoke_order_ready | **false** |
| can_write_orders | **false** |
| exchange_write_call_count | **0** |

## API 端點

- `GET /api/nexus/demo-execution/status`
- `GET /api/nexus/demo-execution/gate`
- `GET /api/nexus/demo-execution/account`
- `GET /api/nexus/demo-execution/epoch`
- `GET /api/nexus/demo-execution/dry-run/latest`
- `GET|POST /api/nexus/demo-execution/run-readonly-cycle`（安全，無 exchange write）

## CI

```bash
python -m pytest tests/test_bybit_demo_execution_validation.py -q
python tools/ci/demo_validation_gate_runner.py
```

## 部署

- 套件：`deploy/zeabur_bybit_demo_validation/`
- Workflow：`.github/workflows/founder_approved_demo_validation_deploy.yml`
- 確認字串：`DEPLOY_DEMO_VALIDATION`
- **禁止** 覆寫 Stage3 SERVICE_ID `6a3b81652fdef84a45a2a553`

## 禁止事項

- 主網（api.bybit.com）端點  
- 真實資金交易  
- DEMO_ORDER_SMOKE_EXECUTED（本輪）  
- virtual_balance / hardcoded 5000U  
- 未經 Founder 批准之首次 Demo 訂單  

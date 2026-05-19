# ACTIVE_SYSTEM_MAP

Last verified: 2026-05-11

## 1. 啟動入口
- `run.py`
- `backend/api/server.py`
- `backend/worker/runner.py`

## 2. 後端使用中的模組
- `backend/core/env_loader.py`
- `backend/core/event_bus.py`
- `backend/core/system_state_manager.py`
- `backend/services/runtime_store.py`
- `backend/services/layout_store.py`
- `backend/services/nexus_runtime.py`
- `backend/market/market_price_feed_service.py`
- `backend/news/news_ingestion_service.py`
- `backend/news/news_analysis_engine.py`
- `backend/trading/binance_futures_testnet_client.py`
- `backend/trading/binance_spot_testnet_client.py`
- `backend/trading/binance_testnet_execution_engine.py`
- `backend/trading/binance_spot_testnet_execution_engine.py`
- `backend/trading/paper_position_manager.py`
- `backend/trading/pnl_tracker.py`
- `backend/wallet/internal_capital_ledger.py`
- `backend/wallet/mock_wallet_service.py`
- `backend/wallet/loan_manager.py`
- `backend/fleets/base_strategy_engine.py`
- `backend/fleets/signal_fusion_engine.py`
- `backend/fleets/meeting_memory_broadcaster.py`
- `backend/risk/risk_control_engine.py`
- `backend/config/capital_config.py`
- `backend/security/secret_manager.py`
- `backend/security/request_validator.py`
- `backend/audit/audit_logger.py`
- `config/security_config.py`

## 3. 前端使用中的模板
- `templates/nexus_command.html`

## 4. 前端使用中的 JS
- `static/nexus/app.js`
- `static/nexus/api_client.js`
- `static/nexus/state_store.js`
- `static/nexus/layout_state.js`

## 5. 前端使用中的 scenes / components / assets

### components
- `static/nexus/components/ui_top_status_bar.js`
- `static/nexus/components/ui_alert_panel.js`
- `static/nexus/components/ui_chat_dock.js`
- `static/nexus/components/ui_meeting_log_panel.js`
- `static/nexus/components/ui_meeting_dock.js`
- `static/nexus/components/hotspot_editor.js`

### scenes / utils
- `static/nexus/scenes/scene_main_hq.js`
- `static/nexus/scenes/scene_hq_roundtable.js`
- `static/nexus/scenes/scene_fleet_bridge_base.js`
- `static/nexus/scenes/scene_radar_outpost.js`
- `static/nexus/scenes/scene_news_nexus.js`
- `static/nexus/scenes/scene_helpers.js`
- `static/nexus/scenes/station_context_panels.js`
- `static/nexus/utils/presentation.js`

### assets
- `static/nexus/assets/nexus_overview.png`
- `static/nexus/assets/btc_bridge.png`
- `static/nexus/assets/eth_bridge.png`
- `static/nexus/assets/sol_bridge.png`
- `static/nexus/assets/pepe_bridge.png`
- `static/nexus/assets/radar_outpost.png`
- `static/nexus/assets/news_nexus.png`
- `static/nexus/assets/hq_roundtable.png`
- `static/nexus/layout_overrides.json`

## 6. 可疑未使用資料夾
- `legacy/`
  - 目前不在 active runtime 入口鏈上，像歷史版本保留。
- `scratch/`
  - 目前像本機驗證、截圖、暫存與 log 輸出區。
- `shared/`
  - 目前未出現在 active runtime 入口鏈上。
- `assets/`
  - 與 `static/nexus/assets/` 分離，需人工判斷是否為歷史素材。
- `node_modules/`
  - 目前只在本機驗證工具鏈使用，不在 Python runtime 主鏈上。
- `venv/`
  - 執行環境本身，不屬於業務 runtime 程式碼，但不可當成一般垃圾資料夾處理。

## 7. 不可刪除清單
- `run.py`
- `backend/api/server.py`
- `backend/worker/runner.py`
- `backend/services/runtime_store.py`
- `backend/services/nexus_runtime.py`
- `templates/nexus_command.html`
- `static/nexus/app.js`
- `static/nexus/api_client.js`
- `static/nexus/state_store.js`
- `static/nexus/scenes/scene_fleet_bridge_base.js`
- `static/nexus/scenes/scene_main_hq.js`
- `static/nexus/scenes/scene_hq_roundtable.js`
- `static/nexus/scenes/scene_radar_outpost.js`
- `static/nexus/scenes/scene_news_nexus.js`
- `static/nexus/assets/*`
- `trading.db`
- `.env`
- `*.md`

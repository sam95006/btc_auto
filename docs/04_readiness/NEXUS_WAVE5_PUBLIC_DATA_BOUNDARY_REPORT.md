# NEXUS Wave 5 Public Data Boundary Report

## 憲法

模組：`backend/nexus_real_shadow/constitution.py`（`PublicMarketDataConstitution`）

### 允許

- 公開市場 REST **GET**（allowlist 路徑）
- 公開市場 WebSocket Subscribe（public topics）
- Instrument／Ticker／Kline／Orderbook／Funding／OI 等公開 metadata

### 禁止

- Private Endpoint、Authentication Header、API Key／Secret／Signature
- Order Create／Amend／Cancel、Position／Leverage／Margin／Trading Stop Write
- Wallet Read、Private Execution Stream
- 對 Bybit Domain 的 POST／PUT／PATCH／DELETE

### Runtime Counters（必須維持 0）

- `private_endpoint_call_count=0`
- `authenticated_request_count=0`
- `exchange_write_call_count=0`

違規狀態：`SECURITY_BLOCKED_PUBLIC_DATA_BOUNDARY`

## 靜態掃描

- `backend/nexus_real_shadow/security_scan.py`
- CI Job：`wave5-security`

## CI 約束

- 不載入任何 Exchange Secret
- Deterministic fixture／mock；外部網路失敗不得判為程式錯誤
- 可選非阻擋：`manual_public_network_smoke`（本輪不阻擋正式 CI）

## 結論

`public_data_constitution=true` · `private_endpoint_block=true` · `exchange_write_call_count=0`

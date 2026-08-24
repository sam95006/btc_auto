# Observational GET-only preflight (2026-08-24)

Ran: `python tools/ci/demo_6h_v2_preflight.py --observational`

Default `DEMO_VAL_URL=https://nexus-bybit-demo-val.zeabur.app`

| Check | Result |
|-------|--------|
| health | HTTP 404 |
| fee-policy | HTTP 404 |
| market/status | HTTP 404 |
| demo account | HTTP 404 |
| control-plane overview | HTTP 404 |
| Stage3 health | HTTP 404 (expected forbidden/legacy) |
| Control-plane health | HTTP 404 (expected) |

**Blocker:** public hostname in workflows is **not** serving the confirmed live Full Engine service `6a82a79aa21454a2cf6b0015`. Founder logs show the engine running; this agent cannot reach it via the documented `.zeabur.app` URL.

No POST / no 6H start / no writes attempted.

## BYBIT_MAINNET_LINEAR

Proven from source (not renamed):

- `backend/market/scanner/universe.py` uses `https://api.bybit.com` public REST (`/v5/market/tickers`, instruments-info)
- `backend/market/scanner/bybit_public_ws.py` uses `wss://stream.bybit.com/v5/public/linear`
- Module docstring: public topics only, **no API key**, **no private streams**
- Trading / Demo writes remain locked to `https://api-demo.bybit.com` (`backend/nexus_demo_execution/demo_write_client.py`)

**Meaning:** read-only public linear **market-data / universe label**, not the Demo trading endpoint selector.

# PUB-J Hard Bans

1. No exchange SDK / client usage (Bybit, Binance, OKX, etc.)
2. No private-core imports or Founder private runtime bindings
3. No trading controls (place/cancel/arm orders, positions, wallets)
4. No production push / billing credentials in this foundation
5. No `*_status.json` artifacts for this lane
6. Mock mode must surface DEMO_DATA; live mode must not fabricate unavailable fields

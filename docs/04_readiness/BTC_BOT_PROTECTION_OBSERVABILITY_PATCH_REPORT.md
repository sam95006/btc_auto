# BTC_BOT Protection Observability Patch Report

## Founder UI Protection
**PROTECTED_VERIFIED_BY_FOUNDER_UI**（Bybit Demo 人工唯讀）

| 欄位 | 值 |
|---|---|
| symbol | BTCUSDT |
| side | Buy 0.026 |
| entry | 63392.30 |
| liq | 61162.50 |
| TP | 64816.70 MarkPrice |
| SL | 62439.60 MarkPrice |
| coverage | FullPosition／SellToCloseLong／PendingTrigger |
| evidence_quality | HIGH_EXTERNAL_UI |
| api_confirmed | **false**（本輪修補尚未 Deploy） |

## API Protection Before
`AMBIGUOUS`／`UNVERIFIED`（僅見 1／2 單；缺 stopOrderType／triggerPrice；status≠orderStatus）

## API Protection After RC
程式可自動判：`PROTECTED_VERIFIED`／`PARTIALLY_PROTECTED`／`UNPROTECTED`／`AMBIGUOUS`／`FLAT_NOT_APPLICABLE`  
（需 Deploy 後才會反映到 Live API）

## Open Orders Exposed
`openOrders[]` + `openOrderCount` + `openOrderCountFromArray`；`currentOrder` 保留向後相容

## Protection Group
`protectionGroups[]`：symbol／positionIdx／TP／SL／coverage／tradingStopMode／evidenceQuality

## Status Normalization
`normalizedOrderStatus`（相容 `orderStatus`／`status`）

## Read-only Verified
無 Exchange Write；缺值 → null／UNKNOWN；不填假 0

## Tests
`tests/test_protection_order_observability.py` 15 passed  
Related／Shadow／Runtime 本機 PASS；Full Suite triage：12 failed／1598 passed；`release_delta_regression=0`

## CI Run
（Push 後填入）

## Latest RC SHA
（Push 後填入）

## Live Position／Orders
1／2（仍 HOLD；send=false）

## Deployment Window
**UNAVAILABLE**（未 0／0）

## Merge／Deploy／Observer／Clean24H
false／false／false／false

## Recommendation
**HOLD_FOR_OPEN_EXPOSURE**

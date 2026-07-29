# NEXUS Current State

> 本檔為累積狀態摘要，不覆寫歷史證據檔。

## 凍結 Source of Truth（不得再向 PR #1～#4 加功能 Commit）

| PR | Branch | Head | Status |
|----|--------|------|--------|
| #1 | `rc/runtime-stall-zeabur-observer` | `c2b3c95…` | Frozen Draft · merge/deploy=false |
| #2 | `feature/wave2-global-market-six-role` | frozen | Frozen Draft |
| #3 | `feature/wave3-adaptive-policy-learning` | `aa43d463…` | Frozen Draft |
| #4 | `feature/wave4-product-ui-intelligence` | `dfbaa61b0e26acd2b0de218e003c40a101e1286d` | Frozen Draft · Wave4 UI 驗收完成 |

## Wave 5（Draft PR #5 · CI Truth Reconciliation）

- Branch：`feature/wave5-real-public-shadow-runtime`
- Base：PR #4 Head `dfbaa61…`
- 修復前 Head：`4b90e16…`（歷史中間 `b3031c…` 僅 docs checkpoint，非 PR Head）
- Recommendation：**`WAVE5_REAL_PUBLIC_SHADOW_PARTIAL_WITH_CI_BLOCKERS`**（待 CI 全綠後才可 Freeze／Ready）
- 固定：PUBLIC ONLY · SHADOW ONLY · NO WRITE · NO DEPLOY · NO MERGE

## Live（唯讀）

- 2026-07-29：`position_count=0` · `open_order_count=0`
- Deployment Window：`AVAILABLE_FOR_PR1_INDEPENDENT_VALIDATION`
- **仍** merge=false · deploy=false（需 Founder 獨立批准）

## 禁止

Mainnet · Real Money · ARM · Exchange Write · Force Push · 平倉／改 TP-SL／Restart 為部署方便

# NEXUS Current State

> 本檔為累積狀態摘要，不覆寫歷史證據檔。

## 凍結 Source of Truth（不得再向 PR #1～#4 加功能 Commit）

| PR | Branch | Head | Status |
|----|--------|------|--------|
| #1 | `rc/runtime-stall-zeabur-observer` | `c2b3c95…` | Frozen Draft · merge/deploy=false |
| #2 | `feature/wave2-global-market-six-role` | frozen | Frozen Draft |
| #3 | `feature/wave3-adaptive-policy-learning` | `aa43d463…` | Frozen Draft |
| #4 | `feature/wave4-product-ui-intelligence` | `dfbaa61b0e26acd2b0de218e003c40a101e1286d` | Frozen Draft · Wave4 UI 驗收完成 |

## Wave 5（Draft PR #5 · Scope Frozen）

- Branch：`feature/wave5-real-public-shadow-runtime`
- Base：PR #4 Head `dfbaa61…`
- CI 全綠 Head：`02426d9…` · run `30413566548`
- Recommendation：`WAVE5_REAL_PUBLIC_SHADOW_DRAFT_PR_READY_FOR_REVIEW`
- `pr5_scope_frozen=true`（僅允許 docs-only CI evidence）
- 固定：PUBLIC ONLY · SHADOW ONLY · NO WRITE · NO DEPLOY · NO MERGE

## Live（唯讀）

- 2026-07-29：`position_count=0` · `open_order_count=0`
- Deployment Window：`AVAILABLE_FOR_PR1_INDEPENDENT_VALIDATION`
- **仍** merge=false · deploy=false（需 Founder 獨立批准）

## 禁止

Mainnet · Real Money · ARM · Exchange Write · Force Push · 平倉／改 TP-SL／Restart 為部署方便

## PR #1 Deployment Window（Wave 5.1）

- runtime_rc_head: `c2b3c95…`（不變）
- docs_truth_head: `630e36e…`（僅文件）
- Live triple 0/0: PASS
- Recommendation: `PR1_DEPLOYMENT_READY_AWAITING_FOUNDER_APPROVAL`
- merge=false · deploy=false · 等待 Founder 批准

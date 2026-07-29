# NEXUS Wave 5 Real Public Shadow Runtime 報告

## 摘要（Truth Reconciliation）

- **目前 Recommendation**：`WAVE5_REAL_PUBLIC_SHADOW_PARTIAL_WITH_CI_BLOCKERS`
- **不得**在 CI 全綠前宣稱 `WAVE5_REAL_PUBLIC_SHADOW_DRAFT_PR_READY_FOR_REVIEW`
- **Draft PR**：[#5](https://github.com/sam95006/btc_auto/pull/5)
- **actual_base_sha**：`dfbaa61b0e26acd2b0de218e003c40a101e1286d`
- **修復前 actual_head_sha**：`4b90e16268bff666710758fcc93c342b93f57278`
- **歷史中間 Commit（非 PR Head）**：`b3031c675320e7c4fe046fe4dc442dcb795ca858`
- merge=false／deploy=false／exchange_write=false／live_effect=false

## CI 失敗證據（run 30412776113）

| Job | 結果 |
|-----|------|
| wave5-security | PASS |
| wave5-provider-contract | PASS |
| wave5-frontend | PASS |
| wave5-docker | PASS |
| wave5-container-soak | PASS |
| wave5-python | **FAIL**（634 passed／1 failed） |
| wave5-browser | **FAIL**（webServer 180s timeout） |

### wave5-python 根因

- 測試：`tests/test_wave4_visual_acceptance.py::TestVisualAcceptanceDocs::test_checkpoint_recommendation_partial_or_ready`
- Checkpoint 正式值：`WAVE4_PRODUCT_UI_DRAFT_PR_READY_FOR_REVIEW`
- 舊 Allowlist 未含此 Canonical enum（僅含 PARTIAL 與已 deprecated 的 `WAVE4_PRODUCT_UI_READY`）
- **修復**：Allowlist 改為明確 Enum：`DRAFT_PR_READY_FOR_REVIEW`｜`PARTIAL_WITH_VISUAL_VALIDATION_BLOCKERS`｜`BLOCKED_WAVE4_PRODUCT_UI`

### wave5-browser 根因

- Playwright `webServer` 執行 `vite preview`，但 CI **未先** `npm run build` → 無 `dist` → 等待 URL 逾時 180s
- **不是**單純把 timeout 加長
- **修復**：
  1. `playwright.config.ts`：`npm run build && vite preview`；`EXPLICIT_FIXTURE_MODE=true`
  2. `tools/ci/wave5_browser_ready.sh`：Backend `/health` → Frontend `/overview` → 再跑 Playwright
  3. CI 上傳 server log artifact 於失敗時

## 模式

PUBLIC MARKET DATA ONLY／SHADOW／NOT EXECUTED／固定 25x

## 本機回歸（修復後、推送前）

- Wave4 visual acceptance：75 passed
- Wave2～5 合計：635 passed／failure=0
- Frontend typecheck：PASS

## 相關文件

- [Checkpoint](./NEXUS_WAVE5_REAL_PUBLIC_SHADOW_CHECKPOINT.json)
- [Public Data Boundary](./NEXUS_WAVE5_PUBLIC_DATA_BOUNDARY_REPORT.md)
- [Soak Report](./NEXUS_WAVE5_SHADOW_RUNTIME_SOAK_REPORT.md)

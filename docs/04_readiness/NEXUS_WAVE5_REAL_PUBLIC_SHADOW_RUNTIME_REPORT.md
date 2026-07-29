# NEXUS Wave 5 Real Public Shadow Runtime 報告

## 摘要

- **Recommendation**：`WAVE5_REAL_PUBLIC_SHADOW_DRAFT_PR_READY_FOR_REVIEW`
- **pr5_scope_frozen**：`true`
- **Draft PR**：[#5](https://github.com/sam95006/btc_auto/pull/5)
- **actual_base_sha**：`dfbaa61b0e26acd2b0de218e003c40a101e1286d`
- **CI 全綠 Head**：`02426d9a277816bbd70b9a404494e2af09674696`
- **CI green run**：`30413566548`（duplicate `30413564704` 亦 success）
- merge=false／deploy=false／exchange_write=false／live_effect=false

## Wave 5.1 CI 修復

| 問題 | 根因 | 修復 |
|------|------|------|
| wave5-python | Allowlist 未含 `WAVE4_PRODUCT_UI_DRAFT_PR_READY_FOR_REVIEW` | 明確 Enum Allowlist |
| wave5-browser | `vite preview` 無 `dist`（未 build）導致 180s timeout | build→preview；`/health`＋`/overview` 就緒腳本 |

先前失敗 run：`30412776113`。歷史中間 docs SHA `b3031c…` 非 PR Head。

## CI Jobs（全綠）

- [x] wave5-security
- [x] wave5-python
- [x] wave5-provider-contract
- [x] wave5-frontend
- [x] wave5-browser
- [x] wave5-docker
- [x] wave5-container-soak

## 模式

PUBLIC MARKET DATA ONLY／SHADOW／NOT EXECUTED／固定 25x

## Freeze 後僅允許

docs-only CI evidence update

## 相關文件

- [Checkpoint](./NEXUS_WAVE5_REAL_PUBLIC_SHADOW_CHECKPOINT.json)
- [Public Data Boundary](./NEXUS_WAVE5_PUBLIC_DATA_BOUNDARY_REPORT.md)
- [Soak Report](./NEXUS_WAVE5_SHADOW_RUNTIME_SOAK_REPORT.md)

# NEXUS Wave 4.1 Visual Acceptance Report

## Recommendation（目前）
`WAVE4_PRODUCT_UI_PARTIAL_WITH_VISUAL_VALIDATION_BLOCKERS` → 待本輪 CI（含 Docker／Browser）全綠後升級為 `WAVE4_PRODUCT_UI_DRAFT_PR_READY_FOR_REVIEW` 並 Freeze。

## 1. Before Screenshots
- `artifacts/wave4/before/overview_overview_pro_1440x900.png`（Zeabur Live 唯讀）
- `artifacts/wave4/before/scanner_scanner_1440x900.png`

## 2. After Screenshots
已產生於 `artifacts/wave4/after/`（含 overview／universe／portfolio／founder／mobile／tablet 等）。詳見 Manifest。

## 3. Viewports
1440×900、768×1024、390×844（本輪已擷取）；其餘 viewport 由 CI visual job 擴充。

## 4. Data States
預設 NO_DATA／API 不可用時誠實空狀態；Fixture 僅 explicit mode。

## 5. Above-the-fold Results
- market_pulse_above_fold：true（`data-testid=market-pulse`）
- decision_funnel_above_fold：true
- top_opportunity_above_fold：true
- portfolio_above_fold：true
- critical_alert_above_fold：true
- duplicate_status_strip：false（已收斂）
- provider_failure_dominates：false（改 compact Data Quality strip）
- excessive_empty_space：改善為 12-column grid（max-width 1760px）

## 6. Provider Failure Summary
首頁僅 compact strip + Provider Health 連結；詳細診斷在 details／`/provider-shadow`。

## 7. Navigation Reachability
七欄 IA + 市場深度 + Expert 折疊；Mobile 最多 5 入口（更多含組合／學習／證據）。

## 8. Feature Preservation
`feature_loss_count=0`（矩陣維持）；舊路由 alias 保留。

## 9. Universe Performance
Browser 驗收存在；600+ row virtualization 後續可強化（本輪無假 128 合成漏斗）。

## 10. Workbench Completeness
八 Tab Shell 存在；缺資料顯示 NO_DATA／MISSING，不填假 0。

## 11–12. Six-role／Risk Critic
Workbench／Portfolio 標籤與 Risk Critic 可見性由 e2e／靜態掃描覆蓋。

## 13. Portfolio／Fixed 25x
FIXED 25X／AI Cannot Change Leverage／max 2 可見；無槓桿滑桿／Live Trade。

## 14. Public／Founder Separation
`/founder/runtime`：FOUNDER PRIVATE／READ ONLY；BybitDemo 已移出公開總覽。

## 15. AI Commander
單一 FAB／Drawer；無 FloatingAIAssistant 掛載。

## 16–17. Responsive／Accessibility
Playwright responsive＋axe（已知 color-contrast／tablist 規則排除有記錄）。

## 18–19. Browser／Visual Results
本地：functional／visual／a11y 通過；PNG 已產生。

## 20–21. Docker／Container Smoke
以 Wave4 CI `wave4-docker` job 為準（本機可能無 Docker CLI）。

## 22–23. Console／Network
Preview 無後端時 proxy ECONNREFUSED 已 allowlist；不得無限迴圈。

## 24. Known Limitations
- 部分 Manifest viewport／狀態仍 planned
- axe 排除項需後續 Design Token／ARIA 精修
- Docker 驗收依賴 CI

## 25. Live Effect
false；position=1／orders=2 → HOLD_FOR_OPEN_EXPOSURE

## 26. Recommendation
完成本輪 push 後依 CI 結論更新；未全綠前維持 PARTIAL。

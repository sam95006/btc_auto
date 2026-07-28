# NEXUS Wave 4.1 Visual Acceptance Report

## 1. Before Screenshots
`artifacts/wave4/before/`（Zeabur Live 唯讀 overview／scanner）。

## 2. After Screenshots
`artifacts/wave4/after/`（Local Wave4 Build PNG）。

## 3. Viewports
1440×900、768×1024、390×844 已擷取；其餘由 CI visual job 擴充。

## 4. Data States
NO_DATA／DEGRADED／EXPLICIT_FIXTURE（Fixture 非預設）。

## 5. Above-the-fold Results
Market Pulse／Funnel／Opportunities／Portfolio／Alerts 於首屏；Provider 不主導。

## 6. Provider Failure Summary
Compact Data Quality strip＋Provider Health 連結。

## 7. Navigation Reachability
七欄 IA；Mobile 最多 5 入口＋更多。

## 8. Feature Preservation
feature_loss=0；舊路由 alias 保留。

## 9. Universe Performance
Browser 驗收；無合成 128 漏斗。

## 10. Workbench Completeness
八 Tab Shell；缺資料誠實標示。

## 11. Six-role Visibility
Workbench／相關頁可達。

## 12. Risk Critic Veto Visibility
Portfolio／Workbench 風險標籤可驗證。

## 13. Portfolio／Fixed 25x
FIXED 25X；無槓桿控制／Live Trade。

## 14. Public／Founder Separation
`/founder/runtime` READ ONLY；BybitDemo 不在公開首頁。

## 15. AI Commander
單一例；無 FloatingAIAssistant 掛載。

## 16. Responsive
Desktop／Tablet／Mobile e2e。

## 17. Accessibility
axe suite；已知排除項有記錄。

## 18. Browser Results
本地／CI browser job。

## 19. Visual Results
PNG captured（部分 planned 於 Manifest）。

## 20. Docker
CI `wave4-docker`；SPA prefixes 含 universe／founder。

## 21. Container Smoke
/health／/overview／/universe／/founder/runtime。

## 22. Console Errors
Proxy allowlist（無後端 preview）。

## 23. Network Errors
無無限迴圈要求。

## 24. Known Limitations
部分 viewport planned；axe token／tablist 後續精修。

## 25. Live Effect
false；HOLD_FOR_OPEN_EXPOSURE。

## 26. Recommendation
待 CI 全綠後可 Freeze；否則維持 PARTIAL_WITH_VISUAL_VALIDATION_BLOCKERS。

# BTC_BOT 五小時 RC CI Final Report

## 1. Started At
2026-07-27T16:55:00Z（約）

## 2. Ended At
2026-07-27T17:45:00Z（約）

## 3. Duration
約 50 分鐘有效執行（CI 來回修正＋驗證；未空等滿五小時）

## 4. RC Base
`2761718d510f35728e5c108003ceb59ab8039dbc`

## 5. RC Branch
`rc/runtime-stall-zeabur-observer`

## 6. RC Commit（最終 HEAD）
`b005a4103b7cba36707b987e137eced2a7f46de0`

初始 Scoped Commit：`38c198332e247f9b2088c45f8fdb0c571075d4df`  
（parent = 2761718）

## 7. Push Result
成功（非 force）；`deployment_triggered=false`

## 8. Remote SHA
`b005a4103b7cba36707b987e137eced2a7f46de0`（= origin/rc/runtime-stall-zeabur-observer）

## 9. Auto Deploy Risk
`rc_branch_deploy_trigger=false`  
（`nexus_deploy_zeabur_on_main.yml` 僅監聽 `main` push）

## 10. Deployment Triggered
false

## 11. Workflow Runs
| Run | SHA | 結果 |
|---|---|---|
| 30287412973 | 38c1983 | failure（path／.env.example 誤判） |
| 30287558489 | 0be7dfc | failure（secret 函式誤判；apt archives 路徑） |
| 30287965361 | 89cfac2 | failure（Docker／Frontend／Runtime PASS；Full Suite triage FAIL） |
| 30288504805 | 75f0518 | failure（Full Suite triage；後證實 CI 多 2 個 singleton） |
| 30289243674 | 31110cc | failure（failed_count=14；2 new singleton） |
| **30289833821** | **b005a41** | **success（全綠）** |

## 12. Python Compile
PASS

## 13. Runtime Tests
PASS（含 stall remediation／demo autonomous）

## 14. Related／Shadow Tests
PASS

## 15. Full Suite
CI：`12 failed／1578 passed`  
`release_delta_regression=0`

## 16. Baseline Debt
`FULL_SUITE_BASELINE_DEBT_12`（不得標成全綠）

## 17. Frontend
npm ci／typecheck／build／safety = PASS

## 18. Docker Build
PASS

## 19. Image Digest
`sha256:044b08af6b336602ac1a7113c3d3377de95d9deb3d0b18465811e5cdce69e8cc`

## 20. Image Safety
PASS（僅掃描 `/app`；無 archives／.env／terminals；controller.py 存在）

## 21. Container Smoke
PASS（≤10 分鐘；observer_default_disabled=true；無 exchange secret）

## 22. Observer Safety
default_disabled／read_only／fail-closed 測試已覆蓋；本輪 **未啟用** Observer

## 23. Fail Injection
`tests/test_runtime_stall_remediation.py` 本機 14 passed（含 boot／commit／owner／stall／mainnet 等）

## 24. Secret Scan
PASS（RC 內 active literal secret hits=0；僅掃字串字面量）

## 25. Scope Check
無 strategy／risk／leverage／Wave1 UI／Genesis／Dirty Archives

## 26. Changed Files（相對 Base）
- `.github/workflows/rc_runtime_stall_validation.yml`
- `backend/nexus_research/demo_autonomous/{api_routes,controller,error_sanitize,ops_status,outcome_reflection,position_supervisor,runtime_bootstrap,validation_observer}.py`
- `backend/runtime/single_instance_guard.py`（Linux flock；CI 發現後補強）
- `tests/test_runtime_stall_remediation.py`
- `tools/research/triage_full_suite_baseline.py`
- `docs/04_readiness/*`（path／secret／observer／zeabur-only 等）

## 27. Additional Commits
CI 誤判修正 ×5 + Linux flock ×1（皆在同一 RC branch）

## 28. Draft PR
https://github.com/sam95006/btc_auto/pull/1  
Base=`stage3-demo-learning`；**draft=true**；未 Merge

## 29. Deployment Package
`docs/04_readiness/BTC_BOT_RC_DEPLOYMENT_PACKAGE.md`

## 30. Rollback Package
見 Deployment Package §D；Rollback Target=部署前 Commit

## 31. Known Limitations
- Full Suite 仍有 12 項 baseline debt（非本 RC 引入）
- Dockerfile 預設 `NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=true` 未改（本輪禁止改 Auto Send）；CI／建議 Deploy 以 env 覆寫／保持已批准值
- image digest 為 CI 建置結果，Zeabur 實際 digest 需 Deploy 後再確認
- Dirty Root Archives 未動

## 32. Mainline Effect
false（未 merge main／stage3）

## 33. Exchange Effect
false

## 34. Observer Enabled
false

## 35. Clean24H Started
false

## 36. Recommendation
**READY_FOR_SCOPED_RUNTIME_FIX_MERGE_AND_ZEABUR_DEPLOY_APPROVAL**

## 37. Next Founder Approval
等待第二階段批准：

> 批准 Scoped Runtime Fix Merge 至 Zeabur 部署分支並 Deploy；  
> 部署後僅做唯讀 Smoke，禁止啟用 Observer 與 Clean 24H。

---

固定旗標：Deploy=false／ObserverEnabled=false／Clean24HStarted=false／ExchangeWrite=false／Mainnet=false／RealMoney=false

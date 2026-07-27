# BTC_BOT RC Deployment Package（尚未 Deploy）

**RC SHA：** `b005a4103b7cba36707b987e137eced2a7f46de0`  
**Base SHA：** `2761718d510f35728e5c108003ceb59ab8039dbc`  
**Branch：** `rc/runtime-stall-zeabur-observer`  
**CI Run：** https://github.com/sam95006/btc_auto/actions/runs/30289833821 （success）  
**狀態：** CI 全綠；等待 Founder 第二階段批准  
**本輪固定：** Deploy=false／ObserverEnabled=false／Clean24HStarted=false

## A. Deployment Candidate

| 欄位 | 值 |
|---|---|
| rc_sha | b005a4103b7cba36707b987e137eced2a7f46de0 |
| base_sha | 2761718d510f35728e5c108003ceb59ab8039dbc |
| image_digest | sha256:044b08af6b336602ac1a7113c3d3377de95d9deb3d0b18465811e5cdce69e8cc |
| schema_change | false |
| migration_required | false |
| env_change_required | false（建議維持 Observer=false） |
| secret_required | 既有 Demo 憑證（不新增；RC secret finding=0） |
| expected_restart | true |
| expected_boot_change | true |
| execution_effect | false |
| rollback_sha | 部署前 Live Commit（Deploy 當下記錄；預期 2761718 或當下 Zeabur HEAD） |

## B. Zeabur Environment Matrix（僅建議，本輪不設定）

| 變數 | 建議值 |
|---|---|
| NEXUS_ZEABUR_CLEAN_OBSERVER | false |
| AUTONOMOUS_SEND / NEXUS_AUTONOMOUS_DEMO_AUTO_SEND | 保持目前已批准值（本輪不改） |
| MAINNET | false |
| REAL_MONEY | false |
| ARM | false |

## C. Post-deploy 唯讀 Smoke Checklist

- deployment_sha／boot_id／controller_owner==1
- scanner_health／controller_health
- position_count／open_order_count／protection／reconciliation
- paper／ledger
- observer_disabled==true
- mainnet==false／real_money==false
- exchange_write_count==0

## D. Rollback

- Rollback Target = 部署前 Commit
- 不修改 Position／不取消 Protection／不人工平倉
- 回滾後重新 Reconcile；Observer 維持關閉

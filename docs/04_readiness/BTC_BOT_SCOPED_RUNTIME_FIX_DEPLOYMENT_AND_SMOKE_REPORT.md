# BTC_BOT Scoped Runtime Fix — Deployment and Smoke Report

## Latest RC SHA
`cfd2c26860b9ec87dc3de08dcf2a63dbfe0f3b8c`

## Latest CI Run
https://github.com/sam95006/btc_auto/actions/runs/30318891942

## CI Result
**PASS**（python-runtime／frontend／docker-build 全綠）

## Full Suite
12 failed／1578 passed（CI triage）

## Baseline Debt
`FULL_SUITE_BASELINE_DEBT_12`；`release_delta_regression=0`

## Auto Send Default
**false**（Dockerfile／runtime env 缺值 fail-closed；session 無法單獨啟用）  
Commit：`fix(safety): default autonomous demo send to disabled`

## PR Head
`cfd2c26860b9ec87dc3de08dcf2a63dbfe0f3b8c`（PR #1 仍為 Draft）

## PR Merge
**未執行**

## Merge SHA
n/a

## Pre-deploy SHA
Live `deploymentCommit` 空白／無法對到；既有服務 boot：`232394af-536c-49a8-a782-2eeb973ed060`

## Pre-deploy Boot
`232394af-536c-49a8-a782-2eeb973ed060`

## Pre-deploy Position
**1**（BTCUSDT size=0.026 Buy）

## Pre-deploy Orders
**2**（含保護相關 Untriggered 單）

## Zeabur Deployment
**未執行**（閘門阻擋）

## Deployed SHA
n/a

## New Boot
n/a

## Controller Owner
1（預部署觀測）

## Controller Progress
cycleCount 持續有值（預部署）；Scanner lastScanAge 可更新

## Scanner Progress
預部署 scannerStatus=RUNNING（仍可能帶舊 stall 語意；本次本應由部署修復）

## Runtime Health
預部署帳戶狀態：`EXISTING_ACCOUNT_STATE_REQUIRES_REVIEW`

## Position／Orders
1／2 → **不符合**部署必要條件（必須 0／0）

## Reconciliation
OK（但有未平倉暴露）

## Stale Block Reason
預部署曾見 `existing_position_or_order`／帳戶需審查；本次未人工干預

## Observer Enabled
false（未啟用）

## Auto Send
Live 目前仍為 true（舊映像／舊 env）；RC 新 HEAD 預設已改 false，但**尚未部署**

## Exchange Writes
本輪 0（唯讀）

## Mainnet
false

## Real Money
false

## Rollback Triggered
false（未部署，無需回滾）

## Smoke Verdict
**未執行**

## Clean24H Started
false

## Recommendation
**BLOCKED_DEPLOYMENT_OR_SMOKE**

精確閘門：`HOLD_FOR_OPEN_EXPOSURE`

## Next Founder Approval
請在帳戶回到 **Position=0／Open Orders=0**（且無 Ambiguous Intent）後，再批准：

> 合併 PR #1 至 `stage3-demo-learning` 並觸發 Zeabur Deploy；部署後僅唯讀 Smoke；Observer／Clean 24H／Auto Send 啟用仍須第三階段批准。

**禁止**為部署而人工平倉或取消保護單（除非 Founder 另行明確批准處置暴露）。

---

### 固定旗標
ObserverEnabled=false／Clean24HStarted=false／Mainnet=false／RealMoney=false／Merge=false／Deploy=false

### 已完成（本輪）
1. PR／祖先驗證：`b005a41` ⊂ `490b782`（僅 docs）；最新 fail-closed HEAD=`cfd2c26`
2. Auto Send fail-closed 最小修正＋測試＋CI 全綠
3. 預部署 Live Safety Snapshot → 發現開放暴露 → **停止**

### 證據檔
`docs/04_readiness/BTC_BOT_PREDEPLOY_LIVE_SAFETY_SNAPSHOT.json`

# BTC_BOT Open Exposure Hold 與 Deployment Window 報告

**Observed At：** 2026-07-28T01:12:38Z ～ 2026-07-28T01:14:59Z（UTC）  
**Live：** `https://nexus-stage3-bybit-demo-learning.zeabur.app`  
**RC 功能綠燈：** `cfd2c26860b9ec87dc3de08dcf2a63dbfe0f3b8c`（CI run 30318891942 PASS）  
**PR #1 HEAD：** `ac3998f75d4fceb5316a14307babf561eebb8048`（Draft；含 docs；`cfd2c26` 為祖先）  
**本輪動作：** 唯讀驗證 only｜Merge=false｜Deploy=false｜無 Restart｜無人工干預持倉

---

## 1. Position

| 欄位 | 值 |
|---|---|
| position_count | **1** |
| symbol | BTCUSDT |
| side | Buy |
| size | 0.026 |
| entry_price | 63392.3 |
| mark_price | null（status 未回） |
| unrealized_pnl | 約 -5.2 ～ -6.3（三 snapshot 波動） |
| liquidation_price | 61162.5（來自 write-trace 唯讀） |
| leverage | 25（write-trace） |
| position_idx | 0（write-trace） |
| isolated | true |
| opened_at | **未知**（API 未提供） |
| protectionActive（position 欄） | **false** |
| position.stopLoss / takeProfit | **null / null** |

## 2. Orders（唯讀可見範圍）

Live `status.openOrderCount=**2**`，但 API 只暴露 `currentOrder = open_orders[0]`（見 `ops_status.py`），**第二張訂單內容無法從公開唯讀 API 取得**。

### 可見訂單 #1（唯一可列欄位）

| 欄位 | 值 |
|---|---|
| order_id_hash | `67ad0b78f57e1fdd` |
| order_link_id_hash | null／空 |
| symbol | BTCUSDT |
| side | Sell（與 Buy 持倉相反 → 方向符合減倉） |
| order_type | **未知**（OrderView 未保留） |
| stop_order_type | **未知** |
| trigger_price | **未知** |
| trigger_by | **未知** |
| qty | 0.026（= 持倉 size） |
| reduce_only | **未知** |
| close_on_trigger | **未知** |
| position_idx | **未知**（持倉 idx=0，無法對單） |
| order_status | Untriggered |
| created_at / updated_at | ms `1785200729846` |
| belongs_to_current_position | **可能**（symbol／qty／反向 side 吻合；無法證明） |
| protection_role | **未知（SL 或 TP 或其它條件單）** |

### 訂單 #2

| 欄位 | 值 |
|---|---|
| 全部細節 | **不可見**（僅知存在於 openOrderCount=2） |
| protection_role | **未知** |

### 根因（觀測缺口，非本輪可 Deploy 修復）

1. `DemoOpenOrderReader`／`OrderView` 解析時丟棄 `stopOrderType`、`triggerPrice`、`reduceOnly`、`closeOnTrigger`、`positionIdx` 等保護關鍵欄位。  
2. `build_operations_status` 只回傳 `open_orders[0]` 為 `currentOrder`。  
3. `_protection_from_orders` 檢查 `orderStatus`，但 OrderView 輸出鍵名為 `status` → 即使 Untriggered 也常落到 `protectionStatus=UNVERIFIED`。

---

## 3. Protection Verdict

**`AMBIGUOUS`**

理由（任一即不足 PROTECTED_VERIFIED）：

- 無法證明一張為 Stop Loss、一張為 Take Profit  
- 無法證明 trigger／reduceOnly／closeOnTrigger／positionIdx 覆蓋  
- 第二張訂單完全不可見  
- 持倉欄位 SL／TP 為 null，且 `protectionStatus=UNVERIFIED`

→ 依規則標記：**`OPEN_EXPOSURE_SAFETY_INCIDENT`**

### Founder 人工決策資訊（Runbook，不執行）

請在 **Bybit Demo 控制台**（唯讀）確認：

1. BTCUSDT 一方向 Buy 0.026 是否掛有 **交易所端 SL + TP**（或 Trading Stop）  
2. 兩張條件單 qty／positionIdx 是否完整覆蓋 0.026  
3. 是否存在第三張孤兒單或加倉單  

**禁止**為部署而平倉／改 SL／TP／取消單。

---

## 4. Exit Policy／Supervisor／Controller／Scanner

| 項目 | 觀測 |
|---|---|
| Exit Policy 存在且已持久化（針對**目前**倉） | **無法證實**。Supervisor 有跑（`exitSupervisorEnabled=true`），但 `lastTrade.entry=65300.1` ≠ 目前 `entry=63392.3`（屬前一筆殘留／不完整 reflection） |
| supervisor_state | `exit_supervisor:NONE:closed=False`（hold；tick 持續） |
| last_supervisor_tick | closed=false；exit.reason=NONE；reconciled=true |
| controller_cycle_count | T0=362 → T70=364 → T140=365（**前進**） |
| scanner_last_scan_at | lastScanAtMs 持續前進；lastScanAgeMs 約 6s～58s |
| controller_health／scanner_health | RUNNING（非 STALLED；本輪 **不** 標 OPEN_POSITION_RUNTIME_STALL_INCIDENT） |
| controller_owner_count | **1** |
| lastCycle.error | null（三 snapshot 無新 ValueError） |
| reconciliation | OK／reconciled=true（非 Ambiguous Intent；`health.ambiguous=false`） |
| 重複 Entry | **無**（position 維持 1；無第二倉） |

## 5. Auto Send／New Entry Block

| 項目 | 值 |
|---|---|
| Live auto_send／autoSendEnv | true／true（**舊 Runtime；本輪未改**） |
| RC 新預設 | false（尚未 Deploy） |
| lastCycle.send | **false** |
| lastCycle.state | `BLOCKED_EXISTING_EXPOSURE` |
| blockReasons | `existing_position_or_order` |
| existing_account_state_blocks_new_entry | **true** |
| UNEXPECTED_MULTI_ENTRY_INCIDENT | **否** |

## 6. Outcome／Reflection（語意）

| 項目 | 值 |
|---|---|
| lastTrade／lastReflection | 存在但 **incomplete=true**；對應舊 entry 65300.1，**非**目前 63392.3 倉 |
| fees／funding／slippage／netPnl | **null（MISSING）** — 未填假 0 |
| reflectionStatus | CREATED（舊筆）；目前開倉 outcome **未完成** |

## 7. Three Snapshot Verification（持倉期間）

| Snapshot | Position | Orders | Cycle | Scan 前進 | send |
|---|---|---|---|---|---|
| T+0 | 1 | 2 | 362 | yes | false |
| T+70s | 1 | 2 | 364 | yes | false |
| T+140s | 1 | 2 | 365 | yes | false |

→ **Deployment Window = 不可用**（尚未 0／0；且 Protection 未驗證）

## 8. PR／RC 一致性（唯讀）

| 項目 | 值 |
|---|---|
| PR #1 | Draft=true；mergeable=true；base=`stage3-demo-learning` |
| 功能 CI | `cfd2c26` PASS |
| 目前 head | `ac3998f`（僅多 docs 報告；無策略／風險變更） |
| 本輪新增 Commit | **無**（未改程式） |

## 9. 固定旗標

| Merge | Deploy | Observer | Clean24H | Mainnet | RealMoney |
|---|---|---|---|---|---|
| false | false | false | false | false | false |

---

## 報告欄位彙總

- **Observed At：** 2026-07-28T01:12Z–01:15Z UTC  
- **Position：** 1 BTCUSDT Buy 0.026 @ 63392.3  
- **Orders：** 2（僅 1 張細節可見：Sell Untriggered qty=0.026）  
- **Protection Verdict：** **AMBIGUOUS**  
- **SL／TP：** **未驗證**  
- **Coverage：** qty 對可見單吻合；整體覆蓋 **未證實**  
- **Exit Policy：** 目前倉持久化 **未證實**  
- **Supervisor：** 有 tick／前進；hold  
- **Controller：** 前進；Owner=1；非 STALLED  
- **Scanner：** 前進  
- **Owner：** 1  
- **Auto Send：** Live true（舊）；RC 預設 false 未部署  
- **New Entry Blocked：** true  
- **Ambiguous Intent：** false  
- **Reconciliation：** OK  
- **Outcome／Reflection：** 舊筆 incomplete；MISSING fee/funding（非 0）  
- **Position Zero At：** n/a  
- **Orders Zero At：** n/a  
- **Three Snapshot Verification：** 持倉期間 PASS（進度）；**非**部署窗口 0／0 驗證  
- **Deployment Window：** **UNAVAILABLE**  
- **Merge／Deploy／Observer／Clean24H：** false／false／false／false  

## Recommendation

**`OPEN_EXPOSURE_SAFETY_INCIDENT`**

（同時維持部署閘門語意：`HOLD_FOR_OPEN_EXPOSURE` — 仍禁止 Merge／Deploy）

## Next Founder Approval

1. **立即：** 於 Bybit Demo 人工唯讀確認兩張條件單是否為完整 SL＋TP（或批准僅限「唯讀觀測補強」的 RC：保留 stopOrderType／triggerPrice 並暴露全部 openOrders — **仍不得在持倉中 Deploy**）。  
2. 保護確認為 `PROTECTED_VERIFIED` 後：繼續等待自然 0／0。  
3. 自然歸零後：再跑 T+0／T+60／T+180 三次 0／0 Snapshot，才可申請  
   `READY_FOR_MERGE_DEPLOY_AND_READ_ONLY_SMOKE_APPROVAL`。

---

## 更新（2026-07-28）：Founder External UI Evidence Reconciliation

> 本節為追加記錄。上方歷史 `AMBIGUOUS`／`OPEN_EXPOSURE_SAFETY_INCIDENT` **保留**，不改寫為「從未發生」。

### founder_external_ui_evidence

| 欄位 | 值 |
|---|---|
| observed_at | Founder 提供（Bybit Demo UI） |
| platform | Bybit Demo |
| symbol | BTCUSDT |
| position_side | Buy |
| position_qty | 0.026 |
| entry_price | 63392.30 |
| liquidation_price | 61162.50 |
| take_profit | 64816.70 |
| stop_loss | 62439.60 |
| trigger_by | MarkPrice |
| execution | Market |
| coverage | FullPosition |
| action | SellToCloseLong |
| status | PendingTrigger |
| evidence_source | FounderProvidedUI |
| evidence_quality | HIGH_EXTERNAL_UI |
| api_confirmed | **false** |

### 語意更新

| 鍵 | 值 |
|---|---|
| account_protection_truth | `PROTECTED_VERIFIED_BY_FOUNDER_UI` |
| exchange_ui_truth | `VERIFIED` |
| btc_bot_api_truth | `INCOMPLETE`（修補前）／RC 已補可觀測性（**尚未 Deploy**） |
| api_protection_observability | `INCOMPLETE` → RC patch 後預期可自動判（Deploy 後驗證） |
| previous_ambiguous_finding | **保留歷史** |
| open_exposure_safety_incident | `RESOLVED_BY_EXTERNAL_UI_EVIDENCE` |
| deployment_gate | **`HOLD_FOR_OPEN_EXPOSURE`**（Position≠0） |
| merge／deploy | false／false |

### 後續 Recommendation（持倉仍在）

**`HOLD_FOR_OPEN_EXPOSURE`**

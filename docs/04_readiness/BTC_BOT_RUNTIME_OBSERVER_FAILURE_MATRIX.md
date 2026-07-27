# Runtime／Observer Failure Matrix（加速測試證據）

## Controller／Scanner Health

| 狀態 | 條件 | allow_new_entries | UI 標示 |
|---|---|---|---|
| HEALTHY | thread alive + progress 新鮮 | true（其餘 gate 通過時） | HEALTHY |
| STALLED | cycle timeout／progress 逾時 | false | STALLED |
| STOPPED | thread 未運行 | false | STOPPED |
| FAILED | validation observer fail-closed | n/a | FAILED（Observer） |

## Observer Fail-closed

| 注入 | 預期 |
|---|---|
| boot change | FAIL `runtime_boot_changed` |
| commit change | FAIL `commit_changed` |
| owner != 1 | FAIL `controller_owner_not_1` |
| STALLED runtime | FAIL `runtime_stalled` |
| mainnet/real_money | FAIL `mainnet_or_real_money` |
| duplicate start | rejected（既有 owner 繼續） |
| default disabled | running=false |
| sequence | 單調遞增（JSONL append） |

## Outcome／Reconciliation

| 情況 | 預期 |
|---|---|
| fees/funding/slippage missing | incomplete=true；值=None；不填 0 |
| incomplete reflection | reconciled=false |
| flat + OK | existing_position_or_order 不得為 active current truth |

測試檔：`tests/test_runtime_stall_remediation.py`（含 fail injection）

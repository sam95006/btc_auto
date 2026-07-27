# BTC_BOT 六筆 Secret Finding 分類結案

**產生時間：** 2026-07-28  
**詳情 JSON：** [BTC_BOT_SECRET_FINDINGS_CLASSIFICATION.json](BTC_BOT_SECRET_FINDINGS_CLASSIFICATION.json)

## 總覽

| finding_id | classification | severity | git_tracked | docker_context | credential_likely |
|---|---|---|---|---|---|
| SF-01 | REDACTED_HISTORICAL_TEXT | low | false | false | false |
| SF-02 | DOCUMENTATION_EXAMPLE | low | false | false | false |
| SF-03 | REDACTED_HISTORICAL_TEXT | low | false | false | false |
| SF-04 | REDACTED_HISTORICAL_TEXT | low | false | false | false |
| SF-05 | POTENTIAL_SECRET | high | false | false | true |
| SF-06 | POTENTIAL_SECRET | high | false | false | true |

**security_hold = true**（因 SF-05、SF-06）

## 處理結論

- 六筆皆位於 `archives/cursor_project/`，**未進 Git tracking**、**未進 Git history**、**被 `.dockerignore` 排除**、**不可能進 Frontend bundle**。
- SF-01～SF-04：遮罩／文件範例／關鍵字，可保留封存。
- SF-05、SF-06：值形狀具 credential 可能性 → **SECURITY_HOLD**；不自動刪除、不輸出原文。建議移出 Repo Root 至 `G:\BTC_BOT_PRIVATE_ARCHIVE\`，或至少維持 gitignore／dockerignore／staged=0。
- Dirty Root 若直接 `git add .` 有誤提交風險；**乾淨 RC worktree（`C:\Temp\BTC_BOT_RUNTIME_RC`）不含 archives**。

## RC 影響

RC 分支 `rc/runtime-stall-zeabur-observer` 不含上述檔案。Secret Hold 阻擋的是 Dirty Root 直接提交，不是阻擋 RC 內容本身；但在 SF-05/06 人工結案前，整體 recommendation 維持 **BLOCKED**／不可 Deploy。

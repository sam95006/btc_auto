# One-shot automation loop:
# - Triage remote Zeabur runtime
# - Run local unit tests (fast)
# - Upload .env and redeploy
# - Re-triage remote
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File tools/autodev/auto_iterate.ps1
#   powershell -ExecutionPolicy Bypass -File tools/autodev/auto_iterate.ps1 -BaseUrl https://btc-auto-bot-2026.zeabur.app

param(
  [string]$BaseUrl = "https://btc-auto-bot-2026.zeabur.app"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $Root
try {
  Write-Host "==> Remote triage (before)"
  python "tools/autodev/triage_remote.py" $BaseUrl

  Write-Host "==> Local unit tests (fast gate)"
  python -m unittest `
    tests.test_pure_ai_hard_exit `
    tests.test_pure_ai_orchestrator `
    tests.test_pure_ai_execution `
    tests.test_pure_ai_position_policy `
    tests.test_pure_ai_status -q

  Write-Host "==> Redeploy to Zeabur (upload .env + deploy)"
  powershell -ExecutionPolicy Bypass -File "tools/deploy/zeabur_pure_ai.ps1"

  Write-Host "==> Remote triage (after)"
  python "tools/autodev/triage_remote.py" $BaseUrl

  Write-Host "==> Done"
}
finally {
  Pop-Location
}


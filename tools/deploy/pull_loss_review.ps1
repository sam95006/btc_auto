# Fetch loss-review JSON from deployed NEXUS (no secrets).
# Usage: .\tools\deploy\pull_loss_review.ps1 -BaseUrl "https://your-app.zeabur.app"
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$outDir = Join-Path $PSScriptRoot "..\..\archives\state_bundles"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $outDir "loss_review_$stamp.json"
$url = ($BaseUrl.TrimEnd("/")) + "/api/nexus/loss-review"
Invoke-RestMethod -Uri $url -Method Get | ConvertTo-Json -Depth 12 | Set-Content -Path $outFile -Encoding UTF8
Write-Host "Saved: $outFile"

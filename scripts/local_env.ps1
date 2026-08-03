$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeTmp = Join-Path $Root '.nexus_runtime\tmp'
$RuntimeData = Join-Path $Root '.nexus_runtime\data'
New-Item -ItemType Directory -Force -Path $RuntimeTmp, $RuntimeData, (Join-Path $Root '.nexus_runtime\logs'), (Join-Path $Root '.nexus_runtime\cache'), (Join-Path $Root '.nexus_runtime\state') | Out-Null
$env:PYTHONPATH = $Root
$env:TMP = $RuntimeTmp
$env:TEMP = $RuntimeTmp
$env:TMPDIR = $RuntimeTmp
$env:NEXUS_DATA_DIR = $RuntimeData
$env:EXCHANGE_WRITE = 'false'
$env:MAINNET = 'false'
$env:REAL_MONEY = 'false'
Remove-Item Env:FLASK_ENV -ErrorAction SilentlyContinue
Remove-Item Env:NEXUS_ENV -ErrorAction SilentlyContinue
Remove-Item Env:NEXUS_FORCE_PRODUCTION_ENTITLEMENTS -ErrorAction SilentlyContinue
Remove-Item Env:NEXUS_VERIFY_ROOT -ErrorAction SilentlyContinue
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $venvPy) { $env:Path = (Join-Path $Root '.venv\Scripts') + ';' + $env:Path }
Set-Location -LiteralPath $Root
Write-Output "ROOT=$Root"
Write-Output "PYTHON=$venvPy"
Write-Output "TMP=$env:TMP"

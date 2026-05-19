$dir = "G:\我的雲端硬碟\btc_bot\static\nexus"
$files = Get-ChildItem -Path $dir -Recurse -Include "*.js"
foreach ($f in $files) {
    Write-Host "Processing $($f.FullName)..."
    $content = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
    # Match any ?v=2026 followed by numbers or letters
    $newContent = [System.Text.RegularExpressions.Regex]::Replace($content, '\?v=2026[0-9a-zA-Z]+', '?v=20260501a')
    [System.IO.File]::WriteAllText($f.FullName, $newContent, [System.Text.Encoding]::UTF8)
}
Write-Host "DONE - All version strings replaced to 20260501a"

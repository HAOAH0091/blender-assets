# HAOAH Blender Asset Library
# yong fa: .\release.ps1

$ErrorActionPreference = "Stop"

$blenderExe = "G:\steam\steamapps\common\Blender\blender.exe"
$repoRoot = $PSScriptRoot

Write-Host ""
Write-Host "=== HAOAH Asset Library Release ===" -ForegroundColor Cyan

# ---- regenerate listing ----
Write-Host ""
Write-Host "Generating asset listing..." -ForegroundColor Cyan
if (-not (Test-Path $blenderExe)) {
    Write-Host "ERROR: Blender not found at $blenderExe" -ForegroundColor Red
    exit 1
}
$prevErrorAction = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $blenderExe -b -c asset_listing generate $repoRoot 2>&1 | Select-String "Writing|Command took|\.blend files found"
$ErrorActionPreference = $prevErrorAction

# ---- fix meta ----
Write-Host ""
Write-Host "Fixing metadata..." -ForegroundColor Yellow

$indexPath = Join-Path $repoRoot "_v1\asset-index.json"
if (Test-Path $indexPath) {
    $indexContent = Get-Content $indexPath -Raw -Encoding UTF8
    $hash = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $hash.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($indexContent))
    $hashStr = "SHA256:" + [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLower()

    $meta = @{
        api_versions = @{ v1 = @{ url = "_v1/asset-index.json"; hash = $hashStr } }
        name = "HAOAH Custom Assets"
        contact = @{ name = "HAOAH"; url = "https://github.com/HAOAH0091"; email = "toukou0091@gmail.com" }
    }
    $meta | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $repoRoot "_asset-library-meta.json") -Encoding UTF8
}

$index = Get-Content $indexPath -Raw | ConvertFrom-Json
Write-Host "  assets: $($index.asset_count) | files: $($index.file_count)"

# ---- git ----
Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
Push-Location $repoRoot
try {
    git add -A
    $gitStatus = git status -s
    if ($gitStatus) {
        git commit -m "update: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
        git push
        Write-Host "  pushed." -ForegroundColor Green
    } else {
        Write-Host "  no changes." -ForegroundColor DarkGray
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan

# HAOAH Blender Asset Library — 一键发布
# 用法: .\release.ps1 [-Push]

param(
    [switch]$Push
)

$ErrorActionPreference = "Stop"

$blenderExe = "G:\steam\steamapps\common\Blender\blender.exe"
$repoRoot = $PSScriptRoot
$sourceDir = "F:\desktop\BaiduSyncdisk\blender_asset\customize"

Write-Host ""
Write-Host "=== HAOAH Asset Library Release ===" -ForegroundColor Cyan

# ---- sync source → repo ----
Write-Host ""
Write-Host "Syncing blend files from source..." -ForegroundColor Yellow
$synced = 0
Get-ChildItem $sourceDir -Filter "*.blend" | ForEach-Object {
    $dest = Join-Path $repoRoot $_.Name
    $copy = $false
    if (-not (Test-Path $dest)) {
        $copy = $true
        Write-Host "  NEW: $($_.Name)"
    } elseif ((Get-Item $_.FullName).LastWriteTime -gt (Get-Item $dest).LastWriteTime) {
        $copy = $true
        Write-Host "  UPD: $($_.Name)"
    }
    if ($copy) {
        Copy-Item $_.FullName $dest -Force
        $synced++
    }
}
Write-Host "Synced: $synced file(s)"

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
if ($Push) {
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
            Write-Host "  no changes." -ForegroundColor DarkYellow
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "Skip push (add -Push to auto-push)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan

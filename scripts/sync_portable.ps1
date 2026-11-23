# ACCIO LUNA - Otomatik Dizin Senkronizasyonu
# Bu betik ana proje dizinindeki degisiklikleri tasinabilir pakete aninda aktarir.

$ErrorActionPreference = "SilentlyContinue"
$src = $PSScriptRoot
$dst = Join-Path $src "dist\LUNA-AI-PORTABLE\app"

if (-not (Test-Path $dst)) {
    New-Item -ItemType Directory -Path $dst -Force | Out-Null
}

$coreFiles = @(
    "index.html",
    "luna_server.py",
    "luna_agent_engine.py",
    "luna_computer_use.py",
    "luna_local_stt.py",
    "luna_tray.ps1",
    "luna_uia_inspect.ps1",
    "luna_uia_action.ps1",
    "start_luna.ps1"
)

$syncedCount = 0
foreach ($file in $coreFiles) {
    $srcPath = Join-Path $src $file
    $dstPath = Join-Path $dst $file
    if (Test-Path $srcPath) {
        Copy-Item -Path $srcPath -Destination $dstPath -Force
        $syncedCount++
    }
}

$staticSrc = Join-Path $src "static"
$staticDst = Join-Path $dst "static"
if (Test-Path $staticSrc) {
    Copy-Item -Path "$staticSrc\*" -Destination $staticDst -Recurse -Force
}

Write-Host "[SENKRONIZASYON] $syncedCount cekirdek dosya ve static dizini basariyla esitlendi." -ForegroundColor Green

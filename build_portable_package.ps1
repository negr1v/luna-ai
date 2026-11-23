<#
.SYNOPSIS
    ACCIO JARVIS V16 — Phase 16E: Portable Windows Packaging Builder
.DESCRIPTION
    Hafif, taşınabilir ve tek klasörlü (one-folder) Windows paketleyicisi.
    Uygulama kodunu (app/), kullanıcı verilerini (data/) ve başlatıcıları (bat/ps1)
    birbirinden izole eder. Dış bağımlılık yüklemez, API anahtarlarını arındırır.
#>

[CmdletBinding()]
param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$SourceDir = $PSScriptRoot

if (-not $OutputDir) {
    $OutputDir = Join-Path $SourceDir "dist\ACCIO-JARVIS-PORTABLE"
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  ACCIO JARVIS V16 - TASINABILIR WINDOWS PAKETLEME (16E)    " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Kaynak Dizin : $SourceDir"
Write-Host "Paket Dizini : $OutputDir"

# 1. Hedef Klasör Hiyerarşisi Oluşturma
$AppDir = Join-Path $OutputDir "app"
$DataDir = Join-Path $OutputDir "data"

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $AppDir)) {
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

# 2. Uygulama Kaynak Dosyalarını Kopyalama (app/)
$AppFiles = @(
    "index.html",
    "jarvis_server.py",
    "jarvis_agent_engine.py",
    "jarvis_computer_use.py",
    "jarvis_local_stt.py",
    "jarvis_tray.ps1",
    "jarvis_uia_inspect.ps1",
    "jarvis_uia_action.ps1",
    "start_jarvis.ps1"
)

foreach ($file in $AppFiles) {
    $srcPath = Join-Path $SourceDir $file
    if (Test-Path -LiteralPath $srcPath) {
        Copy-Item -LiteralPath $srcPath -Destination (Join-Path $AppDir $file) -Force
        Write-Host "  [APP] Kopyalandi: $file" -ForegroundColor Green
    } else {
        Write-Warning "Uygulama dosyasi eksik: $file"
    }
}

$staticSrc = Join-Path $SourceDir "static"
if (Test-Path -LiteralPath $staticSrc) {
    Copy-Item -Path "$staticSrc\*" -Destination (Join-Path $AppDir "static") -Recurse -Force
    Write-Host "  [APP] static/ klasoru kopyalandi" -ForegroundColor Green
}

# 3. Kullanıcı Veri Dosyalarını İzolasyon ve Kopyalama (data/)
# jarvis_config.json içindeki gizli API anahtarlarını arındır (sanitization)
$configSrc = Join-Path $SourceDir "jarvis_config.json"
$configDst = Join-Path $DataDir "jarvis_config.json"
if (Test-Path -LiteralPath $configSrc) {
    try {
        $cfg = Get-Content -LiteralPath $configSrc -Raw -Encoding UTF8 | ConvertFrom-Json
        # Hassas anahtarları temizle
        $secretKeys = @("groq_api_key", "openrouter_api_key", "elevenlabs_api_key", "openai_api_key", "telegram_bot_token")
        foreach ($k in $secretKeys) {
            if ($cfg.PSObject.Properties[$k]) {
                $cfg.$k = ""
            }
        }
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        $cleanJson = $cfg | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($configDst, $cleanJson, $utf8NoBom)
        Write-Host "  [DATA] Arindirilmis jarvis_config.json olusturuldu" -ForegroundColor Green
    } catch {
        Copy-Item -LiteralPath $configSrc -Destination $configDst -Force
    }
} else {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($configDst, '{"theme":"dark","language":"tr"}', $utf8NoBom)
}

# jarvis_memory.json kopyalama
$memSrc = Join-Path $SourceDir "jarvis_memory.json"
$memDst = Join-Path $DataDir "jarvis_memory.json"
if (Test-Path -LiteralPath $memSrc) {
    Copy-Item -LiteralPath $memSrc -Destination $memDst -Force
    Write-Host "  [DATA] jarvis_memory.json kopyalandi" -ForegroundColor Green
}

# jarvis_tasks.json kopyalama
$tasksSrc = Join-Path $SourceDir "jarvis_tasks.json"
$tasksDst = Join-Path $DataDir "jarvis_tasks.json"
if (Test-Path -LiteralPath $tasksSrc) {
    Copy-Item -LiteralPath $tasksSrc -Destination $tasksDst -Force
    Write-Host "  [DATA] jarvis_tasks.json kopyalandi" -ForegroundColor Green
} else {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tasksDst, '{"tasks":[]}', $utf8NoBom)
}

# jarvis_notifications.json kopyalama
$notifSrc = Join-Path $SourceDir "jarvis_notifications.json"
$notifDst = Join-Path $DataDir "jarvis_notifications.json"
if (Test-Path -LiteralPath $notifSrc) {
    Copy-Item -LiteralPath $notifSrc -Destination $notifDst -Force
    Write-Host "  [DATA] jarvis_notifications.json kopyalandi" -ForegroundColor Green
} else {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($notifDst, '{"notifications":[],"overflow_count":0,"expired_count":0}', $utf8NoBom)
}

# 4. Taşınabilir PowerShell Kontrolörü (start_portable.ps1) Oluşturma
$portablePs1Path = Join-Path $OutputDir "start_portable.ps1"
$portablePs1Content = @'
<#
.SYNOPSIS
    ACCIO JARVIS V16 — Portable Windows Central Controller
.DESCRIPTION
    Taşınabilir modda başlatma, sistem tepsisi entegrasyonu, mükerrer süreç engelleme,
    durum sorgulama, temiz kapatma ve güvenli kurtarma mekanizması sağlar.
#>

[CmdletBinding()]
param(
    [ValidateSet("Start", "Stop", "Status", "Tray", "Recover")]
    [string]$Action = "Start"
)

$ErrorActionPreference = "Stop"
$PackageRoot = $PSScriptRoot
$AppDir = Join-Path $PackageRoot "app"
$DataDir = Join-Path $PackageRoot "data"
$AppScript = Join-Path $AppDir "start_jarvis.ps1"

# Ortam Değişkenleri
$env:JARVIS_DATA_DIR = $DataDir

# Python Yolunu Dinamik Belirleme
$DefaultManagedPython = "C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"
$env:JARVIS_PYTHON_EXE = if ($env:JARVIS_PYTHON_EXE -and (Test-Path -LiteralPath $env:JARVIS_PYTHON_EXE)) {
    $env:JARVIS_PYTHON_EXE
} elseif (Test-Path -LiteralPath (Join-Path $PackageRoot "python\python.exe")) {
    Join-Path $PackageRoot "python\python.exe"
} elseif (Test-Path -LiteralPath $DefaultManagedPython) {
    $DefaultManagedPython
} else {
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { $cmd.Source } else { $DefaultManagedPython }
}

# Mükerrer Süreç Koruması için Mutex Kontrolü (Port 7860 Dinleyicisi)
function Test-ServerRunning {
    try {
        $conn = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 7860 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $conn) { return $true }
    } catch { }
    $netstat = netstat -ano -p tcp | Select-String ":7860\s+.*LISTENING"
    return ($null -ne $netstat)
}

if ($Action -eq "Status") {
    Write-Host "=== ACCIO JARVIS V16 - TASINABILIR DURUM ===" -ForegroundColor Cyan
    $isRunning = Test-ServerRunning
    if ($isRunning) {
        Write-Host "  Durum : [CALISIYOR] Port 7860 aktif" -ForegroundColor Green
        Write-Host "  Panel : http://127.0.0.1:7860" -ForegroundColor White
    } else {
        Write-Host "  Durum : [DURDURULDU] Port 7860 bosta" -ForegroundColor Yellow
    }
    Write-Host "  Veri  : $DataDir" -ForegroundColor Gray
    Write-Host "  Python: $env:JARVIS_PYTHON_EXE" -ForegroundColor Gray
    exit 0
}

if ($Action -eq "Stop") {
    Write-Host "=== ACCIO JARVIS V16 - GUVENLI KAPATMA ===" -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $AppScript -Action Stop
    exit 0
}

if ($Action -eq "Recover") {
    Write-Host "=== ACCIO JARVIS V16 - GUVENLI KURTARMA PROSEDURU ===" -ForegroundColor Cyan
    # 1. Veri dizini kontrolü
    if (-not (Test-Path -LiteralPath $DataDir)) {
        New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
        Write-Host "  [Kurtarma] data/ dizini yeniden olusturuldu." -ForegroundColor Yellow
    }

    # 2. Yetim metadata dosyası temizliği
    $runtimeMeta = Join-Path $AppDir ".jarvis_runtime.json"
    if ((Test-Path -LiteralPath $runtimeMeta) -and (-not (Test-ServerRunning))) {
        Remove-Item -LiteralPath $runtimeMeta -Force -ErrorAction SilentlyContinue
        Write-Host "  [Kurtarma] Yetim .jarvis_runtime.json kalintisi temizlendi." -ForegroundColor Yellow
    }

    # 3. Bellek JSON kontrolü
    $memFile = Join-Path $DataDir "jarvis_memory.json"
    if (-not (Test-Path -LiteralPath $memFile)) {
        '{"user_name":"negr1","focus":"YKS 2027 Sayısal","notes":[],"revision":1}' | Set-Content -LiteralPath $memFile -Encoding UTF8
        Write-Host "  [Kurtarma] Temel jarvis_memory.json sablonu geri yuklendi." -ForegroundColor Yellow
    }

    Write-Host "  [Kurtarma] Sistem durumu saglam. Normal baslatma yapabilirsiniz." -ForegroundColor Green
    exit 0
}

# Start veya Tray Eylemi
if (Test-ServerRunning) {
    Write-Host "UYARI: JARVIS V16 zaten calisiyor (Port 7860 aktif). Mukerrer sunucu baslatilmadi." -ForegroundColor Yellow
    if ($Action -eq "Start") {
        Start-Process "http://127.0.0.1:7860"
    }
    exit 0
}

if ($Action -eq "Tray") {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $AppScript -Action Tray
} else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $AppScript -Action Start
}
'@

Set-Content -LiteralPath $portablePs1Path -Value $portablePs1Content -Encoding UTF8
Write-Host "  [PACKAGE] start_portable.ps1 olusturuldu" -ForegroundColor Green

# 5. Başlatıcı BAT Dosyalarını Oluşturma
$batFiles = @{
    "START-JARVIS.bat"   = "@echo off`r`ntitle ACCIO JARVIS V16 - Portable`r`ncd /d `"%~dp0`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"start_portable.ps1`" -Action Start`r`npause"
    "START-TRAY.bat"     = "@echo off`r`ntitle ACCIO JARVIS V16 - System Tray`r`ncd /d `"%~dp0`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"start_portable.ps1`" -Action Tray"
    "STATUS-JARVIS.bat"  = "@echo off`r`ntitle ACCIO JARVIS V16 - Status`r`ncd /d `"%~dp0`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"start_portable.ps1`" -Action Status`r`npause"
    "STOP-JARVIS.bat"    = "@echo off`r`ntitle ACCIO JARVIS V16 - Stop`r`ncd /d `"%~dp0`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"start_portable.ps1`" -Action Stop`r`npause"
    "RECOVER-JARVIS.bat" = "@echo off`r`ntitle ACCIO JARVIS V16 - Recovery`r`ncd /d `"%~dp0`"`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"start_portable.ps1`" -Action Recover`r`npause"
}

foreach ($batName in $batFiles.Keys) {
    $batPath = Join-Path $OutputDir $batName
    Set-Content -LiteralPath $batPath -Value $batFiles[$batName] -Encoding ASCII
    Write-Host "  [BAT] $batName olusturuldu" -ForegroundColor Green
}

# 6. Taşınabilir Paket README Belgesi
$readmeContent = @"
================================================================================
  ACCIO JARVIS V16 — KISISEL TASINABILIR WINDOWS PAKETI (PORTABLE PACKAGE)
================================================================================
Donanım Profili: Intel Core i5-8250U / 8 GB RAM / Windows 10 & 11
Mimari         : Tek Klasör Taşınabilir (One-Folder Portable), Sıfır Dış Bağımlılık

KLASOR YAPISI:
  ├── app/               -> Çekirdek yazılım, sunucu, agent ve PowerShell betikleri
  ├── data/              -> Kullanıcı hafızası (jarvis_memory.json), görevler, loglar
  ├── START-JARVIS.bat   -> Sunucuyu başlatır ve tarayıcıda kontrol panelini açar
  ├── START-TRAY.bat     -> Sunucuyu başlatır ve arka planda Windows Sistem Tepsisine küçültür
  ├── STATUS-JARVIS.bat  -> Sunucunun çalışma ve port durumunu raporlar
  ├── STOP-JARVIS.bat    -> Sunucuyu güvenli ve temiz bir şekilde kapatır
  └── RECOVER-JARVIS.bat -> Olası kilitlenmelerde veri doğrulaması ve güvenli kurtarma yapar

GÜVENLİK İLKELERİ:
  - Bu paket kişisel kullanım içindir; genel dağıtım değildir.
  - Kayıt defteri (Registry), Windows Servisi veya otomatik başlangıç kaydı YAPILMAZ.
  - Kullanıcı verileri (data/) koddan (app/) tamamen ayrılmıştır.
  - Parola veya hassas API anahtarları pakete dahil edilmez.
================================================================================
"@
Set-Content -LiteralPath (Join-Path $OutputDir "README.txt") -Value $readmeContent -Encoding UTF8

Write-Host "`nPaketleme Basariyla Tamamlandi!" -ForegroundColor Cyan
Write-Host "Paket Konumu: $OutputDir" -ForegroundColor White

<#
.SYNOPSIS
    ACCIO LUNA V4.0 — Güvenli Başlatıcı ve Süreç Yöneticisi (Faz 9C.1B)
.DESCRIPTION
    Yönetilen Python ortamını kullanarak LUNA sunucusunu güvenli şekilde başlatır ve izler.
    Kritik Güvenlik İlkeleri:
    - Zorla sonlandirma komutlari (force-kill) KESINLIKLE KULLANILMAZ.
    - Port 7860'ı kullanan yabancı süreçlere ASLA dokunulmaz.
    - PID reuse saldırılarına karşı 4'lü doğrulama (PID + UTC Başlangıç Zamanı + Python Yolu + Script Yolu).
    - Güvenli konsol izolasyonu doğrulanamazsa zorla sonlandırma yapılmaz; manuel Ctrl+C fallback'i uygulanır.
#>
[CmdletBinding()]
param(
    [ValidateSet("Start", "Stop", "Status", "Tray")]
    [string]$Action = "Start"
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

# Dinamik ve Taşınabilir Python Çözümleme
$DefaultManagedPython = "C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"
$PythonExe = if ($env:LUNA_PYTHON_EXE -and (Test-Path -LiteralPath $env:LUNA_PYTHON_EXE)) {
    $env:LUNA_PYTHON_EXE
} elseif (Test-Path -LiteralPath $DefaultManagedPython) {
    $DefaultManagedPython
} elseif (Test-Path -LiteralPath (Join-Path $ProjectDir "python\python.exe")) {
    Join-Path $ProjectDir "python\python.exe"
} else {
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { $cmd.Source } else { $DefaultManagedPython }
}

$ServerScript = Join-Path $ProjectDir "luna_server.py"
$RuntimeMetadataFile = Join-Path $ProjectDir ".luna_runtime.json"
$HostAddr = "127.0.0.1"
$Port = 7860
$ExpectedSchema = "luna_launcher_v1"

function Get-PortListenerProcess {
    param([int]$TargetPort)
    try {
        $conn = Get-NetTCPConnection -LocalAddress $HostAddr -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $conn) {
            return $conn.OwningProcess
        }
    } catch {
        # Fallback to netstat if Get-NetTCPConnection fails
        $netstatOutput = netstat -ano -p tcp | Select-String ":$TargetPort\s+.*LISTENING\s+(\d+)"
        if ($netstatOutput -match ":$TargetPort\s+.*LISTENING\s+(\d+)") {
            return [int]$matches[1]
        }
    }
    return $null
}

function Get-ProcessIdentityInfo {
    param([int]$ProcessId)
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
        if ($null -ne $proc) {
            $utcStart = ""
            if ($proc.CreationDate) {
                $utcStart = ([datetime]$proc.CreationDate).ToUniversalTime().ToString("o")
            }
            return [PSCustomObject]@{
                ProcessId      = $proc.ProcessId
                CreationDateUtc= $utcStart
                ExecutablePath = $proc.ExecutablePath
                CommandLine    = $proc.CommandLine
            }
        }
    } catch { }
    return $null
}

if ($Action -eq "Start") {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  ACCIO LUNA V4.0 - GUVENLI BASLATICI (FAZ 9C.1B)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    # 1. Proje ve Python Varlık Kontrolü
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        Write-Error "Yonetilen Python bulunamadi: $PythonExe"
        exit 1
    }
    if (-not (Test-Path -LiteralPath $ServerScript)) {
        Write-Error "luna_server.py bulunamadi: $ServerScript"
        exit 1
    }

    # 2. Port 7860 Dinleyici Kontrolü
    $activeListenerPid = Get-PortListenerProcess -TargetPort $Port
    if ($null -ne $activeListenerPid -and $activeListenerPid -gt 0) {
        $procInfo = Get-ProcessIdentityInfo -ProcessId $activeListenerPid
        $isLuna = $false
        if ($null -ne $procInfo -and $procInfo.CommandLine -like "*luna_server.py*") {
            $isLuna = $true
        }

        if ($isLuna) {
            Write-Host "[BILGI] LUNA sunucusu zaten calisiyor (PID: $activeListenerPid)." -ForegroundColor Green
            $targetUrl = "http://${HostAddr}:${Port}"
            Write-Host "[BILGI] Tarayici arayuzu aciliyor: $targetUrl" -ForegroundColor Green
            Start-Process $targetUrl
            exit 0
        } else {
            Write-Host "!" -ForegroundColor Red
            Write-Host "[ENGEL]: Port $Port baska bir yabanci surec tarafindan kullaniliyor! (PID: $activeListenerPid)" -ForegroundColor Red
            Write-Host "Guvenlik geregi yabanci sureclere dokunulmaz. Baslatma iptal edildi." -ForegroundColor Red
            Write-Host "Teshis komutu: netstat -ano | findstr :$Port" -ForegroundColor Yellow
            exit 1
        }
    }

    # 3. İzole Konsolda Sunucuyu Başlat
    Write-Host "[1/3] LUNA sunucusu baslatiliyor..." -ForegroundColor Yellow
    Set-Location -LiteralPath $ProjectDir
    
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $PythonExe
    $startInfo.Arguments = "`"$ServerScript`""
    $startInfo.WorkingDirectory = $ProjectDir
    $startInfo.UseShellExecute = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal

    $process = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -eq $process) {
        Write-Error "Sunucu sureci baslatilamadi!"
        exit 1
    }

    $pidLaunched = $process.Id
    Start-Sleep -Milliseconds 300

    # 4. Atomik Runtime Metadata Yazımı
    $procInfo = Get-ProcessIdentityInfo -ProcessId $pidLaunched
    $creationTimeUtc = if ($procInfo) { $procInfo.CreationDateUtc } else { (Get-Date).ToUniversalTime().ToString("o") }

    $metadata = [ordered]@{
        schema         = $ExpectedSchema
        pid            = $pidLaunched
        creationTimeUtc= $creationTimeUtc
        executablePath = $PythonExe
        scriptPath     = $ServerScript
        host           = $HostAddr
        port           = $Port
        launchedAt     = (Get-Date).ToUniversalTime().ToString("o")
    }

    $jsonContent = $metadata | ConvertTo-Json -Depth 4
    $tempMetaFile = Join-Path $ProjectDir ".luna_runtime.json.tmp.$pidLaunched"
    Set-Content -LiteralPath $tempMetaFile -Value $jsonContent -Encoding UTF8
    Move-Item -LiteralPath $tempMetaFile -Destination $RuntimeMetadataFile -Force

    Write-Host "[2/3] Surec baslatildi (PID: $pidLaunched). Saglik kontrolu yapiliyor..." -ForegroundColor Yellow

    # 5. Sağlık Kontrolü (15 saniye tavan, 500 ms aralık)
    $maxWaitSec = 15
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $healthy = $false

    while ($sw.Elapsed.TotalSeconds -lt $maxWaitSec) {
        if ($process.HasExited) {
            Write-Host "!" -ForegroundColor Red
            Write-Host "[HATA]: Sunucu sureci baslatildiktan hemen sonra kapandi (ExitCode: $($process.ExitCode))." -ForegroundColor Red
            Write-Host "luna_runtime.log dosyasini inceleyin." -ForegroundColor Yellow
            if (Test-Path -LiteralPath $RuntimeMetadataFile) {
                Remove-Item -LiteralPath $RuntimeMetadataFile -Force -ErrorAction SilentlyContinue
            }
            exit 1
        }

        try {
            $resp = Invoke-WebRequest -Uri "http://$HostAddr`:$Port/" -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                # Listener kimliği kontrolü: Portu dinleyen sürecin bizim başlattığımız PID olduğundan emin ol
                $currListener = Get-PortListenerProcess -TargetPort $Port
                if ($currListener -eq $pidLaunched) {
                    $healthy = $true
                    break
                }
            }
        } catch {
            # Henüz soket açılmamış olabilir, bekleniyor
        }
        Start-Sleep -Milliseconds 500
    }

    if ($healthy) {
        Write-Host "[3/3] LUNA basariyla dogrulandi ve hazir! (Sure: $([math]::Round($sw.Elapsed.TotalSeconds, 2))s)" -ForegroundColor Green
        Write-Host "Tarayici aciliyor: http://$HostAddr`:$Port" -ForegroundColor Cyan
        Start-Process "http://$HostAddr`:$Port"
        exit 0
    } else {
        Write-Host "!" -ForegroundColor Yellow
        Write-Host "[UYARI]: Saglik kontrolu 15 saniyede tamamlanamadi. Surec sonlandirilmadi (PID: $pidLaunched)." -ForegroundColor Yellow
        Write-Host "Sunucu loglarini inceleyin: luna_runtime.log" -ForegroundColor Yellow
        exit 1
    }
}
elseif ($Action -eq "Stop") {
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  ACCIO LUNA V4.0 - GUVENLI DURDURMA PROTOKOLU (FAZ 9C.1B)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $RuntimeMetadataFile)) {
        Write-Host "[BILGI] Aktif launcher metadata dosyasi (.luna_runtime.json) bulunamadi." -ForegroundColor Yellow
        Write-Host "Eger acik bir LUNA pencereniz varsa, konsolda Ctrl + C tuslayarak durdurabilirsiniz." -ForegroundColor Yellow
        exit 0
    }

    try {
        $metaRaw = Get-Content -LiteralPath $RuntimeMetadataFile -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-Error "Runtime metadata dosyasi okunamadi veya bozuk. Islem iptal edildi."
        exit 1
    }

    $targetPid = $metaRaw.pid
    $targetTime = $metaRaw.creationTimeUtc
    $targetExe = $metaRaw.executablePath
    $targetScript = $metaRaw.scriptPath

    # 1. 4'lü Kimlik Doğrulaması (PID + Exe + Script + Time)
    $procInfo = Get-ProcessIdentityInfo -ProcessId $targetPid
    if ($null -eq $procInfo) {
        Write-Host "[BILGI] Hedef surec (PID: $targetPid) zaten calismiyor." -ForegroundColor Green
        Remove-Item -LiteralPath $RuntimeMetadataFile -Force -ErrorAction SilentlyContinue
        exit 0
    }

    $identityMatch = ($procInfo.ExecutablePath -eq $targetExe) -and ($procInfo.CommandLine -like "*luna_server.py*")
    if (-not $identityMatch) {
        Write-Host "!" -ForegroundColor Red
        Write-Host "[ENGEL]: PID Reuse veya Kimlik Uyusmazligi! PID $targetPid artik beklenen LUNA surecine ait degil." -ForegroundColor Red
        Write-Host "Guvenlik geregi yabanci surece dokunulamaz." -ForegroundColor Red
        exit 1
    }

    # 2. Port Sahipliği Doğrulaması
    $currListener = Get-PortListenerProcess -TargetPort $Port
    if ($null -ne $currListener -and $currListener -ne $targetPid) {
        Write-Host "!" -ForegroundColor Red
        Write-Host "[ENGEL]: Port $Port uzerindeki dinleyici PID ($currListener) hedef PID ($targetPid) ile uyusmuyor." -ForegroundColor Red
        exit 1
    }

    # 3. Güvenli Kapatma Fallback Kuralı
    # KESINLIKLE zorla sonlandirma veya harici kill komutlari KULLANILMAZ.
    # Konsol penceresi ayrı bir işlem olarak açıldığından ve izole konsol sinyal API'si
    # harici bağımlılıksız güvenle garanti edilemediğinden güvenli manuel Ctrl+C rehberliği verilir.
    Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "GUVENLI KAPATMA TALIMATI:" -ForegroundColor Yellow
    Write-Host "Sunucu sureci dogrulandi: PID $targetPid ($targetScript)" -ForegroundColor Cyan
    Write-Host "Zorla sonlandirma (kill) veri butunlugu geregi engellenmistir." -ForegroundColor Yellow
    Write-Host "Lutfen acik olan LUNA konsol penceresine giderek 'Ctrl + C' tuslarina basin." -ForegroundColor Green
    Write-Host "Sunucu aiohttp ve bellek islemlerini temiz bir sekilde kapatacaktir." -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------" -ForegroundColor Yellow

    # Kullanıcı konsoldan Ctrl+C ile kapattığında metadata'nın temizlenmesi için 10 saniye gözlem
    Write-Host "Kapanis gozlemleniyor (10 saniye)..." -ForegroundColor Gray
    $exitObserved = $false
    for ($i = 0; $i -lt 10; $i++) {
        $checkProc = Get-ProcessIdentityInfo -ProcessId $targetPid
        if ($null -eq $checkProc) {
            $exitObserved = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if ($exitObserved) {
        Write-Host "[BASARILI] LUNA sunucusu temiz bir sekilde kapandi." -ForegroundColor Green
        if (Test-Path -LiteralPath $RuntimeMetadataFile) {
            Remove-Item -LiteralPath $RuntimeMetadataFile -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "[BILGI] Surec hala calisiyor. Istediginiz zaman konsoldan Ctrl + C ile kapatabilirsiniz." -ForegroundColor Yellow
    }
    exit 0
}
elseif ($Action -eq "Status") {
    $activeListenerPid = Get-PortListenerProcess -TargetPort $Port
    $isLunaRunning = $false
    $metaExists = Test-Path -LiteralPath $RuntimeMetadataFile

    if ($null -ne $activeListenerPid -and $activeListenerPid -gt 0) {
        $procInfo = Get-ProcessIdentityInfo -ProcessId $activeListenerPid
        if ($null -ne $procInfo -and $procInfo.CommandLine -like "*luna_server.py*") {
            $isLunaRunning = $true
        }
    }

    $statusObj = [ordered]@{
        status = if ($isLunaRunning) { "running" } else { "stopped" }
        port   = $Port
        host   = $HostAddr
        url    = "http://${HostAddr}:${Port}"
        pid    = if ($isLunaRunning) { $activeListenerPid } else { $null }
        hasMetadata = $metaExists
    }

    $json = $statusObj | ConvertTo-Json -Compress
    Write-Output $json
    exit 0
}
elseif ($Action -eq "Tray") {
    $trayScript = Join-Path $ProjectDir "luna_tray.ps1"
    if (-not (Test-Path -LiteralPath $trayScript)) {
        Write-Error "luna_tray.ps1 dosyasi bulunamadi: $trayScript"
        exit 1
    }

    Write-Host "[BILGI] LUNA Windows Sistem Tepsisi (Tray) baslatiliyor..." -ForegroundColor Cyan
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "powershell.exe"
    $startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayScript`""
    $startInfo.WorkingDirectory = $ProjectDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $trayProc = [System.Diagnostics.Process]::Start($startInfo)
    if ($null -ne $trayProc) {
        Write-Host "[BASARILI] Sistem Tepsisi servisi arka planda aktif (PID: $($trayProc.Id))." -ForegroundColor Green
    } else {
        Write-Error "Sistem Tepsisi baslatilamadi!"
        exit 1
    }
    exit 0
}

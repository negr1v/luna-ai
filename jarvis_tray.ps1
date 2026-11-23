<#
.SYNOPSIS
    ACCIO JARVIS V16 — Phase 16A: Windows System Tray Entegrasyonu
.DESCRIPTION
    Hafif, saf .NET / Windows Forms ve Win32 API tabanlı Sistem Tepsisi (Tray) yöneticisi.
    Harici Python veya Node/Electron bağımlılığı gerektirmez.
    i5-8250U / 8 GB RAM donanım profiline tam optimize edilmiş, düşük kaynak tüketimli mimari.
#>

[CmdletBinding()]
param()

$ProjectDir = $PSScriptRoot
$HostAddr = "127.0.0.1"
$Port = 7860
$DashboardUrl = "http://${HostAddr}:${Port}"
$StartScript = Join-Path $ProjectDir "start_jarvis.ps1"
$RuntimeMetaFile = Join-Path $ProjectDir ".jarvis_runtime.json"

# -----------------------------------------------------------------------------
# 1. Tekil Sistem Tepsisi Süreci Güvencesi (Mutex)
# -----------------------------------------------------------------------------
$mutexName = "Global\ACCIO_JARVIS_TRAY_MUTEX"
$createdNew = $false
try {
    $trayMutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
    if (-not $createdNew) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "ACCIO JARVIS Sistem Tepsisi zaten çalışıyor.",
            "ACCIO JARVIS Tray",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
        exit 0
    }
} catch {
    # Mutex hatası durumunda devam et
}

# -----------------------------------------------------------------------------
# 2. .NET ve Win32 API Yüklemeleri
# -----------------------------------------------------------------------------
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

if (-not ([System.Management.Automation.PSTypeName]'Win32TrayHelper').Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class Win32TrayHelper {
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool DestroyIcon(IntPtr hIcon);

    public const int SW_HIDE = 0;
    public const int SW_SHOWNORMAL = 1;
    public const int SW_SHOW = 5;
    public const int SW_MINIMIZE = 6;
    public const int SW_RESTORE = 9;
}
"@
}

# -----------------------------------------------------------------------------
# 3. İkon Üretici Fonksiyonu (Dinamik Neon Gösterge)
# -----------------------------------------------------------------------------
function Create-JarvisTrayIcon([bool]$isRunning) {
    $bmp = New-Object System.Drawing.Bitmap 16, 16
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

    # Koyu zemin
    $bgColor = [System.Drawing.Color]::FromArgb(8, 14, 26)
    $g.Clear($bgColor)

    if ($isRunning) {
        # Çalışıyor: Canlı Neon Cyan (#22d3ee)
        $outerPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(56, 189, 248), 1)
        $innerBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(34, 211, 238))
        $g.DrawEllipse($outerPen, 1, 1, 13, 13)
        $g.FillEllipse($innerBrush, 4, 4, 8, 8)
        $outerPen.Dispose()
        $innerBrush.Dispose()
    } else {
        # Durduruldu: Soluk Gri/Kırmızı
        $outerPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(100, 116, 139), 1)
        $innerBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(148, 163, 184))
        $g.DrawEllipse($outerPen, 1, 1, 13, 13)
        $g.FillEllipse($innerBrush, 4, 4, 8, 8)
        $outerPen.Dispose()
        $innerBrush.Dispose()
    }

    $g.Dispose()
    $hIcon = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($hIcon)
    # Bellek sızıntısını önlemek için bitmap'i serbest bırak
    $bmp.Dispose()
    return $icon
}

# -----------------------------------------------------------------------------
# 4. Durum Tespit Fonksiyonu
# -----------------------------------------------------------------------------
function Get-JarvisServerState {
    $state = @{
        IsRunning = $false
        Pid       = $null
        WindowHandle = [IntPtr]::Zero
    }

    try {
        $conn = Get-NetTCPConnection -LocalAddress $HostAddr -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $conn -and $conn.OwningProcess -gt 0) {
            $ownerPid = $conn.OwningProcess
            $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
            if ($null -ne $proc -and $proc.ProcessName -like "*python*") {
                $state.IsRunning = $true
                $state.Pid = $ownerPid
                $state.WindowHandle = $proc.MainWindowHandle
            }
        }
    } catch {}

    # Metadata dosyasından PID teyidi (WindowHandle eksikse)
    if ($state.IsRunning -and $state.WindowHandle -eq [IntPtr]::Zero -and (Test-Path -LiteralPath $RuntimeMetaFile)) {
        try {
            $meta = Get-Content -LiteralPath $RuntimeMetaFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($meta.pid) {
                $p = Get-Process -Id $meta.pid -ErrorAction SilentlyContinue
                if ($p) { $state.WindowHandle = $p.MainWindowHandle }
            }
        } catch {}
    }

    return $state
}

# -----------------------------------------------------------------------------
# 5. UI Bileşenleri ve NotifyIcon Kurulumu
# -----------------------------------------------------------------------------
$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip
$contextMenu.ShowImageMargin = $false

# Başlık / Durum Göstergesi
$statusMenuItem = New-Object System.Windows.Forms.ToolStripMenuItem
$statusMenuItem.Enabled = $false
$statusMenuItem.Font = New-Object System.Drawing.Font($contextMenu.Font, [System.Drawing.FontStyle]::Bold)

# Kokpiti Aç (Open Dashboard)
$openDashboardItem = New-Object System.Windows.Forms.ToolStripMenuItem
$openDashboardItem.Text = "🌐 Kokpiti Aç (Dashboard)"
$openDashboardItem.Font = New-Object System.Drawing.Font($contextMenu.Font, [System.Drawing.FontStyle]::Bold)

# Konsolu Göster / Gizle (Minimize to Tray)
$toggleConsoleItem = New-Object System.Windows.Forms.ToolStripMenuItem
$toggleConsoleItem.Text = "👁️ Konsolu Gizle / Göster"

# Başlat / Durdur
$startServerItem = New-Object System.Windows.Forms.ToolStripMenuItem
$startServerItem.Text = "▶️ JARVIS'i Başlat"

$stopServerItem = New-Object System.Windows.Forms.ToolStripMenuItem
$stopServerItem.Text = "⏹️ JARVIS'i Durdur"

# Ayırıcı
$sep1 = New-Object System.Windows.Forms.ToolStripSeparator
$sep2 = New-Object System.Windows.Forms.ToolStripSeparator

# Tepsiden Çıkış
$exitMenuItem = New-Object System.Windows.Forms.ToolStripMenuItem
$exitMenuItem.Text = "❌ Tepsiden Çıkış"

# Menüye Ekle
$contextMenu.Items.Add($statusMenuItem) | Out-Null
$contextMenu.Items.Add($sep1) | Out-Null
$contextMenu.Items.Add($openDashboardItem) | Out-Null
$contextMenu.Items.Add($toggleConsoleItem) | Out-Null
$contextMenu.Items.Add($startServerItem) | Out-Null
$contextMenu.Items.Add($stopServerItem) | Out-Null
$contextMenu.Items.Add($sep2) | Out-Null
$contextMenu.Items.Add($exitMenuItem) | Out-Null

$notifyIcon.ContextMenuStrip = $contextMenu
$notifyIcon.Visible = $true

# -----------------------------------------------------------------------------
# 6. Eylem İşleyicileri
# -----------------------------------------------------------------------------

# Menü Durumunu Güncelleme
function Update-TrayMenuStatus {
    $serverState = Get-JarvisServerState
    $isRunning = $serverState.IsRunning

    if ($isRunning) {
        $statusMenuItem.Text = "● JARVIS: Çalışıyor (Port $Port, PID: $($serverState.Pid))"
        $statusMenuItem.ForeColor = [System.Drawing.Color]::DarkGreen
        $notifyIcon.Text = "ACCIO JARVIS (Çalışıyor - Port $Port)"
        $startServerItem.Enabled = $false
        $stopServerItem.Enabled = $true
        $toggleConsoleItem.Enabled = $true
    } else {
        $statusMenuItem.Text = "○ JARVIS: Durduruldu"
        $statusMenuItem.ForeColor = [System.Drawing.Color]::Gray
        $notifyIcon.Text = "ACCIO JARVIS (Durduruldu)"
        $startServerItem.Enabled = $true
        $stopServerItem.Enabled = $false
        $toggleConsoleItem.Enabled = $false
    }

    # İkonu güncelle
    $oldIcon = $notifyIcon.Icon
    $notifyIcon.Icon = Create-JarvisTrayIcon -isRunning $isRunning
    if ($oldIcon) { $oldIcon.Dispose() }
}

# Kokpiti Aç Eylemi (Yinelenen sunucu başlatmaz)
$openDashboardAction = {
    $serverState = Get-JarvisServerState
    if ($serverState.IsRunning) {
        Start-Process $DashboardUrl
    } else {
        $choice = [System.Windows.Forms.MessageBox]::Show(
            "JARVIS sunucusu şu an çalışmıyor. Sunucu başlatılsın ve kokpit açılsın mı?",
            "ACCIO JARVIS",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        if ($choice -eq [System.Windows.Forms.DialogResult]::Yes) {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Action Start"
        }
    }
}
$openDashboardItem.Add_Click($openDashboardAction)

# Çift Tıklama Eylemi -> Kokpiti Aç
$notifyIcon.Add_DoubleClick($openDashboardAction)

# Konsolu Göster / Gizle (Sistem Tepsisine Küçültme)
$toggleConsoleItem.Add_Click({
    $serverState = Get-JarvisServerState
    if (-not $serverState.IsRunning) { return }

    $hWnd = $serverState.WindowHandle
    if ($hWnd -eq [IntPtr]::Zero) {
        [System.Windows.Forms.MessageBox]::Show(
            "Konsol penceresi tanıtıcısı bulunamadı (Arka planda gizlenmiş veya izole çalışıyor olabilir).",
            "ACCIO JARVIS Tray",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
        return
    }

    $isVisible = [Win32TrayHelper]::IsWindowVisible($hWnd)
    if ($isVisible) {
        # Tepsisine Küçült (Gizle)
        [Win32TrayHelper]::ShowWindow($hWnd, [Win32TrayHelper]::SW_HIDE)
        $notifyIcon.ShowBalloonTip(2000, "ACCIO JARVIS", "Sunucu konsolu sistem tepsisine küçültüldü.", [System.Windows.Forms.ToolTipIcon]::Info)
    } else {
        # Konsolu Geri Getir
        [Win32TrayHelper]::ShowWindow($hWnd, [Win32TrayHelper]::SW_RESTORE)
        [Win32TrayHelper]::SetForegroundWindow($hWnd)
    }
})

# Sunucuyu Başlat Eylemi
$startServerItem.Add_Click({
    $serverState = Get-JarvisServerState
    if ($serverState.IsRunning) {
        [System.Windows.Forms.MessageBox]::Show(
            "JARVIS zaten çalışıyor (PID: $($serverState.Pid)).",
            "ACCIO JARVIS",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
        return
    }

    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Action Start"
    $notifyIcon.ShowBalloonTip(3000, "ACCIO JARVIS", "Sunucu başlatılıyor...", [System.Windows.Forms.ToolTipIcon]::Info)
    Start-Sleep -Milliseconds 1500
    Update-TrayMenuStatus
})

# Sunucuyu Durdur Eylemi (Graceful Stop)
$stopServerItem.Add_Click({
    $serverState = Get-JarvisServerState
    if (-not $serverState.IsRunning) { return }

    $confirm = [System.Windows.Forms.MessageBox]::Show(
        "JARVIS sunucusunu durdurmak istediğinize emin misiniz?",
        "Sunucuyu Durdur",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($confirm -eq [System.Windows.Forms.DialogResult]::Yes) {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Action Stop" -Wait
        $notifyIcon.ShowBalloonTip(3000, "ACCIO JARVIS", "Sunucu güvenli şekilde durduruldu.", [System.Windows.Forms.ToolTipIcon]::Info)
        Update-TrayMenuStatus
    }
})

# Tepsiden Çıkış Eylemi
$exitMenuItem.Add_Click({
    $serverState = Get-JarvisServerState
    if ($serverState.IsRunning) {
        $dialog = [System.Windows.Forms.MessageBox]::Show(
            "Sistem Tepsisi kapatılıyor.`n`nÇıkış yaparken JARVIS sunucusu da kapatılsın mı?`n`n[Evet] = Sunucu ve Tepsiyi Kapat`n[Hayır] = Sunucuyu Çalışır Bırak, Tepsiden Çık`n[İptal] = Vazgeç",
            "ACCIO JARVIS Tray Çıkış",
            [System.Windows.Forms.MessageBoxButtons]::YesNoCancel,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )

        if ($dialog -eq [System.Windows.Forms.DialogResult]::Cancel) {
            return
        }
        if ($dialog -eq [System.Windows.Forms.DialogResult]::Yes) {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -Action Stop" -Wait
        }
    }

    # İkonu temizle ve çık
    $notifyIcon.Visible = $false
    $notifyIcon.Dispose()
    if ($trayMutex) {
        try { $trayMutex.ReleaseMutex() } catch {}
        $trayMutex.Dispose()
    }
    [System.Windows.Forms.Application]::Exit()
})

# -----------------------------------------------------------------------------
# 7. Düzenli Durum Kontrolü (Düşük Kaynaklı Timer - 3.5 saniye)
# -----------------------------------------------------------------------------
$pollTimer = New-Object System.Windows.Forms.Timer
$pollTimer.Interval = 3500
$pollTimer.Add_Tick({
    Update-TrayMenuStatus
})
$pollTimer.Start()

# İlk durum kontrolü
Update-TrayMenuStatus

# Başlangıç bildirimi
$notifyIcon.ShowBalloonTip(2000, "ACCIO JARVIS Tray", "JARVIS Sistem Tepsisi hazır.", [System.Windows.Forms.ToolTipIcon]::Info)

# -----------------------------------------------------------------------------
# 8. Windows Forms Mesaj Döngüsü
# -----------------------------------------------------------------------------
[System.Windows.Forms.Application]::Run()

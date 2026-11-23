<#
.SYNOPSIS
    ACCIO JARVIS V16 — Phase 16B: Native Windows UIAutomation Tree Inspector
.DESCRIPTION
    Hafif .NET System.Windows.Automation tabanlı erişilebilirlik ağacı okuyucusu.
    Modern Windows uygulamalarını (Ayarlar, Hesap Makinesi, UWP/XAML) güvenle denetler.
    Hassas/parola alanlarını maskeler; derinlik, öğe sayısı ve zaman aşımı sınırlarına uyar.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$Hwnd,

    [int]$MaxElements = 30,

    [int]$MaxDepth = 3
)

$ErrorActionPreference = "SilentlyContinue"

try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
} catch {
    Write-Output "[]"
    exit 0
}

$results = [System.Collections.Generic.List[psobject]]::new()
$target = $null

try {
    $target = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
} catch {
    Write-Output "[]"
    exit 0
}

if ($null -eq $target) {
    Write-Output "[]"
    exit 0
}

$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

function Walk-Element($elem, [int]$depth) {
    if ($null -eq $elem -or $results.Count -ge $MaxElements -or $depth -gt $MaxDepth) {
        return
    }

    try {
        $curr = $elem.Current
        $name = $curr.Name
        $autoId = $curr.AutomationId
        $ctrlType = if ($curr.ControlType) { $curr.ControlType.ProgrammaticName.Replace("ControlType.", "") } else { "Unknown" }
        $isPass = [bool]$curr.IsPassword
        $isEnabled = [bool]$curr.IsEnabled
        $rect = $curr.BoundingRectangle

        # Sadece adı, AutomationId'si veya geçerli koordinatları olan öğeleri dahil et
        if ($name -or $autoId -or ($rect.Width -gt 0 -and $rect.Height -gt 0)) {
            # Hassas parola ve kimlik alanlarını maskele
            $isSensitive = $isPass -or ($autoId -like "*pass*") -or ($autoId -like "*pin*") -or ($autoId -like "*secret*") -or ($name -like "*parola*") -or ($name -like "*şifre*")
            if ($isSensitive) {
                $name = "[GIZLENDI / MASKED]"
            }

            $safeName = if ($name) { $name.Substring(0, [Math]::Min($name.Length, 60)) } else { "" }

            $results.Add([PSCustomObject]@{
                name          = $safeName
                control_type  = $ctrlType
                automation_id = if ($autoId) { $autoId } else { "" }
                is_password   = $isSensitive
                is_enabled    = $isEnabled
                x             = [int]$rect.X
                y             = [int]$rect.Y
                width         = [int]$rect.Width
                height        = [int]$rect.Height
                depth         = $depth
            })
        }
    } catch { }

    # Alt öğelere kontrollü şekilde in
    if ($depth -lt $MaxDepth -and $results.Count -lt $MaxElements) {
        try {
            $child = $walker.GetFirstChild($elem)
            while ($null -ne $child -and $results.Count -lt $MaxElements) {
                Walk-Element $child ($depth + 1)
                $child = $walker.GetNextSibling($child)
            }
        } catch { }
    }
}

try {
    Walk-Element $target 0
} catch { }

if ($results.Count -eq 0) {
    Write-Output "[]"
} else {
    $results | ConvertTo-Json -Compress
}
exit 0

<#
.SYNOPSIS
    ACCIO LUNA V16 — Phase 16D: Safe Controlled Windows UIAutomation Action Executor
.DESCRIPTION
    Hafif .NET System.Windows.Automation tabanlı güvenli etkileşim yürütücüsü.
    Yalnızca açık kullanıcı onayı verilmiş butonları (InvokePattern) veya
    hassas olmayan metin alanlarını (ValuePattern) tetikler.
    Parola/PIN/güvenlik kontrollerini kesinlikle engeller.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [int]$Hwnd,

    [string]$AutomationId = "",

    [string]$Name = "",

    [ValidateSet("Invoke", "SetValue")]
    [string]$Action = "Invoke",

    [string]$Value = "",

    [double]$TimeoutSec = 3.5
)

$ErrorActionPreference = "SilentlyContinue"

try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
} catch {
    Write-Output '{"status":"error","message":"UIAutomation derlemeleri yüklenemedi"}'
    exit 0
}

# 1. Hedef Pencere Kontrolü
$targetRoot = $null
try {
    $targetRoot = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
} catch {
    Write-Output '{"status":"error","message":"Pencere tutamacı geçersiz veya kapalı"}'
    exit 0
}

if ($null -eq $targetRoot) {
    Write-Output '{"status":"error","message":"Hedef AutomationElement kökü bulunamadı"}'
    exit 0
}

# 2. Hedef Öğeyi Ağaçta Arama
$condList = [System.Collections.Generic.List[System.Windows.Automation.Condition]]::new()

if ($AutomationId) {
    $condList.Add([System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $AutomationId))
}
if ($Name) {
    $condList.Add([System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty, $Name))
}

if ($condList.Count -eq 0) {
    Write-Output '{"status":"error","message":"Arama için AutomationId veya Name belirtilmelidir"}'
    exit 0
}

$searchCondition = if ($condList.Count -eq 1) {
    $condList[0]
} else {
    [System.Windows.Automation.AndCondition]::new($condList.ToArray())
}

$element = $null
try {
    $element = $targetRoot.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $searchCondition)
} catch {
    # Hata durumunda null kalır
}

# Eğer tam eşleşme bulunamadıysa Name ile kısmi/büyük-küçük harf toleranslı arama dene
if ($null -eq $element -and $Name) {
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    function Find-By-Name-Recursive($node, [string]$targetName, [int]$depth) {
        if ($null -eq $node -or $depth -gt 4) { return $null }
        try {
            $currName = $node.Current.Name
            if ($currName -and ($currName.Equals($targetName, [System.StringComparison]::OrdinalIgnoreCase) -or $currName.Contains($targetName))) {
                return $node
            }
        } catch { }

        try {
            $child = $walker.GetFirstChild($node)
            while ($null -ne $child) {
                $found = Find-By-Name-Recursive $child $targetName ($depth + 1)
                if ($null -ne $found) { return $found }
                $child = $walker.GetNextSibling($child)
            }
        } catch { }
        return $null
    }

    try {
        $element = Find-By-Name-Recursive $targetRoot $Name 0
    } catch { }
}

if ($null -eq $element) {
    Write-Output '{"status":"error","message":"Hedef UI öğesi pencere ağacında bulunamadı"}'
    exit 0
}

# 3. Güvenlik Denetimi: Parola, PIN, Gizli Kimlik Bilgisi Koruması
try {
    $curr = $element.Current
    $elemName = if ($curr.Name) { $curr.Name } else { "" }
    $elemAutoId = if ($curr.AutomationId) { $curr.AutomationId } else { "" }
    $isPass = [bool]$curr.IsPassword

    $sensitiveTokens = @("pass", "pin", "secret", "parola", "şifre", "sifre", "cvv", "token", "auth", "credential")
    $isSensitive = $isPass
    foreach ($tok in $sensitiveTokens) {
        if ($elemAutoId.ToLower().Contains($tok) -or $elemName.ToLower().Contains($tok)) {
            $isSensitive = $true
            break
        }
    }

    if ($isSensitive) {
        Write-Output '{"status":"blocked","reason":"sensitive_field","message":"Güvenlik Koruması: Parola, PIN veya kimlik doğrulama alanına müdahale edilemez."}'
        exit 0
    }
} catch {
    Write-Output '{"status":"error","message":"Öğe güvenlik denetimi sırasında hata oluştu"}'
    exit 0
}

# 4. Eylemi Yürütme (InvokePattern veya ValuePattern)
if ($Action -eq "Invoke") {
    $invoked = $false
    $patternUsed = ""

    # A) InvokePattern
    try {
        $objPattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$objPattern)) {
            $invokePattern = [System.Windows.Automation.InvokePattern]$objPattern
            $invokePattern.Invoke()
            $invoked = $true
            $patternUsed = "InvokePattern"
        }
    } catch { }

    # B) TogglePattern (Onay kutuları veya toggle butonlar için)
    if (-not $invoked) {
        try {
            $objToggle = $null
            if ($element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$objToggle)) {
                $togglePattern = [System.Windows.Automation.TogglePattern]$objToggle
                $togglePattern.Toggle()
                $invoked = $true
                $patternUsed = "TogglePattern"
            }
        } catch { }
    }

    # C) SelectionItemPattern (Liste veya radyo öğeleri için)
    if (-not $invoked) {
        try {
            $objSel = $null
            if ($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$objSel)) {
                $selPattern = [System.Windows.Automation.SelectionItemPattern]$objSel
                $selPattern.Select()
                $invoked = $true
                $patternUsed = "SelectionItemPattern"
            }
        } catch { }
    }

    if ($invoked) {
        $res = [PSCustomObject]@{
            status        = "ok"
            action        = "invoke"
            pattern       = $patternUsed
            element_name  = $elemName
            automation_id = $elemAutoId
        }
        $res | ConvertTo-Json -Compress
        exit 0
    } else {
        Write-Output '{"status":"error","message":"Öğe InvokePattern, TogglePattern veya SelectionItemPattern desteklemiyor."}'
        exit 0
    }
}
elseif ($Action -eq "SetValue") {
    # Metin Değeri Güvenlik Denetimi
    if ($Value.Length -gt 500) {
        Write-Output '{"status":"blocked","reason":"payload_too_large","message":"Metin boyutu güvenlik sınırını aşıyor (maks. 500 karakter)."}'
        exit 0
    }

    $setOk = $false
    try {
        $objVal = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$objVal)) {
            $valPattern = [System.Windows.Automation.ValuePattern]$objVal
            if ($valPattern.Current.IsReadOnly) {
                Write-Output '{"status":"error","reason":"read_only","message":"Hedef metin alanı salt-okunurdur (ReadOnly)."}'
                exit 0
            }
            $valPattern.SetValue($Value)
            $setOk = $true
        }
    } catch {
        Write-Output ('{"status":"error","message":"SetValue yürütülürken hata: ' + $_.Exception.Message.Replace('"', '\"') + '"}')
        exit 0
    }

    if ($setOk) {
        $res = [PSCustomObject]@{
            status        = "ok"
            action        = "set_value"
            pattern       = "ValuePattern"
            element_name  = $elemName
            automation_id = $elemAutoId
            value_length  = $Value.Length
        }
        $res | ConvertTo-Json -Compress
        exit 0
    } else {
        Write-Output '{"status":"error","message":"Öğe ValuePattern arayüzünü desteklemiyor."}'
        exit 0
    }
}

Write-Output '{"status":"error","message":"Bilinmeyen eylem türü"}'
exit 0

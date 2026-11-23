<#
 ACCIO JARVIS ULTRA Desktop Agent V1 fixed semantic UIA executor.
 It accepts only exact UI Automation identities, requires exactly one match,
 and deliberately has no Win32 or coordinate fallback.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][int]$Hwnd,
    [Parameter(Mandatory = $true)][string]$AutomationId,
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$ControlType,
    [ValidateSet("Invoke", "SetValue")][string]$Action,
    [string]$Value = "",
    [double]$TimeoutSec = 4.0
)

$ErrorActionPreference = "SilentlyContinue"
function Emit-Result([hashtable]$Result) { $Result | ConvertTo-Json -Compress; exit 0 }

try { Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes }
catch { Emit-Result @{ status = "error"; reason = "uia_unavailable"; message = "UI Automation derlemeleri yüklenemedi." } }

try { $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd) }
catch { Emit-Result @{ status = "error"; reason = "window_closed"; message = "Hedef pencere geçersiz veya kapalı." } }
if ($null -eq $root) { Emit-Result @{ status = "error"; reason = "window_closed"; message = "Hedef pencere bulunamadı." } }
if (-not $AutomationId -and -not $Name) { Emit-Result @{ status = "error"; reason = "missing_identity"; message = "Tam UI öğesi kimliği gerekli." } }

$conditions = [System.Collections.Generic.List[System.Windows.Automation.Condition]]::new()
if ($AutomationId) { $conditions.Add([System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $AutomationId)) }
if ($Name) { $conditions.Add([System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty, $Name)) }
$condition = if ($conditions.Count -eq 1) { $conditions[0] } else { [System.Windows.Automation.AndCondition]::new($conditions.ToArray()) }
try { $matches = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition) }
catch { Emit-Result @{ status = "error"; reason = "element_unavailable"; message = "Hedef UI öğesi bulunamadı." } }
if ($null -eq $matches -or $matches.Count -eq 0) { Emit-Result @{ status = "error"; reason = "element_unavailable"; message = "Hedef UI öğesi bulunamadı." } }
if ($matches.Count -ne 1) { Emit-Result @{ status = "blocked"; reason = "ambiguous_element"; message = "Hedef UI öğesi benzersiz değil; yeniden inceleme gerekli." } }

$element = $matches[0]
try {
    $current = $element.Current
    $actualType = if ($current.ControlType) { $current.ControlType.ProgrammaticName.Replace("ControlType.", "") } else { "" }
    if ($actualType -ne $ControlType) { Emit-Result @{ status = "blocked"; reason = "element_changed"; message = "Hedef UI öğesi türü değişti; yeni inceleme gerekli." } }
    if (-not $current.IsEnabled) { Emit-Result @{ status = "blocked"; reason = "element_disabled"; message = "Hedef UI öğesi etkin değil." } }
    $identifier = (($current.Name + " " + $current.AutomationId) | ForEach-Object { $_.ToLower() })
    $sensitive = @("password", "pass", "parola", "şifre", "sifre", "pin", "secret", "token", "credential", "kimlik", "auth", "cvv", "card", "kart", "payment", "ödeme", "recovery", "kurtarma", "security", "güvenlik")
    $unsafe = @("send", "submit", "save", "delete", "remove", "erase", "clear", "discard", "install", "uninstall", "update", "upgrade", "apply", "confirm", "continue", "finish", "close", "exit", "shutdown", "restart", "format", "pay", "purchase", "transfer", "share", "publish", "upload", "download", "sign", "login", "gönder", "kaydet", "sil", "kaldır", "temizle", "vazgeç", "yükle", "güncelle", "uygula", "onayla", "devam", "bitir", "kapat", "öde", "satın al", "paylaş", "yayımla", "indir", "oturum aç", "giriş")
    if ([bool]$current.IsPassword -or ($sensitive | Where-Object { $identifier.Contains($_) })) { Emit-Result @{ status = "blocked"; reason = "sensitive_field"; message = "Hassas alanlara müdahale edilemez." } }
    if ($unsafe | Where-Object { $identifier.Contains($_) }) { Emit-Result @{ status = "blocked"; reason = "unsafe_control"; message = "Bu tür kontrol Desktop Agent V1 kapsamında değildir." } }
} catch { Emit-Result @{ status = "error"; reason = "element_inspection_failed"; message = "Hedef UI öğesi doğrulanamadı." } }

if ($Action -eq "Invoke") {
    if ($actualType -ne "Button") { Emit-Result @{ status = "blocked"; reason = "unsupported_control"; message = "V1 tıklama yalnızca Button kontrollerini destekler." } }
    try {
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { Emit-Result @{ status = "error"; reason = "pattern_unavailable"; message = "Hedef kontrol InvokePattern desteklemiyor." } }
        ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
        Emit-Result @{ status = "ok"; action = "invoke"; pattern = "InvokePattern"; element_present = $true }
    } catch { Emit-Result @{ status = "error"; reason = "invoke_failed"; message = "UI Automation tıklaması tamamlanamadı." } }
}

if ($Action -eq "SetValue") {
    if ($actualType -ne "Edit" -and $actualType -ne "Document") { Emit-Result @{ status = "blocked"; reason = "unsupported_control"; message = "V1 metin girişi yalnızca Edit veya Document kontrollerini destekler." } }
    if ($Value.Length -lt 1 -or $Value.Length -gt 500) { Emit-Result @{ status = "blocked"; reason = "invalid_text"; message = "Metin boyutu güvenli sınırların dışında." } }
    try {
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) { Emit-Result @{ status = "error"; reason = "pattern_unavailable"; message = "Hedef alan ValuePattern desteklemiyor." } }
        $valuePattern = [System.Windows.Automation.ValuePattern]$pattern
        if ($valuePattern.Current.IsReadOnly) { Emit-Result @{ status = "blocked"; reason = "read_only"; message = "Hedef metin alanı salt-okunur." } }
        $valuePattern.SetValue($Value)
        $matchesValue = ($valuePattern.Current.Value -ceq $Value)
        Emit-Result @{ status = "ok"; action = "set_value"; value_length = $Value.Length; value_matches = $matchesValue; element_present = $true }
    } catch { Emit-Result @{ status = "error"; reason = "set_value_failed"; message = "UI Automation metin girişi tamamlanamadı." } }
}

Emit-Result @{ status = "error"; reason = "unsupported_action"; message = "Desteklenmeyen UI Automation eylemi." }

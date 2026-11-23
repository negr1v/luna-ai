"""
ZERO CORE OS (LUNA-AI) V4 - Windows Desktop Awareness & Computer Use Engine (V13)
Güvenli, modüler, allowlist tabanlı ve yerel Windows User32/Accessibility API destekli masaüstü kontrol çekirdeği.
"""

import os
import sys
import time
import ctypes
import logging
from ctypes import wintypes
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("luna.computer_use")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Güvenli İzinli Uygulamalar Listesi (Allowlist)
# Güvenlik nedeniyle sistem kayıt defteri, powershell, cmd veya harici şifre yöneticilerine ASLA müdahale edilmez.
ALLOWED_APP_NAMES = {
    "notepad.exe", "calc.exe", "calculator.exe", "calculatorapp.exe", "systemsettings.exe",
    "applicationframehost.exe", "mspaint.exe", "chrome.exe", "msedge.exe", "firefox.exe",
    "code.exe", "accio.exe", "explorer.exe"
}

class DesktopAwareness:
    """Windows masaüstü, açık pencereler ve aktif pencere bağlamını tespit eder."""

    @staticmethod
    def get_window_info(hwnd: int) -> Dict[str, Any]:
        """Return identity metadata for one existing top-level window.

        This narrow helper is intentionally read-only.  Desktop Agent V1 uses
        it to revalidate an already selected HWND rather than accepting a
        title or process name as a loose window selector.
        """
        try:
            hwnd = int(hwnd or 0)
        except (TypeError, ValueError):
            hwnd = 0
        if hwnd <= 0 or not user32.IsWindow(hwnd):
            return {"status": "none", "message": "Pencere bulunamadı"}

        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value or "Masaüstü"
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_name = "unknown"
        try:
            import psutil
            proc_name = psutil.Process(pid.value).name()
        except Exception:
            pass
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {
            "status": "ok",
            "hwnd": hwnd,
            "title": title,
            "process_id": pid.value,
            "process_name": proc_name,
            "bounds": {"x": rect.left, "y": rect.top, "width": rect.right - rect.left, "height": rect.bottom - rect.top},
            "is_allowed": proc_name.lower() in ALLOWED_APP_NAMES,
            "timestamp": time.time(),
        }

    @staticmethod
    def get_foreground_window_info() -> Dict[str, Any]:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"status": "none", "message": "Ön planda pencere yok"}
        return DesktopAwareness.get_window_info(hwnd)

    @staticmethod
    def list_visible_windows(max_windows: int = 15) -> List[Dict[str, Any]]:
        windows = []

        def enum_windows_proc(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if title and title not in ("Default IME", "MSCTFIME UI", "Program Manager"):
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "pid": pid.value
                        })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
        try:
            max_windows = max(1, min(int(max_windows), 60))
        except (TypeError, ValueError):
            max_windows = 15
        return windows[:max_windows] # Eski varsayılan korunur; çağıran dar bir sınır seçebilir.


class UIAutomationInspector:
    """
    Phase 16B: Modern Windows UI Automation COM/Accessibility Inspector.
    Windows Ayarlar, Hesap Makinesi, UWP ve XAML uygulamalarının erişilebilirlik
    ağacını (AutomationId, ControlType, Name, BoundingRectangle) salt-okunur denetler.
    Hassas ve parola kontrollerini maskeler, derinlik ve öğe sayısı tavanlarına uyar.
    """

    @staticmethod
    def inspect_window_uia(hwnd: int, max_elements: int = 30, max_depth: int = 3, timeout_sec: float = 3.5) -> List[Dict[str, Any]]:
        if not hwnd or hwnd <= 0:
            return []

        import subprocess
        import json

        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "luna_uia_inspect.ps1")
        if not os.path.exists(script_path):
            return []

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", script_path,
            "-Hwnd", str(hwnd),
            "-MaxElements", str(max_elements),
            "-MaxDepth", str(max_depth)
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            if res.returncode == 0 and res.stdout.strip():
                raw = res.stdout.strip()
                s_idx = raw.find("[")
                e_idx = raw.rfind("]")
                if s_idx != -1 and e_idx != -1:
                    parsed = json.loads(raw[s_idx:e_idx + 1])
                    if isinstance(parsed, list):
                        return parsed
        except Exception as e:
            logger.warning(f"[UIA COM Inspection Notice]: {e}")

        return []


class UIElementInspector:
    """Temel Win32 ve modern Windows UI Automation kontrollerini denetler."""

    @staticmethod
    def inspect_active_window_elements(use_uia: bool = True, max_elements: int = 30, max_depth: int = 3) -> Dict[str, Any]:
        info = DesktopAwareness.get_foreground_window_info()
        if info.get("status") != "ok":
            return {"status": "error", "message": "Pencere bulunamadı"}

        # Güvenlik Allowlist Denetimi
        if not info.get("is_allowed", False):
            return {
                "status": "blocked",
                "message": f"Uygulama allowlist içinde değil: {info.get('process_name')}",
                "parent_window": info.get("title"),
                "process_name": info.get("process_name"),
                "is_allowed": False,
                "elements": []
            }

        hwnd = info["hwnd"]

        # 1. Öncelikli Modern UI Automation İncelemesi
        if use_uia:
            uia_elements = UIAutomationInspector.inspect_window_uia(
                hwnd=hwnd,
                max_elements=max_elements,
                max_depth=max_depth,
                timeout_sec=3.5
            )
            if uia_elements:
                return {
                    "status": "ok",
                    "inspection_mode": "uia",
                    "parent_window": info["title"],
                    "process_name": info["process_name"],
                    "hwnd": hwnd,
                    "element_count": len(uia_elements),
                    "elements": uia_elements[:max_elements]
                }

        # 2. Klasik Win32 Geri Dönüş (Fallback) İncelemesi
        elements = []

        def enum_child_proc(child_hwnd, extra):
            if user32.IsWindowVisible(child_hwnd):
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(child_hwnd, class_buf, 256)
                cls_name = class_buf.value

                length = user32.GetWindowTextLengthW(child_hwnd)
                text = ""
                if length > 0:
                    text_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(child_hwnd, text_buf, length + 1)
                    text = text_buf.value

                rect = wintypes.RECT()
                user32.GetWindowRect(child_hwnd, ctypes.byref(rect))

                # Şifre veya gizli alan tespiti (Win32 ES_PASSWORD stili veya şifre anahtarı)
                is_sensitive = "pass" in cls_name.lower() or "şifre" in text.lower() or "parola" in text.lower()
                safe_text = "[GIZLENDI / MASKED]" if is_sensitive else text[:50]

                # Sadece tıklanabilir veya metin girilebilir standart alanları filtrele
                if cls_name.lower() in ("button", "edit", "combobox", "static", "directuihwnd", "element"):
                    elements.append({
                        "child_hwnd": child_hwnd,
                        "class_name": cls_name,
                        "control_type": cls_name.capitalize(),
                        "automation_id": "",
                        "name": safe_text,
                        "text": safe_text,
                        "is_password": is_sensitive,
                        "x": rect.left,
                        "y": rect.top,
                        "width": rect.right - rect.left,
                        "height": rect.bottom - rect.top
                    })
            return True

        CHILDWNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(hwnd, CHILDWNDENUMPROC(enum_child_proc), 0)

        return {
            "status": "ok",
            "inspection_mode": "win32_fallback",
            "parent_window": info["title"],
            "process_name": info["process_name"],
            "hwnd": hwnd,
            "element_count": len(elements),
            "elements": elements[:max_elements]
        }


class SafeComputerController:
    """Yalnızca açık kullanıcı onayı alındıktan sonra çalışan dar kapsamlı güvenli girdi kontrolcüsü."""

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        if not user32.IsWindow(hwnd):
            return False
        user32.ShowWindow(hwnd, 9) # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        return True

    @staticmethod
    def send_safe_text(text: str) -> bool:
        """Yalnızca aktif seçili alana basit harf dizisi gönderir (kullanıcı onayı zorunludur)."""
        if not text or len(text) > 200:
            return False
        
        # Basit güvenli tuş gönderme simülasyonu
        for char in text:
            vk = user32.VkKeyScanW(ord(char))
            if vk != -1:
                user32.keybd_event(vk & 0xFF, 0, 0, 0)
                user32.keybd_event(vk & 0xFF, 0, 2, 0) # KEYEVENTF_KEYUP
                time.sleep(0.01)
        return True


class UIAutomationActionController:
    """
    Phase 16D: Safe Advanced Computer Use & UIAutomation Action Controller.
    Açık kullanıcı onayı gerektiren, güvenli, denetimli ve allowlist tabanlı
    UIA InvokePattern ve ValuePattern masaüstü etkileşim çekirdeği.
    Parola ve güvenlik kontrollerini engeller, hedef öğeyi yürütme öncesi tekrar
    doğrular ve mükerrer eylem koruması sağlar.
    """

    BLOCKED_APP_NAMES = {
        "powershell.exe", "cmd.exe", "wt.exe", "bash.exe", "regedit.exe",
        "taskmgr.exe", "mmc.exe", "credwiz.exe", "consent.exe"
    }

    SENSITIVE_FIELD_TOKENS = [
        "pass", "pin", "secret", "parola", "şifre", "sifre",
        "cvv", "token", "auth", "credential", "kart", "admin"
    ]

    DESTRUCTIVE_TOKENS = [
        "rm ", "del ", "format ", "drop ", "truncate ",
        "shutdown", "reboot", "erase ", "diskpart", "attrib "
    ]

    # Mükerrer / Yinelenen Eylem Önleme Önbelleği (TTL: 30s)
    _executed_action_tokens: Dict[str, float] = {}

    @classmethod
    def _is_duplicate(cls, token: str) -> bool:
        now = time.time()
        # Temizlik
        cls._executed_action_tokens = {
            t: ts for t, ts in cls._executed_action_tokens.items() if (now - ts) < 30.0
        }
        return token in cls._executed_action_tokens

    @classmethod
    def _record_execution(cls, token: str):
        cls._executed_action_tokens[token] = time.time()

    @classmethod
    def preview_ui_action(cls, hwnd: int, action: str, automation_id: str = "", name: str = "", value: str = "") -> Dict[str, Any]:
        """Kullanıcı onayına sunulmadan önce hedef uygulama, kontrol ve eylem özetini üretir."""
        info = DesktopAwareness.get_foreground_window_info()
        try:
            foreground_hwnd = int(info.get("hwnd") or 0)
            requested_hwnd = int(hwnd or 0)
        except (TypeError, ValueError):
            foreground_hwnd, requested_hwnd = 0, 0
        if foreground_hwnd <= 0 or (requested_hwnd and requested_hwnd != foreground_hwnd):
            return {
                "status": "blocked", "reason": "target_window_changed",
                "message": "Önizleme yalnızca mevcut ön plan penceresi için oluşturulabilir."
            }
        proc_name = info.get("process_name", "unknown").lower()
        title = info.get("title", "")

        is_allowed = (proc_name in ALLOWED_APP_NAMES) and (proc_name not in cls.BLOCKED_APP_NAMES)
        target_ctrl = automation_id or name or "Belirtilmemiş Kontrol"

        # Hassas alan kontrolü
        is_sensitive = any(tok in target_ctrl.lower() for tok in cls.SENSITIVE_FIELD_TOKENS)

        action_display = "Tıklama / Tetikleme (InvokePattern)" if action == "Invoke" else f"Metin Girişi (ValuePattern: '{value[:20]}...')" if action == "SetValue" else action

        return {
            "status": "preview",
            "target_app": proc_name,
            "target_window": title,
            "target_hwnd": foreground_hwnd,
            "control": target_ctrl,
            "action": action,
            "action_display": action_display,
            "value": value,
            "is_allowed": is_allowed,
            "is_sensitive": is_sensitive,
            "requires_approval": True
        }

    @classmethod
    def execute_ui_action(
        cls,
        hwnd: int,
        action: str,
        automation_id: str = "",
        name: str = "",
        value: str = "",
        action_token: Optional[str] = None,
        timeout_sec: float = 3.5,
        expected_window_title: str = "",
        expected_process_name: str = "",
    ) -> Dict[str, Any]:
        """
        Kullanıcı onayı almış UIA eylemini (Invoke veya SetValue) güvenle yürütür.
        1. Ön plan pencere ve allowlist revalidasyonu
        2. Parola / Güvenlik alan kısıtlaması
        3. Mükerrer eylem engeli
        4. Yerel PowerShell UIA yürütücüsü ve Win32 fallback
        """
        import hashlib
        import subprocess
        import json

        # 1. Hedef Pencere ve Allowlist Doğrulaması
        info = DesktopAwareness.get_foreground_window_info()
        proc_name = info.get("process_name", "unknown").lower()
        try:
            foreground_hwnd = int(info.get("hwnd") or 0)
            requested_hwnd = int(hwnd or 0)
        except (TypeError, ValueError):
            foreground_hwnd, requested_hwnd = 0, 0

        if proc_name in cls.BLOCKED_APP_NAMES:
            return {
                "status": "blocked",
                "reason": "security_restricted_app",
                "message": f"Güvenlik Kısıtlaması: '{proc_name}' sistem kritik uygulaması olduğundan etkileşim kesinlikle engellenmiştir."
            }

        if proc_name not in ALLOWED_APP_NAMES:
            return {
                "status": "blocked",
                "reason": "app_not_allowed",
                "message": f"Uygulama allowlist içinde değil: {proc_name}"
            }

        target_identifier = (automation_id or name or "").lower()

        # 2. Hassas Alan ve Yıkıcı Komut Koruması
        if any(tok in target_identifier for tok in cls.SENSITIVE_FIELD_TOKENS):
            return {
                "status": "blocked",
                "reason": "sensitive_field",
                "message": "Güvenlik Koruması: Parola, PIN veya kimlik doğrulama kontrollerine müdahale edilemez."
            }

        if action == "SetValue" and any(tok in value.lower() for tok in cls.DESTRUCTIVE_TOKENS):
            return {
                "status": "blocked",
                "reason": "destructive_command_blocked",
                "message": "Güvenlik Koruması: Yıkıcı veya sistem dosyalarını silmeye yönelik komutlar engellenmiştir."
            }

        # 3. Mükerrer Eylem (Duplicate Replay) Kontrolü
        if not action_token:
            action_token = hashlib.sha256(f"{hwnd}:{action}:{automation_id}:{name}:{value}".encode()).hexdigest()[:16]

        if cls._is_duplicate(action_token):
            return {
                "status": "blocked",
                "reason": "duplicate_action",
                "message": "Yinelenen Eylem Koruması: Bu işlem yakın zamanda yürütülmüştür, mükerrer yürütme engellendi."
            }

        # Target identity is checked after independent allowlist/sensitive/duplicate
        # guards so they retain their stable, more specific rejection reasons.
        if foreground_hwnd <= 0 or requested_hwnd != foreground_hwnd:
            return {
                "status": "blocked", "reason": "target_window_changed",
                "message": "Onaylanan hedef pencere artık ön planda değil; yeni önizleme ve onay gerekli."
            }
        if expected_window_title and expected_window_title != str(info.get("title") or ""):
            return {
                "status": "blocked", "reason": "target_window_changed",
                "message": "Hedef pencere başlığı değişti; yeni önizleme ve onay gerekli."
            }
        if expected_process_name and expected_process_name.lower() != proc_name:
            return {
                "status": "blocked", "reason": "target_window_changed",
                "message": "Hedef uygulama değişti; yeni önizleme ve onay gerekli."
            }

        # 4. Yürütme Öncesi Hedef Öğeyi Doğrulama (Immediate Pre-execution Revalidation)
        if not user32.IsWindow(hwnd):
            return {
                "status": "error",
                "reason": "window_closed",
                "message": "Hedef pencere yürütme öncesinde kapatılmış veya geçersiz."
            }

        # 5. Native PowerShell UIAutomation Yürütücüsünü Çağırma
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "luna_uia_action.ps1")
        if not os.path.exists(script_path):
            return {"status": "error", "message": "luna_uia_action.ps1 betiği bulunamadı."}

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", script_path,
            "-Hwnd", str(hwnd),
            "-AutomationId", str(automation_id or ""),
            "-Name", str(name or ""),
            "-Action", action,
            "-Value", str(value or ""),
            "-TimeoutSec", str(timeout_sec)
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec + 1.0)
            if res.returncode == 0 and res.stdout.strip():
                raw = res.stdout.strip()
                s_idx = raw.find("{")
                e_idx = raw.rfind("}")
                if s_idx != -1 and e_idx != -1:
                    parsed = json.loads(raw[s_idx:e_idx + 1])
                    if parsed.get("status") == "ok":
                        cls._record_execution(action_token)
                    return parsed
        except subprocess.TimeoutExpired:
            return {"status": "error", "reason": "timeout", "message": f"UIA eylemi zaman aşımına uğradı ({timeout_sec}s)."}
        except Exception as e:
            logger.warning(f"[UIA Action Warning]: {e}")

        # 6. Win32 Fallback
        # Eğer UIA başarısız olduysa ve temel Win32 buton/alan tıklaması gerekiyorsa
        if action == "Invoke":
            try:
                # BM_CLICK (0x00F5) fallback
                user32.SendMessageW(hwnd, 0x00F5, 0, 0)
                cls._record_execution(action_token)
                return {
                    "status": "ok",
                    "action": "invoke",
                    "pattern": "win32_bm_click_fallback",
                    "target_window": info.get("title")
                }
            except Exception as e:
                return {"status": "error", "reason": "win32_fallback_failed", "message": str(e)}

        return {"status": "error", "reason": "execution_failed", "message": "UI eylemi gerçekleştirilemedi."}


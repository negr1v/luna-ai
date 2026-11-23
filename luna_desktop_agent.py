"""ACCIO LUNA ULTRA Desktop Agent V1.

This is intentionally a small semantic Windows UI Automation workflow.  It is
not a general desktop controller: no coordinates, process launch, shell,
browser automation, clipboard access, or unattended work is exposed here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from luna_agent_engine import AgentController, AgentTask, PermissionLevel, TaskState, TaskStep, ToolDefinition


class DesktopAgentError(Exception):
    """A safe error that can be presented in the Desktop Agent workspace."""


class DesktopVerificationError(DesktopAgentError):
    """The UIA request returned, but its bounded verification did not pass."""


MAX_WINDOWS = 20
MAX_ELEMENTS = 30
MAX_TEXT_LENGTH = 500
UIA_TIMEOUT_SECONDS = 4.0

# This is deliberately narrower than the legacy Computer Use allowlist.  In
# particular, browser, shell, file-manager and code-editor windows are not V1
# targets because their UI can carry web, shell or file-system side effects.
DESKTOP_V1_ALLOWED_PROCESSES = {
    "notepad.exe", "calc.exe", "calculator.exe", "calculatorapp.exe",
    "mspaint.exe", "accio.exe",
}
_BLOCKED_WINDOW_TOKENS = (
    "password", "parola", "şifre", "sifre", "pin", "credential", "kimlik",
    "security", "güvenlik", "windows security", "uac", "account", "hesap",
    "sign in", "oturum aç", "recovery", "kurtarma", "payment", "ödeme",
)
_SENSITIVE_TOKENS = (
    "password", "pass", "parola", "şifre", "sifre", "pin", "secret", "token",
    "credential", "kimlik", "auth", "cvv", "card", "kart", "payment", "ödeme",
    "recovery", "kurtarma", "security", "güvenlik",
)
_UNSAFE_CONTROL_TOKENS = (
    "send", "submit", "save", "delete", "remove", "erase", "clear", "discard",
    "install", "uninstall", "update", "upgrade", "apply", "confirm", "continue",
    "finish", "close", "exit", "shutdown", "restart", "format", "pay", "purchase",
    "transfer", "share", "publish", "upload", "download", "sign", "login", "log in",
    "gönder", "kaydet", "sil", "kaldır", "temizle", "vazgeç", "yükle", "güncelle",
    "uygula", "onayla", "devam", "bitir", "kapat", "yeniden başlat", "biçimlendir",
    "öde", "satın al", "paylaş", "yayımla", "indir", "oturum aç", "giriş",
)
_UNSAFE_CONTEXT_TOKENS = ("terminal", "command", "console", "shell", "powershell", "cmd", "script")
_CLICKABLE_CONTROL_TYPES = {"Button"}
_EDITABLE_CONTROL_TYPES = {"Edit", "Document"}


def _compact(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:20]


def _canonical(value: Dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class WindowTarget:
    window_id: str
    hwnd: int
    process_id: int
    process_name: str
    title: str
    title_fingerprint: str

    def public_view(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "process_name": self.process_name,
            "title": self.title,
        }


@dataclass
class DesktopActionRecord:
    action_id: str
    window_id: str
    action: str
    element_id: str = ""
    text: str = ""
    target: Optional[WindowTarget] = None
    element: Optional[Dict[str, Any]] = None
    binding: Dict[str, Any] = field(default_factory=dict)
    task_id: Optional[str] = None
    state: str = "PLANNED"
    result: Optional[Dict[str, Any]] = None
    error: str = ""
    created_at: float = field(default_factory=time.time)


class DesktopSemanticBackend:
    """The fixed-script UIA adapter used by Desktop Agent V1 only."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def list_windows() -> List[Dict[str, Any]]:
        from luna_computer_use import DesktopAwareness
        windows: List[Dict[str, Any]] = []
        for item in DesktopAwareness.list_visible_windows(max_windows=60):
            info = DesktopAwareness.get_window_info(item.get("hwnd"))
            if info.get("status") == "ok":
                windows.append(info)
        return windows

    @staticmethod
    def get_window_info(hwnd: int) -> Dict[str, Any]:
        from luna_computer_use import DesktopAwareness
        return DesktopAwareness.get_window_info(hwnd)

    @staticmethod
    def get_foreground_window_info() -> Dict[str, Any]:
        from luna_computer_use import DesktopAwareness
        return DesktopAwareness.get_foreground_window_info()

    def inspect_window(self, hwnd: int) -> List[Dict[str, Any]]:
        from luna_computer_use import UIAutomationInspector
        # Desktop V1 has no Win32 / coordinate fallback.
        return UIAutomationInspector.inspect_window_uia(hwnd, max_elements=MAX_ELEMENTS, max_depth=3, timeout_sec=UIA_TIMEOUT_SECONDS)

    @staticmethod
    def focus_window(hwnd: int) -> bool:
        from luna_computer_use import SafeComputerController
        return bool(SafeComputerController.focus_window(hwnd))

    def execute_element(self, target: WindowTarget, element: Dict[str, Any], action: str, text: str) -> Dict[str, Any]:
        script_path = os.path.join(self.base_dir, "luna_desktop_uia_action.ps1")
        if not os.path.isfile(script_path):
            raise DesktopAgentError("Desktop Agent UI Automation yürütücüsü bulunamadı.")
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path,
            "-Hwnd", str(target.hwnd),
            "-AutomationId", str(element.get("automation_id") or ""),
            "-Name", str(element.get("label") or ""),
            "-ControlType", str(element.get("control_type") or ""),
            "-Action", "Invoke" if action == "click_element" else "SetValue",
            "-Value", text,
            "-TimeoutSec", str(UIA_TIMEOUT_SECONDS),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=UIA_TIMEOUT_SECONDS + 1.0)
        except subprocess.TimeoutExpired:
            return {"status": "error", "reason": "timeout", "message": "UI Automation eylemi zaman aşımına uğradı."}
        except OSError:
            return {"status": "error", "reason": "executor_unavailable", "message": "UI Automation yürütücüsü başlatılamadı."}
        if completed.returncode != 0 or not completed.stdout.strip():
            return {"status": "error", "reason": "execution_failed", "message": "UI Automation eylemi tamamlanamadı."}
        raw = completed.stdout.strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < start:
            return {"status": "error", "reason": "invalid_executor_response", "message": "UI Automation sonucu doğrulanamadı."}
        try:
            result = json.loads(raw[start:end + 1])
        except (TypeError, ValueError):
            return {"status": "error", "reason": "invalid_executor_response", "message": "UI Automation sonucu doğrulanamadı."}
        if not isinstance(result, dict):
            return {"status": "error", "reason": "invalid_executor_response", "message": "UI Automation sonucu doğrulanamadı."}
        return result


class DesktopAgent:
    """One-action, semantic desktop automation workflow bound to AgentController."""

    def __init__(self, data_dir: Optional[str] = None, backend: Optional[Any] = None):
        self.backend = backend or DesktopSemanticBackend()
        self.engine = AgentController(project_dir=os.getcwd(), data_dir=data_dir)
        self._lock = threading.RLock()
        self._windows: Dict[str, WindowTarget] = {}
        self._inspections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.actions: Dict[str, DesktopActionRecord] = {}
        self._register_tools()

    # ---------- Policy and identity ----------

    @staticmethod
    def _window_is_eligible(info: Dict[str, Any]) -> bool:
        process = _compact(info.get("process_name")).lower()
        title = _compact(info.get("title"), 300)
        if process not in DESKTOP_V1_ALLOWED_PROCESSES or not title:
            return False
        lowered = title.lower()
        return not any(token in lowered for token in _BLOCKED_WINDOW_TOKENS)

    @staticmethod
    def _target_from_info(info: Dict[str, Any]) -> WindowTarget:
        try:
            hwnd = int(info.get("hwnd") or 0)
            process_id = int(info.get("process_id", info.get("pid")) or 0)
        except (TypeError, ValueError):
            raise DesktopAgentError("Pencere kimliği geçersiz.")
        process_name = _compact(info.get("process_name"), 128).lower()
        title = _compact(info.get("title"), 300)
        if hwnd <= 0 or process_id <= 0 or not process_name or not title:
            raise DesktopAgentError("Pencere kimliği eksik veya geçersiz.")
        title_fingerprint = _fingerprint(title)
        window_id = "desktop_window_" + _fingerprint(f"{hwnd}|{process_id}|{process_name}|{title_fingerprint}")
        return WindowTarget(window_id, hwnd, process_id, process_name, title, title_fingerprint)

    @staticmethod
    def _element_source(element: Dict[str, Any]) -> str:
        return "|".join((
            _compact(element.get("control_type"), 80),
            _compact(element.get("automation_id"), 180),
            _compact(element.get("name", element.get("label")), 180),
        ))

    @classmethod
    def _element_safety_reason(cls, item: Dict[str, Any], requested_action: str = "") -> str:
        identifier = " ".join((str(item.get("automation_id") or ""), str(item.get("label") or item.get("name") or ""))).lower()
        control_type = str(item.get("control_type") or "")
        if bool(item.get("is_password")) or any(token in identifier for token in _SENSITIVE_TOKENS):
            return "Hassas parola, PIN, kimlik veya ödeme alanları Desktop Agent V1 kapsamı dışındadır."
        if any(token in identifier for token in _UNSAFE_CONTEXT_TOKENS):
            return "Komut, konsol veya betik bağlamları Desktop Agent V1 kapsamı dışındadır."
        if any(token in identifier for token in _UNSAFE_CONTROL_TOKENS):
            return "Gönderme, kaydetme, silme, kurulum veya onay kontrolü Desktop Agent V1 kapsamında değildir."
        if requested_action == "click_element" and control_type not in _CLICKABLE_CONTROL_TYPES:
            return "V1 tıklama yalnızca güvenli ve benzersiz Button kontrollerini destekler."
        if requested_action == "set_text" and control_type not in _EDITABLE_CONTROL_TYPES:
            return "V1 metin girişi yalnızca Edit veya Document kontrollerini destekler."
        if not bool(item.get("is_enabled", True)) and requested_action:
            return "Devre dışı bir kontrol çalıştırılamaz."
        return ""

    def _require_window(self, window_id: str) -> WindowTarget:
        target = self._windows.get(window_id)
        if not target:
            raise DesktopAgentError("Pencere seçimi geçersiz veya yenilenmiş. Listeden tekrar seçin.")
        return target

    def _fresh_target(self, target: WindowTarget) -> WindowTarget:
        info = self.backend.get_window_info(target.hwnd)
        if not isinstance(info, dict) or info.get("status") != "ok" or not self._window_is_eligible(info):
            raise DesktopAgentError("Seçilen pencere artık uygun veya erişilebilir değil.")
        current = self._target_from_info(info)
        if (
            current.hwnd != target.hwnd or current.process_id != target.process_id or
            current.process_name != target.process_name or current.title_fingerprint != target.title_fingerprint
        ):
            raise DesktopAgentError("İşlem, pencere tutamacı veya başlık değişti; yeni inceleme ve onay gerekli.")
        return current

    def _normalize_elements(self, raw_elements: Any) -> Dict[str, Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for raw in list(raw_elements or [])[:MAX_ELEMENTS]:
            if not isinstance(raw, dict):
                continue
            label = _compact(raw.get("name", raw.get("label")), 160)
            automation_id = _compact(raw.get("automation_id"), 180)
            control_type = _compact(raw.get("control_type"), 80)
            if not (label or automation_id) or not control_type:
                continue
            item = {
                "control_type": control_type,
                "label": label,
                "automation_id": automation_id,
                "is_enabled": bool(raw.get("is_enabled", True)),
                "is_password": bool(raw.get("is_password", False)),
            }
            item["identity"] = _fingerprint(self._element_source(item))
            item["safety_reason"] = self._element_safety_reason(item)
            candidates.append(item)
        counts: Dict[str, int] = {}
        for item in candidates:
            counts[item["identity"]] = counts.get(item["identity"], 0) + 1
        normalized: Dict[str, Dict[str, Any]] = {}
        for index, item in enumerate(candidates):
            item["ambiguous"] = counts[item["identity"]] != 1
            if item["ambiguous"] or item["safety_reason"]:
                item["element_id"] = ""
            else:
                item["element_id"] = "desktop_element_" + item["identity"]
            # Keep ambiguous entries visible to the user, but store them under
            # an internal key.  They receive no usable element_id and therefore
            # cannot be selected for an action.
            storage_key = item["element_id"] or f"_ambiguous_{item['identity']}_{index}"
            normalized[storage_key] = item
        return normalized

    @staticmethod
    def _public_element(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "element_id": item.get("element_id", ""),
            "control_type": item.get("control_type", ""),
            "label": item.get("label", ""),
            "automation_id": item.get("automation_id", ""),
            "is_enabled": bool(item.get("is_enabled", False)),
            "ambiguous": bool(item.get("ambiguous", False)),
            "safe_for_action": not bool(item.get("safety_reason")),
            "safety_reason": item.get("safety_reason", ""),
        }

    # ---------- Read-only tools ----------

    async def _execute_read_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        validation = self.engine.registry.validate_arguments(name, arguments)
        if not validation["valid"]:
            first = validation["errors"][0]
            raise DesktopAgentError(f"Geçersiz Desktop Agent isteği: {first['field']} ({first['code']}).")
        tool = self.engine.registry.get(name)
        if not tool:
            raise DesktopAgentError("Desktop Agent aracı bulunamadı.")
        return await asyncio.wait_for(tool.handler(arguments), timeout=tool.timeout_sec)

    async def _tool_list_windows(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del arguments
        listed: Dict[str, WindowTarget] = {}
        for info in list(self.backend.list_windows() or []):
            if len(listed) >= MAX_WINDOWS:
                break
            if not isinstance(info, dict) or not self._window_is_eligible(info):
                continue
            try:
                target = self._target_from_info(info)
            except DesktopAgentError:
                continue
            listed[target.window_id] = target
        with self._lock:
            self._windows = listed
            self._inspections = {key: value for key, value in self._inspections.items() if key in listed}
        return {"status": "ok", "windows": [target.public_view() for target in listed.values()]}

    async def list_windows(self) -> Dict[str, Any]:
        return await self._execute_read_tool("desktop.list_windows", {})

    async def _tool_inspect_window(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = self._fresh_target(self._require_window(arguments["window_id"]))
        elements = self._normalize_elements(self.backend.inspect_window(target.hwnd))
        with self._lock:
            self._inspections[target.window_id] = elements
        # Ambiguous items intentionally remain visible, but never get a usable ID.
        public = [self._public_element(item) for item in elements.values()]
        return {"status": "ok", "window": target.public_view(), "elements": public, "element_count": len(public)}

    async def inspect_window(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_read_tool("desktop.inspect_window", arguments)

    def _current_element(self, target: WindowTarget, element_id: str) -> Dict[str, Any]:
        previous = self._inspections.get(target.window_id, {}).get(element_id)
        if not previous:
            raise DesktopAgentError("Öğe seçimi geçersiz veya önce pencere incelemesi yapılmadı.")
        current = self._normalize_elements(self.backend.inspect_window(target.hwnd)).get(element_id)
        if not current or current.get("identity") != previous.get("identity"):
            raise DesktopAgentError("Hedef UI öğesi değişti veya artık benzersiz değil; yeni inceleme ve onay gerekli.")
        return current

    async def _tool_read_element_state(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = self._fresh_target(self._require_window(arguments["window_id"]))
        element = self._current_element(target, arguments["element_id"])
        return {
            "status": "ok", "window": target.public_view(),
            "element": self._public_element(element), "present": True,
        }

    async def read_element_state(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_read_tool("desktop.read_element_state", arguments)

    # ---------- Preview / approval / execution ----------

    def _action_binding(self, record: DesktopActionRecord) -> Dict[str, Any]:
        if not record.target:
            raise DesktopAgentError("Masaüstü eylem hedefi oluşturulamadı.")
        return {
            "action_id": record.action_id,
            "window_id": record.window_id,
            "window_handle": record.target.hwnd,
            "process_id": record.target.process_id,
            "process_name": record.target.process_name,
            "title_fingerprint": record.target.title_fingerprint,
            "element_identity": (record.element or {}).get("identity", ""),
            "action": record.action,
            "text": record.text,
        }

    def _action_view(self, record: DesktopActionRecord) -> Dict[str, Any]:
        return {
            "action_id": record.action_id,
            "state": record.state,
            "planned_action": record.action,
            "target": record.target.public_view() if record.target else None,
            "element": self._public_element(record.element) if record.element else None,
            # Exact text is deliberately present in the user-facing preview and
            # bound to approval.  It is never written to the audit log by this module.
            "text": record.text if record.action == "set_text" else "",
            "result": record.result,
            "error": record.error,
        }

    def _require_action(self, action_id: str) -> DesktopActionRecord:
        record = self.actions.get(action_id)
        if not record:
            raise DesktopAgentError("Desktop Agent eylem önizlemesi bulunamadı.")
        return record

    async def create_action_preview(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        validation = self.engine.registry.validate_arguments("desktop.create_action", arguments)
        if not validation["valid"]:
            first = validation["errors"][0]
            raise DesktopAgentError(f"Geçersiz eylem önizlemesi: {first['field']} ({first['code']}).")
        action = arguments["action"]
        target = self._fresh_target(self._require_window(arguments["window_id"]))
        element: Optional[Dict[str, Any]] = None
        element_id = arguments.get("element_id", "")
        text = arguments.get("text", "")
        if action == "focus_window":
            if element_id or text:
                raise DesktopAgentError("Pencere odaklama bir öğe veya metin kabul etmez.")
        else:
            element = self._current_element(target, element_id)
            safety = self._element_safety_reason(element, action)
            if safety:
                raise DesktopAgentError(safety)
            if action == "set_text":
                if not isinstance(text, str) or not text or len(text) > MAX_TEXT_LENGTH:
                    raise DesktopAgentError("Metin girişi için 1-500 karakterlik kesin bir metin gerekli.")
            elif text:
                raise DesktopAgentError("Tıklama eylemi metin kabul etmez.")

        record = DesktopActionRecord(
            action_id="desktop_action_" + uuid.uuid4().hex[:12], window_id=target.window_id,
            action=action, element_id=element_id, text=text, target=target, element=element,
        )
        record.binding = self._action_binding(record)
        with self._lock:
            self.actions[record.action_id] = record
        return {"status": "ok", "preview": self._action_view(record)}

    async def begin_action_approval(self, action_id: str) -> Dict[str, Any]:
        record = self._require_action(action_id)
        if record.state not in {"PLANNED", "AWAITING_APPROVAL"}:
            raise DesktopAgentError("Bu eylem artık onaylanabilir değil; yeni bir önizleme oluşturun.")
        # Revalidate before opening the approval, then bind every relevant value.
        self._revalidate_record(record)
        task = AgentTask(
            task_id="desktop_task_" + uuid.uuid4().hex[:12],
            user_request="Desktop Agent V1 yapılandırılmış eylemi",
            description="Tek, sınırlandırılmış Desktop Agent V1 eylemi",
            steps=[TaskStep(1, "Önizlemesi yapılan masaüstü eylemini tek kez uygula", f"desktop.{record.action}", dict(record.binding), PermissionLevel.USER_APPROVAL)],
            state=TaskState.CREATED,
        )
        self.engine.tasks[task.task_id] = task
        record.task_id = task.task_id
        await self.engine.execute_task(task.task_id)
        record.state = "AWAITING_APPROVAL"
        task_view = self.engine.to_dict(task.task_id) or {}
        step = task_view.get("steps", [{}])[0]
        return {
            "status": "ok", "preview": self._action_view(record),
            "approval": {"task_id": task.task_id, "step_id": 1, "approval_id": step.get("approval_id"), "expires_at": step.get("approval_expires_at")},
        }

    async def approve_action(self, action_id: str, approval_id: str) -> Dict[str, Any]:
        record = self._require_action(action_id)
        if not record.task_id or not isinstance(approval_id, str) or not approval_id:
            raise DesktopAgentError("Geçerli, tek kullanımlık Desktop Agent onayı gerekli.")
        if not self.engine.approve_step(record.task_id, 1, approval_id):
            raise DesktopAgentError("Onay geçersiz, kullanılmış, süresi dolmuş veya eylem değişmiş. Yeni önizleme gerekli.")
        await self.engine.execute_task(record.task_id)
        task = self.engine.to_dict(record.task_id) or {}
        if task.get("state") != TaskState.COMPLETED.value:
            if not record.error:
                record.state = "FAILED"
                record.error = str(task.get("error") or "Masaüstü eylemi tamamlanamadı.")[:400]
            return {"status": "error", "preview": self._action_view(record)}
        return {"status": "ok", "preview": self._action_view(record)}

    def reject_action(self, action_id: str) -> Dict[str, Any]:
        record = self._require_action(action_id)
        if record.task_id:
            self.engine.reject_step(record.task_id, 1, "Kullanıcı Desktop Agent eylemini reddetti")
        record.state = "REJECTED"
        record.error = "Kullanıcı tarafından reddedildi."
        return self._action_view(record)

    def _revalidate_record(self, record: DesktopActionRecord) -> None:
        if record.binding != self._action_binding(record):
            raise DesktopAgentError("Önizleme eylemi değişti; yeni bir onay önizlemesi gerekli.")
        target = self._fresh_target(record.target) if record.target else None
        if not target:
            raise DesktopAgentError("Hedef pencere bulunamadı.")
        if record.action != "focus_window":
            current = self._current_element(target, record.element_id)
            if not record.element or current.get("identity") != record.element.get("identity"):
                raise DesktopAgentError("Hedef UI öğesi değişti; yeni inceleme ve onay gerekli.")
            safety = self._element_safety_reason(current, record.action)
            if safety:
                raise DesktopAgentError(safety)
            record.element = current
        record.target = target

    async def _tool_execute_action(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        record = self._require_action(arguments["action_id"])
        try:
            if _canonical(arguments) != _canonical(record.binding):
                raise DesktopAgentError("Onaylanan işlem, pencere, hedef öğe veya metin değişti.")
            self._revalidate_record(record)
            if record.action == "focus_window":
                if not self.backend.focus_window(record.target.hwnd):
                    raise DesktopAgentError("Seçilen pencere odaklanamadı.")
                try:
                    self._fresh_target(record.target)
                except DesktopAgentError:
                    raise DesktopVerificationError("Pencere odağı eylem sonrasında doğrulanamadı.")
                # A focus action additionally requires this exact window to be foreground.
                foreground = self.backend.get_foreground_window_info()
                if int(foreground.get("hwnd") or 0) != record.target.hwnd:
                    raise DesktopVerificationError("Pencere odağı eylem sonrasında doğrulanamadı.")
                result = {"status": "ok", "verification": {"status": "verified", "observed": "window_focused"}}
            else:
                foreground = self.backend.get_foreground_window_info()
                if int(foreground.get("hwnd") or 0) != record.target.hwnd:
                    raise DesktopAgentError("Seçilen pencere ön planda değil; önce yalnızca bu pencere için odak eylemini onaylayın.")
                execution = self.backend.execute_element(record.target, record.element or {}, record.action, record.text)
                if not isinstance(execution, dict) or execution.get("status") != "ok":
                    raise DesktopAgentError(str((execution or {}).get("message") or "UI Automation eylemi gerçekleştirilemedi.")[:400])
                if record.action == "set_text" and execution.get("value_matches") is not True:
                    raise DesktopVerificationError("Metin girişi doğrulanamadı; eylem başarılı sayılmadı.")
                state = await self._tool_read_element_state({"window_id": record.window_id, "element_id": record.element_id})
                if state.get("status") != "ok" or not state.get("present"):
                    raise DesktopVerificationError("UI öğesi eylem sonrasında doğrulanamadı.")
                result = {
                    "status": "ok",
                    "verification": {"status": "verified", "observed": "element_present", "element": state.get("element")},
                    "execution": {key: value for key, value in execution.items() if key not in {"value", "text"}},
                }
            record.result = result
            record.state = "SUCCEEDED"
            return result
        except DesktopVerificationError as exc:
            record.state = "VERIFICATION_FAILED"
            record.error = str(exc)[:400]
            raise
        except DesktopAgentError as exc:
            record.state = "INVALIDATED"
            record.error = str(exc)[:400]
            raise

    # ---------- Tool schemas ----------

    def _register_tools(self) -> None:
        no_arguments = {"type": "object", "properties": {}, "additionalProperties": False}
        window_schema = {
            "type": "object", "properties": {"window_id": {"type": "string", "maxLength": 80}},
            "required": ["window_id"], "additionalProperties": False,
        }
        element_schema = {
            "type": "object", "properties": {
                "window_id": {"type": "string", "maxLength": 80},
                "element_id": {"type": "string", "maxLength": 80},
            }, "required": ["window_id", "element_id"], "additionalProperties": False,
        }
        create_schema = {
            "type": "object", "properties": {
                "window_id": {"type": "string", "maxLength": 80},
                "action": {"type": "string", "enum": ["focus_window", "click_element", "set_text"]},
                "element_id": {"type": "string", "maxLength": 80},
                "text": {"type": "string", "maxLength": MAX_TEXT_LENGTH},
            }, "required": ["window_id", "action"], "additionalProperties": False,
        }
        approval_schema = {
            "type": "object", "properties": {
                "action_id": {"type": "string", "maxLength": 80}, "window_id": {"type": "string", "maxLength": 80},
                "window_handle": {"type": "integer", "minimum": 1}, "process_id": {"type": "integer", "minimum": 1},
                "process_name": {"type": "string", "maxLength": 128}, "title_fingerprint": {"type": "string", "maxLength": 80},
                "element_identity": {"type": "string", "maxLength": 80},
                "action": {"type": "string", "enum": ["focus_window", "click_element", "set_text"]},
                "text": {"type": "string", "maxLength": MAX_TEXT_LENGTH},
            },
            "required": ["action_id", "window_id", "window_handle", "process_id", "process_name", "title_fingerprint", "element_identity", "action", "text"],
            "additionalProperties": False,
        }
        self.engine.registry.register(ToolDefinition("desktop.list_windows", "Uygun üst seviye pencereleri sınırlı metaveriyle listeler.", PermissionLevel.READ_ONLY, 4.0, self._tool_list_windows, no_arguments))
        self.engine.registry.register(ToolDefinition("desktop.inspect_window", "Kullanıcının seçtiği uygun pencerenin sınırlı anlamsal UI ağacını okur.", PermissionLevel.READ_ONLY, 6.0, self._tool_inspect_window, window_schema))
        self.engine.registry.register(ToolDefinition("desktop.read_element_state", "Hassas olmayan öğe durumunu doğrulama amacıyla okur.", PermissionLevel.READ_ONLY, 6.0, self._tool_read_element_state, element_schema))
        self.engine.registry.register(ToolDefinition("desktop.create_action", "Bir tek Desktop Agent eyleminin bağlı önizlemesini oluşturur.", PermissionLevel.READ_ONLY, 6.0, lambda _args: {"status": "internal"}, create_schema))
        for action_name, description in (
            ("focus_window", "Onaylanan uygun pencereyi odaklar ve odağı doğrular."),
            ("click_element", "Onaylanan benzersiz, güvenli Button kontrolünü UIA ile tetikler."),
            ("set_text", "Onaylanan kesin metni benzersiz, güvenli metin alanına UIA ile yazar."),
        ):
            action_schema = dict(approval_schema)
            action_schema["properties"] = dict(approval_schema["properties"])
            action_schema["properties"]["action"] = {"type": "string", "enum": [action_name]}
            self.engine.registry.register(ToolDefinition(
                f"desktop.{action_name}", description, PermissionLevel.USER_APPROVAL, 12.0,
                self._tool_execute_action, action_schema,
            ))

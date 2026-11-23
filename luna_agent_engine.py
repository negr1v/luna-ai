"""
ZERO CORE OS (LUNA-AI) V4 - Autonomous Agent Core Engine (V11/V12)
Modüler, güvenli, izin denetimli ve mevcut aiohttp backend'i ile tam entegre otonom ajan çekirdeği.
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
import hashlib
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger("luna.agent")

class TaskState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINAL_DENIED = "TERMINAL_DENIED"

class PermissionLevel(str, Enum):
    READ_ONLY = "READ_ONLY"         # Otomatik izin verilebilir (sistem telemetrisi, dosya listeleme)
    USER_APPROVAL = "USER_APPROVAL" # Açık kullanıcı onayı gerektirir (dosya okuma, durum değiştirme)
    RESTRICTED = "RESTRICTED"       # Tamamen engellenmiş (rastgele kod çalıştırma, silme)

class AgentEventManager:
    """Ajanın canlı durum olaylarını tutar ve dinleyicilere iletir."""
    def __init__(self, max_history=100):
        self.events: List[Dict[str, Any]] = []
        self.max_history = max_history

    def emit(self, event_type: str, task_id: str, data: Dict[str, Any]):
        evt = {
            "id": uuid.uuid4().hex[:12],
            "timestamp": time.time(),
            "event_type": event_type,
            "task_id": task_id,
            "data": data
        }
        self.events.append(evt)
        if len(self.events) > self.max_history:
            self.events.pop(0)
        logger.info(f"[AgentEventManager] Olay yayımlandı: {event_type} (Görev: {task_id})")

    def get_events_since(self, since_timestamp: float = 0.0) -> List[Dict[str, Any]]:
        return [e for e in self.events if e["timestamp"] > since_timestamp]

@dataclass
class ToolDefinition:
    name: str
    description: str
    permission_level: PermissionLevel
    timeout_sec: float
    handler: Callable
    input_schema: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskStep:
    step_id: int
    description: str
    tool_name: str
    arguments: Dict[str, Any]
    permission_level: PermissionLevel
    status: str = "PENDING"
    result: Optional[Any] = None
    error: Optional[str] = None
    approval_granted: bool = False
    # The approval record is deliberately separate from tool input.  It gives
    # an approval a short lifetime and prevents it being replayed for a
    # changed action or desktop target.
    approval_id: Optional[str] = None
    approval_expires_at: Optional[float] = None
    approval_descriptor: Optional[Dict[str, Any]] = None
    approval_used: bool = False
    bound_target: Optional[Dict[str, Any]] = None
    target_was_explicit: bool = False

@dataclass
class AgentTask:
    task_id: str
    user_request: str
    description: str
    steps: List[TaskStep]
    state: TaskState
    current_step_index: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    summary: Optional[str] = None
    denied_tools: List[str] = field(default_factory=list)

class ToolRegistry:
    """Yalnızca kayıtlı ve izinli güvenli araçları yönetir. Rastgele kabuk/komut erişimi kesinlikle yasaktır."""
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        # An omitted schema means "no arguments", never an implicit arbitrary
        # object.  This keeps newly registered tools fail-closed by default.
        if not tool.input_schema:
            tool.input_schema = {"type": "object", "properties": {}, "additionalProperties": False}
        self._tools[tool.name] = tool
        logger.info(f"[ToolRegistry] Araç kaydedildi: {tool.name} (İzin: {tool.permission_level.value})")

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def validate_arguments(self, name: str, arguments: Any) -> Dict[str, Any]:
        """Validate a registered tool's small JSON-schema subset at the call boundary.

        Validation errors intentionally contain field names and rule names only;
        they never echo potentially sensitive input values back to the caller.
        """
        tool = self.get(name)
        if not tool:
            return {"valid": False, "errors": [{
                "field": "tool_name", "code": "UNKNOWN_TOOL",
                "message": "Kayıtlı olmayan araç çağrılamaz."
            }]}
        schema = tool.input_schema or {"type": "object"}
        errors: List[Dict[str, str]] = []
        self._validate_value(arguments, schema, "arguments", errors)
        return {"valid": not errors, "errors": errors}

    @classmethod
    def _validate_value(cls, value: Any, schema: Dict[str, Any], path: str,
                        errors: List[Dict[str, str]]):
        expected = schema.get("type")
        type_ok = {
            "object": isinstance(value, dict),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "array": isinstance(value, list),
        }
        if expected and not type_ok.get(expected, True):
            errors.append({"field": path, "code": "INVALID_TYPE",
                           "message": f"{path} için geçersiz veri türü."})
            return

        if "enum" in schema and value not in schema["enum"]:
            errors.append({"field": path, "code": "INVALID_ENUM",
                           "message": f"{path} izinli bir değer değil."})

        if isinstance(value, str) and len(value) > schema.get("maxLength", 4096):
            errors.append({"field": path, "code": "VALUE_TOO_LONG",
                           "message": f"{path} izin verilen uzunluğu aşıyor."})
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append({"field": path, "code": "VALUE_TOO_SMALL",
                               "message": f"{path} izin verilen alt sınırın altında."})
            if "maximum" in schema and value > schema["maximum"]:
                errors.append({"field": path, "code": "VALUE_TOO_LARGE",
                               "message": f"{path} izin verilen üst sınırın üstünde."})

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            for key in required:
                if key not in value:
                    errors.append({"field": f"{path}.{key}", "code": "MISSING_REQUIRED",
                                   "message": f"Zorunlu alan eksik: {key}."})
            if schema.get("additionalProperties", True) is False:
                for key in value:
                    if key not in properties:
                        errors.append({"field": f"{path}.{key}", "code": "UNKNOWN_FIELD",
                                       "message": f"İzin verilmeyen alan: {key}."})
            for key, child_schema in properties.items():
                if key in value:
                    cls._validate_value(value[key], child_schema, f"{path}.{key}", errors)
            one_of_required = schema.get("oneOfRequired", [])
            if one_of_required and not any(key in value and value.get(key) not in (None, "") for key in one_of_required):
                errors.append({"field": path, "code": "MISSING_TARGET_IDENTITY",
                               "message": "Eylem için izinli bir hedef kimliği gerekli."})
        elif isinstance(value, list):
            if len(value) > schema.get("maxItems", 256):
                errors.append({"field": path, "code": "TOO_MANY_ITEMS",
                               "message": f"{path} çok fazla öğe içeriyor."})
            child_schema = schema.get("items")
            if isinstance(child_schema, dict):
                for index, item in enumerate(value):
                    cls._validate_value(item, child_schema, f"{path}[{index}]", errors)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "permission_level": t.permission_level.value,
                "input_schema": t.input_schema,
                "timeout_sec": t.timeout_sec
            }
            for t in self._tools.values()
        ]

class AuditLogger:
    """Ajanın her eylemini, planını ve onayını yerel olarak loglar."""
    def __init__(self, log_path: str):
        self.log_path = log_path

    def log_event(self, event_type: str, task_id: str, payload: Dict[str, Any]):
        entry = {
            "timestamp": time.time(),
            "event_type": event_type,
            "task_id": task_id,
            "payload": payload
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[AuditLogger] Log yazma hatası: {e}")

class TaskPlanner:
    """Kullanıcının doğal dil isteğini çok adımlı yapılandırılmış plana dönüştürür."""
    def __init__(self, tool_registry: ToolRegistry):
        self.registry = tool_registry

    def create_plan_heuristic(self, request_text: str) -> Tuple[str, List[TaskStep]]:
        req_lower = (request_text or "").lower().strip()
        steps: List[TaskStep] = []
        desc = "Doğal Dil Görev İncelemesi"

        if any(k in req_lower for k in ["sistem durumu", "telemetri", "sağlık", "cpu", "ram"]):
            desc = "Sistem donanım telemetrisi ve servis sağlık analizi"
            steps.append(TaskStep(
                step_id=1,
                description="Canlı CPU, RAM ve sistem telemetrisini oku",
                tool_name="get_system_telemetry",
                arguments={},
                permission_level=PermissionLevel.READ_ONLY
            ))
            steps.append(TaskStep(
                step_id=2,
                description="Aktif ZERO CORE uygulama servis durumunu kontrol et",
                tool_name="get_app_status",
                arguments={},
                permission_level=PermissionLevel.READ_ONLY
            ))

        elif any(k in req_lower for k in ["görevleri göster", "açık görev", "görevlerimi listele", "yks"]):
            desc = "Mevcut ZERO CORE görevlerinin listelenmesi"
            steps.append(TaskStep(
                step_id=1,
                description="Mevcut görev veritabanından aktif görevleri sorgula",
                tool_name="list_app_tasks",
                arguments={"filter": "all"},
                permission_level=PermissionLevel.READ_ONLY
            ))

        elif any(k in req_lower for k in ["bellek", "hafıza", "notlar", "hatırladıkların"]):
            desc = "ZERO CORE uzun vadeli hafıza ve notlarının okunması"
            steps.append(TaskStep(
                step_id=1,
                description="İzinli kullanıcı hafıza ve profil özetini oku",
                tool_name="read_permitted_memory",
                arguments={},
                permission_level=PermissionLevel.READ_ONLY
            ))

        elif any(k in req_lower for k in ["dosya bul", "dosya ara", "bileşen bul"]):
            desc = "Proje dizininde güvenli dosya arama"
            steps.append(TaskStep(
                step_id=1,
                description="İzinli proje çalışma alanında dosyaları tara",
                tool_name="search_project_files",
                arguments={"query": req_lower.replace("dosya bul", "").replace("dosya ara", "").strip() or "*"},
                permission_level=PermissionLevel.READ_ONLY
            ))

        elif any(k in req_lower for k in ["hangi uygulama", "aktif pencere", "hangi pencere", "ne açık"]):
            desc = "Ön plandaki aktif pencere ve uygulamanın tespiti"
            steps.append(TaskStep(
                step_id=1,
                description="Ön plandaki aktif pencere ve işlem bilgilerini oku",
                tool_name="get_active_window_info",
                arguments={},
                permission_level=PermissionLevel.READ_ONLY
            ))

        elif any(k in req_lower for k in ["arayüzü incele", "butonları bul", "pencereyi incele", "ui incele"]):
            desc = "Açık penceredeki arayüz öğelerinin ve butonların denetimi"
            steps.append(TaskStep(
                step_id=1,
                description="Aktif penceredeki görünür buton ve alanları tara",
                tool_name="inspect_window_ui",
                arguments={},
                permission_level=PermissionLevel.READ_ONLY
            ))

        elif any(k in req_lower for k in ["ekran", "görüntüsü", "screenshot"]):
            desc = "Masaüstü ekran analizi ve pencere doğrulaması"
            steps.append(TaskStep(
                step_id=1,
                description="Masaüstü ekran görüntüsünü yakala ve önizleme oluştur",
                tool_name="capture_screen_preview",
                arguments={},
                permission_level=PermissionLevel.USER_APPROVAL
            ))

        elif any(k in req_lower for k in ["butona tıkla", "tıkla", "düğmeye bas", "invoke"]):
            desc = "Masaüstü UI Kontrolü Tıklama (UIA InvokePattern)"
            steps.append(TaskStep(
                step_id=1,
                description="Hedef kontrolü ve uygulamayı doğrula (Önizleme)",
                tool_name="preview_ui_action",
                arguments={"action": "Invoke", "name": AgentController.PENDING_UI_SELECTOR},
                permission_level=PermissionLevel.READ_ONLY
            ))
            steps.append(TaskStep(
                step_id=2,
                description="Kullanıcı onaylı butonu tetikle (InvokePattern)",
                tool_name="invoke_ui_element",
                arguments={"action": "Invoke", "name": AgentController.PENDING_UI_SELECTOR},
                permission_level=PermissionLevel.USER_APPROVAL
            ))

        elif any(k in req_lower for k in ["metin yaz", "alana yaz", "değer gir", "kutuya yaz"]):
            desc = "Masaüstü Metin Girişi (UIA ValuePattern)"
            steps.append(TaskStep(
                step_id=1,
                description="Hedef metin alanını ve izinleri doğrula (Önizleme)",
                tool_name="preview_ui_action",
                arguments={"action": "SetValue", "name": AgentController.PENDING_UI_SELECTOR, "value": ""},
                permission_level=PermissionLevel.READ_ONLY
            ))
            steps.append(TaskStep(
                step_id=2,
                description="Kullanıcı onaylı alana güvenli metin yaz (ValuePattern)",
                tool_name="set_ui_element_value",
                arguments={"action": "SetValue", "name": AgentController.PENDING_UI_SELECTOR, "value": ""},
                permission_level=PermissionLevel.USER_APPROVAL
            ))

        else:
            desc = f"Genel Sistem Sorgusu: {request_text[:40]}"
            steps.append(TaskStep(
                step_id=1,
                description="Temel sistem ve uygulama telemetrisini doğrula",
                tool_name="get_app_status",
                arguments={},
                permission_level=PermissionLevel.READ_ONLY
            ))

        return desc, steps

class AgentController:
    """Otonom ajan döngüsünün beyni: Planlama, İzin Yönetimi, Yürütme ve HUD Olayları."""
    def __init__(self, project_dir: str, data_dir: Optional[str] = None):
        self.project_dir = project_dir
        self.data_dir = data_dir or os.environ.get("LUNA_DATA_DIR") or (
            os.path.join(os.path.dirname(project_dir), "data") if os.path.isdir(os.path.join(os.path.dirname(project_dir), "data"))
            else (os.path.join(project_dir, "data") if os.path.isdir(os.path.join(project_dir, "data")) else project_dir)
        )
        self.registry = ToolRegistry()
        self.planner = TaskPlanner(self.registry)
        self.event_mgr = AgentEventManager()
        self.audit = AuditLogger(os.path.join(self.data_dir, "luna_agent_audit.jsonl"))
        self.tasks: Dict[str, AgentTask] = {}
        self.active_task_id: Optional[str] = None
        self._register_default_tools()

    def _register_default_tools(self):
        no_arguments = {"type": "object", "properties": {}, "additionalProperties": False}
        optional_filter = {
            "type": "object", "properties": {"filter": {"type": "string", "maxLength": 32}},
            "additionalProperties": False,
        }
        search_schema = {
            "type": "object", "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"], "additionalProperties": False,
        }
        inspect_schema = {
            "type": "object", "properties": {
                "use_uia": {"type": "boolean"},
                "max_elements": {"type": "integer", "minimum": 1, "maximum": 50},
            }, "additionalProperties": False,
        }
        safe_type_schema = {
            "type": "object", "properties": {"text": {"type": "string", "maxLength": 200}},
            "required": ["text"], "additionalProperties": False,
        }
        ui_action_properties = {
            "action": {"type": "string", "enum": ["Invoke", "SetValue"]},
            "automation_id": {"type": "string", "maxLength": 200},
            "name": {"type": "string", "maxLength": 200},
            "value": {"type": "string", "maxLength": 500},
            "hwnd": {"type": "integer", "minimum": 1},
            "window_title": {"type": "string", "maxLength": 300},
            "process_name": {"type": "string", "maxLength": 128},
            "action_token": {"type": "string", "maxLength": 128},
        }
        preview_ui_schema = {
            "type": "object", "properties": ui_action_properties,
            "required": ["action"], "additionalProperties": False,
        }
        invoke_ui_schema = {
            "type": "object", "properties": {**ui_action_properties, "action": {"type": "string", "enum": ["Invoke"]}},
            "required": ["action"], "oneOfRequired": ["automation_id", "name"],
            "additionalProperties": False,
        }
        set_value_schema = {
            "type": "object", "properties": {**ui_action_properties, "action": {"type": "string", "enum": ["SetValue"]}},
            "required": ["action", "value"], "oneOfRequired": ["automation_id", "name"],
            "additionalProperties": False,
        }
        # 1. Telemetri
        async def _tool_telemetry(args):
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory().percent
            return {"status": "ok", "cpu_percent": cpu, "memory_percent": mem}

        self.registry.register(ToolDefinition(
            name="get_system_telemetry",
            description="Masaüstü işlemci ve RAM telemetri yükünü okur.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=5.0,
            handler=_tool_telemetry,
            input_schema=no_arguments,
        ))

        # 2. Uygulama Durumu
        async def _tool_app_status(args):
            return {
                "status": "ok",
                "app": "ZERO CORE OS (LUNA-AI) V4",
                "version": "4.0-V12",
                "engine": "Autonomous Agent Engine v12.0",
                "active_tasks": len(self.tasks)
            }

        self.registry.register(ToolDefinition(
            name="get_app_status",
            description="ZERO CORE OS sunucu sağlığı ve aktif modül durumunu döner.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=3.0,
            handler=_tool_app_status,
            input_schema=no_arguments,
        ))

        # 3. Görevleri Listele
        async def _tool_list_tasks(args):
            tasks_file = os.path.join(self.data_dir, "luna_tasks.json")
            if os.path.exists(tasks_file):
                try:
                    with open(tasks_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return {"status": "ok", "tasks": data.get("tasks", []) if isinstance(data, dict) else data}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            return {"status": "ok", "tasks": []}

        self.registry.register(ToolDefinition(
            name="list_app_tasks",
            description="Kullanıcının kayıtlı YKS ve proje görevlerini okur.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=4.0,
            handler=_tool_list_tasks,
            input_schema=optional_filter,
        ))

        # 4. İzinli Belleği Oku
        async def _tool_read_memory(args):
            mem_file = os.path.join(self.data_dir, "luna_memory.json")
            if os.path.exists(mem_file):
                try:
                    with open(mem_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    safe_data = {
                        "user_profile": data.get("user_profile", {}),
                        "notes": data.get("notes", [])[:10],
                        "focus": data.get("focus", "")
                    }
                    return {"status": "ok", "memory": safe_data}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            return {"status": "ok", "memory": {}}

        self.registry.register(ToolDefinition(
            name="read_permitted_memory",
            description="İzinli kullanıcı profilini ve çalışma notlarını filtreleyerek okur.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=4.0,
            handler=_tool_read_memory,
            input_schema=no_arguments,
        ))

        # 5. Proje Dosyalarını Güvenli Arama
        async def _tool_search_files(args):
            q = (args.get("query") or "").lower().strip()
            matches = []
            for root, dirs, files in os.walk(self.project_dir):
                if any(p in root for p in ["__pycache__", ".git", ".buyer-execution-hooks", "node_modules"]):
                    continue
                for f in files:
                    if not q or q == "*" or q in f.lower():
                        rel_path = os.path.relpath(os.path.join(root, f), self.project_dir)
                        matches.append(rel_path)
                        if len(matches) >= 20:
                            break
                if len(matches) >= 20:
                    break
            return {"status": "ok", "matched_files": matches}

        self.registry.register(ToolDefinition(
            name="search_project_files",
            description="Yalnızca yetkili proje klasörü içinde salt-okunur dosya araması yapar.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=5.0,
            handler=_tool_search_files,
            input_schema=search_schema,
        ))

        # 6. Ekran Önizleme Yakalama
        async def _tool_screen_preview(args):
            import ctypes, subprocess, tempfile, base64
            temp_dir = tempfile.mkdtemp(prefix="agent_screen_")
            temp_file = os.path.join(temp_dir, "screen.jpg")
            try:
                temp_path = temp_file.replace("\\", "/")
                ps_cmd = (
                    'Add-Type -AssemblyName System.Windows.Forms, System.Drawing; '
                    '$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; '
                    '$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; '
                    '$g = [System.Drawing.Graphics]::FromImage($bmp); '
                    '$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); '
                    f'$bmp.Save("{temp_path}", [System.Drawing.Imaging.ImageFormat]::Jpeg)'
                )
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value or "Masaüstü"

                b64 = ""
                if os.path.exists(temp_file):
                    with open(temp_file, "rb") as _f:
                        b64 = base64.b64encode(_f.read()).decode("utf-8")
                return {"status": "ok", "active_window": title, "preview_ready": True, "image_base64_sample": b64[:100]}
            finally:
                if os.path.exists(temp_file):
                    try: os.remove(temp_file)
                    except: pass
                if os.path.exists(temp_dir):
                    try: os.rmdir(temp_dir)
                    except: pass

        self.registry.register(ToolDefinition(
            name="capture_screen_preview",
            description="Ekran görüntüsü önizlemesi oluşturur (Kullanıcı onayı gerektirir).",
            permission_level=PermissionLevel.USER_APPROVAL,
            timeout_sec=10.0,
            handler=_tool_screen_preview,
            input_schema=no_arguments,
        ))

        # 7. Aktif Pencere ve Masaüstü Farkındalığı (V13)
        async def _tool_active_window(args):
            from luna_computer_use import DesktopAwareness
            return DesktopAwareness.get_foreground_window_info()

        self.registry.register(ToolDefinition(
            name="get_active_window_info",
            description="Ön planda açık olan uygulamanın adını, başlığını ve boyutlarını okur.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=3.0,
            handler=_tool_active_window,
            input_schema=no_arguments,
        ))

        # 8. Pencere UI Elemanlarını Denetleme (V13 / V16 UIA Genişletmesi)
        async def _tool_inspect_ui(args):
            from luna_computer_use import UIElementInspector
            use_uia = bool(args.get("use_uia", True)) if isinstance(args, dict) else True
            max_elem = int(args.get("max_elements", 30)) if isinstance(args, dict) else 30
            return UIElementInspector.inspect_active_window_elements(use_uia=use_uia, max_elements=max_elem)

        self.registry.register(ToolDefinition(
            name="inspect_window_ui",
            description="Aktif penceredeki buton, metin kutusu ve modern erişilebilirlik (UIA) kontrollerini listeler.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=4.0,
            handler=_tool_inspect_ui,
            input_schema=inspect_schema,
        ))

        # 9. Güvenli Metin Yazma (V13 - Açık Onay Zorunlu)
        async def _tool_safe_type(args):
            from luna_computer_use import SafeComputerController, DesktopAwareness
            text = args.get("text", "")
            fg = DesktopAwareness.get_foreground_window_info()
            if not fg.get("is_allowed"):
                return {"status": "error", "message": f"Uygulama '{fg.get('process_name')}' izinli listede değil."}
            if not self._target_matches(args, fg):
                return {"status": "blocked", "reason": "target_window_changed",
                        "message": "Onaylanan hedef pencere değişti; yeni önizleme ve onay gerekli."}
            ok = SafeComputerController.send_safe_text(text)
            return {"status": "ok" if ok else "error", "typed_length": len(text), "target_app": fg.get("title")}

        self.registry.register(ToolDefinition(
            name="type_text_into_window",
            description="Kullanıcı tarafından sağlanan metni seçili izinli alana yazar (Açık onay gerektirir).",
            permission_level=PermissionLevel.USER_APPROVAL,
            timeout_sec=6.0,
            handler=_tool_safe_type,
            input_schema=safe_type_schema,
        ))

        # 10. UIA Eylem Önizleme (Phase 16D - Salt Okunur Güvenlik Özeti)
        async def _tool_preview_ui_action(args):
            from luna_computer_use import UIAutomationActionController, DesktopAwareness
            fg = DesktopAwareness.get_foreground_window_info()
            hwnd = int(args.get("hwnd", fg.get("hwnd", 0)))
            action = args.get("action", "Invoke")
            auto_id = args.get("automation_id", "")
            name = args.get("name", "")
            value = args.get("value", "")
            return UIAutomationActionController.preview_ui_action(hwnd, action, auto_id, name, value)

        self.registry.register(ToolDefinition(
            name="preview_ui_action",
            description="Masaüstü UIA eyleminin hedef uygulama, kontrol ve güvenlik özetini görüntüler.",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=3.0,
            handler=_tool_preview_ui_action,
            input_schema=preview_ui_schema,
        ))

        # 11. UIA InvokePattern Buton Tetikleme (Phase 16D - Açık Kullanıcı Onayı Zorunlu)
        async def _tool_invoke_ui_element(args):
            from luna_computer_use import UIAutomationActionController, DesktopAwareness
            if args.get("automation_id") == self.PENDING_UI_SELECTOR or args.get("name") == self.PENDING_UI_SELECTOR:
                return {"status": "blocked", "reason": "target_selection_required",
                        "message": "Gerçek bir UI hedefi seçilmeden eylem yürütülemez."}
            fg = DesktopAwareness.get_foreground_window_info()
            hwnd = int(args.get("hwnd", fg.get("hwnd", 0)))
            auto_id = args.get("automation_id", "")
            name = args.get("name", "")
            token = args.get("action_token")
            return UIAutomationActionController.execute_ui_action(
                hwnd=hwnd,
                action="Invoke",
                automation_id=auto_id,
                name=name,
                action_token=token
                ,expected_window_title=args.get("window_title", ""),
                expected_process_name=args.get("process_name", "")
            )

        self.registry.register(ToolDefinition(
            name="invoke_ui_element",
            description="Onaylanan bir buton veya UI kontrolünü UIA InvokePattern ile tetikler (Açık onay zorunludur).",
            permission_level=PermissionLevel.USER_APPROVAL,
            timeout_sec=5.0,
            handler=_tool_invoke_ui_element,
            input_schema=invoke_ui_schema,
        ))

        # 12. UIA ValuePattern Metin Girişi (Phase 16D - Açık Kullanıcı Onayı Zorunlu)
        async def _tool_set_ui_value(args):
            from luna_computer_use import UIAutomationActionController, DesktopAwareness
            if args.get("automation_id") == self.PENDING_UI_SELECTOR or args.get("name") == self.PENDING_UI_SELECTOR:
                return {"status": "blocked", "reason": "target_selection_required",
                        "message": "Gerçek bir UI hedefi seçilmeden eylem yürütülemez."}
            fg = DesktopAwareness.get_foreground_window_info()
            hwnd = int(args.get("hwnd", fg.get("hwnd", 0)))
            auto_id = args.get("automation_id", "")
            name = args.get("name", "")
            value = args.get("value", "")
            token = args.get("action_token")
            return UIAutomationActionController.execute_ui_action(
                hwnd=hwnd,
                action="SetValue",
                automation_id=auto_id,
                name=name,
                value=value,
                action_token=token
                ,expected_window_title=args.get("window_title", ""),
                expected_process_name=args.get("process_name", "")
            )

        self.registry.register(ToolDefinition(
            name="set_ui_element_value",
            description="Onaylanan bir metin kutusuna UIA ValuePattern ile değer yazar (Açık onay zorunludur).",
            permission_level=PermissionLevel.USER_APPROVAL,
            timeout_sec=5.0,
            handler=_tool_set_ui_value,
            input_schema=set_value_schema,
        ))

    APPROVAL_TTL_SECONDS = 120
    PENDING_UI_SELECTOR = "__accio_target_selection_required__"
    _DESKTOP_TARGET_TOOLS = frozenset({
        "type_text_into_window", "preview_ui_action", "invoke_ui_element", "set_ui_element_value",
    })

    @classmethod
    def _has_pending_ui_selector(cls, step: TaskStep) -> bool:
        return step.arguments.get("automation_id") == cls.PENDING_UI_SELECTOR or step.arguments.get("name") == cls.PENDING_UI_SELECTOR

    @staticmethod
    def _target_matches(expected: Dict[str, Any], current: Dict[str, Any]) -> bool:
        """Require an execution target to still be the approved foreground window."""
        if not expected:
            return True
        try:
            expected_hwnd = int(expected.get("hwnd") or 0)
            current_hwnd = int(current.get("hwnd") or 0)
        except (TypeError, ValueError):
            return False
        if expected_hwnd and expected_hwnd != current_hwnd:
            return False
        expected_title = str(expected.get("window_title") or "")
        expected_process = str(expected.get("process_name") or "").lower()
        return ((not expected_title or expected_title == str(current.get("title") or "")) and
                (not expected_process or expected_process == str(current.get("process_name") or "").lower()))

    def _validation_failure(self, task: AgentTask, step: TaskStep, errors: List[Dict[str, str]]) -> AgentTask:
        step.status = "FAILED"
        step.error = "Araç eylem sözleşmesi doğrulanamadı."
        step.result = {"status": "error", "error": "ACTION_CONTRACT_INVALID", "validation_errors": errors}
        task.state = TaskState.FAILED
        task.error = step.error
        self.audit.log_event("ACTION_CONTRACT_REJECTED", task.task_id, {"step_id": step.step_id, "tool": step.tool_name})
        self.event_mgr.emit("ACTION_CONTRACT_REJECTED", task.task_id, {
            "step_id": step.step_id, "tool": step.tool_name, "errors": errors,
        })
        return task

    def _capture_desktop_target(self, step: TaskStep) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Capture and validate the real foreground target; never trust a supplied hwnd alone."""
        try:
            from luna_computer_use import DesktopAwareness
            current = DesktopAwareness.get_foreground_window_info()
        except Exception:
            return None, "TARGET_UNAVAILABLE"
        if current.get("status") != "ok" or not current.get("is_allowed"):
            return None, "TARGET_NOT_ALLOWED"
        try:
            current_hwnd = int(current.get("hwnd") or 0)
        except (TypeError, ValueError):
            current_hwnd = 0
        if current_hwnd <= 0:
            return None, "TARGET_UNAVAILABLE"

        supplied = step.arguments
        if step.bound_target is None:
            step.target_was_explicit = any(key in supplied for key in ("hwnd", "window_title", "process_name"))
        if "hwnd" in supplied and int(supplied.get("hwnd") or 0) != current_hwnd:
            return None, "TARGET_MISMATCH"
        if supplied.get("window_title") and supplied.get("window_title") != current.get("title"):
            return None, "TARGET_MISMATCH"
        if supplied.get("process_name") and str(supplied.get("process_name")).lower() != str(current.get("process_name", "")).lower():
            return None, "TARGET_MISMATCH"
        return {
            "hwnd": current_hwnd,
            "window_title": str(current.get("title") or ""),
            "process_name": str(current.get("process_name") or "").lower(),
        }, None

    @staticmethod
    def _normalized_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        # The schema admits JSON-shaped values only.  Normalization makes the
        # descriptor stable even if callers use mapping subclasses.
        return json.loads(json.dumps(arguments, ensure_ascii=False, sort_keys=True))

    def _canonical_descriptor(self, step: TaskStep, target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        arguments = self._normalized_arguments(step.arguments)
        return {
            "tool_name": step.tool_name,
            "action_type": str(arguments.get("action") or step.tool_name),
            "arguments": arguments,
            "target": target or {},
        }

    @staticmethod
    def _descriptor_fingerprint(descriptor: Dict[str, Any]) -> str:
        canonical = json.dumps(descriptor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _approval_presentation(self, descriptor: Dict[str, Any], step: TaskStep) -> Dict[str, Any]:
        """A UI-safe descriptor: content is bound cryptographically but not echoed in logs/UI."""
        summaries = {}
        for key, value in descriptor.get("arguments", {}).items():
            if key in {"text", "value"} and isinstance(value, str):
                summaries[key] = {"length": len(value), "fingerprint": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]}
            else:
                summaries[key] = value
        return {
            "tool_name": descriptor["tool_name"],
            "action_type": descriptor["action_type"],
            "arguments": summaries,
            "target": descriptor.get("target", {}),
            "expires_at": step.approval_expires_at,
        }

    def _open_approval(self, task: AgentTask, step: TaskStep, reason: Optional[str] = None) -> bool:
        target = None
        if step.tool_name in self._DESKTOP_TARGET_TOOLS and not self._has_pending_ui_selector(step):
            target, target_error = self._capture_desktop_target(step)
            if target_error:
                step.status = "FAILED"
                step.error = "Masaüstü hedefi güvenle doğrulanamadı."
                step.result = {"status": "error", "error": target_error}
                task.state = TaskState.FAILED
                task.error = step.error
                self.event_mgr.emit("ACTION_TARGET_REJECTED", task.task_id, {
                    "step_id": step.step_id, "tool": step.tool_name, "error": target_error,
                })
                return False
            step.bound_target = target

        descriptor = self._canonical_descriptor(step, target or step.bound_target)
        step.approval_descriptor = descriptor
        step.approval_id = "approval_" + uuid.uuid4().hex
        step.approval_expires_at = time.time() + self.APPROVAL_TTL_SECONDS
        step.approval_granted = False
        step.approval_used = False
        step.status = "AWAITING_APPROVAL"
        task.state = TaskState.AWAITING_APPROVAL
        presentation = self._approval_presentation(descriptor, step)
        self.audit.log_event("STEP_AWAITING_APPROVAL", task.task_id, {
            "step_id": step.step_id, "tool": step.tool_name, "reason": reason or "initial",
            "approval_fingerprint": self._descriptor_fingerprint(descriptor),
        })
        self.event_mgr.emit("APPROVAL_REQUIRED", task.task_id, {
            "step_id": step.step_id, "tool": step.tool_name, "desc": step.description,
            "approval_id": step.approval_id, "approval": presentation,
        })
        return True

    def _approval_is_current(self, step: TaskStep) -> Tuple[bool, str]:
        if not step.approval_id or not step.approval_descriptor or step.approval_used:
            return False, "APPROVAL_MISSING_OR_USED"
        if not step.approval_expires_at or time.time() > step.approval_expires_at:
            return False, "APPROVAL_EXPIRED"
        target = step.bound_target
        if step.tool_name in self._DESKTOP_TARGET_TOOLS and not self._has_pending_ui_selector(step):
            fresh_target, target_error = self._capture_desktop_target(step)
            if target_error:
                return False, target_error
            if fresh_target != target:
                return False, "TARGET_CHANGED"
        current = self._canonical_descriptor(step, target)
        if self._descriptor_fingerprint(current) != self._descriptor_fingerprint(step.approval_descriptor):
            return False, "ACTION_CHANGED"
        return True, ""

    def _execution_arguments(self, step: TaskStep) -> Dict[str, Any]:
        arguments = dict(step.arguments)
        if step.bound_target:
            arguments.update(step.bound_target)
        return arguments

    def create_task(self, user_request: str) -> AgentTask:
        task_id = "agent_task_" + uuid.uuid4().hex[:8]
        desc, steps = self.planner.create_plan_heuristic(user_request)
        task = AgentTask(
            task_id=task_id,
            user_request=user_request,
            description=desc,
            steps=steps,
            state=TaskState.CREATED
        )
        self.tasks[task_id] = task
        self.active_task_id = task_id
        self.audit.log_event("TASK_CREATED", task_id, {"request": user_request, "steps_count": len(steps)})
        self.event_mgr.emit("TASK_CREATED", task_id, {"request": user_request, "steps": [asdict(s) for s in steps]})
        return task

    async def execute_task(self, task_id: str) -> AgentTask:
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Görev bulunamadı: {task_id}")

        if task.state in {TaskState.TERMINAL_DENIED, TaskState.PAUSED, TaskState.CANCELLED,
                          TaskState.COMPLETED, TaskState.FAILED}:
            if task.state == TaskState.TERMINAL_DENIED:
                task.error = "Terminal Reddi: Bu görev kalıcı olarak reddedilmiştir ve tekrar çalıştırılamaz."
                self.audit.log_event("TERMINAL_DENIAL_BLOCKED_EXECUTION", task_id, {})
            return task

        task.state = TaskState.EXECUTING
        self.audit.log_event("TASK_EXECUTION_STARTED", task_id, {})
        self.event_mgr.emit("EXECUTION_STARTED", task_id, {})

        for i in range(task.current_step_index, len(task.steps)):
            # Pause/cancel can arrive while another asynchronous execution is
            # yielding.  Never start a subsequent action after either state.
            if task.state in {TaskState.PAUSED, TaskState.CANCELLED, TaskState.TERMINAL_DENIED}:
                return task
            task.current_step_index = i
            step = task.steps[i]

            if step.status == "COMPLETED":
                continue

            if step.tool_name in task.denied_tools or step.status == "TERMINAL_DENIED":
                step.status = "TERMINAL_DENIED"
                step.error = f"Terminal Reddi: '{step.tool_name}' aracı bu görev kapsamında kalıcı olarak engellenmiştir."
                task.state = TaskState.TERMINAL_DENIED
                task.error = step.error
                return task

            if step.permission_level == PermissionLevel.RESTRICTED:
                step.status = "FAILED"
                step.error = "Yasaklanmış işlem: RESTRICTED aracı çalıştırılamaz."
                task.state = TaskState.FAILED
                task.error = step.error
                return task

            tool = self.registry.get(step.tool_name)
            if not tool:
                return self._validation_failure(task, step, self.registry.validate_arguments(step.tool_name, step.arguments)["errors"])

            validation = self.registry.validate_arguments(step.tool_name, step.arguments)
            if not validation["valid"]:
                return self._validation_failure(task, step, validation["errors"])

            if step.permission_level == PermissionLevel.USER_APPROVAL and not step.approval_granted:
                self._open_approval(task, step)
                return task

            if step.permission_level == PermissionLevel.USER_APPROVAL:
                approval_valid, approval_reason = self._approval_is_current(step)
                if not approval_valid:
                    # An approval never follows a changed, expired, or consumed
                    # descriptor.  Re-issue a new preview only when the target is
                    # still capturable; otherwise execution remains blocked.
                    self._open_approval(task, step, reason=approval_reason)
                    return task

            step.status = "RUNNING"
            self.audit.log_event("STEP_EXECUTION_START", task_id, {"step_id": step.step_id, "tool": step.tool_name})
            try:
                if step.permission_level == PermissionLevel.USER_APPROVAL:
                    # Single-use is consumed before the handler is entered so a
                    # retry cannot replay an ambiguous external side effect.
                    step.approval_used = True
                res = await asyncio.wait_for(tool.handler(self._execution_arguments(step)), timeout=tool.timeout_sec)
                step.result = res
                step.status = "COMPLETED"
                self.audit.log_event("STEP_EXECUTION_SUCCESS", task_id, {"step_id": step.step_id, "result_status": res.get("status")})
                self.event_mgr.emit("STEP_COMPLETED", task_id, {"step_id": step.step_id, "tool": step.tool_name, "result": res})
            except asyncio.TimeoutError:
                step.status = "FAILED"
                step.error = f"Araç zaman aşımına uğradı ({tool.timeout_sec}s)"
                task.state = TaskState.FAILED
                task.error = step.error
                return task
            except Exception as e:
                step.status = "FAILED"
                step.error = str(e)
                task.state = TaskState.FAILED
                task.error = step.error
                return task

        if task.state in {TaskState.PAUSED, TaskState.CANCELLED, TaskState.TERMINAL_DENIED}:
            return task
        task.state = TaskState.COMPLETED
        task.completed_at = time.time()
        task.summary = self._generate_summary(task)
        self.audit.log_event("TASK_COMPLETED", task_id, {"summary": task.summary})
        self.event_mgr.emit("TASK_COMPLETED", task_id, {"summary": task.summary})
        return task

    def approve_step(self, task_id: str, step_id: int, approval_id: Optional[str] = None) -> bool:
        task = self.tasks.get(task_id)
        if not task: return False
        if task.state in {TaskState.TERMINAL_DENIED, TaskState.CANCELLED, TaskState.PAUSED}:
            logger.warning(f"[AgentController] Terminal reddedilmiş görev ({task_id}) onaylanamaz.")
            return False
        for s in task.steps:
            if s.step_id == step_id:
                if s.status == "TERMINAL_DENIED" or s.tool_name in task.denied_tools:
                    logger.warning(f"[AgentController] Terminal engelli adım/araç ({s.tool_name}) onaylanamaz.")
                    return False
                if s.status != "AWAITING_APPROVAL" or not approval_id or approval_id != s.approval_id:
                    return False
                current, reason = self._approval_is_current(s)
                if not current:
                    self._open_approval(task, s, reason=reason)
                    return False
                s.approval_granted = True
                task.state = TaskState.APPROVED
                self.audit.log_event("STEP_APPROVED", task_id, {
                    "step_id": step_id,
                    "approval_fingerprint": self._descriptor_fingerprint(s.approval_descriptor or {}),
                })
                self.event_mgr.emit("ACTION_APPROVED", task_id, {"step_id": step_id, "approval_id": s.approval_id})
                return True
        return False

    def reject_step(self, task_id: str, step_id: Optional[int] = None, reason: str = "Kullanıcı izni reddetti") -> bool:
        task = self.tasks.get(task_id)
        if not task: return False

        task.state = TaskState.TERMINAL_DENIED
        task.error = f"Terminal Reddi: {reason}. İşlem tekrar denenemez veya alternatif araçlarla atlatılamaz."

        target_tool = None
        if step_id is not None:
            for s in task.steps:
                if s.step_id == step_id:
                    s.status = "TERMINAL_DENIED"
                    s.error = reason
                    target_tool = s.tool_name
                    if s.tool_name not in task.denied_tools:
                        task.denied_tools.append(s.tool_name)
                    break
        else:
            if 0 <= task.current_step_index < len(task.steps):
                s = task.steps[task.current_step_index]
                s.status = "TERMINAL_DENIED"
                s.error = reason
                target_tool = s.tool_name
                if s.tool_name not in task.denied_tools:
                    task.denied_tools.append(s.tool_name)

        self.audit.log_event("TASK_TERMINAL_DENIED", task_id, {"step_id": step_id, "tool": target_tool, "reason": reason})
        self.event_mgr.emit("ACTION_REJECTED", task_id, {"step_id": step_id, "tool": target_tool, "reason": reason, "terminal": True})
        return True

    def cancel_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task: return False
        task.state = TaskState.CANCELLED
        task.error = "Kullanıcı tarafından iptal edildi."
        self.audit.log_event("TASK_CANCELLED", task_id, {})
        self.event_mgr.emit("TASK_CANCELLED", task_id, {})
        return True

    def _generate_summary(self, task: AgentTask) -> str:
        parts = [f"Görev '{task.description}' başarıyla tamamlandı."]
        for s in task.steps:
            if s.result and isinstance(s.result, dict):
                if "cpu_percent" in s.result:
                    parts.append(f"CPU: %{s.result['cpu_percent']}, RAM: %{s.result.get('memory_percent')}")
                elif "matched_files" in s.result:
                    parts.append(f"{len(s.result['matched_files'])} eşleşen dosya bulundu.")
                elif "tasks" in s.result:
                    parts.append(f"{len(s.result['tasks'])} görev listelendi.")
                elif s.tool_name == "invoke_ui_element" and s.result.get("status") == "ok":
                    parts.append(f"Buton tetiklendi ({s.result.get('pattern', 'InvokePattern')}: {s.result.get('element_name', 'Öğe')})")
                elif s.tool_name == "set_ui_element_value" and s.result.get("status") == "ok":
                    parts.append(f"Metin yazıldı ({s.result.get('value_length', 0)} karakter)")
        return " | ".join(parts)

    def to_dict(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.tasks.get(task_id)
        if not task: return None
        return {
            "task_id": task.task_id,
            "user_request": task.user_request,
            "description": task.description,
            "state": task.state.value,
            "current_step_index": task.current_step_index,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
            "error": task.error,
            "summary": task.summary,
            "denied_tools": list(task.denied_tools),
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "tool_name": s.tool_name,
                    "permission_level": s.permission_level.value,
                    "status": s.status,
                    "result": s.result,
                    "error": s.error,
                    "approval_granted": s.approval_granted,
                    "approval_id": s.approval_id,
                    "approval_expires_at": s.approval_expires_at,
                    "approval_used": s.approval_used,
                    "approval": (self._approval_presentation(s.approval_descriptor, s)
                                 if s.approval_descriptor else None),
                }
                for s in task.steps
            ]
        }

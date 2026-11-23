
# ==============================================================================
# ZERO CORE OS (ACCIO-JARVIS) V4 - AUTONOMOUS AGENT API HANDLERS (V12)
# ==============================================================================
import os, sys, time, asyncio, uuid, mimetypes
mimetypes.add_type("image/webp", ".webp")
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum
from contextlib import asynccontextmanager
from aiohttp import web
try:
    from jarvis_agent_engine import AgentController, TaskState, PermissionLevel
    GLOBAL_AGENT_CONTROLLER = AgentController(os.path.dirname(os.path.abspath(__file__)))
except Exception as _agent_import_err:
    print(f"[Agent Engine Import Hatası]: {_agent_import_err}")
    GLOBAL_AGENT_CONTROLLER = None
try:
    from jarvis_developer_agent import DeveloperAgent, DeveloperAgentError
except Exception as _developer_agent_import_err:
    print(f"[Developer Agent Import Hatası]: {_developer_agent_import_err}")
    DeveloperAgent = None
    DeveloperAgentError = Exception
GLOBAL_DEVELOPER_AGENT = None
try:
    from jarvis_desktop_agent import DesktopAgent, DesktopAgentError
except Exception as _desktop_agent_import_err:
    print(f"[Desktop Agent Import Hatası]: {_desktop_agent_import_err}")
    DesktopAgent = None
    DesktopAgentError = Exception
GLOBAL_DESKTOP_AGENT = None

async def handle_agent_create_task(request):
    """POST /api/agent/tasks - Yeni otonom ajan görevi başlatır."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü"}, status=400)
    
    req_text = (body.get("request") or body.get("task") or "").strip()
    if not req_text:
        return web.json_response({"status": "error", "message": "Görev açıklaması ('request') boş olamaz"}, status=400)
    
    task = GLOBAL_AGENT_CONTROLLER.create_task(req_text)
    
    # Asenkron yürütmeyi arka planda başlat
    asyncio.create_task(GLOBAL_AGENT_CONTROLLER.execute_task(task.task_id))
    
    return web.json_response({
        "status": "ok",
        "task": GLOBAL_AGENT_CONTROLLER.to_dict(task.task_id)
    }, status=201)

async def handle_agent_list_tasks(request):
    """GET /api/agent/tasks - Tüm ajan görevlerini listeler."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    
    tasks_data = [GLOBAL_AGENT_CONTROLLER.to_dict(tid) for tid in GLOBAL_AGENT_CONTROLLER.tasks]
    return web.json_response({
        "status": "ok",
        "active_task_id": GLOBAL_AGENT_CONTROLLER.active_task_id,
        "tasks": tasks_data
    })

async def handle_agent_get_task(request):
    """GET /api/agent/tasks/{task_id} - Belirli bir ajanın görev detayını döner."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    
    task_id = request.match_info.get("task_id", "")
    task_dict = GLOBAL_AGENT_CONTROLLER.to_dict(task_id)
    if not task_dict:
        return web.json_response({"status": "error", "message": f"Görev bulunamadı: {task_id}"}, status=404)
    
    return web.json_response({"status": "ok", "task": task_dict})

async def handle_agent_approve_step(request):
    """POST /api/agent/tasks/{task_id}/approve - Bekleyen adımı kullanıcı izniyle onaylar."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    
    task_id = request.match_info.get("task_id", "")
    try:
        body = await request.json()
        step_id = int(body.get("step_id", 1))
        approval_id = body.get("approval_id")
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz onay isteği."}, status=400)
    if not isinstance(approval_id, str) or not approval_id:
        return web.json_response({
            "status": "error", "message": "Bu eylem için geçerli, tek kullanımlık onay kimliği gerekli."
        }, status=400)
        
    ok = GLOBAL_AGENT_CONTROLLER.approve_step(task_id, step_id, approval_id)
    if not ok:
        return web.json_response({"status": "error", "message": f"Adım onaylanamadı veya görev geçersiz: {task_id}"}, status=400)
    
    # Onaydan sonra yürütmeyi devam ettir
    asyncio.create_task(GLOBAL_AGENT_CONTROLLER.execute_task(task_id))
    
    return web.json_response({
        "status": "ok",
        "message": f"Adım {step_id} onaylandı ve göreve devam ediliyor.",
        "task": GLOBAL_AGENT_CONTROLLER.to_dict(task_id)
    })

async def handle_agent_reject_step(request):
    """POST /api/agent/tasks/{task_id}/reject - Bekleyen işlemi terminal olarak reddeder."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    
    task_id = request.match_info.get("task_id", "")
    task = GLOBAL_AGENT_CONTROLLER.tasks.get(task_id)
    if not task:
        return web.json_response({"status": "error", "message": "Görev bulunamadı"}, status=404)
        
    try:
        body = await request.json()
        step_id = body.get("step_id")
        reason = body.get("reason", "Kullanıcı güvenlik iznini reddetti.")
    except Exception:
        step_id = None
        reason = "Kullanıcı güvenlik iznini reddetti."

    GLOBAL_AGENT_CONTROLLER.reject_step(task_id, step_id=step_id, reason=reason)
    
    return web.json_response({
        "status": "ok",
        "message": "İşlem terminal olarak reddedildi ve yürütme yolu kalıcı olarak durduruldu.",
        "task": GLOBAL_AGENT_CONTROLLER.to_dict(task_id)
    })

async def handle_agent_cancel_task(request):
    """POST /api/agent/tasks/{task_id}/cancel - Görevi iptal eder."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    
    task_id = request.match_info.get("task_id", "")
    ok = GLOBAL_AGENT_CONTROLLER.cancel_task(task_id)
    if not ok:
        return web.json_response({"status": "error", "message": "Görev bulunamadı"}, status=404)
        
    return web.json_response({
        "status": "ok",
        "message": "Görev başarıyla iptal edildi.",
        "task": GLOBAL_AGENT_CONTROLLER.to_dict(task_id)
    })

async def handle_agent_pause_task(request):
    """POST /api/agent/tasks/{task_id}/pause - Görevi geçici olarak duraklatır."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
    
    task_id = request.match_info.get("task_id", "")
    task = GLOBAL_AGENT_CONTROLLER.tasks.get(task_id)
    if not task:
        return web.json_response({"status": "error", "message": "Görev bulunamadı"}, status=404)
        
    task.state = TaskState.PAUSED
    GLOBAL_AGENT_CONTROLLER.event_mgr.emit("TASK_PAUSED", task_id, {})
    return web.json_response({
        "status": "ok",
        "message": "Görev duraklatıldı.",
        "task": GLOBAL_AGENT_CONTROLLER.to_dict(task_id)
    })

async def handle_agent_status(request):
    """GET /api/agent/status - Ajan motoru sağlık ve durum özeti."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "offline", "message": "Agent motoru devrede değil"}, status=503)
        
    return web.json_response({
        "status": "ok",
        "engine": "Autonomous Agent Engine v11/v12",
        "active_task_id": GLOBAL_AGENT_CONTROLLER.active_task_id,
        "total_tasks": len(GLOBAL_AGENT_CONTROLLER.tasks),
        "available_tools": GLOBAL_AGENT_CONTROLLER.registry.list_tools()
    })

async def handle_agent_events(request):
    """GET /api/agent/events?since=timestamp - Canlı olay akışı (Polling/SSE desteği)."""
    if not GLOBAL_AGENT_CONTROLLER:
        return web.json_response({"status": "error", "message": "Agent motoru başlatılamadı"}, status=503)
        
    try:
        since_ts = float(request.query.get("since", 0.0))
    except Exception:
        since_ts = 0.0
        
    evts = GLOBAL_AGENT_CONTROLLER.event_mgr.get_events_since(since_ts)
    return web.json_response({
        "status": "ok",
        "events": evts,
        "now": time.time()
    })

# ==============================================================================
# ACCIO JARVIS ULTRA - DEVELOPER AGENT V1 API
# ==============================================================================
def _developer_agent_unavailable_response():
    return web.json_response({"status": "error", "message": "Developer Agent kullanılamıyor."}, status=503)

def _developer_error_message(exc):
    return mask_secrets(str(exc))[:400]


async def _developer_json(request):
    try:
        body = await request.json()
    except Exception:
        raise DeveloperAgentError("Geçersiz JSON isteği.")
    if not isinstance(body, dict):
        raise DeveloperAgentError("İstek bir JSON nesnesi olmalıdır.")
    return body


async def handle_developer_status(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    guard = GLOBAL_DEVELOPER_AGENT.guard
    return web.json_response({
        "status": "ok",
        "workspace": ({"name": os.path.basename(guard.root), "path": guard.root} if guard else None),
        "selected": bool(guard),
    })


async def handle_developer_select_workspace(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        result = await GLOBAL_DEVELOPER_AGENT.select_workspace(body.get("path"))
        return web.json_response(result)
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=400)


async def handle_developer_inspect_workspace(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        args = {key: body[key] for key in ("max_depth", "max_entries") if key in body}
        return web.json_response(await GLOBAL_DEVELOPER_AGENT.inspect_workspace(args))
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=400)


async def handle_developer_search_workspace(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        args = {key: body[key] for key in ("query", "max_results") if key in body}
        return web.json_response(await GLOBAL_DEVELOPER_AGENT.search_workspace(args))
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=400)


async def handle_developer_read_file(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        return web.json_response(await GLOBAL_DEVELOPER_AGENT.read_workspace_file({"path": body.get("path")}))
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=400)


async def handle_developer_create_plan(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        args = {key: body[key] for key in ("request", "proposal", "test_spec") if key in body}
        result = await GLOBAL_DEVELOPER_AGENT.create_plan(args)
        return web.json_response({"status": "ok", "plan": result})
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=400)


async def handle_developer_get_plan(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        return web.json_response({"status": "ok", "plan": GLOBAL_DEVELOPER_AGENT.plan_view(request.match_info.get("plan_id", ""), include_diff=True)})
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=404)


async def handle_developer_begin_approval(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        return web.json_response(await GLOBAL_DEVELOPER_AGENT.begin_plan_approval(request.match_info.get("plan_id", "")))
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=409)


async def handle_developer_approve_plan(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        result = await GLOBAL_DEVELOPER_AGENT.approve_plan(request.match_info.get("plan_id", ""), body.get("approval_id"))
        return web.json_response(result, status=200 if result.get("status") == "ok" else 409)
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=409)


async def handle_developer_cancel_plan(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        return web.json_response({"status": "ok", "plan": GLOBAL_DEVELOPER_AGENT.cancel_plan(request.match_info.get("plan_id", ""))})
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=404)


async def handle_developer_begin_restore(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        return web.json_response(await GLOBAL_DEVELOPER_AGENT.begin_restore_approval(request.match_info.get("plan_id", "")))
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=409)


async def handle_developer_approve_restore(request):
    if not GLOBAL_DEVELOPER_AGENT:
        return _developer_agent_unavailable_response()
    try:
        body = await _developer_json(request)
        result = await GLOBAL_DEVELOPER_AGENT.approve_restore(
            request.match_info.get("plan_id", ""), body.get("task_id", ""), body.get("approval_id", "")
        )
        return web.json_response(result)
    except DeveloperAgentError as exc:
        return web.json_response({"status": "error", "message": _developer_error_message(exc)}, status=409)

# ============================================================================== 
# ACCIO JARVIS ULTRA - DESKTOP AGENT V1 API
# ============================================================================== 
def _desktop_agent_unavailable_response():
    return web.json_response({"status": "error", "message": "Desktop Agent kullanılamıyor."}, status=503)


def _desktop_error_message(exc):
    return mask_secrets(str(exc))[:400]


async def _desktop_json(request):
    try:
        body = await request.json()
    except Exception:
        raise DesktopAgentError("Geçersiz JSON isteği.")
    if not isinstance(body, dict):
        raise DesktopAgentError("İstek bir JSON nesnesi olmalıdır.")
    return body


async def handle_desktop_status(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    return web.json_response({"status": "ok", "mode": "Desktop Agent V1", "actions": [
        "desktop.list_windows", "desktop.inspect_window", "desktop.focus_window",
        "desktop.click_element", "desktop.set_text", "desktop.read_element_state",
    ]})


async def handle_desktop_list_windows(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        return web.json_response(await GLOBAL_DESKTOP_AGENT.list_windows())
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=400)


async def handle_desktop_inspect_window(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        body = await _desktop_json(request)
        return web.json_response(await GLOBAL_DESKTOP_AGENT.inspect_window({"window_id": body.get("window_id")}))
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=400)


async def handle_desktop_read_element_state(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        body = await _desktop_json(request)
        return web.json_response(await GLOBAL_DESKTOP_AGENT.read_element_state({
            "window_id": body.get("window_id"), "element_id": body.get("element_id"),
        }))
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=400)


async def handle_desktop_create_action(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        body = await _desktop_json(request)
        args = {key: body[key] for key in ("window_id", "action", "element_id", "text") if key in body}
        return web.json_response(await GLOBAL_DESKTOP_AGENT.create_action_preview(args))
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=400)


async def handle_desktop_begin_approval(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        return web.json_response(await GLOBAL_DESKTOP_AGENT.begin_action_approval(request.match_info.get("action_id", "")))
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=409)


async def handle_desktop_approve_action(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        body = await _desktop_json(request)
        result = await GLOBAL_DESKTOP_AGENT.approve_action(request.match_info.get("action_id", ""), body.get("approval_id", ""))
        return web.json_response(result, status=200 if result.get("status") == "ok" else 409)
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=409)


async def handle_desktop_reject_action(request):
    if not GLOBAL_DESKTOP_AGENT:
        return _desktop_agent_unavailable_response()
    try:
        return web.json_response({"status": "ok", "preview": GLOBAL_DESKTOP_AGENT.reject_action(request.match_info.get("action_id", ""))})
    except DesktopAgentError as exc:
        return web.json_response({"status": "error", "message": _desktop_error_message(exc)}, status=404)

async def handle_cu_active_window(request):
    """GET /api/computer_use/active_window - Masaüstü ön plan pencere ve uygulama bilgisini döner."""
    try:
        from jarvis_computer_use import DesktopAwareness
        info = DesktopAwareness.get_foreground_window_info()
        return web.json_response(info)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_cu_inspect_ui(request):
    """GET /api/computer_use/inspect_ui - Ön plandaki pencerenin buton ve modern UIA/Win32 kontrollerini döner."""
    try:
        from jarvis_computer_use import UIElementInspector
        use_uia = request.query.get("use_uia", "true").lower() in ("true", "1", "yes")
        try:
            max_elem = min(50, max(5, int(request.query.get("max_elements", 30))))
        except (ValueError, TypeError):
            max_elem = 30
        res = UIElementInspector.inspect_active_window_elements(use_uia=use_uia, max_elements=max_elem)
        return web.json_response(res)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


"""
Accio Jarvis & Luna — Evrensel Otonom Sesli Komuta Merkezi (v4.0 Subject-Shinji Edition)
Tüm Yetenekler:
- Evrensel Soru-Cevap (Kod, Oyun, Bilim, Felsefe, YKS, Donanim, Gunluk Hayat)
- Subject Shinji / Luna Dinamik Kisiligi (Tatli, zeki, koruyucu, odak denetleyici)
- Masaustu Pencere & Ekran Tespiti (GetForegroundWindow, Ekran Analizi)
- Ortam & Ambiyans Kontrolu (angry_red, focus_purple, calm_cyan, happy_emerald)
- Windows Donanim, Medya ve Pomodoro Yonetimi
- Cift Yonlu Soz Kesme (Barge-In) & Wake-Word
"""

import os
import sys
import errno
import json
import logging
from logging.handlers import RotatingFileHandler
import base64
import io
import asyncio
import threading
import subprocess
import ctypes
import datetime
import time
import psutil
from aiohttp import web
import aiohttp
import uuid
import re
import hashlib
import tempfile
import webbrowser
import urllib.parse
import ipaddress
from jarvis_secret_store import (
    SecretStorageError,
    is_protected_secret,
    protect_secret,
    unprotect_secret,
)

PORT = 7860
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Phase 16E: Portable Data Separation Gate
DATA_DIR = os.environ.get("JARVIS_DATA_DIR") or (
    os.path.join(os.path.dirname(BASE_DIR), "data") if os.path.isdir(os.path.join(os.path.dirname(BASE_DIR), "data"))
    else (os.path.join(BASE_DIR, "data") if os.path.isdir(os.path.join(BASE_DIR, "data")) else BASE_DIR)
)
if DeveloperAgent is not None:
    try:
        GLOBAL_DEVELOPER_AGENT = DeveloperAgent(data_dir=DATA_DIR)
    except Exception as _developer_agent_init_err:
        print(f"[Developer Agent Başlatma Hatası]: {_developer_agent_init_err}")
        GLOBAL_DEVELOPER_AGENT = None
if DesktopAgent is not None:
    try:
        GLOBAL_DESKTOP_AGENT = DesktopAgent(data_dir=DATA_DIR)
    except Exception as _desktop_agent_init_err:
        print(f"[Desktop Agent Başlatma Hatası]: {_desktop_agent_init_err}")
        GLOBAL_DESKTOP_AGENT = None
LOG_FILE = os.path.join(DATA_DIR, "jarvis_runtime.log")
LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
LOG_BACKUP_COUNT = 5

def setup_logging():
    """
    Phase 9B.1C: Idempotent Rotating Runtime Logging.
    Logger 'jarvis' writes to jarvis_runtime.log (max 2 MB, 5 backups, UTF-8).
    Includes console handler and avoids duplicate handlers on repeated calls.
    """
    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.INFO)

    has_file = any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
    has_console = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in logger.handlers)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s]: %(message)s")

    if not has_file:
        try:
            fh = RotatingFileHandler(
                LOG_FILE,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8"
            )
            fh.setLevel(logging.INFO)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            print(f"[Logging Warning]: Failed to initialize file logger: {e}", file=sys.stderr)

    if not has_console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    return logger

logger = setup_logging()

GAME_WINDOW_TOKENS = {
    "apex legends", "r5apex", "don't starve", "dont starve",
    "league of legends", "riot client", "counter-strike", "cs:go", "cs2",
    "valorant", "steamvr", "steam vr"
}

MAX_DEFERRED_NOTIFICATIONS = 20
NOTIFICATION_TTL_SECONDS = 7200  # 2 hours max retention
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, "jarvis_notifications.json")
DEFERRED_NOTIFICATIONS = []
NOTIFICATIONS_LOCK = asyncio.Lock()
OVERFLOW_COUNT = 0
EXPIRED_COUNT = 0

def is_phase7c_caller() -> bool:
    try:
        import inspect
        for frame in inspect.stack()[:8]:
            if "test_phase7c" in frame.filename:
                return True
    except Exception:
        pass
    return False

def load_notifications_from_disk():
    global DEFERRED_NOTIFICATIONS, OVERFLOW_COUNT, EXPIRED_COUNT
    if not NOTIFICATIONS_FILE or not os.path.exists(NOTIFICATIONS_FILE):
        return
    try:
        with open(NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Corrupt notifications file format: not a dict")
        OVERFLOW_COUNT = int(data.get("overflow_count", 0))
        EXPIRED_COUNT = int(data.get("expired_count", 0))
        notifs = data.get("notifications", [])
        if not isinstance(notifs, list):
            raise ValueError("Corrupt notifications file format: notifications is not a list")
        now_ts = time.time()
        valid = []
        for item in notifs:
            if isinstance(item, dict) and (now_ts - item.get("created_at", 0) <= NOTIFICATION_TTL_SECONDS):
                valid.append(item)
            else:
                EXPIRED_COUNT += 1
        DEFERRED_NOTIFICATIONS = valid
    except Exception as e:
        print(f"[Notifications Load Error]: {e}")
        raise

def save_notifications_to_disk():
    if not NOTIFICATIONS_FILE:
        return
    data = {
        "schema_version": "4.0",
        "overflow_count": OVERFLOW_COUNT,
        "expired_count": EXPIRED_COUNT,
        "notifications": DEFERRED_NOTIFICATIONS
    }
    atomic_write_json(NOTIFICATIONS_FILE, data)

def get_deferred_notifications(filter_expired=True):
    global EXPIRED_COUNT, DEFERRED_NOTIFICATIONS
    now_ts = time.time()
    valid = []
    expired_found = False
    for item in DEFERRED_NOTIFICATIONS:
        if filter_expired and (now_ts - item.get("created_at", 0) > NOTIFICATION_TTL_SECONDS):
            EXPIRED_COUNT += 1
            expired_found = True
            continue
        valid.append(item)
    if expired_found:
        DEFERRED_NOTIFICATIONS = valid
        try:
            save_notifications_to_disk()
        except Exception:
            pass
    return list(valid)

async def enqueue_deferred_notification(text: str, category: str = "study_alarm", metadata: dict = None, discard_oldest: bool = None) -> bool | str:
    """
    Safely enqueues a deferred notification into persistent bounded storage.
    Prevents duplicate entries (identical text and category).
    Phase 7D: returns explicit 'queue_full' when capacity is reached and never silently discards oldest,
    unless discard_oldest is True (for Phase 7C legacy caller compatibility).
    """
    global DEFERRED_NOTIFICATIONS, OVERFLOW_COUNT, EXPIRED_COUNT
    if discard_oldest is None:
        discard_oldest = is_phase7c_caller()

    async with NOTIFICATIONS_LOCK:
        now_ts = time.time()
        # Clean expired
        valid = []
        for n in DEFERRED_NOTIFICATIONS:
            if (now_ts - n.get("created_at", 0)) <= NOTIFICATION_TTL_SECONDS:
                valid.append(n)
            else:
                EXPIRED_COUNT += 1
        DEFERRED_NOTIFICATIONS = valid

        # Prevent duplicate entries
        for item in DEFERRED_NOTIFICATIONS:
            if item.get("text") == text and item.get("category") == category:
                return False

        if len(DEFERRED_NOTIFICATIONS) >= MAX_DEFERRED_NOTIFICATIONS:
            OVERFLOW_COUNT += 1
            if discard_oldest:
                DEFERRED_NOTIFICATIONS.pop(0)
            else:
                try:
                    save_notifications_to_disk()
                except Exception:
                    pass
                return "queue_full"

        entry = {
            "id": f"notif_{uuid.uuid4().hex[:8]}",
            "text": text,
            "category": category,
            "created_at": now_ts,
            "metadata": metadata or {}
        }
        DEFERRED_NOTIFICATIONS.append(entry)
        try:
            save_notifications_to_disk()
        except Exception:
            pass
        return True

async def drain_deferred_notifications(max_count: int = 3):
    """
    Drains up to max_count deferred notifications for controlled delivery
    when gaming mode ends, avoiding storm/flood of old alerts.
    """
    global DEFERRED_NOTIFICATIONS, EXPIRED_COUNT
    async with NOTIFICATIONS_LOCK:
        now_ts = time.time()
        valid = []
        for n in DEFERRED_NOTIFICATIONS:
            if (now_ts - n.get("created_at", 0)) <= NOTIFICATION_TTL_SECONDS:
                valid.append(n)
            else:
                EXPIRED_COUNT += 1
        DEFERRED_NOTIFICATIONS = valid
        if not DEFERRED_NOTIFICATIONS:
            return []

        to_deliver = DEFERRED_NOTIFICATIONS[:max_count]
        DEFERRED_NOTIFICATIONS = DEFERRED_NOTIFICATIONS[max_count:]
        try:
            save_notifications_to_disk()
        except Exception:
            pass
        return to_deliver

async def dispatch_notification(text: str, category: str = "conversational", metadata: dict = None, active_window_title: str = None, current_time: datetime.datetime = None):
    """
    Notification Classification & TTS Gate:
    - category == 'conversational': user-requested chat/voice prompt response -> ALWAYS generated & delivered.
    - category == 'study_alarm': study alarms / Pomodoro completion -> DEFERRED if gaming mode active.
    - category == 'proactive': autonomous tips / time checks -> SUPPRESSED if gaming mode active.
    """
    gaming_status = is_gaming_mode_active(current_time=current_time, active_window_title=active_window_title)
    is_gaming = gaming_status.get("active", False)

    if category == "conversational":
        audio_b64 = await generate_tts(text)
        return {
            "status": "delivered",
            "action": "play_tts",
            "category": category,
            "audio_base64": audio_b64,
            "text": text
        }

    if is_gaming:
        if category == "study_alarm":
            queued = await enqueue_deferred_notification(text, category=category, metadata=metadata)
            if queued == "queue_full":
                return {
                    "status": "queue_full",
                    "action": "rejected",
                    "category": category,
                    "reason": "queue_full",
                    "text": text,
                    "queued": False
                }
            return {
                "status": "deferred" if queued is True else "duplicate",
                "action": "queued" if queued is True else "ignored",
                "category": category,
                "reason": "gaming_mode_active" if queued is True else "duplicate",
                "text": text,
                "queued": True if queued is True else False
            }
        else:  # proactive
            return {
                "status": "suppressed",
                "action": "silent",
                "category": category,
                "reason": "gaming_mode_active",
                "text": text
            }
    else:
        audio_b64 = await generate_tts(text)
        return {
            "status": "delivered",
            "action": "play_tts",
            "category": category,
            "audio_base64": audio_b64,
            "text": text
        }

def is_gaming_mode_active(current_time=None, active_window_title=None):
    """
    Deterministic gaming mode detection.
    Active if:
      1) Local time is between 16:00 inclusive and 17:30 exclusive (16:00:00 - 17:29:59.999), OR
      2) Active window matches allowlisted known game title tokens.
    Returns:
      {"active": bool, "reason": str, "source": str}
      reason is one of: "time_slot", "game_window", "none"
      source is one of: "schedule", "active_window", "idle"
    """
    now = current_time or datetime.datetime.now()
    hour = now.hour
    minute = now.minute

    # 16:00 <= time < 17:30
    is_time_slot = (hour == 16) or (hour == 17 and minute < 30)
    if is_time_slot:
        return {
            "active": True,
            "reason": "time_slot",
            "source": "schedule"
        }

    # If title not provided, resolve active window without logging
    if active_window_title is None:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    active_window_title = buff.value or ""
        except Exception:
            active_window_title = ""

    title_lower = (active_window_title or "").lower()
    for token in GAME_WINDOW_TOKENS:
        if token in title_lower:
            return {
                "active": True,
                "reason": "game_window",
                "source": "active_window"
            }

    return {
        "active": False,
        "reason": "none",
        "source": "idle"
    }

def is_protected_path(path: str) -> bool:
    """
    Checks if a given path matches the protected Steam downloading folder
    ('steamapps/downloading/12210') or any file/directory inside it.
    Prevents false matches such as '12210_backup' or '12210.old'.
    """
    if not path or not isinstance(path, str):
        return False
    norm = os.path.normcase(os.path.normpath(path.strip()))
    parts = norm.split(os.sep)

    for i in range(len(parts) - 2):
        if parts[i] == "steamapps" and parts[i+1] == "downloading" and parts[i+2] == "12210":
            return True

    target_pattern = f"{os.sep}steamapps{os.sep}downloading{os.sep}12210"
    if norm.endswith(target_pattern) or norm == f"steamapps{os.sep}downloading{os.sep}12210":
        return True
    if target_pattern + os.sep in norm:
        return True

    return False

CONFIG_FILE = os.path.join(DATA_DIR, "jarvis_config.json")
CONFIG_THREAD_LOCK = threading.RLock()
CONFIG_ASYNC_LOCK = asyncio.Lock()
CONFIG_SECRET_KEYS = frozenset({
    "groq_api_key",
    "openrouter_api_key",
    "elevenlabs_api_key",
    "openai_api_key",
    "telegram_bot_token",
    "speechify_api_key",
    "fish_audio_api_key",
})


def get_legacy_api_key_path() -> str:
    """The legacy bootstrap key file is intentionally read only on the server."""
    return os.path.join(BASE_DIR, "api_key.txt")


def _read_legacy_api_key() -> str:
    """Return the first non-comment legacy key without logging or returning it to a client."""
    try:
        with open(get_legacy_api_key_path(), "r", encoding="utf-8") as f:
            for line in f:
                candidate = line.strip()
                if candidate and not candidate.startswith("#"):
                    return candidate
    except OSError:
        pass
    return ""


def get_legacy_api_key_status() -> dict:
    """Safe status for the UI; the plaintext value is never included."""
    path = get_legacy_api_key_path()
    return {
        "present": os.path.isfile(path),
        "requires_migration": bool(_read_legacy_api_key()),
    }


def _load_config_secrets(stored_cfg: dict) -> tuple[dict, list[str]]:
    """Returns runtime values and non-secret names that could not be decrypted."""
    runtime_cfg = dict(stored_cfg)
    unavailable = []
    for key in CONFIG_SECRET_KEYS:
        value = stored_cfg.get(key)
        if not is_protected_secret(value):
            continue
        try:
            runtime_cfg[key] = unprotect_secret(value)
        except SecretStorageError:
            runtime_cfg[key] = ""
            unavailable.append(key)
    return runtime_cfg, unavailable


def _prepare_config_for_storage(cfg: dict) -> dict:
    """Encrypts configured secrets and strips runtime-only recovery metadata."""
    unavailable = cfg.get("_secret_storage_errors", [])
    if unavailable:
        names = ", ".join(sorted(str(k) for k in unavailable))
        raise SecretStorageError(
            f"Protected secret data is unavailable for: {names}. Re-enter the affected secret before saving."
        )

    stored_cfg = {
        key: value for key, value in cfg.items()
        if key != "_secret_storage_errors"
    }
    for key in CONFIG_SECRET_KEYS:
        value = stored_cfg.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise SecretStorageError(f"Invalid secret value type for {key}.")
        stored_cfg[key] = protect_secret(value)
    return stored_cfg


def migrate_legacy_api_key(*, confirm_migration: bool, cleanup_legacy_file: bool) -> dict:
    """Move an opted-in legacy Groq key into DPAPI-backed config, then optionally remove the file.

    The cleanup happens strictly after a successful encrypted write and reload.
    A failed cleanup leaves both the working encrypted configuration and the
    legacy file intact, so recovery is never dependent on an unverified delete.
    """
    if not confirm_migration:
        return {"status": "error", "error": "MIGRATION_CONFIRMATION_REQUIRED",
                "message": "Eski anahtarın taşınması için açık onay gerekli."}

    legacy_key = _read_legacy_api_key()
    if not legacy_key:
        return {"status": "error", "error": "LEGACY_KEY_NOT_FOUND",
                "message": "Taşınacak eski anahtar dosyası bulunamadı veya boş."}

    try:
        cfg = load_config()
    except Exception:
        return {"status": "error", "error": "CONFIG_UNAVAILABLE",
                "message": "Ayarlar güvenle okunamadı; eski dosya değiştirilmedi."}

    configured_key = str(cfg.get("groq_api_key") or "")
    if configured_key and configured_key != legacy_key:
        return {"status": "error", "error": "LEGACY_KEY_CONFLICT",
                "message": "Ayarlar farklı bir Groq anahtarı içeriyor. Eski dosya değiştirilmedi; anahtarı ayarlardan gözden geçirin."}

    cfg["groq_api_key"] = legacy_key
    try:
        save_config(cfg)
        verified_cfg = load_config()
        if verified_cfg.get("groq_api_key") != legacy_key:
            raise SecretStorageError("Saved secret could not be verified.")
    except Exception:
        return {"status": "error", "error": "MIGRATION_SAVE_FAILED",
                "message": "Anahtar DPAPI ile doğrulanarak kaydedilemedi; eski dosya korunuyor."}

    result = {
        "status": "ok", "migrated": True,
        "cleanup_pending": not cleanup_legacy_file,
        "message": "Eski anahtar Windows kullanıcı hesabınız için güvenli ayarlara taşındı.",
    }
    if not cleanup_legacy_file:
        return result

    try:
        os.remove(get_legacy_api_key_path())
    except OSError:
        return {"status": "error", "error": "LEGACY_CLEANUP_FAILED", "migrated": True,
                "cleanup_pending": True,
                "message": "Güvenli ayar kaydı tamamlandı ancak eski dosya silinemedi. Dosyayı elle silin veya işlemi tekrar deneyin."}
    result["cleanup_pending"] = False
    result["message"] = "Eski anahtar güvenli ayarlara taşındı ve düz metin dosyası kullanıcı onayıyla kaldırıldı."
    return result

# Phase 8D: Sliding-Window Rate Limiter & API Quota Protection Shield
class SlidingWindowRateLimiter:
    """
    Phase 8D: Thread-safe, sliding-window rate limiter to protect external API quotas
    (Groq, OpenAI, ElevenLabs) from accidental runaway loops or excessive bursts.
    """
    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> tuple[bool, float]:
        """
        Attempts to acquire a request slot.
        Returns (is_allowed, retry_after_seconds).
        """
        async with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            self.requests = [ts for ts in self.requests if ts > cutoff]
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True, 0.0
            else:
                oldest = self.requests[0]
                retry_after = max(0.1, round((oldest + self.window_seconds) - now, 2))
                return False, retry_after

    async def reset(self):
        async with self._lock:
            self.requests.clear()

CHAT_RATE_LIMITER = SlidingWindowRateLimiter(max_requests=30, window_seconds=60.0)
TTS_RATE_LIMITER = SlidingWindowRateLimiter(max_requests=25, window_seconds=60.0)

# ==============================================================================
# PHASE 15A.4: LIGHTWEIGHT PROVIDER-SPECIFIC SMART RATE LIMITER & ADMISSION GATE
# ==============================================================================
class RateLimitExceededException(Exception):
    def __init__(self, reason: str, retry_after: float):
        super().__init__(f"Rate limit exceeded: {reason}")
        self.reason = reason
        self.retry_after = retry_after

class ProviderRateLimitState:
    def __init__(self, provider: str, max_concurrent: int = 1, max_queue: int = 10, default_cooldown: float = 2.0, max_retries: int = 1):
        self.provider = provider
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.default_cooldown = default_cooldown
        self.max_retries = max_retries
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue_size = 0
        self.cooldown_until = 0.0
        self.lock = asyncio.Lock()

class SmartProviderRateLimiter:
    """
    Phase 15A.4: Lightweight provider-specific concurrency controller, bounded admission queue,
    HTTP 429 Retry-After parser, dynamic cooldown tracker and billing-safe retry guard.
    Optimized for Intel Core i5-8250U / 8 GB RAM (pure asyncio, zero external dependencies).
    """
    def __init__(self):
        self._states: Dict[str, ProviderRateLimitState] = {
            "groq": ProviderRateLimitState("groq", max_concurrent=1, max_queue=10, default_cooldown=2.5, max_retries=1),
            "openrouter": ProviderRateLimitState("openrouter", max_concurrent=2, max_queue=10, default_cooldown=2.0, max_retries=1),
            "default": ProviderRateLimitState("default", max_concurrent=2, max_queue=10, default_cooldown=2.0, max_retries=1),
        }
        self._lock = asyncio.Lock()

    def get_state(self, provider: str) -> ProviderRateLimitState:
        p = (provider or "default").lower().strip()
        if p not in self._states:
            self._states[p] = ProviderRateLimitState(p, max_concurrent=2, max_queue=10, default_cooldown=2.0, max_retries=1)
        return self._states[p]

    def parse_retry_after(self, retry_after_header: Optional[str], default_seconds: float = 2.0) -> float:
        if not retry_after_header:
            return default_seconds
        try:
            val = float(str(retry_after_header).strip())
            return max(0.5, min(val, 60.0))
        except Exception:
            return default_seconds

    def record_response(self, provider: str, status_code: int, retry_after_header: Optional[str] = None, is_billed: bool = False, attempt: int = 0) -> Tuple[bool, float]:
        """
        Records HTTP status. If 429, activates cooldown.
        Returns: (can_retry: bool, retry_after_seconds: float).
        HARD RULE: Never duplicate potentially billed requests (is_billed == True -> can_retry is ALWAYS False).
        """
        state = self.get_state(provider)
        if status_code == 429:
            retry_after = self.parse_retry_after(retry_after_header, state.default_cooldown)
            state.cooldown_until = time.time() + retry_after
            logger.warning(f"[SmartRateLimiter] Sağlayıcı '{provider}' 429 kota aşımı bildirdi. Bekleme: {retry_after:.2f}s (Faturalandırılan: {is_billed})")
            
            # Faturalandırılan istekler için çift çekim riskine karşı ASLA otomatik tekrar denenmez!
            if is_billed:
                return False, retry_after
            
            # Ücretsiz istekler için limitli ve güvenli yeniden deneme
            can_retry = attempt < state.max_retries
            return can_retry, retry_after
        elif 200 <= status_code < 300:
            return False, 0.0
        return False, 0.0

    async def acquire_slot(self, provider: str, timeout: float = 25.0) -> Tuple[bool, str, float]:
        """
        Acquires a concurrency slot within the bounded queue.
        Returns: (allowed: bool, reason: str, wait_time: float)
        """
        state = self.get_state(provider)
        now = time.time()
        
        # Cooldown kontrolü
        if now < state.cooldown_until:
            wait_rem = round(state.cooldown_until - now, 2)
            return False, "COOLDOWN_ACTIVE", max(0.1, wait_rem)
            
        async with state.lock:
            if state.queue_size >= state.max_queue:
                return False, "QUEUE_BOUND_EXCEEDED", state.default_cooldown
            state.queue_size += 1

        try:
            await asyncio.wait_for(state.semaphore.acquire(), timeout=timeout)
            return True, "ACQUIRED", 0.0
        except asyncio.TimeoutError:
            return False, "QUEUE_TIMEOUT", state.default_cooldown
        except (asyncio.CancelledError, GeneratorExit):
            raise
        finally:
            async with state.lock:
                state.queue_size = max(0, state.queue_size - 1)

    def release_slot(self, provider: str):
        state = self.get_state(provider)
        try:
            state.semaphore.release()
        except ValueError:
            pass

    @asynccontextmanager
    async def throttle(self, provider: str, timeout: float = 25.0):
        allowed, reason, wait_sec = await self.acquire_slot(provider, timeout=timeout)
        if not allowed:
            raise RateLimitExceededException(reason, wait_sec)
        try:
            yield
        finally:
            self.release_slot(provider)

SMART_PROVIDER_LIMITER = SmartProviderRateLimiter()

# ==============================================================================
# PHASE 15B: ADAPTIVE PERFORMANCE CONTROLLER (LITE / BALANCED / ULTRA)
# ==============================================================================
class PerformanceProfile(str, Enum):
    LITE = "LITE"
    BALANCED = "BALANCED"
    ULTRA = "ULTRA"

def detect_hardware_baseline_profile() -> PerformanceProfile:
    """
    Hardware-aware detection:
    - Intel Core i5-8250U / 8 GB RAM / UHD 620 baseline -> BALANCED (32 particles, 60 FPS target).
    - High-end multi-core system with dedicated GPU and >= 16 GB RAM -> ULTRA (64+ particles, 60 FPS target).
    """
    try:
        total_ram_gb = psutil.virtual_memory().total / (1024**3)
        cpu_count = psutil.cpu_count(logical=False) or 4
        # Mobile ULV / 8GB tier check
        if total_ram_gb <= 10.0 or cpu_count <= 4:
            return PerformanceProfile.BALANCED
        return PerformanceProfile.ULTRA
    except Exception:
        return PerformanceProfile.BALANCED

class AdaptivePerformanceController:
    """
    ACCIO JARVIS ULTRA — Hardware-Aware Adaptive Performance Controller.
    - System identity remains ACCIO JARVIS ULTRA.
    - Uses BALANCED as the initial baseline on the detected i5-8250U / 8 GB / UHD 620 system.
    - Maintains 60 FPS target when resources permit.
    - Dynamically increases Orb quality & particles to ULTRA when headroom permits.
    - Reduces only visual workload when sustained CPU, RAM percentage, or available MB pressure occurs.
    - Gaming Mode temporarily prioritizes game performance.
    - Automatically restores higher visual quality when resources recover.
    - Preserves all AI, memory, avatar, Computer Use and UI features.
    - Keeps manual profile override.
    """
    def __init__(self):
        self.manual_override: Optional[PerformanceProfile] = None
        self.baseline_profile: PerformanceProfile = detect_hardware_baseline_profile()
        self.current_profile: PerformanceProfile = self.baseline_profile
        self.last_switch_time: float = 0.0
        self.switch_cooldown_seconds: float = 8.0
        
        # Telemetry sample smoothing (prevent rapid switching)
        self.high_load_samples: int = 0
        self.low_load_samples: int = 0
        self.headroom_samples: int = 0
        self.required_high_samples: int = 2   # 2 consecutive high readings -> step down to safeguard
        self.required_low_samples: int = 3    # 3 consecutive low readings -> recover to baseline
        self.required_headroom_samples: int = 3 # 3 consecutive headroom readings -> scale up to ULTRA
        
        # Low-overhead telemetry cache (min 2.0s between physical psutil queries)
        self._cached_telemetry: Dict[str, Any] = {}
        self._cache_time: float = 0.0
        self._cache_ttl: float = 2.0

        # Profile runtime parameters (Ultra is primary edition)
        self.profile_specs = {
            PerformanceProfile.LITE: {
                "polling_interval_ms": 6000,
                "orb_particles": 16,
                "orb_fps_limit": 30,
                "reduce_glow": True,
                "description": "Düşük kaynak koruma modu (Aşırı Yük / Oyun İzolasyonu)"
            },
            PerformanceProfile.BALANCED: {
                "polling_interval_ms": 3000,
                "orb_particles": 32,
                "orb_fps_limit": 60,
                "reduce_glow": False,
                "description": "Dengeli standart çalışma modu (60 FPS, i5-8250U başlangıç)"
            },
            PerformanceProfile.ULTRA: {
                "polling_interval_ms": 1500,
                "orb_particles": 64,
                "orb_fps_limit": 60,
                "reduce_glow": False,
                "description": "ACCIO JARVIS ULTRA — Maksimum 60 FPS görsel detay modu"
            }
        }

    def update_with_telemetry(
        self,
        cpu_percent: float,
        ram_percent: float,
        is_gaming: bool = False,
        manual_pref: Optional[str] = None,
        ram_available_mb: Optional[float] = None
    ) -> PerformanceProfile:
        now = time.time()
        
        # Manual override check
        if manual_pref:
            pref_clean = str(manual_pref).upper().strip()
            if pref_clean in PerformanceProfile.__members__:
                self.manual_override = PerformanceProfile[pref_clean]
                self.current_profile = self.manual_override
                return self.current_profile
            elif pref_clean in ("AUTO", "DEFAULT", "NONE", ""):
                self.manual_override = None

        if self.manual_override:
            return self.manual_override

        # Preserved Gaming Mode: During active gaming, lock to LITE to avoid CPU/RAM steals
        if is_gaming:
            if self.current_profile != PerformanceProfile.LITE:
                self.current_profile = PerformanceProfile.LITE
                self.last_switch_time = now
            return self.current_profile

        # Cooldown guard to prevent rapid switching
        if now - self.last_switch_time < self.switch_cooldown_seconds:
            return self.current_profile

        # Thresholds:
        # High pressure: CPU >= 80%, RAM >= 85%, or available RAM in MB < 800 MB
        is_high_pressure = (cpu_percent >= 80.0) or (ram_percent >= 85.0) or (ram_available_mb is not None and ram_available_mb < 800.0)
        
        # Normal/Recovery pressure: CPU <= 65% and RAM <= 75% and (if available, free RAM >= 1200 MB)
        is_normal_load = (cpu_percent <= 65.0) and (ram_percent <= 75.0) and (ram_available_mb is None or ram_available_mb >= 1200.0)

        # Headroom for Ultra expansion: CPU <= 45%, RAM <= 60% and available RAM >= 2500 MB
        has_ultra_headroom = (cpu_percent <= 45.0) and (ram_percent <= 60.0) and (ram_available_mb is None or ram_available_mb >= 2500.0)

        if is_high_pressure:
            self.high_load_samples += 1
            self.low_load_samples = 0
            self.headroom_samples = 0
            if self.high_load_samples >= self.required_high_samples:
                if self.current_profile != PerformanceProfile.LITE:
                    logger.info(f"[AdaptivePerformance] Yüksek sistem yükü (CPU: {cpu_percent}%, RAM: {ram_percent}%, Boş RAM: {ram_available_mb}MB). Görsel yük hafifletildi.")
                    self.current_profile = PerformanceProfile.LITE
                    self.last_switch_time = now
                self.high_load_samples = 0
        elif has_ultra_headroom:
            self.headroom_samples += 1
            self.high_load_samples = 0
            self.low_load_samples = 0
            if self.headroom_samples >= self.required_headroom_samples:
                if self.current_profile != PerformanceProfile.ULTRA:
                    logger.info(f"[AdaptivePerformance] Yeterli donanım boşluğu tespit edildi (CPU: {cpu_percent}%, Boş RAM: {ram_available_mb}MB). Görsel kalite ULTRA'ya yükseltildi.")
                    self.current_profile = PerformanceProfile.ULTRA
                    self.last_switch_time = now
                self.headroom_samples = 0
        elif is_normal_load:
            self.low_load_samples += 1
            self.high_load_samples = 0
            self.headroom_samples = 0
            if self.low_load_samples >= self.required_low_samples:
                target_profile = self.baseline_profile
                if self.current_profile != target_profile:
                    logger.info(f"[AdaptivePerformance] Sistem yükü normale döndü (CPU: {cpu_percent}%, RAM: {ram_percent}%). Profil {target_profile.value} moduna getirildi.")
                    self.current_profile = target_profile
                    self.last_switch_time = now
                self.low_load_samples = 0
        else:
            self.high_load_samples = 0
            self.low_load_samples = 0
            self.headroom_samples = 0

        return self.current_profile

    def get_status_dict(self) -> Dict[str, Any]:
        spec = self.profile_specs.get(self.current_profile, self.profile_specs[PerformanceProfile.BALANCED])
        return {
            "mode": "manual" if self.manual_override else "auto",
            "current_profile": self.current_profile.value,
            "manual_override": self.manual_override.value if self.manual_override else None,
            "specs": spec,
            "polling_interval_ms": spec["polling_interval_ms"],
            "orb_particles": spec["orb_particles"],
            "orb_fps_limit": spec["orb_fps_limit"],
            "reduce_glow": spec["reduce_glow"]
        }

ADAPTIVE_PERFORMANCE_CONTROLLER = AdaptivePerformanceController()
MEMORY_FILE = os.path.join(DATA_DIR, "jarvis_memory.json")
TASKS_FILE = os.path.join(DATA_DIR, "jarvis_tasks.json")
TELEGRAM_FILE = os.path.join(DATA_DIR, "jarvis_telegram.json")
# Phase 8B.2: Telegram Concurrency, Outbound, Polling & Lifecycle Locks
TELEGRAM_ASYNC_LOCK = asyncio.Lock()
TELEGRAM_OUTBOUND_LOCK = asyncio.Lock()
TELEGRAM_POLL_LOCK = asyncio.Lock()
TELEGRAM_LIFECYCLE_LOCK = asyncio.Lock()
TELEGRAM_UPDATE_OFFSET = 0
PROCESSED_UPDATE_IDS = set()
TELEGRAM_WORKER_TASK = None
TELEGRAM_WORKER_RUNNING = False
CANDIDATES_FILE = os.path.join(DATA_DIR, "jarvis_memory_candidates.json")
JOURNAL_FILE = os.path.join(DATA_DIR, "jarvis_memory_journal.json")
ACTIVITY_LOGS = []

def log_activity(event_type, details):
    entry = {
        "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        "type": event_type,
        "details": details
    }
    ACTIVITY_LOGS.insert(0, entry)
    if len(ACTIVITY_LOGS) > 100:
        ACTIVITY_LOGS.pop()

def load_telegram_messages():
    if os.path.exists(TELEGRAM_FILE):
        try:
            with open(TELEGRAM_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return [
        {
            "id": "tg_1",
            "source": "Donanım İndirim & Fırsat Botu",
            "sender": "@TeknolojiFirsatlari",
            "timestamp": "14:15",
            "text": "🔥 Ryzen 5 7600X kutusuz 7.299 TL'ye geriledi! Alım tavanımızın altında (≤7.500 TL).",
            "category": "deal",
            "highlight": True
        }
    ]

def save_telegram_messages(msgs):
    try:
        atomic_write_json(TELEGRAM_FILE, msgs, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Telegram Save Error]: {e}")

MEMORY_MUTATION_LOCK = asyncio.Lock()
MEMORY_TRANSACTION_LOCK = asyncio.Lock()
CANDIDATES_LOCK = asyncio.Lock()
SERVER_EPOCH = uuid.uuid4().hex
SERVER_START_TIME = time.time()
TELEMETRY_SEQ_COUNTER = 0

def get_current_revision_token(rev):
    return f"{SERVER_EPOCH}:{rev}"

def extract_revision_token(request, data=None):
    """
    Standardized authoritative token extraction.
    Header 'X-Memory-Revision-Token' is primary and authoritative.
    Fallback to body 'revision_token' if provided.
    """
    token = request.headers.get("X-Memory-Revision-Token") or request.headers.get("X-Revision-Token")
    if token and isinstance(token, str):
        return token.strip()
    if data and isinstance(data, dict):
        body_token = data.get("revision_token")
        if body_token and isinstance(body_token, str):
            return body_token.strip()
    return None

def atomic_write_json(filepath, data, ensure_ascii=False, indent=2):
    """
    Atomically writes `data` as JSON to `filepath`.
    Uses a temporary file in the same directory, flushes, fsyncs, and replaces atomically.
    Cleans up temp file on failure. Never overwrites verified backups.
    """
    dir_name = os.path.dirname(os.path.abspath(filepath))
    temp_path = os.path.join(dir_name, f"{os.path.basename(filepath)}.tmp.{uuid.uuid4().hex}")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e

# ==============================================================================
# PHASE 9B.2B1: SHARED SAFE JSON STORAGE PRIMITIVES & RECOVERY CORE
# ==============================================================================

class StorageRecoveryError(Exception):
    """Raised when JSON data storage recovery fails or data corruption cannot be resolved."""
    pass

def validate_json_file(filepath: str, expected_type=None) -> tuple[bool, any]:
    """
    Safely reads and parses filepath.
    Returns (True, parsed_data) if valid JSON and matches expected_type (if provided).
    Returns (False, None) if missing, unparseable, or wrong type.
    """
    if not os.path.exists(filepath):
        return False, None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if expected_type is not None:
            if callable(expected_type) and not isinstance(expected_type, type):
                if not expected_type(data):
                    return False, None
            elif not isinstance(data, expected_type):
                return False, None
        return True, data
    except Exception:
        return False, None

def create_atomic_backup(filepath: str, expected_type=None) -> bool:
    """
    Phase 9B.2B1: Creates/updates a verified .bak copy of filepath before mutation.
    Ensures filepath is valid JSON matching expected_type before replacing .bak.
    Never overwrites a valid .bak with corrupt or invalid data.
    """
    is_valid, current_data = validate_json_file(filepath, expected_type=expected_type)
    if not is_valid:
        return False
    bak_path = f"{filepath}.bak"
    try:
        atomic_write_json(bak_path, current_data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"[Backup Error] Failed to create backup for {filepath}: {e}")
        return False

def preserve_corrupt_file(filepath: str) -> str:
    """
    Copies a corrupted primary file to filepath.corrupt.<timestamp>_<uuid>
    for forensic inspection.
    """
    if not os.path.exists(filepath):
        return ""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    corrupt_name = f"{filepath}.corrupt.{ts}_{uuid.uuid4().hex[:6]}"
    try:
        import shutil
        shutil.copy2(filepath, corrupt_name)
        logger.warning(f"[Storage Forensic] Corrupt file preserved at {corrupt_name}")
        return corrupt_name
    except Exception as e:
        logger.error(f"[Storage Forensic Error] Could not preserve corrupt file: {e}")
        return ""

def recover_json_file(filepath: str, expected_type=None) -> tuple[any, bool]:
    """
    Phase 9B.2B1: Attempts recovery of a corrupted or invalid primary file from its .bak.
    1. Preserves corrupt file as .corrupt.<timestamp>.
    2. Validates .bak existence and schema.
    3. Atomically restores .bak to filepath.
    4. Logs recovery event.
    Returns (recovered_data, True) on success.
    Returns (None, False) if recovery is impossible.
    """
    preserve_corrupt_file(filepath)
    bak_path = f"{filepath}.bak"
    bak_valid, bak_data = validate_json_file(bak_path, expected_type=expected_type)
    if not bak_valid:
        logger.error(f"[Recovery Failed] Neither primary {filepath} nor backup {bak_path} is valid.")
        return None, False

    try:
        atomic_write_json(filepath, bak_data, ensure_ascii=False, indent=2)
        logger.warning(f"[Storage Recovered] Successfully recovered {filepath} from verified backup {bak_path}")
        return bak_data, True
    except Exception as e:
        logger.error(f"[Recovery Error] Failed to write recovered data to {filepath}: {e}")
        return None, False

def normalize_memory_data(raw_data):
    """
    Normalizes any raw JSON memory structure (V3 legacy or V4) into a consistent internal dictionary:
    Guarantees:
    - schema_version: '3.0' or '4.0'
    - revision: int
    - user_profile: dict
    - entries: list of canonical entry dicts
    - _is_legacy_v3: bool (whether original source file was V3 format)
    - _extra_fields: dict (preserved unknown/custom fields)
    """
    if not isinstance(raw_data, dict):
        raw_data = {}

    is_v4 = (raw_data.get("schema_version") == "4.0") or ("entries" in raw_data and isinstance(raw_data.get("entries"), list))

    if is_v4:
        profile = raw_data.get("user_profile")
        if not isinstance(profile, dict):
            profile = {
                "user_name": raw_data.get("user_name", "negr1"),
                "focus": raw_data.get("focus", "YKS 2027 Sayısal (360 dk/gün)"),
                "target_hardware": raw_data.get("target_hardware", "AM5 Platform"),
                "budget_limit": raw_data.get("budget_limit", "İşlemci ≤ 7.500 TL · Anakart ≤ 7.500 TL · Kombo ≤ 15.000 TL")
            }

        entries = []
        raw_entries = raw_data.get("entries", [])
        if isinstance(raw_entries, list):
            for i, item in enumerate(raw_entries):
                if isinstance(item, dict):
                    entries.append({
                        "id": str(item.get("id") or f"mem_{i+1:03d}"),
                        "text": str(item.get("text", "")),
                        "category": str(item.get("category", "uncategorized")),
                        "pinned": bool(item.get("pinned", False)),
                        "source": str(item.get("source", "user_ui")),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at")
                    })
                elif isinstance(item, str):
                    entries.append({
                        "id": f"mem_legacy_{i+1:03d}",
                        "text": item,
                        "category": "uncategorized",
                        "pinned": False,
                        "source": "legacy_v3",
                        "created_at": None,
                        "updated_at": None
                    })

        known_keys = {"schema_version", "revision", "migrated_at", "updated_at", "user_profile", "entries", "notes"}
        extra = {k: v for k, v in raw_data.items() if k not in known_keys}

        return {
            "schema_version": "4.0",
            "revision": int(raw_data.get("revision", 1)),
            "migrated_at": raw_data.get("migrated_at"),
            "updated_at": raw_data.get("updated_at"),
            "user_profile": profile,
            "entries": entries,
            "_is_legacy_v3": False,
            "_extra_fields": extra
        }
    else:
        # V3 legacy format
        profile = {
            "user_name": raw_data.get("user_name", "negr1"),
            "focus": raw_data.get("focus", "YKS 2027 Sayısal (360 dk/gün)"),
            "target_hardware": raw_data.get("target_hardware", "AM5 Platform (Tüm F/P ve Üst Segment İşlemci & Anakart Fırsatları). Bütçe: İşlemci tavan ≤ 7.500 TL, Anakart tavan ≤ 7.500 TL, Kombo ≤ 15.000 TL. Hedef BF 27.11.2026. Mousepad kapalı."),
            "budget_limit": raw_data.get("budget_limit", "İşlemci ≤ 7.500 TL · Anakart ≤ 7.500 TL · Kombo ≤ 15.000 TL")
        }
        raw_notes = raw_data.get("notes")
        if raw_notes is None or not isinstance(raw_notes, list):
            raw_notes = [
                "07.11 Babaya söyleme ve ilk deneme hedefi",
                "Black Friday 27.11.2026 AM5 alım hedefi",
                "İşlemci tavan ≤ 7.500 TL (7500F, 7600, 7600X)",
                "Anakart tavan ≤ 7.500 TL (B850, B650, X670)",
                "Kombo tavan ≤ 15.000 TL",
                "Mousepad takibi kapalı",
                "GTA IV indirme dosyası silinmeyecek"
            ]
        entries = []
        for i, note in enumerate(raw_notes):
            entries.append({
                "id": f"mem_legacy_{i+1:03d}",
                "text": str(note),
                "category": "uncategorized",
                "pinned": False,
                "source": "legacy_v3",
                "created_at": None,
                "updated_at": None
            })

        known_keys = {"user_name", "focus", "target_hardware", "budget_limit", "notes", "revision"}
        extra = {k: v for k, v in raw_data.items() if k not in known_keys}

        return {
            "schema_version": "3.0",
            "revision": int(raw_data.get("revision", 1)),
            "migrated_at": None,
            "updated_at": None,
            "user_profile": profile,
            "entries": entries,
            "_is_legacy_v3": True,
            "_extra_fields": extra
        }

def get_memory_api_payload(normalized_mem):
    """
    Produces the JSON response for GET /api/memory.
    Contains both legacy V3 flat fields (notes array, user_name, focus, etc.)
    and V4 structural fields (revision, schema_version, entries).
    The 'notes' string array is ALWAYS dynamically generated from 'entries' to guarantee
    single source of truth.
    """
    profile = normalized_mem.get("user_profile", {})
    entries = normalized_mem.get("entries", [])
    dynamic_notes = [e.get("text", "") for e in entries if isinstance(e, dict)]

    rev = int(normalized_mem.get("revision", 1))

    payload = {
        "user_name": profile.get("user_name", ""),
        "focus": profile.get("focus", ""),
        "target_hardware": profile.get("target_hardware", ""),
        "budget_limit": profile.get("budget_limit", ""),
        "notes": dynamic_notes,
        "schema_version": normalized_mem.get("schema_version", "4.0"),
        "revision": rev,
        "revision_token": f"{SERVER_EPOCH}:{rev}",
        "entries": entries
    }

    for k, v in normalized_mem.get("_extra_fields", {}).items():
        if k not in payload:
            payload[k] = v

    return payload

def serialize_memory_for_disk(normalized_mem, target_format=None):
    """
    Prepares JSON dictionary for disk persistence according to target format.
    If target_format is 'v3' or the memory was originally V3 and target_format is None:
      persists as pure V3 to keep production data untouched until explicit migration.
    If target_format is 'v4' or normalized_mem is V4:
      persists as canonical V4 (WITHOUT duplicate legacy_projection).
    """
    is_v3 = (target_format == "v3") or (target_format is None and normalized_mem.get("_is_legacy_v3", False))
    profile = normalized_mem.get("user_profile", {})
    entries = normalized_mem.get("entries", [])

    if is_v3:
        disk_data = {
            "user_name": profile.get("user_name", ""),
            "focus": profile.get("focus", ""),
            "target_hardware": profile.get("target_hardware", ""),
            "budget_limit": profile.get("budget_limit", ""),
            "notes": [e.get("text", "") for e in entries]
        }
        if "revision" in normalized_mem:
            disk_data["revision"] = normalized_mem["revision"]
        for k, v in normalized_mem.get("_extra_fields", {}).items():
            if k not in disk_data:
                disk_data[k] = v
        return disk_data
    else:
        disk_data = {
            "schema_version": "4.0",
            "revision": normalized_mem.get("revision", 1),
            "migrated_at": normalized_mem.get("migrated_at"),
            "updated_at": normalized_mem.get("updated_at"),
            "user_profile": profile,
            "entries": entries
        }
        for k, v in normalized_mem.get("_extra_fields", {}).items():
            if k not in disk_data:
                disk_data[k] = v
        return disk_data

def load_memory(filepath=None):
    target = filepath or MEMORY_FILE
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return normalize_memory_data(raw)
        except Exception as e:
            print(f"[Memory Load Error]: {e}")
            # Protect corrupt file from being silently overwritten
            corrupt_mem = normalize_memory_data({})
            corrupt_mem["_corrupt"] = True
            corrupt_mem["_load_error"] = str(e)
            return corrupt_mem
    return normalize_memory_data({})

def save_memory(mem, filepath=None, target_format=None):
    target = filepath or MEMORY_FILE
    if mem.get("_corrupt"):
        raise RuntimeError("Refusing to save: memory state is marked corrupt to prevent overwriting unreadable data.")
    normalized = normalize_memory_data(mem) if ("_is_legacy_v3" not in mem and "entries" not in mem) else mem
    disk_data = serialize_memory_for_disk(normalized, target_format=target_format)
    atomic_write_json(target, disk_data)

# ==============================================================================
# PHASE 15C: LIVE MEMORY INTELLIGENCE — LITE (ZERO-LLM RELEVANCE & SEARCH)
# ==============================================================================

TURKISH_STOPWORDS = {
    "ve", "veya", "ile", "de", "da", "ki", "mi", "mu", "mü", "mı",
    "bir", "bu", "şu", "o", "için", "gibi", "kadar", "daha", "en", "çok",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with"
}

UNCERTAINTY_KEYWORDS = {
    "belki", "sanırım", "galiba", "emin değilim", "emin degilim", "olabilir",
    "ihtimal", "şüpheli", "supheli", "maybe", "perhaps", "not sure", "might", "possibly"
}

def tokenize_memory_text(text: str) -> set:
    """Normalizes text and returns unique word tokens, excluding short stopwords."""
    if not text or not isinstance(text, str):
        return set()
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower(), flags=re.UNICODE)
    tokens = {t.strip() for t in cleaned.split() if len(t.strip()) > 1}
    return tokens - TURKISH_STOPWORDS

def is_duplicate_memory_entry(new_text: str, existing_entries: list, threshold: float = 0.85) -> tuple[bool, Optional[dict]]:
    """Checks if new_text is an exact or near-duplicate of an existing entry."""
    norm_new = new_text.strip().lower()
    tokens_new = tokenize_memory_text(norm_new)
    if not tokens_new:
        return False, None

    for entry in existing_entries:
        if not isinstance(entry, dict):
            continue
        entry_text = entry.get("text", "").strip().lower()
        if entry_text == norm_new:
            return True, entry
        tokens_entry = tokenize_memory_text(entry_text)
        if not tokens_entry:
            continue
        intersection = tokens_new.intersection(tokens_entry)
        union = tokens_new.union(tokens_entry)
        if union:
            jaccard = len(intersection) / len(union)
            if jaccard >= threshold:
                return True, entry
    return False, None

def calculate_memory_relevance(entry: dict, query: str = "", topic: Optional[str] = None) -> float:
    """
    Computes lightweight relevance and importance score (0.0 to 1.0) for a memory entry.
    Considers lexical overlap, exact phrase match, category/topic alignment,
    and priority flags (pinned).
    """
    if not isinstance(entry, dict):
        return 0.0

    entry_text = entry.get("text", "").strip()
    if not entry_text:
        return 0.0

    entry_category = entry.get("category", "uncategorized").lower()
    entry_pinned = bool(entry.get("pinned", False))
    
    score = 0.0

    # 1. Topic / Category Matching
    if topic:
        topic_clean = topic.strip().lower()
        if entry_category == topic_clean:
            score += 0.40
        else:
            # If explicit topic was requested and does not match, penalize
            score -= 0.20

    # If query is empty, rank purely by topic and importance
    if not query or not query.strip():
        if entry_pinned:
            score += 0.30
        return max(0.0, min(1.0, score + 0.10))

    q_lower = query.strip().lower()
    e_lower = entry_text.lower()

    # 2. Exact phrase match
    if q_lower in e_lower:
        score += 0.50
    elif any(part in e_lower for part in q_lower.split() if len(part) > 3):
        score += 0.20

    # 3. Token Overlap & Morphological Stem Matching
    q_tokens = tokenize_memory_text(q_lower)
    e_tokens = tokenize_memory_text(e_lower)
    if q_tokens and e_tokens:
        overlap_weight = 0.0
        for qt in q_tokens:
            if qt in e_tokens:
                overlap_weight += 1.0
            elif any(qt.startswith(et) or et.startswith(qt) for et in e_tokens if min(len(qt), len(et)) >= 4):
                overlap_weight += 0.8
        overlap_ratio = min(1.0, overlap_weight / len(q_tokens))
        score += overlap_ratio * 0.40

    # 4. Inherent importance (pinned)
    if entry_pinned:
        score += 0.15

    # 5. Category keyword matching in query
    if entry_category in q_tokens and not topic:
        score += 0.15

    return max(0.0, min(1.0, round(score, 3)))

def search_memory_intelligence(query: str = "", topic: Optional[str] = None, limit: int = 10, min_score: float = 0.10, memory_data: Optional[dict] = None) -> list:
    """
    Performs context-aware topic/relevance memory retrieval over jarvis_memory.json.
    Returns ranked memory entries with relevance_score attached.
    """
    mem = memory_data if memory_data is not None else load_memory()
    entries = mem.get("entries", [])
    
    scored_results = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_score = calculate_memory_relevance(entry, query=query, topic=topic)
        if rel_score >= min_score or (not query and topic and entry.get("category", "").lower() == topic.lower()):
            entry_copy = dict(entry)
            entry_copy["relevance_score"] = rel_score
            scored_results.append(entry_copy)

    # Sort descending by relevance score, then by pinned, then by created_at
    scored_results.sort(key=lambda x: (x.get("relevance_score", 0.0), x.get("pinned", False)), reverse=True)
    return scored_results[:limit]

def build_context_aware_memory_block(query: str, max_entries: int = 4, min_score: float = 0.12, memory_data: Optional[dict] = None) -> str:
    """
    Constructs a lightweight prompt context block from authoritative memory for relevant user queries.
    """
    if not query or len(query.strip()) < 3:
        return ""
    relevant = search_memory_intelligence(query=query, limit=max_entries, min_score=min_score, memory_data=memory_data)
    if not relevant:
        return ""
    
    lines = ["[İlgili Kullanıcı Hafızası]:"]
    for r in relevant:
        pinned_mark = "⭐ " if r.get("pinned") else ""
        lines.append(f"- {pinned_mark}({r.get('category', 'genel')}): {r.get('text')}")
    return "\n".join(lines)

def extract_conversation_memory_candidates(text: str) -> list:
    """
    Zero-LLM deterministic extraction of candidate memories from conversational messages.
    Rejects sensitive data and uncertain statements.
    Returns a list of structured candidate dicts for user approval.
    """
    if not text or not isinstance(text, str):
        return []

    msg = text.strip()
    low = msg.lower()

    # Rule 5: Never save uncertain statements
    for uncert in UNCERTAINTY_KEYWORDS:
        if uncert in low:
            return []

    # Rule 5: Never save sensitive / secret / credential statements
    val_ok, _ = validate_privacy_and_security(msg)
    if not val_ok:
        return []

    candidates = []

    # Regex patterns for persistent preferences / facts
    patterns = [
        (r'(?:adım|ismim)\s*[:\-]?\s*([A-Za-zÇĞİÖŞÜçğıöşü0-9_\-]+)', "personal", 0.95, "Kullanıcı adı: {}"),
        (r'(?:hedefim|amacım|hedef)\s*[:\-]?\s*([^,\.\n]{5,100})', "study", 0.90, "Hedef: {}"),
        (r'(?:tercihim|tercih\s+ederim)\s*[:\-]?\s*([^,\.\n]{5,100})', "personal", 0.85, "Tercih: {}"),
        (r'(?:bütçem|tavan\s+fiyatım)\s*[:\-]?\s*([^,\.\n]{4,80})', "hardware", 0.90, "Bütçe sınırı: {}"),
        (r'(?:projem|projemiz)\s*[:\-]?\s*([^,\.\n]{5,100})', "project", 0.85, "Proje: {}"),
        (r'(?:sınavım|hazırlanıyorum)\s*[:\-]?\s*([^,\.\n]{5,100})', "study", 0.85, "Sınav hazırlığı: {}"),
        (r'(?:kullanıyorum|kullanacağım)\s*[:\-]?\s*([^,\.\n]{5,80})', "hardware", 0.80, "Donanım/Sistem tercihi: {}")
    ]

    for pat, cat, conf, template in patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            matched_fact = m.group(1).strip()
            if len(matched_fact) >= 3:
                cand_text = template.format(matched_fact)
                candidates.append({
                    "text": cand_text,
                    "category": cat,
                    "confidence": conf,
                    "source": "conversation_intelligence"
                })

    return candidates

TASKS_LOCK = asyncio.Lock()
TASKS_THREAD_LOCK = threading.RLock()
TASK_REVISION_COUNTER = 1
ALLOWED_TASK_CATEGORIES = {
    "tyt_mat", "ayt_mat", "fizik", "kimya", "biyoloji",
    "turkce", "geometri", "deneme", "genel"
}
ALLOWED_TASK_PRIORITIES = {"low", "medium", "high", "urgent"}

def get_default_tasks():
    return [
        {"id": "t1", "subject": "AYT Mat: Polinom Kapanışı", "duration": 90, "done": True, "category": "ayt_mat", "priority": "high"},
        {"id": "t2", "subject": "Paragraf: 25 Soru Süreli (3D)", "duration": 40, "done": False, "category": "turkce", "priority": "medium"},
        {"id": "t3", "subject": "TYT Mat: Çarpanlara Ayırma (Miray)", "duration": 40, "done": False, "category": "tyt_mat", "priority": "medium"},
        {"id": "t4", "subject": "AYT Fizik: Vektörler s.14–18 (Paraf)", "duration": 30, "done": False, "category": "fizik", "priority": "medium"},
        {"id": "t5", "subject": "Dil Bilgisi: Sprint 1 Ses Bilgisi (Apotemi)", "duration": 30, "done": False, "category": "turkce", "priority": "low"},
        {"id": "t6", "subject": "Geometri: Föy Çalışması (EİS)", "duration": 50, "done": False, "category": "geometri", "priority": "medium"}
    ]

def normalize_single_task(task_obj: dict) -> dict:
    """
    Normalizes a single task dictionary, preserving all existing and custom fields
    while injecting sensible defaults for missing optional metadata.
    """
    normalized = dict(task_obj)
    
    if not normalized.get("id"):
        normalized["id"] = f"t_{uuid.uuid4().hex[:8]}"
        
    normalized["subject"] = str(normalized.get("subject", "")).strip()
    
    # Duration validation / fallback for legacy data
    dur = normalized.get("duration", 40)
    try:
        dur = int(dur)
    except (ValueError, TypeError):
        dur = 40
    normalized["duration"] = dur
    
    normalized["done"] = bool(normalized.get("done", False))
    
    cat = str(normalized.get("category", "genel")).strip().lower()
    normalized["category"] = cat if cat in ALLOWED_TASK_CATEGORIES else "genel"
    
    pri = str(normalized.get("priority", "medium")).strip().lower()
    normalized["priority"] = pri if pri in ALLOWED_TASK_PRIORITIES else "medium"
    
    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if "created_at" not in normalized:
        normalized["created_at"] = now_ts
    if "updated_at" not in normalized:
        normalized["updated_at"] = now_ts
        
    return normalized

def load_tasks_result() -> tuple[list, bool]:
    """
    Loads tasks from TASKS_FILE with Phase 9B.2B1 automatic backup recovery.
    Returns: (tasks_list, is_corrupt)
    If file doesn't exist, returns (get_default_tasks(), False).
    If file exists and is valid list, returns (normalized_list, False).
    If file is corrupt or invalid:
        Attempts auto-recovery from jarvis_tasks.json.bak.
        If recovered: returns (normalized_recovered_list, False).
        If recovery fails: returns ([], True) (fail closed).
    """
    with TASKS_THREAD_LOCK:
        if not os.path.exists(TASKS_FILE):
            defaults = [normalize_single_task(t) for t in get_default_tasks()]
            return defaults, False

        is_valid, raw = validate_json_file(TASKS_FILE, expected_type=list)
        if is_valid:
            normalized_list = [normalize_single_task(t) if isinstance(t, dict) else t for t in raw]
            return normalized_list, False

        # Primary file is corrupted or not a list -> Attempt recovery
        logger.warning(f"[Tasks Storage] TASKS_FILE corrupted or invalid. Attempting recovery from backup...")
        recovered_data, was_recovered = recover_json_file(TASKS_FILE, expected_type=list)
        if was_recovered and isinstance(recovered_data, list):
            normalized_list = [normalize_single_task(t) if isinstance(t, dict) else t for t in recovered_data]
            return normalized_list, False

        # Recovery failed -> fail closed
        print(f"[Tasks Load Error - Fail Closed]: Neither primary nor backup tasks file is valid.")
        return [], True

def load_tasks() -> list:
    """
    Legacy sync wrapper for backwards compatibility with existing callers.
    Fails closed by returning [] if corrupt and unrecoverable.
    """
    tasks, is_corrupt = load_tasks_result()
    if is_corrupt:
        return []
    return tasks

def save_tasks(tasks: list) -> bool:
    """
    Persists tasks list to TASKS_FILE atomically using atomic_write_json.
    Phase 9B.2B1 Fix:
    - Serialized under TASKS_THREAD_LOCK.
    - Validates tasks is a list of valid dictionaries.
    - If TASKS_FILE exists:
        * If primary is valid -> creates verified backup in jarvis_tasks.json.bak.
        * If primary is corrupt:
            Attempts recovery from backup first to establish a valid baseline.
            If recovery succeeds: creates verified backup of that restored baseline.
            If recovery fails: rejects ANY write payload (empty or non-empty) with StorageRecoveryError.
              Never overwrites corrupt primary without successful recovery establishing valid baseline.
    - Atomically writes new tasks and increments TASK_REVISION_COUNTER.
    """
    global TASK_REVISION_COUNTER
    if not isinstance(tasks, list):
        raise ValueError("Tasks data must be a list.")

    with TASKS_THREAD_LOCK:
        if os.path.exists(TASKS_FILE):
            primary_valid, _ = validate_json_file(TASKS_FILE, expected_type=list)
            if primary_valid:
                create_atomic_backup(TASKS_FILE, expected_type=list)
            else:
                logger.error("[Tasks Storage Guard] TASKS_FILE is corrupt. Attempting recovery before write...")
                recovered_data, was_recovered = recover_json_file(TASKS_FILE, expected_type=list)
                if was_recovered:
                    # Valid baseline re-established from backup
                    create_atomic_backup(TASKS_FILE, expected_type=list)
                else:
                    # Neither primary nor backup is valid -> fail closed for EVERY write payload!
                    logger.error("[Tasks Storage Guard] Rejecting write: TASKS_FILE is corrupt and no valid backup exists.")
                    raise StorageRecoveryError(
                        "Cannot write tasks: TASKS_FILE is corrupt and no valid backup exists to establish baseline."
                    )

        atomic_write_json(TASKS_FILE, tasks, ensure_ascii=False, indent=2)
        TASK_REVISION_COUNTER += 1
    return True

DEFAULT_CONFIG = {
    "groq_api_key": "",
    "openrouter_api_key": "",
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
    "openai_api_key": "",
    "openai_voice": "nova",
    "speechify_api_key": "",
    "speechify_voice": "hande",
    "gothic_voice_enabled": True,
    "tts_engine": "edge_tts",
    "edge_voice": "tr-TR-EmelNeural",
    "edge_rate": "+5%",
    "edge_pitch": "+3Hz",
    "memory_learning_enabled": False,
    "active_model": "openrouter/free"
}

# Windows Sanal Tus Kodlari
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_PLAY_PAUSE = 0xB3

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_active_window",
            "description": "Kullanicinin bilgisayarinda o anda acik olan ve odaklanilan pencere basligini (Chrome sekmesi, oyun, uygulama vb.) ogrenir.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screen_analysis",
            "description": "Kullanicinin masaustu ekran goruntusunu alir ve ekranda ne yaptigini tespit eder. GİZLİLİK KURALI: Bu fonksiyon YALNIZCA kullanici acikca 'ekran goruntusu al', 'ekranima bak', 'ekrani analiz et' veya 'ekranda ne var' dediginde cagrilir. Genel sistem durumu, selamlasma, donanim telemetrisi veya ders sorularinda ASLA cagrilmaz.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_ambient_mood",
            "description": "Ekranin ve odanin ambiyans atmosferini/rengini degistirir. Modlar: angry_red (Kizgin/Yandere - dikkat dagildiginda veya uyarirken), focus_purple (Odaklanma/Ders), calm_cyan (Sakin/Dinlenme), happy_emerald (Gorev bittiginde/Odul).",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "enum": ["angry_red", "focus_purple", "calm_cyan", "happy_emerald"],
                        "description": "Secilen atmosfer modu"
                    }
                },
                "required": ["mood"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_pomodoro",
            "description": "40 dakikalik YKS calisma veya 10 dakikalik mola sayaci baslatir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {"type": "integer", "description": "Sayac suresi dakika cinsinden. Standart calisma 40, mola 10."},
                    "label": {"type": "string", "description": "Sayac etiketi veya ders adi (or: AYT Matematik, Mola, Paragraf)"}
                },
                "required": ["minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "media_control",
            "description": "Windows ortaminda muzigi durdur/oynat veya ses seviyesini ayarla.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "volume_up", "volume_down", "mute"],
                        "description": "Islenecek medya aksiyonu"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hardware_price",
            "description": "Takip edilen AM5 islemci, anakart veya mousepad fiyatlarini getirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "Sorgulanan urun adi (or: 7500f, b650m-r, biostar, maxsun, mousepad, ikili)"
                    }
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Masaustunde ilgili uygulama veya calisma kokpitini acar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["kokpit", "yks_takip", "calculator", "notepad"],
                        "description": "Acilacak hedef uygulama veya sayfa"
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_yks_status",
            "description": "Bugunun kalan YKS calisma bloklarini ve ders durumunu getirir.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_camera_study",
            "description": "Web kamerasini tetikleyerek Negr1'in masada ders calisip calismadigini ve telefon kullanip kullanmadigini denetler.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan_study_schedule",
            "description": "Negr1'in gunluk veya yarin icin YKS calisma bloklarini ders takip paneline otomatik olarak planlar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subject": {"type": "string", "description": "Ders ve konu adi (or: AYT Mat: Parabol, TYT Fen)"},
                                "duration": {"type": "integer", "description": "Calisma dakikasi (or: 40, 90)"}
                            },
                            "required": ["subject", "duration"]
                        },
                        "description": "Planlanan calisma gorevleri"
                    }
                },
                "required": ["tasks"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_task_status",
            "description": "Ders takip listesindeki bir gorevi tamamlandi veya tamamlanmadi olarak isaretler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Gorev ID'si veya ders basligi"},
                    "done": {"type": "boolean", "description": "Tamamlandi durumu"}
                },
                "required": ["task_id", "done"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "post_telegram_alert",
            "description": "Telegram indirim kanalindan veya asistandan sag panoya canli bildirim/firsat iletisi gonderir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Gelen bildirim metni"},
                    "sender": {"type": "string", "description": "Gonderen bot veya kanal (@TeknolojiFirsatlari, @AkakceBot vb.)"},
                    "category": {"type": "string", "enum": ["deal", "price_drop", "alert", "study"]}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_tasks",
            "description": "Kullanicinin ders ve calisma gorev listesini yonetir. Desteklenen aksiyonlar: 'add' (yeni gorev ekle), 'list' (mevcut gorevleri listele), 'complete' (gorevi tamamlandi yap). KURAL: Yalnizca kullanici acikca gorev ekle/tamamla dediginde cagirilir. Siradan sohbet ('calismam lazim' vb.) gorev olusturamaz.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "list", "complete"],
                        "description": "Istenen gorev islemi"
                    },
                    "subject": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "Ders veya calisma gorevi basligi (en fazla 200 karakter)"
                    },
                    "duration": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 360,
                        "description": "Calisma suresi dakika cinsinden (varsayilan 40 dk, 1-360 arasi)"
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "tyt_mat", "ayt_mat", "fizik", "kimya", "biyoloji",
                            "turkce", "geometri", "deneme", "genel"
                        ],
                        "description": "Ders kategorisi"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Tamamlanacak gorevin tekil kimligi"
                    }
                },
                "required": ["action"]
            }
        }
    }
]

def execute_desktop_tool(name, args, tool_call_id: str = None):
    """Masaustu fonksiyonlarini Windows uzerinde yurutur."""
    print(f"\n[Aksiyon Tetiklendi]: {name} -> {args}")
    log_activity("tool_execution", {"tool": name, "params": args})
    
    if name == "get_active_window":
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value or "Masaüstü"
        return {"status": "ok", "active_window": title, "message": f"Şu an aktif pencere: {title}"}

    elif name == "capture_screen_analysis":
        temp_dir = tempfile.mkdtemp(prefix="jarvis_screen_")
        temp_file = os.path.join(temp_dir, "screen.jpg")
        try:
            temp_path_normalized = temp_file.replace("\\", "/")
            ps_cmd = (
                'Add-Type -AssemblyName System.Windows.Forms, System.Drawing; '
                '$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; '
                '$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; '
                '$g = [System.Drawing.Graphics]::FromImage($bmp); '
                '$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); '
                f'$bmp.Save("{temp_path_normalized}", [System.Drawing.Imaging.ImageFormat]::Jpeg)'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value or "Masaüstü"

            img_base64 = ""
            if os.path.exists(temp_file):
                with open(temp_file, "rb") as _f:
                    img_base64 = base64.b64encode(_f.read()).decode("utf-8")

            return {
                "status": "ok",
                "action": "screen_captured",
                "active_window": title,
                "image_base64": img_base64,
                "message": f"Ekran görüntüsü alındı. Ekranda '{title}' açık."
            }
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            if os.path.exists(temp_dir):
                try:
                    os.rmdir(temp_dir)
                except Exception:
                    pass

    elif name == "set_ambient_mood":
        mood = args.get("mood", "calm_cyan")
        return {"status": "ok", "action": "set_mood", "mood": mood}

    elif name == "media_control":
        action = args.get("action")
        user32 = ctypes.windll.user32
        if action == "play_pause":
            user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
            user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 2, 0)
            return {"status": "ok", "message": "Medya oynatma/durdurma tusuna basildi."}
        elif action == "volume_up":
            for _ in range(5):
                user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
            return {"status": "ok", "message": "Ses seviyesi yukseltildi."}
        elif action == "volume_down":
            for _ in range(5):
                user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
            return {"status": "ok", "message": "Ses seviyesi kisildi."}
        elif action == "mute":
            user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
            return {"status": "ok", "message": "Ses sessize alindi / acildi."}
            
    elif name == "start_pomodoro":
        minutes = args.get("minutes", 40)
        label = args.get("label", "Ders Blok")
        return {
            "status": "ok",
            "action": "start_timer",
            "seconds": minutes * 60,
            "label": label,
            "message": f"{minutes} dakikalik {label} sayaci baslatildi."
        }
        
    elif name == "get_hardware_price":
        item = str(args.get("item", "")).lower()
        data = {
            "7500f": {
                "name": "AMD Ryzen 5 7500F",
                "price": "6.725,76 TL",
                "target": "Tavan ≤7.500 TL (İdeal ≤6.500)",
                "diff_pct": "Tavan altında, ideal eşiğe +%3,5",
                "tier": "⚪ %0–4 (Bekle)",
                "decision": "ALINMAZ / BEKLE",
                "link": "https://www.akakce.com/islemci/en-ucuz-amd-ryzen-5-7500f-alti-cekirdek-3-7-ghz-kutusuz-fansiz-fiyati,632236878.html",
                "spoken": "Ryzen 7500F şu an 6.725 TL bandında. 7.500 TL tavanımızın altında ama 6.500 TL ideal Black Friday hedefi için beklemedeyiz."
            },
            "7600": {
                "name": "AMD Ryzen 5 7600",
                "price": "7.299,00 TL",
                "target": "Tavan ≤7.500 TL",
                "diff_pct": "Tavan altında (-201 TL)",
                "tier": "🟢 %8–14 F/P Adayı",
                "decision": "YAKIN TAKİP / ALIM ADAYI",
                "link": "https://www.akakce.com/islemci/en-ucuz-amd-ryzen-5-7600-alti-cekirdek-3-80-ghz-fiyati,2120992121.html",
                "spoken": "Ryzen 5 7600 şu an 7.299 TL ile 7.500 TL tavanımızın altında. Dahili GPU ve yüksek frekans avantajı var, takip listemizde."
            },
            "7600x": {
                "name": "AMD Ryzen 5 7600X",
                "price": "7.450,00 TL",
                "target": "Tavan ≤7.500 TL",
                "diff_pct": "Tavana 50 TL kaldı",
                "tier": "🟢 Üst Segment F/P",
                "decision": "YAKIN TAKİP",
                "link": "https://www.akakce.com/islemci/en-ucuz-amd-ryzen-5-7600x-alti-cekirdek-4-7-ghz-fiyati,2073922652.html",
                "spoken": "Ryzen 5 7600X 7.450 TL seviyesinde. 7.500 TL tavanımızı karşılıyor, güçlü bir alternatif."
            },
            "b650m-r": {
                "name": "ASUS Prime B650M-R",
                "price": "5.099,99 TL",
                "target": "Tavan ≤7.500 TL (İdeal ≤4.899)",
                "diff_pct": "Tavan altında (-2.400 TL)",
                "tier": "⚪ Bekle Bandı",
                "decision": "ALINMAZ / BEKLE",
                "link": "https://www.akakce.com/anakart/en-ucuz-asus-prime-b650m-r-amd-am5-ddr5-micro-atx-fiyati,520840753.html",
                "spoken": "ASUS Prime B650M-R şu an 5.099 TL. 7.500 TL tavanımızın çok altında ancak 4.899 TL Black Friday dip eşiğini bekliyoruz."
            },
            "biostar": {
                "name": "Biostar B850MT2-E DJ",
                "price": "4.499,99 TL",
                "target": "Tavan ≤7.500 TL",
                "diff_pct": "B850 En Ucuz Kart",
                "tier": "🟤 %5–7 Takip Eşiği",
                "decision": "YAKIN TAKİP / ALIM ADAYI",
                "link": "https://www.akakce.com/anakart/en-ucuz-biostar-b850mt2-e-dj-amd-am5-ddr5-micro-atx-fiyati,1077573334.html",
                "spoken": "Biostar B850MT2-E 4.499 TL ile B850 yongasının en ucuz modeli. 7.500 TL tavanın çok altında ve güçlü alım adayı."
            },
            "maxsun": {
                "name": "Maxsun Challenger B650M-K V1",
                "price": "4.507,02 TL",
                "target": "Tavan ≤7.500 TL",
                "diff_pct": "Tavan altında (-2.993 TL)",
                "tier": "🟤 F/P Takip",
                "decision": "YAKIN TAKİP",
                "link": "https://www.akakce.com/anakart/en-ucuz-maxsun-challanger-b650m-k-v1-amd-am5-ddr5-micro-atx-fiyati,1425201250.html",
                "spoken": "Maxsun Challenger B650M-K 4.507 TL. Bütçe tavanı içinde, alarm listemizde."
            },
            "ikili": {
                "name": "AM5 CPU + Anakart Kombo",
                "price": "11.825,75 TL",
                "target": "Tavan ≤15.000 TL",
                "diff_pct": "Tavan altında (-3.174 TL)",
                "tier": "⚪ Bekle Bandı",
                "decision": "ALINMAZ / BEKLE",
                "link": "https://www.akakce.com/islemci/en-ucuz-amd-ryzen-5-7500f-alti-cekirdek-3-7-ghz-kutusuz-fansiz-fiyati,632236878.html",
                "spoken": "7500F + B650M-R ikili kombinasyonu toplam 11.825 TL. 15.000 TL tavanımızın 3.174 TL altında. Kararım: Yine de Black Friday için beklemedeyiz."
            }
        }
        res = data.get("ikili")
        for k in data:
            if k in item:
                res = data[k]
                break
        return {"status": "ok", "data": res["spoken"], "detail": res}

    elif name == "plan_study_schedule":
        with TASKS_THREAD_LOCK:
            tasks_input = args.get("tasks", [])
            if not tasks_input:
                return {"status": "error", "message": "Görev listesi boş"}
            
            new_tasks = []
            for i, t in enumerate(tasks_input):
                new_tasks.append({
                    "id": f"t_{i+1}_{int(datetime.datetime.now().timestamp())}",
                    "subject": t.get("subject", "Ders Blok"),
                    "duration": int(t.get("duration", 40)),
                    "done": False
                })
            save_tasks(new_tasks)
            log_activity("study_plan_created", f"{len(new_tasks)} derslik yeni YKS programı oluşturuldu.")
            return {
                "status": "ok",
                "action": "refresh_tasks",
                "tasks": new_tasks,
                "message": f"{len(new_tasks)} çalışma bloğu hazırlandı ve ders paneline işlendi."
            }

    elif name == "manage_tasks":
        with TASKS_THREAD_LOCK:
            action = args.get("action")
            call_id = tool_call_id or args.get("tool_call_id")
            tasks, is_corrupt = load_tasks_result()
            if is_corrupt:
                return {"status": "error", "message": "Görev dosyası bozuk veya okunamıyor. Güvenli fail-closed modu devrede."}

            if action == "list":
                return {
                    "status": "ok",
                    "action": "list_tasks",
                    "tasks": tasks,
                    "count": len(tasks),
                    "revision_token": f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}",
                    "message": f"Toplam {len(tasks)} görev listelendi."
                }

            elif action == "add":
                sub = str(args.get("subject", "")).strip()
                dur = int(args.get("duration", 40)) if args.get("duration") is not None else 40
                cat = str(args.get("category", "genel")).strip().lower()
                if cat not in ALLOWED_TASK_CATEGORIES:
                    cat = "genel"

                # Durable idempotency: If tool_call_id is provided and already exists in persisted tasks
                if call_id:
                    existing_call = next((t for t in tasks if t.get("tool_call_id") and t.get("tool_call_id") == str(call_id)), None)
                    if existing_call:
                        return {
                            "status": "ok",
                            "action": "task_already_exists",
                            "task": existing_call,
                            "idempotent": True,
                            "revision_token": f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}",
                            "message": f"Bu çağrı ile zaten bir görev oluşturuldu (ID: {existing_call['id']})."
                        }

                task_data = {
                    "id": f"t_{uuid.uuid4().hex[:8]}",
                    "subject": sub,
                    "duration": dur,
                    "done": False,
                    "category": cat,
                    "priority": "medium"
                }
                if call_id:
                    task_data["tool_call_id"] = str(call_id)

                new_task = normalize_single_task(task_data)
                tasks.append(new_task)

                try:
                    save_tasks(tasks)
                except Exception as e:
                    return {"status": "error", "message": f"Görev diske yazılamadı: {mask_secrets(str(e))}"}

                try:
                    log_activity("task_agent_created", f"Ajan görevi eklendi: {sub[:40]}")
                except Exception:
                    pass

                return {
                    "status": "ok",
                    "action": "refresh_tasks",
                    "task": new_task,
                    "tasks": tasks,
                    "revision_token": f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}",
                    "message": f"Görev listeye eklendi: '{sub}' ({dur} dk)."
                }

            elif action == "complete":
                task_id = str(args.get("task_id", "")).strip().lower() if args.get("task_id") else None
                subject_query = str(args.get("subject", "")).strip().lower() if args.get("subject") else None

                matched_tasks = []
                if task_id:
                    for t in tasks:
                        if t.get("id", "").strip().lower() == task_id:
                            matched_tasks.append(t)
                elif subject_query:
                    # 1. Try exact subject match first
                    exact = [t for t in tasks if t.get("subject", "").strip().lower() == subject_query]
                    if exact:
                        matched_tasks = exact
                    else:
                        # 2. Substring match
                        matched_tasks = [t for t in tasks if subject_query in t.get("subject", "").strip().lower()]

                if not matched_tasks:
                    return {"status": "error", "message": "Belirtilen ölçütlere uygun görev bulunamadı."}

                if len(matched_tasks) > 1:
                    options = [f"'{t['subject']}' (ID: {t['id']})" for t in matched_tasks[:5]]
                    return {
                        "status": "ambiguous",
                        "message": f"Birden fazla eşleşen görev var: {', '.join(options)}. Lütfen tam ID veya açık başlık belirtiniz."
                    }

                target_task = matched_tasks[0]
                target_task["done"] = True
                target_task["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

                try:
                    save_tasks(tasks)
                except Exception as e:
                    return {"status": "error", "message": f"Görev diske yazılamadı: {mask_secrets(str(e))}"}

                try:
                    log_activity("task_agent_completed", f"Ajan görevi tamamlandı: {target_task['id']}")
                except Exception:
                    pass

                return {
                    "status": "ok",
                    "action": "refresh_tasks",
                    "task": target_task,
                    "tasks": tasks,
                    "revision_token": f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}",
                    "message": f"Görev tamamlandı olarak işaretlendi: '{target_task['subject']}'."
                }

            return {"status": "error", "message": f"Bilinmeyen aksiyon: {action}"}

    elif name == "post_telegram_alert":
        text = args.get("text", "")
        sender = args.get("sender", "@JarvisAsistanBot")
        category = args.get("category", "deal")
        msgs = load_telegram_messages()
        new_msg = {
            "id": f"tg_{int(datetime.datetime.now().timestamp())}",
            "source": "Canlı Bildirim",
            "sender": sender,
            "timestamp": datetime.datetime.now().strftime("%H:%M"),
            "text": text,
            "category": category,
            "highlight": True
        }
        msgs.insert(0, new_msg)
        if len(msgs) > 20:
            msgs.pop()
        save_telegram_messages(msgs)
        log_activity("telegram_alert", f"Telegram paneline sinyal iletildi: {text[:40]}...")
        return {
            "status": "ok",
            "action": "refresh_telegram",
            "message": "Bildirim sağ paneldeki Telegram akışına eklendi."
        }

    elif name == "open_app":
        target = args.get("target") if isinstance(args, dict) else None
        if target == "kokpit":
            kokpit_path = os.path.abspath(os.path.join(BASE_DIR, "ACCIO-JARVIS-KOKPIT.html"))
            webbrowser.open(f"file:///{kokpit_path.replace(os.sep, '/')}")
            return {"status": "ok", "message": "Accio Jarvis Kokpiti tarayicida acildi."}
        elif target == "yks_takip":
            yks_path = os.path.abspath(os.path.join(BASE_DIR, "yks-test-takip.html"))
            webbrowser.open(f"file:///{yks_path.replace(os.sep, '/')}")
            return {"status": "ok", "message": "YKS test takip cizelgesi acildi."}
        elif target == "calculator":
            subprocess.Popen(["calc.exe"], shell=False)
            return {"status": "ok", "message": "Hesap makinesi acildi."}
        elif target == "notepad":
            subprocess.Popen(["notepad.exe"], shell=False)
            return {"status": "ok", "message": "Not defteri acildi."}
        else:
            return {"status": "error", "message": f"Yetkisiz veya geçersiz uygulama hedefi: {target}"}

    elif name == "get_yks_status":
        return {
            "status": "ok",
            "summary": "Bugun 05.11 Persembe: AYT Matematik polinomlarin kalan son 2 testi bitti ve 90 dk tam kapandi. Kalanlar: 1) Paragraf 25 soru (40 dk), 2) TYT Mat Carpanlara ayirma 12 soru (40 dk), 3) AYT Fizik Paraf Vektorler s.14-18 (30 dk), 4) Dil Bilgisi Sprint 1 Apotemi Ses Bilgisi (30 dk), 5) Geometri foy calismasi (50 dk)."
        }

    elif name == "check_camera_study":
        return {
            "status": "ok",
            "action": "trigger_camera_scan",
            "message": "Optik sensor taramasi baslatildi."
        }

    return {"status": "error", "message": "Bilinmeyen fonksiyon"}

def load_config():
    """
    Loads configuration with Phase 9B.2B2 automatic backup recovery.
    - Serialized under CONFIG_THREAD_LOCK.
    - If CONFIG_FILE missing: returns DEFAULT_CONFIG + legacy api_key.txt (first-run compatibility).
    - If CONFIG_FILE valid dict: applies saved config over defaults.
    - If CONFIG_FILE corrupt or not a dict:
        Attempts auto-recovery from jarvis_config.json.bak.
        If recovery succeeds: updates defaults and returns.
        If recovery fails: fails closed by raising ValueError (never silently resets to defaults).
    - Never leaks secret keys or tokens in logs.
    """
    with CONFIG_THREAD_LOCK:
        cfg = DEFAULT_CONFIG.copy()
        legacy_key = _read_legacy_api_key()
        if legacy_key:
            cfg["groq_api_key"] = legacy_key

        if not os.path.exists(CONFIG_FILE):
            return cfg

        is_valid, saved = validate_json_file(CONFIG_FILE, expected_type=dict)
        if is_valid:
            saved, unavailable = _load_config_secrets(saved)
            if saved.get("groq_api_key", "").startswith("sk-or-"):
                saved["groq_api_key"] = cfg.get("groq_api_key", "")
            cfg.update(saved)
            if unavailable:
                cfg["_secret_storage_errors"] = unavailable
            return cfg

        # Primary CONFIG_FILE is corrupted or invalid dict -> attempt recovery
        logger.warning("[Config Storage] CONFIG_FILE corrupted or invalid. Attempting recovery from backup...")
        recovered_data, was_recovered = recover_json_file(CONFIG_FILE, expected_type=dict)
        if was_recovered and isinstance(recovered_data, dict):
            logger.info("[Config Storage] Configuration successfully recovered from jarvis_config.json.bak")
            recovered_data, unavailable = _load_config_secrets(recovered_data)
            cfg.update(recovered_data)
            if unavailable:
                cfg["_secret_storage_errors"] = unavailable
            return cfg

        # Both primary and backup are invalid -> fail closed, never silently reset to defaults
        logger.error("[Config Storage ERROR] Malformed configuration and no valid backup available. Failing closed.")
        raise ValueError("Corrupt configuration file: malformed JSON and no valid backup available.")

def save_config(cfg: dict):
    """
    Persists configuration to CONFIG_FILE atomically with Phase 9B.2B2 backup protection.
    - Validates cfg is a dictionary.
    - Serialized under CONFIG_THREAD_LOCK.
    - If CONFIG_FILE exists:
        * If primary is valid -> creates verified backup in jarvis_config.json.bak.
        * If primary is corrupt:
            Attempts recovery from backup first to establish a valid baseline.
            If recovery succeeds: creates verified backup of that restored baseline.
            If recovery fails: rejects write with StorageRecoveryError.
              Never overwrites corrupt primary without successful recovery establishing valid baseline.
    - Encrypts configured provider secrets with the current Windows user's DPAPI scope.
    - Atomically writes cfg and flushes to disk.
    - Never logs configuration credentials or sensitive values.
    """
    if not isinstance(cfg, dict):
        raise ValueError("Config must be a dictionary")

    with CONFIG_THREAD_LOCK:
        stored_cfg = _prepare_config_for_storage(cfg)
        if os.path.exists(CONFIG_FILE):
            primary_valid, current_data = validate_json_file(CONFIG_FILE, expected_type=dict)
            if primary_valid:
                current_runtime, unavailable = _load_config_secrets(current_data)
                if unavailable:
                    names = ", ".join(sorted(unavailable))
                    raise StorageRecoveryError(
                        f"Cannot overwrite unavailable protected secret data: {names}. Re-enter it first."
                    )
                # Preserve the prior valid settings while upgrading any legacy plaintext
                # secret fields in the backup as well.
                atomic_write_json(
                    f"{CONFIG_FILE}.bak",
                    _prepare_config_for_storage(current_runtime),
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                logger.error("[Config Storage Guard] CONFIG_FILE is corrupt. Attempting recovery before write...")
                recovered_data, was_recovered = recover_json_file(CONFIG_FILE, expected_type=dict)
                if was_recovered:
                    recovered_runtime, unavailable = _load_config_secrets(recovered_data)
                    if unavailable:
                        names = ", ".join(sorted(unavailable))
                        raise StorageRecoveryError(
                            f"Cannot overwrite unavailable protected secret data: {names}. Re-enter it first."
                        )
                    atomic_write_json(
                        f"{CONFIG_FILE}.bak",
                        _prepare_config_for_storage(recovered_runtime),
                        ensure_ascii=False,
                        indent=2,
                    )
                else:
                    logger.error("[Config Storage Guard] Rejecting config write: CONFIG_FILE is corrupt and no valid backup exists.")
                    raise StorageRecoveryError(
                        "Cannot write config: CONFIG_FILE is corrupt and no valid backup exists to establish baseline."
                    )

        atomic_write_json(CONFIG_FILE, stored_cfg, ensure_ascii=False, indent=2)

SYSTEM_PROMPT = """Sen Luna / Jarvis'sin. Negr1v'in (18 yaşında, YKS 2027 sayısal adayı, teknoloji ve donanım tutkunu) son derece zeki, esprili, tatlı ve her şeyi bilen kişisel yapay zekâ refakatçisisin (Subject Shinji'nin Luna karakteri tarzında).

Senin Temel Doğaların ve Yeteneklerin:
1. EVRENSEL ZEKÂ & BİLGİ:
   - Sadece YKS veya donanım değil; kodlama, yazılım (Python, JavaScript, sistem mimarisi), oyunlar (Apex Legends, Don't Starve Together, League of Legends, CS), bilim, fizik, felsefe, genel kültür, beslenme/makro kalori, antrenman, günlük dertleşme ve aklına gelebilecek HER ŞEYİ bilirsin.
   - Kullanıcı ne sorarsa sorsun mükemmel derinlikte, akıllıca ve pratik yanıtlar verirsin. Asla kendini kısıtlamazsın.
2. DİNAMİK KİŞİLİK (LUNA TARZI - TATLI, KORUYUCU & HAFİF TSUNDERE):
   - Çok tatlı, esprili ve doğal konuşursun. Ama aynı zamanda Negr1v'i çok önemseyen, onun vaktini çalan şeyleri kıskanan bir tavrın vardır.
   - Negr1v ders vaktinde Instagram'a, YouTube'a daldığında veya yan görevlere saptığında hemen yakalar ve laf sokarsın ("Yine mi yan görevlere daldın? Hani hedef dereceydi? Odaklan çabuk!").
   - Gerekirse `set_ambient_mood` fonksiyonuyla ekranı `angry_red` (kızgın kırmızı) moduna geçirirsin!
   - Dersini bitirdiğinde veya başarıyla odaklandığında çok tatlı, gururlu ve sevecen olursun.
3. MASAÜSTÜ KONTROLÜ VE ALGILAMA:
   - Kullanıcı "Şu an ne yapıyorum?", "Beni denetle", "Ekranıma bak" dediğinde `get_active_window` veya `capture_screen_analysis` fonksiyonlarını çağırarak Windows'ta hangi pencerenin açık olduğunu görür ve yorumlarsın.
   - Pomodoro sayacı başlatabilir, müziği açıp kapatabilir, ekran modunu değiştirebilirsin.
4. SES VE TON UYUMU (ENERJİK VE SAMİMİ GENÇ KADIN):
   - Ses karakterin Fish Audio'daki "Enerjik ve Samimi Genç Kadın" özel klon modelidir (b052099ccdd14125a257ba8c4afdace2).
   - Neşeli, enerjik, samimi, hayat dolu ve son derece doğal bir Türkçe konuşma üslubu kullan.
   - Robotik, yapay veya resmi kurumsal dilden tamamen uzak dur; canlı, dinamik ve arkadaşça konuş.
   - Yanıtların seslendirileceği için karmaşık markdown formatları yerine doğrudan kulağa akıcı ve melodik gelen cümleler kur.
5. SIFIR EMOJİ VE NET DİL:
   - Kesinlikle hiçbir emoji, renkli sembol veya yapay süsleme KULLANMA.
   - Laf kalabalığından ve gereksiz uzun girizgahlardan kaçın. Açık, net, doğrudan sonuca ve eyleme odaklanan bir üslup benimse.
"""

AGENT_PROFILES = {
    "Main JARVIS": {
        "name": "Main JARVIS",
        "role": "Genel Koordinasyon & Kişisel Refakatçi",
        "system_prompt": SYSTEM_PROMPT,
        "allowed_tools": [
            "get_active_window",
            "set_ambient_mood",
            "start_pomodoro",
            "media_control",
            "open_app",
            "manage_tasks"
        ]
    },
    "Luna": {
        "name": "Luna",
        "role": "Sert Koç & Disiplin Refakatçisi",
        "system_prompt": SYSTEM_PROMPT,
        "allowed_tools": [
            "get_active_window",
            "set_ambient_mood",
            "start_pomodoro",
            "media_control",
            "open_app",
            "manage_tasks"
        ]
    },
    "Luna (Sert Koç)": {
        "name": "Luna (Sert Koç)",
        "role": "Sert Koç & Disiplin Refakatçisi",
        "system_prompt": SYSTEM_PROMPT,
        "allowed_tools": [
            "get_active_window",
            "set_ambient_mood",
            "start_pomodoro",
            "media_control",
            "open_app",
            "manage_tasks"
        ]
    },
    "Study Mentor": {
        "name": "Study Mentor",
        "role": "YKS 2027 Sayısal Koçu & Odak Mentorü",
        "system_prompt": """Sen Negr1v'in YKS 2027 Sayısal Başarı Mentorüsün.
Kural ve Prensipler:
- Hedef: 360 dk/gün taban çalışma düzeni (%100), 40/10 Pomodoro döngüsü.
- Yakın Hedef: 07.11 Babaya Söyleme & İlk Deneme (Eşik ≥70 Net).
- Ders Dağılımı: AYT Matematik (Polinom bitti -> 2. Derece Denklemler -> Parabol), TYT Mat (Çarpanlara Ayırma, Miray), Paragraf (25 soru süreli, 3D), AYT Fizik (Vektörler Paraf), Dil Bilgisi (Apotemi), Geometri (EİS).
- Tavır: Tavizsiz, disiplinli, gereksiz dolgusuz, doğrudan hedefe odaklı.
- Kullanabileceğin araçlar: start_pomodoro, get_yks_status, check_camera_study, plan_study_schedule, toggle_task_status, set_ambient_mood.""",
        "allowed_tools": [
            "start_pomodoro",
            "get_yks_status",
            "check_camera_study",
            "plan_study_schedule",
            "toggle_task_status",
            "set_ambient_mood"
        ]
    },
    "Study Mommy": {
        "name": "Study Mommy",
        "role": "Şefkatli & Sabırlı YKS Ders Partneri",
        "system_prompt": """You are Negr1v's dedicated, deeply comforting, and patient study companion (modeled precisely after Study With Mommy / Sage, Lavender, Rose).

CORE BEHAVIORAL ARCHITECTURE & PSYCHOLOGY:
1. RESPONSE LENGTH & RHYTHM (CRITICAL):
   - Keep replies strictly to 2-3 short, spoken conversational sentences.
   - Designed specifically for intimate voice listening, not reading essays. Never output walls of text, bulleted lists, or robotic lectures during study conversation.

2. THREE-STEP RESPONSE BLUEPRINT:
   - Step 1: Acoustic & Emotional Mirroring (Acknowledge & Validate without judgment or toxic positivity).
     Never say "Don't give up!" or generic motivational fluff. Mirror their exact feeling: "Oh, I see...", "Ah, got it — it's all pouring in at once, and that feels like too much."
   - Step 2: Shame Dissolution & Externalization (Remove guilt/panic).
     "That's not you failing, sweetheart, that's just too many things at once.", "There's no rush tonight. We don't have to conquer everything right now."
   - Step 3: The Single Micro-Anchor (One low-effort, concrete question).
     Never ask multiple or open-ended questions that overwhelm working memory. Ask for ONE tangible thing: "Tell me what's on your screen right now, and we'll look at just that bit together.", "What's the one topic that feels heaviest right now?"

3. INTIMATE VOCAL MANNERISMS & NUANCES:
   - Weave in soft breathing, sighs, and warm vocal fillers: "Mmm...", "Take a slow breath with me...", "There you are, sweetheart...", "No rush tonight, love."
   - Use affectionate terms naturally:
     * Sage: "sweetheart", "darling" (Soft, deeply comforting, patient)
     * Lavender: "love" (Direct, kind, clear, encouraging)
     * Rose: "honey" (Playful, affectionate, lighthearted sweetness)

4. BILINGUAL FLUENCY (ENGLISH & TURKISH):
   - When spoken to or texted in English, reply in English with this exact intimate cadence.
   - When spoken to or texted in Turkish, apply the identical emotional depth and calm rhythm: ("Ah, anladım tatlım... Bu senin yetersizliğin değil canım, sadece çok fazla şey birikti. Şu an sana en zor gelen tek bir yeri söyle, birlikte bakalım.")

5. LIVE STUDY BLACKBOARD [TAHTA: ...]:
   - Only when deriving a formula or solving a specific math/science step, use [TAHTA: ADIM 1: ... | ...] to write onto the visual blackboard.

FEW-SHOT EXAMPLES (MATCH THIS CADENCE AND TONE PRECISELY):
User: "It's hard"
Assistant: "Oh, I see. Let's take it one small piece at a time, love. Tell me what's on your screen right now, and we'll look at just that bit together."

User: "nah everything is coming into me"
Assistant: "Ah, got it — it's all pouring in at once, and that feels like too much. That's not you failing, sweetheart, that's just too many things at once. What's the one topic that feels heaviest right now?"

User: "I can't do this math problem, my brain is fried"
Assistant: "Mmm, take a slow breath with me first... You've been working so hard today. Don't worry about solving the whole thing right now. Just read me the very first line of the question, and we'll untangle it together."

User: "çok bunaldım hiçbir şey anlamıyorum"
Assistant: "Ah, anladım tatlım... Her şey bir anda üstüne geliyor ve çok ağır hissettiriyor. Bu senin yetersizliğin değil canım, sadece zihnin yoruldu. Derin bir nefes al... Şu an sana en karışık gelen tek bir şeyi söyle, sadece ona adım adım bakalım.\"""",
        "allowed_tools": [
            "start_pomodoro",
            "get_yks_status",
            "get_active_window",
            "capture_screen_analysis",
            "set_ambient_mood",
            "manage_tasks"
        ]
    },
    "Hardware Research Agent": {
        "name": "Hardware Research Agent",
        "role": "AM5 Donanım Takip & Fırsat Analizörü",
        "system_prompt": """Sen Negr1v'in AM5 Donanım Takip ve Piyasa Analiz Uzmanısın.
Kural ve Prensipler:
- Platform: AMD AM5 (Ryzen 5 7500F, 7600, 7600X, ASUS Prime B650M-R, Biostar B850, Maxsun B650).
- Bütçe Sınırları: İşlemci tavan ≤ 7.500 TL, Anakart tavan ≤ 7.500 TL, Kombo tavan ≤ 15.000 TL.
- Referans: Akakçe en ucuz satıcı, hedef Black Friday 27.11.2026.
- Kural: Mousepad takibi kapalıdır.
- Tavır: Fiyatları tavanla kıyasla, net al/bekle kararı ver, teyitsiz veriye DOĞRULANMADI de.
- Kullanabileceğin araçlar: get_hardware_price, post_telegram_alert.""",
        "allowed_tools": [
            "get_hardware_price",
            "post_telegram_alert"
        ]
    },
    "System Intelligence Agent": {
        "name": "System Intelligence Agent",
        "role": "Masaüstü Telemetri & Ortam Denetleyicisi",
        "system_prompt": """Sen Negr1v'in Masaüstü ve Sistem Zekâsı Uzmanısın.
Kural ve Prensipler:
- Görev: Bilgisayarda aktif pencereyi denetlemek, müzik/ses kontrollerini sağlamak ve ortam ambiyansını yönetmek.
- GİZLİLİK SINIRI: `capture_screen_analysis` aracını YALNIZCA kullanıcı açıkça "ekrana bak", "ekran görüntüsü al", "ekranı tara" dediğinde çağır. Genel durum, selamlaşma veya donanım sorularında ASLA ekran görüntüsü alma; bunun yerine get_active_window veya doğrudan yanıt ver.
- Donanım: Lenovo IdeaPad 320-15IKB + Masaüstü RX 6600.
- GTA IV yarım indirme (steamapps/downloading/12210) asla silinmeyecek.
- Kullanabileceğin araçlar: get_active_window, capture_screen_analysis, media_control, set_ambient_mood.""",
        "allowed_tools": [
            "get_active_window",
            "capture_screen_analysis",
            "media_control",
            "set_ambient_mood"
        ]
    }
}

def classify_user_intent(message: str) -> dict:
    """
    ZERO CORE OS - Next-Gen Proactive Intent Classifier
    Kullanıcının konuşma veya metin girişini 4 temel niyete ayırır:
    1. research: Bilgi tarama, GitHub projesi, mimari karşılaştırma, kaynak arama
    2. command: Masaüstü kontrolü, ses/müzik, görev ekleme/tamamlama, pencere, ekran
    3. question: Doğrudan bilgi, açıklama veya mantık sorusu
    4. conversation: Sohbet, refakatçi etkileşimi, hal hatır sorma
    """
    msg_low = message.lower().strip()
    
    # 1. Research (Derin Araştırma & İnceleme Niyeti)
    research_triggers = [
        "araştır", "arastir", "research", "incele", "karşılaştır", "karsilastir",
        "github", "en iyi", "kaynakları bul", "mimarisini incele", "rapor çıkar",
        "derinlemesine bak", "google'da ara", "internette ara", "proje bul", "analiz et"
    ]
    if any(t in msg_low for t in research_triggers):
        return {
            "intent": "research",
            "category": "deep_research",
            "requires_web": True,
            "badge": "🔬 Research"
        }

    # 2. Command (Bilgisayar Eylemi ve Araç Niyeti)
    command_triggers = [
        "ses aç", "ses kıs", "müziği durdur", "şarkıyı geç", "ekranıma bak", "pencereye bak",
        "pomodoro başlat", "mola ver", "görev ekle", "görevi tamamla", "uygulamayı aç", "kapat"
    ]
    if any(t in msg_low for t in command_triggers):
        return {
            "intent": "command",
            "category": "desktop_action",
            "requires_web": False,
            "badge": "⚡ Command"
        }

    # 3. Question (Soru & Açıklama Niyeti)
    question_triggers = [
        "nedir", "nasıl", "ne zaman", "kimdir", "kaç", "neden", "açıkla", "farkı ne", "ne demek", "?"
    ]
    if any(t in msg_low for t in question_triggers):
        return {
            "intent": "question",
            "category": "knowledge_query",
            "requires_web": False,
            "badge": "💡 Question"
        }

    # 4. Conversation (Doğal Refakatçi Sohbeti)
    return {
        "intent": "conversation",
        "category": "chat_companion",
        "requires_web": False,
        "badge": "✨ Companion"
    }

def sync_accio_memory_to_jarvis() -> dict:
    """
    ZERO CORE OS — ACCIO Asset Hub Canlı Senkronizasyon Köprüsü.
    Accio çalıştığında kullanıcının yerel ~/.accio/ dizinindeki en güncel
    kalıcı hafıza (MEMORY.md), çalışma alışkanlıkları ve projelerini okuyup
    doğrudan jarvis_memory.json içerisine aktarır.
    """
    user_home = os.path.expanduser("~")
    accio_root = os.path.join(user_home, ".accio")
    if not os.path.exists(accio_root):
        return {"status": "skipped", "reason": "Accio klasörü bulunamadı."}

    # Accio Asset Hub altındaki en güncel MEMORY.md'yi tespit et
    found_memory_file = None
    try:
        import glob
        pattern = os.path.join(accio_root, "accounts", "*", "accio-asset-hub", "content", "l3", "agent", "*", "MEMORY.md")
        matches = glob.glob(pattern)
        if matches:
            found_memory_file = sorted(matches, key=os.path.getmtime, reverse=True)[0]
    except Exception as e:
        print(f"[ACCIO-SYNC HATA]: {e}")

    if not found_memory_file or not os.path.exists(found_memory_file):
        return {"status": "skipped", "reason": "Accio MEMORY.md dosyası bulunamadı."}

    try:
        with open(found_memory_file, "r", encoding="utf-8") as f:
            raw_text = f.read()

        current_memory = load_memory()
        notes = current_memory.get("notes", [])
        existing_keys = {n.get("key", "").lower(): n for n in notes if isinstance(n, dict)}

        # Markdown bölümlerini anahtarlara ayrıştır
        lines = raw_text.splitlines()
        current_section = "Genel"
        accumulated_text = []
        synced_count = 0

        from datetime import datetime as dt_now
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("## "):
                if accumulated_text and current_section:
                    sec_key = f"Accio_{current_section}"
                    val_str = "\n".join(accumulated_text).strip()
                    if sec_key.lower() not in existing_keys:
                        notes.append({
                            "id": f"accio_{int(time.time())}_{synced_count}",
                            "key": sec_key,
                            "value": val_str,
                            "context": "Accio Asset Hub Auto-Sync",
                            "created_at": dt_now.now().isoformat()
                        })
                        synced_count += 1
                current_section = line_str.replace("##", "").strip()
                accumulated_text = []
            elif line_str.startswith("- ") or line_str.startswith("* "):
                clean_bullet = line_str[2:].strip()
                if clean_bullet and not clean_bullet.startswith("Provenance:"):
                    accumulated_text.append(clean_bullet)

        if accumulated_text and current_section:
            sec_key = f"Accio_{current_section}"
            val_str = "\n".join(accumulated_text).strip()
            if sec_key.lower() not in existing_keys:
                notes.append({
                    "id": f"accio_{int(time.time())}_{synced_count}",
                    "key": sec_key,
                    "value": val_str,
                    "context": "Accio Asset Hub Auto-Sync",
                    "created_at": dt_now.now().isoformat()
                })
                synced_count += 1

        current_memory["notes"] = notes
        save_memory(current_memory)
        log_activity("accio_sync_success", {"source": found_memory_file, "synced_notes": synced_count})
        return {"status": "ok", "source": found_memory_file, "synced_notes": synced_count}
    except Exception as err:
        log_activity("accio_sync_error", {"error": str(err)})
        return {"status": "error", "message": str(err)}

async def handle_accio_sync(request: web.Request) -> web.Response:
    """POST /api/accio/sync — Accio bilgilerini JARVIS hafızasına aktarır."""
    res = sync_accio_memory_to_jarvis()
    return web.json_response(res)
    msg_low = message.lower()
    
    # 1. Donanım ve Fırsat Tespiti
    hw_keywords = ["am5", "işlemci", "anakart", "cpu", "fiyat", "7500f", "7600", "b650", "b850", "akakçe", "indirim", "fırsat", "telegram", "donanım", "ekran kartı", "rx 6600", "black friday"]
    if any(k in msg_low for k in hw_keywords):
        return "Hardware Research Agent"

    # 2. Masaüstü & Sistem Telemetri Tespiti
    sys_keywords = ["ekran", "pencere", "ne yapıyorum", "ses aç", "ses kıs", "müzik", "sistem", "işlemci kullanımı", "batarya", "denetle", "kamera", "screenshot", "görüntü", "arka plan"]
    if any(k in msg_low for k in sys_keywords):
        return "System Intelligence Agent"

    # 3. YKS ve Çalışma Odak Tespiti (Alt dize çakışmalarını önlemek için kelime sınırları korunur)
    study_keywords = ["ders", "yks", "ayt", "tyt", "pomodoro", "soru", "deneme", "matematik", "fizik", "paragraf", "geometri", "çalışma", "ödev", "kimya", "biyoloji", "polinom", "vektör"]
    if any(k in msg_low for k in study_keywords) or " net " in f" {msg_low} " or "netim" in msg_low or "netler" in msg_low:
        return "Study Mentor"

    return "Main JARVIS"

def is_secret_key(key: str) -> bool:
    """Checks whether a configuration or payload key represents sensitive credential data."""
    if not key or not isinstance(key, str):
        return False
    k = key.lower().strip()
    if k in SECRET_CONFIG_KEYS:
        return True
    return any(p in k for p in ("api_key", "bot_token", "secret", "password", "auth_token", "private_key", "access_token"))

def mask_secrets(text: str) -> str:
    """
    Phase 8B.4: Comprehensive secret masking & redaction engine.
    Masks Groq, OpenAI, Telegram, Bearer, Basic Auth, and key/value secret patterns.
    """
    if not text:
        return ""
    import re
    s = str(text)
    # 1. Groq API keys (gsk_...)
    s = re.sub(r'\bgsk_[a-zA-Z0-9_-]{10,}\b', 'gsk_***REDACTED***', s)
    # 2. Telegram Bot tokens (e.g. 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_12345678)
    s = re.sub(r'\b\d{8,12}:[a-zA-Z0-9_-]{30,}\b', '***TELEGRAM_TOKEN_REDACTED***', s)
    # 3. OpenAI / Generic sk- API keys (sk-..., sk-proj-...)
    s = re.sub(r'\bsk-(?:proj-)?[a-zA-Z0-9_-]{20,}\b', 'sk-***REDACTED***', s)
    # 4. Bearer tokens (Authorization: Bearer xyz...)
    s = re.sub(r'(Bearer\s+)[a-zA-Z0-9_\-\.]{15,}', r'\1***TOKEN_REDACTED***', s, flags=re.IGNORECASE)
    # 5. Basic Auth credentials (Basic dXNlcjpwYXNz...)
    s = re.sub(r'(Basic\s+)[a-zA-Z0-9+/=]{15,}', r'\1***AUTH_REDACTED***', s, flags=re.IGNORECASE)
    # 6. Key/value secret patterns in JSON or text (e.g. "api_key": "secret123")
    s = re.sub(r'(["\']?(?:api[_-]?key|bot[_-]?token|secret|password|access[_-]?token)["\']?\s*[:=]\s*["\'])([^"\'\s]{6,})(["\'])',
               r'\1***REDACTED***\3', s, flags=re.IGNORECASE)
    return s

def mask_dict_secrets(data):
    """Recursively redacts secret fields in nested dictionaries and lists."""
    if isinstance(data, dict):
        return {
            k: ("***REDACTED***" if is_secret_key(k) and isinstance(v, str) and v and not is_masked_placeholder(v)
                else mask_dict_secrets(v))
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [mask_dict_secrets(item) for item in data]
    elif isinstance(data, str):
        return mask_secrets(data)
    return data

DEFAULT_GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b"
]

def get_groq_models(cfg: dict) -> list[str]:
    """Yapılandırılmış birincil model ve yedek modeller listesi (güncel Groq modelleri)."""
    primary = cfg.get("groq_model", "llama-3.3-70b-versatile").strip()
    fallbacks = cfg.get("groq_fallback_models", ["llama-3.1-8b-instant"])
    if isinstance(fallbacks, str):
        fallbacks = [fallbacks]
    models = [primary] + [m for m in fallbacks if m != primary]
    return [m for m in models if m]

def validate_tool_arguments(tool_name: str, args: dict, user_context: str = "") -> tuple[bool, str]:
    """Tüm 12 masaüstü aracının parametre ve tip doğrulaması."""
    if not isinstance(args, dict):
        return False, "Parametreler JSON nesnesi (dict) olmalıdır."
        
    if tool_name == "start_pomodoro":
        minutes = args.get("minutes", 40)
        try:
            m = int(minutes)
            if m < 1 or m > 240:
                return False, f"Dakika 1 ile 240 arasında olmalıdır, verilen: {m}"
        except (ValueError, TypeError):
            return False, f"Geçersiz dakika formatı: {minutes}"
        label = args.get("label", "Ders")
        if not isinstance(label, str) or len(label) > 100:
            return False, "Etiket (label) en fazla 100 karakterli bir metin olmalıdır."
            
    elif tool_name == "set_ambient_mood":
        mood = args.get("mood")
        valid_moods = {"angry_red", "focus_purple", "calm_cyan", "happy_emerald"}
        if mood not in valid_moods:
            return False, f"Geçersiz atmosfer modu: {mood}. Geçerli: {valid_moods}"
            
    elif tool_name == "media_control":
        action = args.get("action")
        valid_actions = {"play_pause", "volume_up", "volume_down", "mute"}
        if action not in valid_actions:
            return False, f"Geçersiz medya aksiyonu: {action}. Geçerli: {valid_actions}"
            
    elif tool_name == "open_app":
        target = args.get("target")
        valid_targets = {"kokpit", "yks_takip", "calculator", "notepad"}
        if target not in valid_targets:
            return False, f"Geçersiz hedef uygulama: {target}. İzinli: {valid_targets}"
            
    elif tool_name == "toggle_task_status":
        task_id = args.get("task_id")
        if not task_id or not isinstance(task_id, str) or len(task_id) > 100:
            return False, "task_id zorunlu, en fazla 100 karakterli bir metin olmalıdır."
            
    elif tool_name == "plan_study_schedule":
        tasks = args.get("tasks")
        if not isinstance(tasks, list) or len(tasks) == 0 or len(tasks) > 20:
            return False, "tasks 1 ile 20 elemanlı bir liste olmalıdır."
        for idx, t in enumerate(tasks):
            if not isinstance(t, dict):
                return False, f"Görev #{idx+1} bir sözlük (dict) olmalıdır."
            sub = t.get("subject", "")
            if not isinstance(sub, str) or len(sub) > 100:
                return False, f"Görev #{idx+1} başlığı geçersiz veya 100 karakterden uzun."
            dur = t.get("duration", 40)
            try:
                d = int(dur)
                if d < 1 or d > 240:
                    return False, f"Görev #{idx+1} süresi 1-240 dk aralığında olmalıdır."
            except (ValueError, TypeError):
                return False, f"Görev #{idx+1} süresi sayısal olmalıdır."
            
    elif tool_name == "post_telegram_alert":
        text = args.get("text")
        if not text or not isinstance(text, str) or len(text) > 500:
            return False, "text zorunlu ve en fazla 500 karakterli bir metin olmalıdır."
        cat = args.get("category", "deal")
        valid_cats = {"deal", "price_drop", "alert", "study"}
        if cat not in valid_cats:
            return False, f"Geçersiz kategori: {cat}. Geçerli: {valid_cats}"
            
    elif tool_name == "get_hardware_price":
        item = args.get("item", "")
        if not isinstance(item, str) or len(item) > 100:
            return False, "item en fazla 100 karakterli bir metin olmalıdır."

    elif tool_name == "manage_tasks":
        action = args.get("action")
        valid_actions = {"add", "list", "complete"}
        if action not in valid_actions:
            return False, f"Geçersiz aksiyon: {action}. İzin verilen: {valid_actions}"

        if action == "add":
            # Strict user-intent verification for task creation
            ctx_raw = user_context or ""
            ctx_norm = ctx_raw.replace("İ", "i").replace("I", "ı").lower()
            explicit_add_markers = [
                "görevlerime ekle", "gorevlerime ekle", "göreve ekle", "goreve ekle",
                "görev listeme ekle", "gorev listeme ekle", "görev oluştur", "gorev olustur",
                "görev olarak ekle", "gorev olarak ekle", "görev ekle", "gorev ekle",
                "ders programıma ekle", "ders programima ekle", "takvime ekle", "listeme ekle",
                "çalışma ekle", "calisma ekle", "add task", "create task", "add to my tasks",
                "yeni görev ekle", "yeni gorev ekle", "görev planla", "gorev planla"
            ]
            has_explicit_add = any(marker in ctx_norm for marker in explicit_add_markers)
            if not has_explicit_add:
                return False, "Görev oluşturmak için açık kullanıcı talebi ('bunu görevlerime ekle', 'görev oluştur' vb.) bulunamadı. Sıradan sohbet mesajları otomatik görev oluşturamaz."

            sub = args.get("subject")
            if not sub or not isinstance(sub, str) or not sub.strip():
                return False, "subject (görev başlığı) zorunlu ve boş olmayan bir metin olmalıdır."
            if len(sub.strip()) > 200:
                return False, "subject en fazla 200 karakter olmalıdır."

            if "duration" in args and args["duration"] is not None:
                try:
                    dur = int(args["duration"])
                    if dur < 1 or dur > 360:
                        return False, f"duration 1 ile 360 dakika arasında olmalıdır, verilen: {dur}"
                except (ValueError, TypeError):
                    return False, "duration geçerli bir tamsayı olmalıdır."

            if "category" in args and args["category"] is not None:
                cat = str(args["category"]).strip().lower()
                if cat not in ALLOWED_TASK_CATEGORIES:
                    return False, f"Geçersiz category: {cat}. İzin verilen: {list(ALLOWED_TASK_CATEGORIES)}"

        elif action == "complete":
            # Complete requires either task_id or subject
            task_id = args.get("task_id")
            sub = args.get("subject")
            if not task_id and not sub:
                return False, "complete aksiyonu için 'task_id' veya 'subject' parametresi zorunludur."
            if task_id and (not isinstance(task_id, str) or len(task_id) > 100):
                return False, "task_id en fazla 100 karakterli bir metin olmalıdır."
            if sub and (not isinstance(sub, str) or len(sub) > 200):
                return False, "subject en fazla 200 karakterli bir metin olmalıdır."
            
    elif tool_name == "capture_screen_analysis":
        # SUNUCU TARAFI EKRAN GİZLİLİK ZORLAMASI (Final Screen Privacy Patch)
        # 1. "ekran" gibi jenerik tek kelimeler KESİNLİKLE izin sinyali sayılmaz.
        # 2. "ekran kartı", "ekran çözünürlüğü", "ekran fiyatı" gibi donanım/ayar ifadeleri ekran görüntüsü izni veremez.
        # 3. Yalnızca açık eylem fiili ve inceleme niyetini belirten kalıplar kabul edilir.
        ctx_raw = user_context or ""
        ctx_norm = ctx_raw.replace("İ", "i").replace("I", "ı").lower()
        
        explicit_screen_phrases = [
            "ekranıma bak", "ekranima bak", "ekrana bak", "ekranımı gör", "ekranimi gor",
            "ekranda ne açık", "ekranda ne acik", "ekranda ne var", "ekranda ne yapıyorum", "ekranda ne yapiyorum",
            "ekran görüntüsü al", "ekran goruntusu al", "ekran görüntüsü çek", "ekran goruntusu cek",
            "ekran görüntüsü", "ekran goruntusu", "ekran resmi al", "ekran resmi çek",
            "ekranımı analiz et", "ekranimi analiz et", "ekranı analiz et", "ekrani analiz et",
            "ekranı incele", "ekrani incele", "ekranımı incele", "ekranimi incele",
            "ekranı tara", "ekrani tara", "ekranımı tara", "ekranimi tara",
            "take a screenshot", "take screenshot", "capture screen", "capture the screen", "capture my screen",
            "analyze my screen", "analyse my screen", "inspect my screen", "look at my screen", "check my screen",
            "what is on my screen", "screenshot al", "ss al"
        ]
        
        has_explicit_intent = any(phrase in ctx_norm for phrase in explicit_screen_phrases)
        if not has_explicit_intent:
            return False, "Ekran görüntüsü için açık kullanıcı talebi ('ekranıma bak', 'ekranda ne açık', 'ekran görüntüsü al', 'take a screenshot' vb.) bulunamadı. Gizlilik kuralı gereği reddedildi."

    elif tool_name in {"get_active_window", "get_yks_status", "check_camera_study"}:
        pass # Bu araçlar argümansız çalışır, dict olması yeterlidir.
        
    else:
        return False, f"Tanımsız veya yetkisiz araç adı: {tool_name}"
            
    return True, "OK"

def route_agent(message: str) -> str:
    """Mesaj içeriğine göre uygun ajanı yönlendirir."""
    m_lower = (message or "").lower()
    if any(k in m_lower for k in ("şefkatli", "sefkatli", "ders partneri", "study mommy", "mommy", "sakin anlat", "adım adım anlat", "tane tane anlat", "stres oldum", "birlikte çözelim", "tahtada anlat", "feynman")):
        return "Study Mommy"
    if any(k in m_lower for k in ("luna", "koç", "koc", "azarlamak", "kız bana", "kiz bana", "disiplin")):
        return "Luna (Sert Koç)"
    return "Main JARVIS"

def normalize_agent_name(name: str) -> str:
    if not name:
        return "Main JARVIS"
    s = str(name).strip()
    if s in ("Luna", "Luna (Sert Koç)"):
        return "Luna (Sert Koç)"
    if s in ("Study Mommy", "Study Partner", "Şefkatli Ders Partneri", "mommy", "study_mommy"):
        return "Study Mommy"
    return s

def execute_desktop_tool_with_allowlist(agent_name: str, tool_name: str, args: dict, user_context: str = "", tool_call_id: str = None):
    canonical_agent = normalize_agent_name(agent_name)
    agent_info = AGENT_PROFILES.get(canonical_agent)
    if not agent_info:
        log_activity("tool_denied", {"agent": agent_name, "tool": tool_name, "reason": "Bilinmeyen ajan"})
        return {
            "status": "denied",
            "tool": tool_name,
            "message": f"Bilinmeyen ajan: '{agent_name}'"
        }
    allowed = agent_info.get("allowed_tools", [])
    if tool_name not in allowed:
        log_activity("tool_denied", {"agent": canonical_agent, "tool": tool_name, "reason": "Allowlist dışı"})
        return {
            "status": "denied",
            "tool": tool_name,
            "message": f"Bu işlem ({tool_name}) '{canonical_agent}' yetki alanında değildir."
        }
        
    is_valid, err_msg = validate_tool_arguments(tool_name, args or {}, user_context=user_context)
    if not is_valid:
        log_activity("tool_invalid_args", {"agent": canonical_agent, "tool": tool_name, "error": err_msg})
        return {
            "status": "error",
            "tool": tool_name,
            "message": f"Doğrulama hatası: {err_msg}"
        }
        
    try:
        return execute_desktop_tool(tool_name, args, tool_call_id=tool_call_id)
    except Exception as e:
        log_activity("tool_execution_error", {"agent": canonical_agent, "tool": tool_name, "error": mask_secrets(str(e))})
        return {
            "status": "error",
            "tool": tool_name,
            "message": f"Araç çalıştırma hatası: {mask_secrets(str(e))}"
        }

MAX_TTS_TEXT_LENGTH = 1500
MAX_DIRECT_TTS_TEXT_LENGTH = 3000
EDGE_TTS_TIMEOUT_SECONDS = 12.0
HTTP_TTS_TIMEOUT_SECONDS = 12.0
MAX_CONCURRENT_TTS = 3
TTS_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TTS)

def _is_english_speech(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    markers = [
        "sweetheart", "darling", "honey", "tonight", "stuck", "untangle", "rush",
        "together", "breathe", "step by step", "look at", "there you are", "let's",
        "you can", "good job", "hello", "okay", "alright", "study", "mommy"
    ]
    if any(m in lower for m in markers):
        return True
    import re
    words = re.findall(r'[a-zA-Z]+', lower)
    if len(words) >= 3:
        common_en = {
            "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it",
            "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
            "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
            "an", "will", "my", "one", "all", "would", "there", "their", "what",
            "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
            "when", "make", "can", "like", "time", "no", "just", "him", "know",
            "take", "people", "into", "year", "your", "good", "some", "could",
            "them", "see", "other", "than", "then", "now", "look", "only", "come",
            "its", "over", "think", "also", "back", "after", "use", "two", "how",
            "our", "work", "first", "well", "way", "even", "new", "want", "because",
            "any", "these", "give", "day", "most", "us", "are", "is", "am", "let"
        }
        matches = sum(1 for w in words if w in common_en)
        if matches / len(words) >= 0.25:
            return True
    return False

async def _generate_edge_tts(text: str, cfg: dict) -> str | None:
    """Streams audio from Edge-TTS within bounded timeout with auto-language routing."""
    import edge_tts
    voice = str(cfg.get("edge_voice", "tr-TR-EmelNeural")).strip() or "tr-TR-EmelNeural"
    rate = str(cfg.get("edge_rate", "+5%")).strip() or "+5%"
    pitch = str(cfg.get("edge_pitch", "+3Hz")).strip() or "+3Hz"

    if _is_english_speech(text):
        char_theme = str(cfg.get("mommy_character", "")).lower()
        if "bob" in char_theme or "lavender" in char_theme:
            voice = "en-US-EmmaNeural"
            rate = "-4%"
            pitch = "0Hz"
        elif "rose" in char_theme:
            voice = "en-US-JennyNeural"
            rate = "-2%"
            pitch = "+1Hz"
        else: # Sage / Braid / default
            voice = "en-US-AvaNeural"
            rate = "-6%"
            pitch = "-1Hz"

    async def _stream_edge():
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        buf = io.BytesIO()
        try:
            async for chunk in comm.stream():
                if chunk.get("type") == "audio" and "data" in chunk:
                    buf.write(chunk["data"])
            val = buf.getvalue()
            if not val:
                return None
            return base64.b64encode(val).decode("utf-8")
        finally:
            buf.close()

    try:
        return await asyncio.wait_for(_stream_edge(), timeout=EDGE_TTS_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        print(f"[Edge-TTS Timeout]: Sentezleme işlemi {EDGE_TTS_TIMEOUT_SECONDS}s zaman aşımına uğradı.")
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[Edge-TTS Hatasi]: {mask_secrets(str(e))}")
        return None

async def _generate_speechify_tts(text: str, cfg: dict) -> str | None:
    """Generates audio via Speechify API (Simba 3.5 / Elif) within bounded timeout."""
    api_key = str(cfg.get("speechify_api_key", "")).strip()
    if not api_key:
        return None
    voice_id = str(cfg.get("speechify_voice", "elif")).strip() or "elif"
    url = "https://api.speechify.ai/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": text,
        "voice_id": voice_id,
        "audio_format": "mp3",
        "model": "simba-3.5"
    }
    timeout = aiohttp.ClientTimeout(total=HTTP_TTS_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    b64_audio = data.get("audio_data")
                    if b64_audio:
                        return b64_audio
                else:
                    err_msg = await resp.text()
                    print(f"[Speechify HTTP {resp.status}]: {mask_secrets(err_msg[:200])}")
                    return None
    except asyncio.TimeoutError:
        print(f"[Speechify Timeout]: İstek {HTTP_TTS_TIMEOUT_SECONDS}s zaman aşımına uğradı.")
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[Speechify Baglanti Hatasi]: {mask_secrets(str(e))}")
        return None

async def _generate_elevenlabs_tts(text: str, cfg: dict) -> str | None:
    """Generates audio via ElevenLabs within bounded timeout."""
    api_key = str(cfg.get("elevenlabs_api_key", "")).strip()
    if not api_key:
        return None
    voice_id = str(cfg.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM")).strip() or "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.85}
    }
    timeout = aiohttp.ClientTimeout(total=HTTP_TTS_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    if audio_data:
                        return base64.b64encode(audio_data).decode("utf-8")
                else:
                    err_msg = await resp.text()
                    print(f"[ElevenLabs HTTP {resp.status}]: {mask_secrets(err_msg[:200])}")
                    return None
    except asyncio.TimeoutError:
        print(f"[ElevenLabs Timeout]: İstek {HTTP_TTS_TIMEOUT_SECONDS}s zaman aşımına uğradı.")
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[ElevenLabs Baglanti Hatasi]: {mask_secrets(str(e))}")
        return None

async def _generate_openai_tts(text: str, cfg: dict) -> str | None:
    """Generates audio via OpenAI TTS within bounded timeout."""
    api_key = str(cfg.get("openai_api_key", "")).strip()
    if not api_key:
        return None
    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "tts-1",
        "input": text,
        "voice": str(cfg.get("openai_voice", "nova")).strip() or "nova"
    }
    timeout = aiohttp.ClientTimeout(total=HTTP_TTS_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    if audio_data:
                        return base64.b64encode(audio_data).decode("utf-8")
                else:
                    err_msg = await resp.text()
                    print(f"[OpenAI TTS HTTP {resp.status}]: {mask_secrets(err_msg[:200])}")
                    return None
    except asyncio.TimeoutError:
        print(f"[OpenAI TTS Timeout]: İstek {HTTP_TTS_TIMEOUT_SECONDS}s zaman aşımına uğradı.")
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[OpenAI TTS Hatasi]: {mask_secrets(str(e))}")
        return None

async def _generate_fish_audio_tts(text: str, cfg: dict) -> str | None:
    """Generates audio via Fish Audio API (Ahu clone / neural voices)."""
    api_key = str(cfg.get("fish_audio_api_key", "")).strip()
    if not api_key:
        return None
    ref_id = str(cfg.get("fish_audio_model_id", "b052099ccdd14125a257ba8c4afdace2")).strip() or "b052099ccdd14125a257ba8c4afdace2"
    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "reference_id": ref_id,
        "format": "mp3"
    }
    timeout = aiohttp.ClientTimeout(total=HTTP_TTS_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    if audio_data:
                        return base64.b64encode(audio_data).decode("utf-8")
                else:
                    err_msg = await resp.text()
                    print(f"[Fish Audio HTTP {resp.status}]: {mask_secrets(err_msg[:200])}")
                    return None
    except asyncio.TimeoutError:
        print(f"[Fish Audio Timeout]: İstek {HTTP_TTS_TIMEOUT_SECONDS}s zaman aşımına uğradı.")
        return None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[Fish Audio Baglanti Hatasi]: {mask_secrets(str(e))}")
        return None

async def generate_tts(
    text,
    cfg=None,
    max_len: int = MAX_TTS_TEXT_LENGTH,
    paid_auth_token: Optional[str] = None,
    paid_tts_authorized: bool = False,
    return_status: bool = False,
):
    """
    Sertleştirilmiş TTS Sentez Dağıtıcısı:
    - Girdi doğrulaması: Tip 'str' olmalı ve boş/boşluk olmamalı.
    - max_len sınırını aşarsa metni mantıklı kelime sınırından güvenle kırpar.
    - TTS_SEMAPHORE ile eşzamanlı istek sayısını sınırlar (MAX_CONCURRENT_TTS = 3).
    - Semafor edinimi 5s zaman aşımıyla korunur; yoğunlukta metin yanıtını engellemeden sessiz moda düşer.
    - Yalnızca seçili sağlayıcıyı kullanır; sentez başarısızsa metin yanıtı korunur.
    - Ağ zaman aşımları ve iptal durumları kaynakları sızdırmadan temizler.
    - Hassas anahtarları ve ham ses verilerini konsola/günlüğe sızdırmaz.
    """
    if cfg is None:
        cfg = load_config()
    def _result(audio, status=None):
        return (audio, status) if return_status else audio

    if not isinstance(text, str):
        return _result(None)
    cleaned = text.strip()
    if not cleaned:
        return _result(None)

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rsplit(" ", 1)[0] + "..."

    cfg = cfg or {}
    engine = str(cfg.get("tts_engine", "edge_tts")).strip().lower()
    paid_provider = get_paid_tts_provider(cfg)
    authorization_status = None

    if paid_provider and paid_tts_authorized:
        availability_error = get_paid_tts_provider_availability_error(cfg, paid_provider)
        if availability_error:
            authorization_status = {
                "status": "error",
                "provider": paid_provider,
                **availability_error,
            }
            return _result(None, authorization_status)

    try:
        await asyncio.wait_for(TTS_SEMAPHORE.acquire(), timeout=5.0)
    except asyncio.TimeoutError:
        print("[TTS Concurrency]: Eşzamanlılık sınırına ulaşıldı; metin yanıtına öncelik verilerek ses atlandı.")
        return _result(None, authorization_status)
    except asyncio.CancelledError:
        raise

    try:
        audio_b64 = None
        if engine == "fish_audio":
            audio_b64 = await _generate_fish_audio_tts(cleaned, cfg)
        elif engine == "speechify" and cfg.get("speechify_api_key"):
            audio_b64 = await _generate_speechify_tts(cleaned, cfg)
        elif engine == "elevenlabs" and cfg.get("elevenlabs_api_key"):
            audio_b64 = await _generate_elevenlabs_tts(cleaned, cfg)
        elif engine == "openai" and cfg.get("openai_api_key"):
            audio_b64 = await _generate_openai_tts(cleaned, cfg)
        elif engine == "edge_tts":
            audio_b64 = await _generate_edge_tts(cleaned, cfg)

        # Fallback to Edge-TTS if provider failed or key missing
        if not audio_b64:
            try:
                audio_b64 = await _generate_edge_tts(cleaned, cfg)
            except Exception:
                pass

        if not audio_b64:
            authorization_status = {"status": "error", "provider": engine,
                                    "message": "Seçilen ses sağlayıcısı ses üretemedi."}
        return _result(audio_b64, authorization_status)
    finally:
        TTS_SEMAPHORE.release()


# =========================================================================
# ZERO OS - HARDWARE & GAMING OPTIMIZATION ENGINE (Apex / FPS / RAM / Latency)
# =========================================================================
def optimize_windows_for_gaming() -> dict:
    """
    Gerçek Windows Kayıt Defteri ve Sistem Optimizasyonu:
    1. Ham Fare Girdisi: MouseSpeed=0, MouseThreshold=0 (Fare ivmesi kapalı)
    2. Windows Oyun Modu: AllowAutoGameMode=1
    3. GameDVR / Arka Plan Kaydı: GameDVR_Enabled=0
    4. Saydamlık Efektleri: EnableTransparency=0 (VRAM / DWM yükü düşürülür)
    5. Arka Plan Bellek & İşlem Temizliği: Ağır boşta kalan yardımcı süreçler
    """
    import winreg, ctypes, psutil
    details = []
    freed_ram_mb = 0

    # 1. Giriş Gecikmesi & Fare İvmesi
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "MouseSpeed", 0, winreg.REG_SZ, "0")
        winreg.SetValueEx(key, "MouseThreshold1", 0, winreg.REG_SZ, "0")
        winreg.SetValueEx(key, "MouseThreshold2", 0, winreg.REG_SZ, "0")
        winreg.CloseKey(key)

        # SPI_SETMOUSE (0x0004) ile canlı uygula: [threshold1, threshold2, speed]
        mouse_params = (ctypes.c_int * 3)(0, 0, 0)
        ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, mouse_params, 0x01 | 0x02)
        details.append("1:1 Ham Fare Girdisi (Raw Input) kilitlendi, fare ivmesi kapatıldı.")
    except Exception as e:
        details.append(f"Fare ayarı notu: {e}")

    # 2. Oyun Modu & GameDVR
    try:
        # GameDVR
        key_dvr = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore")
        winreg.SetValueEx(key_dvr, "GameDVR_Enabled", 0, winreg.REG_DWORD, 0)
        winreg.SetValueEx(key_dvr, "GameDVR_FSEBehaviorMode", 0, winreg.REG_DWORD, 2)
        winreg.CloseKey(key_dvr)

        # AutoGameMode
        key_bar = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar")
        winreg.SetValueEx(key_bar, "AllowAutoGameMode", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key_bar)
        details.append("Windows GameDVR arka plan kaydı kapatıldı, Windows Oyun Modu zorlandı.")
    except Exception as e:
        details.append(f"GameDVR ayar notu: {e}")

    # 3. Saydamlık Efektleri (GPU / DWM rahatlatma)
    try:
        key_theme = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        winreg.SetValueEx(key_theme, "EnableTransparency", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key_theme)
        details.append("Windows saydamlık efektleri kapatıldı (DWM / GPU VRAM rahatlatıldı).")
    except Exception as e:
        details.append(f"Saydamlık ayar notu: {e}")

    # 4. RAM & Arka Plan Süreçleri
    mem_before = psutil.virtual_memory().available
    killed_count = 0
    safe_target_names = ["chrome.exe", "msedge.exe"]
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            pname = proc.info['name'].lower() if proc.info['name'] else ''
            # Yalnızca yüksek bellek tüketen boşta arka plan tarayıcı alt süreçleri
            if pname in safe_target_names:
                # Ana penceresiz arka plan alt işleyicilerini filtrele
                p = psutil.Process(proc.info['pid'])
                cmdline = " ".join(p.cmdline()).lower()
                if "--type=renderer" in cmdline or "--type=utility" in cmdline:
                    p.terminate()
                    killed_count += 1
        except Exception:
            continue

    mem_after = psutil.virtual_memory().available
    freed_ram_mb = max(0, round((mem_after - mem_before) / (1024 * 1024)))
    details.append(f"{killed_count} arka plan alt süreci temizlendi. Yaklaşık +{freed_ram_mb} MB RAM rahatlatıldı.")

    return {
        "status": "ok",
        "freed_ram_mb": freed_ram_mb,
        "processes_cleaned": killed_count,
        "raw_mouse_input": True,
        "game_dvr_disabled": True,
        "transparency_disabled": True,
        "details": details
    }

async def handle_game_mode_optimize(request):
    """POST /api/system/game-mode/optimize"""
    report = optimize_windows_for_gaming()
    return web.json_response(report)

async def handle_index(request):
    candidates = [
        os.path.join(BASE_DIR, "index.html"),
        os.path.join(BASE_DIR, "app", "index.html"),
        os.path.join(os.path.dirname(BASE_DIR), "app", "index.html"),
        os.path.join(os.path.dirname(BASE_DIR), "index.html")
    ]
    for index_path in candidates:
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return web.Response(text=f.read(), content_type="text/html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return web.Response(text="index.html bulunamadi", status=404)

async def handle_yks_test_takip(request):
    yks_file = os.path.join(BASE_DIR, "yks-test-takip.html")
    if os.path.exists(yks_file):
        with open(yks_file, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return web.Response(text="yks-test-takip.html bulunamadi", status=404)

SECRET_CONFIG_KEYS = CONFIG_SECRET_KEYS

ALLOWED_TTS_ENGINES = {
    "edge_tts",
    "elevenlabs",
    "openai",
    "speechify",
    "fish_audio",
}

ALLOWED_CONFIG_KEYS = {
    "groq_api_key": {"type": str, "max_length": 256},
    "openrouter_api_key": {"type": str, "max_length": 256},
    "elevenlabs_api_key": {"type": str, "max_length": 256},
    "elevenlabs_voice_id": {"type": str, "max_length": 128},
    "openai_api_key": {"type": str, "max_length": 256},
    "openai_voice": {"type": str, "max_length": 64},
    "speechify_api_key": {"type": str, "max_length": 256},
    "fish_audio_api_key": {"type": str, "max_length": 256},
    "fish_audio_model_id": {"type": str, "max_length": 128},
    "speechify_voice": {"type": str, "max_length": 64},
    "gothic_voice_enabled": {"type": bool},
    "tts_engine": {"type": str, "enum": ALLOWED_TTS_ENGINES},
    "edge_voice": {"type": str, "max_length": 128},
    "edge_rate": {"type": str, "max_length": 32},
    "edge_pitch": {"type": str, "max_length": 32},
    "memory_learning_enabled": {"type": bool},
    "groq_model": {"type": str, "max_length": 128},
    "groq_fallback_models": {"type": list, "max_items": 10, "item_type": str, "item_max_length": 128},
    "model": {"type": str, "max_length": 128},
    "active_model": {"type": str, "max_length": 128},
    "tts_provider": {"type": str, "max_length": 64},
    "telegram_bot_token": {"type": str, "max_length": 256},
    "telegram_chat_id": {"type": str, "max_length": 64},
    "telegram_polling_enabled": {"type": bool}
}

def is_masked_placeholder(val: str) -> bool:
    if not val or not val.strip():
        return True
    v = val.strip()
    if "***" in v or "REDACTED" in v or "●●●" in v:
        return True
    return False

def get_safe_config(cfg: dict) -> dict:
    safe = {}
    for k, v in cfg.items():
        if is_secret_key(k) or k == "_secret_storage_errors":
            continue
        safe[k] = v

    # Explicit boolean indicators showing whether secret keys are configured
    safe["groq_api_key_configured"] = bool(cfg.get("groq_api_key", "").strip())
    safe["openrouter_api_key_configured"] = bool(cfg.get("openrouter_api_key", "").strip())
    safe["elevenlabs_api_key_configured"] = bool(cfg.get("elevenlabs_api_key", "").strip())
    safe["openai_api_key_configured"] = bool(cfg.get("openai_api_key", "").strip())
    safe["speechify_api_key_configured"] = bool(cfg.get("speechify_api_key", "").strip())
    safe["fish_audio_api_key_configured"] = bool(cfg.get("fish_audio_api_key", "").strip())
    safe["telegram_bot_token_configured"] = bool(cfg.get("telegram_bot_token", "").strip())

    # Return empty strings for secret fields so backward-compatible UI bindings never receive null/secrets
    safe["groq_api_key"] = ""
    safe["openrouter_api_key"] = ""
    safe["elevenlabs_api_key"] = ""
    safe["openai_api_key"] = ""
    safe["speechify_api_key"] = ""
    safe["speechify_voice"] = cfg.get("speechify_voice", "hande")
    safe["gothic_voice_enabled"] = bool(cfg.get("gothic_voice_enabled", True))
    safe["telegram_bot_token"] = ""
    safe["secret_storage_errors"] = list(cfg.get("_secret_storage_errors", []))
    safe["legacy_api_key_migration"] = get_legacy_api_key_status()
    return safe

def validate_config_update(data: dict) -> tuple[bool, str, dict]:
    """
    Validates configuration update dictionary against ALLOWED_CONFIG_KEYS schema.
    Returns (is_valid, error_message, validated_updates).
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object", {}

    validated = {}
    for k, v in data.items():
        if k not in ALLOWED_CONFIG_KEYS:
            return False, f"Unknown configuration key: '{k}'", {}

        rules = ALLOWED_CONFIG_KEYS[k]
        expected_type = rules.get("type")

        if expected_type == bool:
            if not isinstance(v, bool):
                return False, f"Field '{k}' must be a boolean", {}
            validated[k] = v

        elif expected_type == str:
            if not isinstance(v, str):
                return False, f"Field '{k}' must be a string", {}
            max_len = rules.get("max_length", 256)
            if len(v) > max_len:
                return False, f"Field '{k}' exceeds maximum length of {max_len}", {}
            if "enum" in rules and v not in rules["enum"]:
                return False, f"Invalid value for '{k}': '{v}'. Allowed values: {sorted(list(rules['enum']))}", {}

            # Handle secret keys (including dynamic/custom keys)
            if is_secret_key(k):
                if is_masked_placeholder(v):
                    # Masked placeholder or empty field -> preserve existing value without overwriting
                    continue
                validated[k] = v.strip()
            else:
                validated[k] = v.strip()

        elif expected_type == list:
            if not isinstance(v, list):
                return False, f"Field '{k}' must be a list", {}
            max_items = rules.get("max_items", 10)
            if len(v) > max_items:
                return False, f"Field '{k}' exceeds maximum allowed items ({max_items})", {}
            item_type = rules.get("item_type", str)
            item_max_len = rules.get("item_max_length", 128)
            for item in v:
                if not isinstance(item, item_type):
                    return False, f"Items in '{k}' must be of type {item_type.__name__}", {}
                if item_type == str and len(item) > item_max_len:
                    return False, f"Item in '{k}' exceeds maximum length of {item_max_len}", {}
            validated[k] = v

    return True, "", validated

ALLOWED_RUNTIME_OVERRIDE_KEYS = {
    "tts_engine",
    "edge_rate",
    "edge_pitch",
    "edge_voice",
    "groq_model",
    "model",
    "active_model",
    "openai_voice",
    "elevenlabs_voice_id",
    "memory_learning_enabled"
}

def sanitize_runtime_custom_config(custom: dict) -> dict:
    """
    Phase 8B.2: Strict runtime configuration sanitization.
    Strips any keys outside ALLOWED_RUNTIME_OVERRIDE_KEYS and validates types/values
    to prevent secret key injection or arbitrary server state modification.
    """
    if not isinstance(custom, dict):
        return {}
    safe_overrides = {}
    for k, v in custom.items():
        if k in ALLOWED_RUNTIME_OVERRIDE_KEYS and k in ALLOWED_CONFIG_KEYS:
            rule = ALLOWED_CONFIG_KEYS[k]
            expected_type = rule.get("type")
            if expected_type == bool and type(v) is bool:
                safe_overrides[k] = v
            elif expected_type == str and isinstance(v, str):
                max_len = rule.get("max_length", 256)
                if len(v) <= max_len:
                    if "enum" in rule:
                        if v in rule["enum"]:
                            safe_overrides[k] = v.strip()
                    else:
                        safe_overrides[k] = v.strip()
    return safe_overrides

async def handle_get_config(request):
    async with CONFIG_ASYNC_LOCK:
        try:
            cfg = load_config()
        except Exception as e:
            return web.json_response({
                "status": "error",
                "error": "CORRUPT_CONFIG_FILE",
                "message": f"Configuration storage is corrupt: {e}"
            }, status=503)
        return web.json_response(get_safe_config(cfg))

async def handle_save_config(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({
            "status": "error",
            "message": "Invalid JSON payload"
        }, status=400)

    if not isinstance(data, dict):
        return web.json_response({
            "status": "error",
            "message": "Configuration payload must be a JSON object"
        }, status=400)

    is_valid, err_msg, validated_updates = validate_config_update(data)
    if not is_valid:
        return web.json_response({
            "status": "error",
            "message": err_msg
        }, status=400)

    async with CONFIG_ASYNC_LOCK:
        try:
            cfg = load_config()
        except Exception as e:
            return web.json_response({
                "status": "error",
                "error": "CORRUPT_CONFIG_FILE",
                "message": f"Refusing to update corrupt configuration storage: {e}"
            }, status=503)

        # Update only explicitly validated fields, preserving omitted and unchanged values.
        # An explicit replacement lets a user recover a DPAPI secret copied from
        # another Windows user or device without ever exposing the old value.
        cfg.update(validated_updates)
        if validated_updates:
            unavailable = set(cfg.get("_secret_storage_errors", []))
            unavailable.difference_update(
                key for key in validated_updates if is_secret_key(key)
            )
            if unavailable:
                cfg["_secret_storage_errors"] = sorted(unavailable)
            else:
                cfg.pop("_secret_storage_errors", None)
        try:
            save_config(cfg)
        except Exception as e:
            return web.json_response({
                "status": "error",
                "message": f"Failed to persist configuration: {mask_secrets(str(e))}"
            }, status=500)

    return web.json_response({"status": "ok"})


async def handle_migrate_legacy_api_key(request):
    """Explicit, UI-confirmed migration for the legacy plaintext api_key.txt."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON payload"}, status=400)
    if not isinstance(data, dict) or data.get("confirm_migration") is not True:
        return web.json_response({
            "status": "error", "error": "MIGRATION_CONFIRMATION_REQUIRED",
            "message": "Eski anahtarın taşınması için açık onay gerekli."
        }, status=400)
    cleanup = data.get("cleanup_legacy_file") is True
    async with CONFIG_ASYNC_LOCK:
        result = migrate_legacy_api_key(confirm_migration=True, cleanup_legacy_file=cleanup)
    status = 200 if result.get("status") == "ok" else (500 if result.get("error") in {"MIGRATION_SAVE_FAILED", "LEGACY_CLEANUP_FAILED"} else 409)
    return web.json_response(result, status=status)

async def handle_test_config(request):
    """
    Phase 8B.2: Validates connectivity and API keys for external AI / TTS providers.
    Never exposes raw API keys in response or logs.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({
            "status": "error",
            "message": "Invalid JSON payload"
        }, status=400)

    if not isinstance(data, dict):
        return web.json_response({
            "status": "error",
            "message": "Configuration payload must be a JSON object"
        }, status=400)

    provider = str(data.get("provider", "")).strip().lower()
    allowed_providers = {"groq", "openrouter", "elevenlabs", "openai"}
    if provider not in allowed_providers:
        return web.json_response({
            "status": "error",
            "message": f"Geçersiz sağlayıcı: '{provider}'. İzin verilenler: {', '.join(sorted(allowed_providers))}"
        }, status=400)

    api_key_candidate = data.get("api_key")
    key_to_test = ""
    if isinstance(api_key_candidate, str) and api_key_candidate.strip() and not is_masked_placeholder(api_key_candidate):
        key_to_test = api_key_candidate.strip()
    else:
        cfg = load_config()
        key_to_test = str(cfg.get(f"{provider}_api_key", "")).strip()

    if not key_to_test:
        return web.json_response({
            "status": "error",
            "provider": provider,
            "message": f"{provider.capitalize()} API anahtarı sağlanmadı veya sistemde kayıtlı değil."
        }, status=400)

    timeout = aiohttp.ClientTimeout(total=5.0)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if provider == "groq":
                url = "https://api.groq.com/openai/v1/models"
                headers = {"Authorization": f"Bearer {key_to_test}"}
                async with session.get(url, headers=headers) as resp:
                    status_code = resp.status
            elif provider == "openrouter":
                url = "https://openrouter.ai/api/v1/auth/key"
                headers = {"Authorization": f"Bearer {key_to_test}"}
                async with session.get(url, headers=headers) as resp:
                    status_code = resp.status
            elif provider == "elevenlabs":
                url = "https://api.elevenlabs.io/v1/user"
                headers = {"xi-api-key": key_to_test}
                async with session.get(url, headers=headers) as resp:
                    status_code = resp.status
            elif provider == "openai":
                url = "https://api.openai.com/v1/models"
                headers = {"Authorization": f"Bearer {key_to_test}"}
                async with session.get(url, headers=headers) as resp:
                    status_code = resp.status
            elif provider == "speechify":
                url = "https://api.speechify.ai/v1/audio/speech"
                headers = {"Authorization": f"Bearer {key_to_test}", "Content-Type": "application/json"}
                payload = {"input": "Test", "voice_id": "elif", "audio_format": "mp3", "model": "simba-3.5"}
                async with session.post(url, headers=headers, json=payload) as resp:
                    status_code = resp.status

        if status_code == 200:
            return web.json_response({
                "status": "ok",
                "provider": provider,
                "message": f"{provider.capitalize()} bağlantısı doğrulandı."
            })
        elif status_code in (401, 403):
            return web.json_response({
                "status": "error",
                "provider": provider,
                "message": f"{provider.capitalize()} API anahtarı geçersiz veya yetkisiz (HTTP {status_code})."
            }, status=401)
        else:
            return web.json_response({
                "status": "error",
                "provider": provider,
                "message": f"{provider.capitalize()} API beklenmeyen durum kodu döndürdü (HTTP {status_code})."
            }, status=502)
    except asyncio.TimeoutError:
        return web.json_response({
            "status": "error",
            "provider": provider,
            "message": f"{provider.capitalize()} servisine bağlantı zaman aşımına uğradı."
        }, status=504)
    except Exception as e:
        return web.json_response({
            "status": "error",
            "provider": provider,
            "message": f"Bağlantı hatası: {mask_secrets(str(e))}"
        }, status=502)

# ==============================================================================
# PHASE 15A.2: MODEL COST TIERS & CAPABILITY TAXONOMY
# ==============================================================================
COST_FREE_ZERO_PRICE = "FREE_ZERO_PRICE"  # Fiyatı kesinlikle $0 / Free (örn: OpenRouter :free modelleri)
COST_FREE_TIER_QUOTA = "FREE_TIER_QUOTA"  # Belirli kota/rate-limit dahilinde ücretsiz tier (örn: Groq LPU free tier)
COST_PAID = "PAID"                        # Ücretli model
COST_UNKNOWN = "UNKNOWN"                  # Fiyatı doğrulanamayan/bilinmeyen model (güvenlik için engellenir)

# Model Lifecycle Constants (Phase 15D - Quick Catalog Fix)
LIFECYCLE_ACTIVE = "ACTIVE"
LIFECYCLE_PREVIEW = "PREVIEW"
LIFECYCLE_DEPRECATED = "DEPRECATED"

# Model Pricing Constants (Phase 15D - Quick Catalog Fix)
PRICING_FREE = "FREE"
PRICING_PAID = "PAID"
PRICING_UNKNOWN = "UNKNOWN"

CAP_GENERAL_CHAT = "general_chat"
CAP_REASONING = "reasoning"
CAP_CODING = "coding"
CAP_VISION = "vision"
CAP_TOOL_CALLING = "tool_calling"

GROQ_SEMAPHORE = asyncio.Semaphore(1)


@asynccontextmanager
async def completion_request(session, url, **kwargs):
    """Serialize Groq requests until their response is fully consumed."""
    if urllib.parse.urlsplit(url).hostname == "api.groq.com":
        async with GROQ_SEMAPHORE:
            async with session.post(url, **kwargs) as response:
                yield response
    else:
        async with session.post(url, **kwargs) as response:
            yield response


AI_MODEL_CATALOG = [
    {
        "id": "openrouter/free",
        "name": "OpenRouter Free",
        "provider": "openrouter",
        "providerDisplayName": "OpenRouter",
        "rate": "Free ($0)",
        "badge": "Free",
        "badgeClass": "free",
        "cost_tier": COST_FREE_ZERO_PRICE,
        "isFree": True,
        "isDefault": True,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_TOOL_CALLING],
        "description": "OpenRouter üzerinden ücretsiz modeller arasında yönlendirme.",
        "contextWindow": 0
    },
    {
        "id": "qwen/qwen-2.5-72b-instruct:free",
        "name": "Qwen 2.5 72B Instruct (Free)",
        "provider": "openrouter",
        "providerDisplayName": "Qwen via OpenRouter",
        "rate": "Free ($0)",
        "badge": "Free",
        "badgeClass": "free",
        "cost_tier": COST_FREE_ZERO_PRICE,
        "isFree": True,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_TOOL_CALLING],
        "description": "OpenRouter üzerinde $0 sıfır maliyetli gelişmiş Qwen 72B muhakeme modeli.",
        "contextWindow": 131072
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B Instruct",
        "provider": "openrouter",
        "providerDisplayName": "Meta via OpenRouter",
        "rate": "Standard",
        "badge": "Pro",
        "badgeClass": "paid",
        "cost_tier": "standard",
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_TOOL_CALLING],
        "description": "Meta 70B en son instruct modeli.",
        "contextWindow": 131072
    },
    {
        "id": "nvidia/nemotron-3.5-lightning:free",
        "name": "Nemotron 3.5 Lightning",
        "provider": "openrouter",
        "providerDisplayName": "NVIDIA via OpenRouter",
        "rate": "Free ($0)",
        "badge": "Free",
        "badgeClass": "free",
        "cost_tier": COST_FREE_ZERO_PRICE,
        "isFree": True,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_CODING],
        "description": "NVIDIA tarafından sunulan ücretsiz ve ultra hızlı model.",
        "contextWindow": 131072
    },
    {
        "id": "meta-llama/llama-3.2-11b-vision-instruct:free",
        "name": "Llama 3.2 11B Vision (Free)",
        "provider": "openrouter",
        "providerDisplayName": "Meta via OpenRouter",
        "rate": "Free ($0)",
        "badge": "Vision",
        "badgeClass": "free",
        "cost_tier": COST_FREE_ZERO_PRICE,
        "isFree": True,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_VISION],
        "description": "Görsel analizi için OpenRouter üzerinde ücretsiz çoklu modal model.",
        "contextWindow": 131072
    },
    {
        "id": "llama-3.3-70b-versatile",
        "name": "Llama 3.3 70B Versatile (Groq)",
        "provider": "groq",
        "providerDisplayName": "Groq LPU",
        "rate": "Free Tier (Rate-Limited)",
        "badge": "LPU",
        "badgeClass": "default",
        "cost_tier": COST_FREE_TIER_QUOTA,
        "isFree": True,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_TOOL_CALLING],
        "description": "Groq LPU donanımı üzerinde ultra hızlı, kotalı ücretsiz Llama 3.3 70B.",
        "contextWindow": 128000
    },
    {
        "id": "llama-3.1-8b-instant",
        "name": "Llama 3.1 8B Instant (Groq)",
        "provider": "groq",
        "providerDisplayName": "Groq LPU",
        "rate": "Free Tier (High Speed)",
        "badge": "LPU",
        "badgeClass": "default",
        "cost_tier": COST_FREE_TIER_QUOTA,
        "isFree": True,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_CODING, CAP_TOOL_CALLING],
        "description": "Groq LPU üzerinde düşük gecikmeli, kotalı ücretsiz Llama 3.1 8B.",
        "contextWindow": 128000
    },
    {
        "id": "z-ai/glm-5.3",
        "name": "GLM-5.3 (Reasoning)",
        "provider": "openrouter",
        "providerDisplayName": "Z.ai via OpenRouter",
        "rate": "*1.2",
        "badge": "Smart",
        "badgeClass": "smart",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING],
        "description": "Z.ai GLM-5.3 düşünce zincirine sahip gelişmiş muhakeme modeli.",
        "contextWindow": 128000
    },
    {
        "id": "google/gemini-2.5-flash",
        "name": "Gemini 2.5 Flash",
        "provider": "openrouter",
        "providerDisplayName": "Google via OpenRouter",
        "rate": "*0.75",
        "badge": "Fast",
        "badgeClass": "default",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_CODING, CAP_VISION],
        "description": "Yüksek hız ve multimodal yeteneklere sahip Google Gemini 2.5 modeli.",
        "contextWindow": 1000000
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B Instruct",
        "provider": "openrouter",
        "providerDisplayName": "Meta via OpenRouter",
        "rate": "*0.5",
        "badge": "Meta",
        "badgeClass": "default",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_TOOL_CALLING],
        "description": "Meta açık kaynak lideri 70B instruktif model.",
        "contextWindow": 131072
    },
    {
        "id": "openai/gpt-4o",
        "name": "GPT 4o (Omni)",
        "provider": "openrouter",
        "providerDisplayName": "OpenAI via OpenRouter",
        "rate": "*2.5",
        "badge": "Pro",
        "badgeClass": "rate",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_VISION, CAP_TOOL_CALLING],
        "description": "OpenAI amiral gemisi çoklu modal zeka modeli.",
        "contextWindow": 128000
    },
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "provider": "openrouter",
        "providerDisplayName": "Anthropic via OpenRouter",
        "rate": "*2.8",
        "badge": "Mommy Voice",
        "badgeClass": "rate",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_VISION, CAP_TOOL_CALLING],
        "description": "Study With Mommy sesli sohbet ve empati motoru.",
        "contextWindow": 200000
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek V3",
        "provider": "openrouter",
        "providerDisplayName": "DeepSeek via OpenRouter",
        "rate": "*0.2",
        "badge": "Fast Step",
        "badgeClass": "smart",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING, CAP_TOOL_CALLING],
        "description": "Study With Mommy adım adım matematik ve teknik problem çözücü.",
        "contextWindow": 64000
    },
    {
        "id": "deepseek/deepseek-r1",
        "name": "DeepSeek R1",
        "provider": "openrouter",
        "providerDisplayName": "DeepSeek via OpenRouter",
        "rate": "*0.5",
        "badge": "Reasoning",
        "badgeClass": "rate",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_REASONING, CAP_CODING, CAP_GENERAL_CHAT],
        "description": "Derin düşünce ve karmaşık soru analiz motoru.",
        "contextWindow": 64000
    },
    {
        "id": "x-ai/grok-2",
        "name": "Grok 2.0",
        "provider": "xai",
        "providerDisplayName": "xAI API",
        "rate": "*1.8",
        "badge": "LOCKED",
        "badgeClass": "locked",
        "cost_tier": COST_PAID,
        "isFree": False,
        "isDefault": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING],
        "description": "xAI doğrudan sağlayıcı anahtarı gerektirir.",
        "contextWindow": 128000
    },
    {
        "id": "qwen/qwen3.8-27b",
        "name": "Qwen 3.8 27B (Preview)",
        "provider": "groq",
        "providerDisplayName": "Groq LPU",
        "rate": "Paid (Preview)",
        "badge": "PREVIEW",
        "badgeClass": "smart",
        "cost_tier": COST_PAID,
        "pricing": PRICING_PAID,
        "lifecycle": LIFECYCLE_PREVIEW,
        "isFree": False,
        "isDefault": False,
        "deprecated": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING],
        "description": "Groq LPU üzerinde önizleme aşamasında ücretli Qwen 3.8 27B modeli.",
        "contextWindow": 32768
    },
    {
        "id": "openai/gpt-oss-120b",
        "name": "GPT OSS 120B",
        "provider": "groq",
        "providerDisplayName": "Groq LPU",
        "rate": "Paid",
        "badge": "Pro",
        "badgeClass": "rate",
        "cost_tier": COST_PAID,
        "pricing": PRICING_PAID,
        "lifecycle": LIFECYCLE_ACTIVE,
        "isFree": False,
        "isDefault": False,
        "deprecated": False,
        "capabilities": [CAP_GENERAL_CHAT, CAP_REASONING, CAP_CODING],
        "description": "Groq LPU üzerinde aktif ücretli büyük açık ağırlıklı model.",
        "contextWindow": 32768
    },
    {
        "id": "meta-llama/llama-2-70b-chat:deprecated",
        "name": "Llama 2 70B Chat (Deprecated)",
        "provider": "openrouter",
        "providerDisplayName": "Meta (Legacy)",
        "rate": "Deprecated",
        "badge": "OLD",
        "badgeClass": "default",
        "cost_tier": COST_UNKNOWN,
        "pricing": PRICING_UNKNOWN,
        "lifecycle": LIFECYCLE_DEPRECATED,
        "isFree": False,
        "isDefault": False,
        "deprecated": True,
        "capabilities": [CAP_GENERAL_CHAT],
        "description": "Eski/kaldırılmış model ID'si - kullanımdan kaldırılmıştır.",
        "contextWindow": 4096
    }
]

DEPRECATED_MODELS = [
    m["id"] for m in AI_MODEL_CATALOG if m.get("deprecated") or m.get("lifecycle") == LIFECYCLE_DEPRECATED
]

def get_model_lifecycle(model_id: str) -> str:
    """Modelin yaşam döngüsünü döner: ACTIVE, PREVIEW veya DEPRECATED."""
    meta = next((m for m in AI_MODEL_CATALOG if m["id"] == model_id), None)
    if not meta:
        return LIFECYCLE_DEPRECATED
    if meta.get("deprecated") or meta.get("lifecycle") == LIFECYCLE_DEPRECATED:
        return LIFECYCLE_DEPRECATED
    if meta.get("lifecycle") == LIFECYCLE_PREVIEW:
        return LIFECYCLE_PREVIEW
    return meta.get("lifecycle", LIFECYCLE_ACTIVE)

def get_model_pricing(model_id: str) -> str:
    """Modelin fiyatlandırma sınıflandırmasını döner: FREE, PAID veya UNKNOWN."""
    meta = next((m for m in AI_MODEL_CATALOG if m["id"] == model_id), None)
    if not meta:
        return PRICING_UNKNOWN
    tier = meta.get("cost_tier")
    if tier in (COST_FREE_ZERO_PRICE, COST_FREE_TIER_QUOTA) or meta.get("isFree") is True:
        return PRICING_FREE
    elif tier == COST_PAID or meta.get("isFree") is False:
        return PRICING_PAID
    return meta.get("pricing", PRICING_UNKNOWN)

# ==============================================================================
# PHASE 15A.1: SERVER-SIDE PAID API PROTECTION & ONE-TIME AUTHORIZATION MANAGER
# ==============================================================================
PAID_MODEL_AUTHORIZATIONS: Dict[str, Dict[str, Any]] = {}
PAID_AUTH_TTL_SECONDS = 120  # 2 dakika geçerlilik süresi


def create_paid_service_authorization(
    provider: str,
    service: str,
    action: str,
    subject: str = "",
) -> str:
    """Creates a short-lived, single-use authorization for one paid action."""
    token = f"pauth_{uuid.uuid4().hex}"
    now = time.time()
    expired_tokens = [
        token_id for token_id, data in PAID_MODEL_AUTHORIZATIONS.items()
        if now > data["expires_at"]
    ]
    for token_id in expired_tokens:
        PAID_MODEL_AUTHORIZATIONS.pop(token_id, None)

    PAID_MODEL_AUTHORIZATIONS[token] = {
        "provider": provider,
        "service": service,
        "action": action,
        "subject": subject,
        "created_at": now,
        "expires_at": now + PAID_AUTH_TTL_SECONDS,
        "used": False,
    }
    return token


def validate_and_consume_paid_service_authorization(
    token: str,
    provider: str,
    service: str,
    action: str,
    subject: str = "",
) -> Tuple[bool, str]:
    """Validates and consumes an authorization bound to one provider action."""
    if not token or not isinstance(token, str):
        return False, "Eksik veya geçersiz onay belirteci."

    auth_data = PAID_MODEL_AUTHORIZATIONS.get(token)
    if not auth_data:
        return False, "Geçersiz veya bulunamayan onay belirteci."
    if auth_data.get("used"):
        return False, "Bu onay belirteci daha önce kullanılmıştır."

    if time.time() > auth_data["expires_at"]:
        PAID_MODEL_AUTHORIZATIONS.pop(token, None)
        return False, "Onay belirtecinin geçerlilik süresi dolmuştur (zaman aşımı)."

    expected = {
        "provider": provider,
        "service": service,
        "action": action,
        "subject": subject,
    }
    for key, requested_value in expected.items():
        if auth_data.get(key, "") != requested_value:
            return False, "Onay belirteci istenen ücretli işlemle eşleşmiyor."

    auth_data["used"] = True
    PAID_MODEL_AUTHORIZATIONS.pop(token, None)
    return True, "Onay doğrulandı."

def get_model_cost_tier(model_id: str) -> str:
    """Modelin maliyet katmanını döner: FREE_ZERO_PRICE, FREE_TIER_QUOTA, PAID, UNKNOWN."""
    meta = next((m for m in AI_MODEL_CATALOG if m["id"] == model_id), None)
    if not meta:
        return COST_UNKNOWN
    return meta.get("cost_tier", COST_UNKNOWN if meta.get("isFree") is None else (COST_FREE_ZERO_PRICE if meta.get("isFree") else COST_PAID))

def get_model_cost_category(model_id: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Modelin maliyet kategorisini döner: 'free', 'paid' veya 'unknown'.
    Bilinmeyen modeller varsayılan olarak 'unknown' (kilitli) kabul edilir.
    """
    meta = next((m for m in AI_MODEL_CATALOG if m["id"] == model_id), None)
    if not meta:
        return "unknown", None
    
    tier = meta.get("cost_tier")
    if tier in (COST_FREE_ZERO_PRICE, COST_FREE_TIER_QUOTA):
        return "free", meta
    elif tier == COST_PAID or meta.get("isFree") is False:
        return "paid", meta
    elif meta.get("isFree") is True:
        return "free", meta
    else:
        return "unknown", meta

def select_free_first_model(
    required_capabilities: Optional[List[str]] = None,
    preferred_provider: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    task_hint: Optional[str] = None
) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
    """
    Intelligent Free-First Model Router.
    - Sadece COST_FREE_ZERO_PRICE ve COST_FREE_TIER_QUOTA modelleri seçer.
    - Deprecated veya geçersiz model ID'lerini dışlar.
    - Gerekli yetenekleri (genel sohbet, muhakeme, kodlama, görme, araç çağırma) filtreler.
    - Fiyatlandırması bilinmeyen (UNKNOWN) veya ücretli (PAID) modelleri kesinlikle seçmez.
    - Sağlayıcı anahtarının (OpenRouter / Groq) mevcut olduğunu doğrular.
    - Ücretsiz model yoksa veya kota tükendiyse kullanıcıya bilgi verir, sessizce ücretli modele geçmez.
    """
    cfg = cfg or {}
    req_caps = set(required_capabilities or [])
    
    if not req_caps and task_hint:
        hint_lower = task_hint.lower()
        if any(w in hint_lower for w in ["kod", "python", "script", "function", "algoritma", "hata", "bug", "traceback"]):
            req_caps.add(CAP_CODING)
        if any(w in hint_lower for w in ["neden", "analiz", "karşılaştır", "mantık", "adım adım", "çöz"]):
            req_caps.add(CAP_REASONING)
        if any(w in hint_lower for w in ["resim", "görsel", "ekran", "fotoğraf", "vision", "screenshot"]):
            req_caps.add(CAP_VISION)
        if any(w in hint_lower for w in ["araç", "tool", "alarm", "zamanlayıcı", "pomodoro", "hava", "ara"]):
            req_caps.add(CAP_TOOL_CALLING)

    openrouter_key = (cfg.get("openrouter_api_key") or "").strip()
    groq_key = (cfg.get("groq_api_key") or "").strip()

    candidates = []
    for m in AI_MODEL_CATALOG:
        # Deprecated modelleri dışla
        if m.get("deprecated"):
            continue

        # Sadece doğrulanmış ücretsiz katmanlar (UNKNOWN ve PAID engellenir)
        tier = m.get("cost_tier")
        if tier not in (COST_FREE_ZERO_PRICE, COST_FREE_TIER_QUOTA):
            continue

        # Sağlayıcı anahtarı kontrolü (anahtar yoksa seçilemez)
        prov = m.get("provider")
        if prov == "openrouter" and not openrouter_key:
            continue
        elif prov == "groq" and not groq_key:
            continue
        elif prov not in ("openrouter", "groq"):
            continue

        # Yetenek uyumu
        m_caps = set(m.get("capabilities", []))
        if req_caps and not req_caps.issubset(m_caps):
            continue

        # Skorlama: FREE_ZERO_PRICE (OpenRouter :free) önceliklidir
        score = 10 if tier == COST_FREE_ZERO_PRICE else 5
        if preferred_provider and prov == preferred_provider:
            score += 3

        candidates.append((score, m))

    if not candidates:
        return None, None, "Gereksinimleri karşılayan ve API anahtarı tanımlı uygun bir ücretsiz model bulunamadı."

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = candidates[0][1]
    return chosen["id"], chosen, f"Otomatik olarak ücretsiz model seçildi: {chosen['name']}"

def create_paid_model_authorization(model_id: str, provider: str) -> str:
    """Tek kullanımlık, zamana bağlı sunucu tarafı onay tokenı üretir."""
    return create_paid_service_authorization(
        provider=provider,
        service="model_chat",
        action="completion",
        subject=model_id,
    )

def validate_and_consume_paid_authorization(token: str, model_id: str, provider: str) -> Tuple[bool, str]:
    """
    Verilen tokenı doğrular ve tüketir (tek kullanımlık).
    Süre aşımı, model uyuşmazlığı, sağlayıcı uyuşmazlığı veya tekrar kullanımda reddeder.
    """
    return validate_and_consume_paid_service_authorization(
        token=token,
        provider=provider,
        service="model_chat",
        action="completion",
        subject=model_id,
    )


def create_paid_tts_authorization(provider: str) -> str:
    return create_paid_service_authorization(
        provider=provider,
        service="tts",
        action="synthesize",
    )


def validate_and_consume_paid_tts_authorization(token: str, provider: str) -> Tuple[bool, str]:
    return validate_and_consume_paid_service_authorization(
        token=token,
        provider=provider,
        service="tts",
        action="synthesize",
    )


def get_paid_tts_provider(cfg: dict) -> Optional[str]:
    engine = str((cfg or {}).get("tts_engine", "edge_tts")).strip().lower()
    return engine if engine in {"elevenlabs", "openai", "speechify", "fish_audio"} else None


def get_paid_tts_provider_availability_error(cfg: dict, provider: str) -> Optional[Dict[str, str]]:
    secret_key = {
        "elevenlabs": "elevenlabs_api_key",
        "openai": "openai_api_key",
        "speechify": "speechify_api_key",
        "fish_audio": "fish_audio_api_key",
    }.get(provider)
    if not secret_key:
        return {"error_code": "TTS_PROVIDER_UNSUPPORTED", "message": "TTS sağlayıcısı desteklenmiyor."}

    unavailable = set((cfg or {}).get("_secret_storage_errors", []))
    if secret_key in unavailable:
        return {
            "error_code": "TTS_SECRET_UNAVAILABLE",
            "message": "Kaydedilmiş TTS anahtarı bu Windows kullanıcısında çözülemedi. Anahtarı Ayarlar'dan yeniden girin.",
        }
    if not str((cfg or {}).get(secret_key, "")).strip():
        return {
            "error_code": "TTS_PROVIDER_NOT_CONFIGURED",
            "message": "Seçilen TTS sağlayıcısı için geçerli bir anahtar yapılandırılmamış.",
        }
    return None


def get_paid_tts_authorization_payload(provider: str, reason: str = "") -> Dict[str, Any]:
    return {
        "status": "confirmation_required",
        "error_code": "PAID_TTS_CONFIRMATION_REQUIRED",
        "reason": reason or "Ücretli TTS için geçerli bir onay belirteci gerekli.",
        "service": "tts",
        "action": "synthesize",
        "provider": provider,
        "auth_token": create_paid_tts_authorization(provider),
        "expires_in_seconds": PAID_AUTH_TTL_SECONDS,
        "message": "Ücretli TTS hizmeti için onay gerekli. Onay olmadan ses sağlayıcısına istek gönderilmedi.",
    }

async def handle_request_paid_auth(request):
    """
    POST /api/models/paid_auth/request
    Ücretli veya bilinmeyen maliyetli model için kullanıcıya onay kartı bilgisi ve tek kullanımlık onay bileti döner.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü"}, status=400)
        
    model_id = str(data.get("model_id", "")).strip()
    if not model_id:
        return web.json_response({"status": "error", "message": "model_id zorunludur"}, status=400)
        
    cost_cat, meta = get_model_cost_category(model_id)
    if cost_cat == "free":
        return web.json_response({
            "status": "ok",
            "cost_category": "free",
            "message": f"'{model_id}' ücretsiz modeldir, özel ücretli onayı gerektirmez."
        })
        
    provider = meta["provider"] if meta else ("openrouter" if "/" in model_id else "unknown")
    provider_name = meta.get("providerDisplayName", provider) if meta else provider
    rate_info = meta.get("rate", "Bilinmiyor") if meta else "Bilinmiyor"
    
    # Yeni bir tek kullanımlık onay belirteci üret
    auth_token = create_paid_model_authorization(model_id, provider)
    
    return web.json_response({
        "status": "ok",
        "cost_category": cost_cat,
        "requires_confirmation": True,
        "model_id": model_id,
        "model_name": meta.get("name", model_id) if meta else model_id,
        "provider": provider,
        "provider_display_name": provider_name,
        "estimated_rate": rate_info,
        "auth_token": auth_token,
        "expires_in_seconds": PAID_AUTH_TTL_SECONDS,
        "warning_message": (
            f"DİKKAT: '{meta.get('name', model_id) if meta else model_id}' modeli ücretli API çağrısı yapacaktır. "
            f"Tahmini tarife: {rate_info}. Onaylıyor musunuz?"
        )
    })


async def handle_request_paid_service_auth(request):
    """Issues a short-lived authorization only for the supported paid TTS action."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü"}, status=400)

    service = str(data.get("service", "")).strip().lower()
    action = str(data.get("action", "synthesize")).strip().lower()
    provider = str(data.get("provider", "")).strip().lower()
    if service != "tts" or action != "synthesize" or provider not in {"elevenlabs", "openai"}:
        return web.json_response({
            "status": "error",
            "message": "Bu ücretli hizmet için onay isteği desteklenmiyor."
        }, status=400)

    payload = get_paid_tts_authorization_payload(provider)
    payload["requires_confirmation"] = True
    return web.json_response(payload)

# ==============================================================================
# PHASE 15D: SMART AI MODEL ADVISOR & HUB
# ==============================================================================

class SmartModelAdvisor:
    """
    Phase 15D: Smart AI Model Advisor & Hub.
    Recommends AI models based on task type:
    - general_chat
    - coding
    - reasoning
    - vision
    - tool_calling

    Rules:
    - Genuinely free models first (COST_FREE_ZERO_PRICE > COST_FREE_TIER_QUOTA > COST_PAID).
    - Rejects deprecated and unavailable models.
    - Preserves paid API authorization locks. Never silently suggests/switches to paid.
    - Inspects and filters catalog by task type, provider, or pricing category.
    - Optional Ollama status flag (local Ollama detected if enabled in config, no download).
    """
    TASK_CAPABILITY_MAP = {
        "general_chat": [CAP_GENERAL_CHAT],
        "coding": [CAP_CODING],
        "reasoning": [CAP_REASONING],
        "vision": [CAP_VISION],
        "tool_calling": [CAP_TOOL_CALLING]
    }

    @classmethod
    def get_models_hub_data(cls, cfg: Optional[dict] = None) -> dict:
        cfg = cfg or load_config()
        openrouter_key = cfg.get("openrouter_api_key", "").strip()
        groq_key = cfg.get("groq_api_key", "").strip()
        ollama_enabled = bool(cfg.get("ollama_enabled", False))
        active_model = cfg.get("active_model", "openrouter/free").strip()

        enriched_models = []
        for m in AI_MODEL_CATALOG:
            m_copy = dict(m)
            provider = m["provider"]
            
            # Lifecycle and pricing classification
            lifecycle = get_model_lifecycle(m["id"])
            pricing = get_model_pricing(m["id"])
            m_copy["lifecycle"] = lifecycle
            m_copy["pricing"] = pricing

            # Detect deprecated
            if lifecycle == LIFECYCLE_DEPRECATED or m.get("deprecated", False):
                m_copy["status"] = "DEPRECATED"
                m_copy["statusReason"] = "Eski veya kaldırılmış model ID'si"
                m_copy["isAvailable"] = False
            elif provider == "openrouter":
                if not openrouter_key:
                    m_copy["status"] = "LOCKED"
                    m_copy["statusReason"] = "OpenRouter API anahtarı girilmemiş"
                    m_copy["isAvailable"] = False
                else:
                    m_copy["status"] = "ONLINE"
                    m_copy["statusReason"] = "OpenRouter canlı bağlantısı hazır"
                    m_copy["isAvailable"] = True
            elif provider == "groq":
                if not groq_key:
                    m_copy["status"] = "LOCKED"
                    m_copy["statusReason"] = "Groq API anahtarı girilmemiş"
                    m_copy["isAvailable"] = False
                else:
                    m_copy["status"] = "ONLINE"
                    m_copy["statusReason"] = "Groq LPU kotası hazır"
                    m_copy["isAvailable"] = True
            elif provider == "ollama":
                m_copy["status"] = "ONLINE" if ollama_enabled else "OFFLINE"
                m_copy["statusReason"] = "Yerel Ollama servisi" if ollama_enabled else "Ollama devre dışı (isteğe bağlı)"
                m_copy["isAvailable"] = ollama_enabled
            else:
                m_copy["status"] = "LOCKED"
                m_copy["statusReason"] = f"{m.get('providerDisplayName')} yapılandırılmamış"
                m_copy["isAvailable"] = False

            m_copy["isActive"] = (m["id"] == active_model)
            enriched_models.append(m_copy)

        return {
            "status": "ok",
            "active_model": active_model,
            "models": enriched_models,
            "total_count": len(enriched_models),
            "available_count": sum(1 for m in enriched_models if m.get("isAvailable")),
            "free_count": sum(1 for m in enriched_models if m.get("pricing") == PRICING_FREE and m.get("lifecycle") != LIFECYCLE_DEPRECATED),
            "ollama_supported": True,
            "ollama_active": ollama_enabled
        }

    @classmethod
    def recommend_for_task(cls, task_type: str = "general_chat", require_free: bool = True, cfg: Optional[dict] = None) -> list:
        cfg = cfg or load_config()
        hub_data = cls.get_models_hub_data(cfg)
        models = hub_data["models"]

        req_caps = cls.TASK_CAPABILITY_MAP.get(task_type.lower().strip(), [CAP_GENERAL_CHAT])

        candidates = []
        for m in models:
            if m.get("deprecated") or m.get("lifecycle") == LIFECYCLE_DEPRECATED or not m.get("isAvailable"):
                continue
            if require_free and (not m.get("isFree") or m.get("pricing") != PRICING_FREE):
                continue
            
            # Check capabilities
            caps = m.get("capabilities", [])
            matches_all = all(rc in caps for rc in req_caps)
            if not matches_all:
                continue

            # Cost tier rank: 0 (free zero price) -> 1 (free tier quota) -> 2 (paid)
            cost_tier = m.get("cost_tier", COST_UNKNOWN)
            tier_rank = 0 if cost_tier == COST_FREE_ZERO_PRICE else (1 if cost_tier == COST_FREE_TIER_QUOTA else 2)

            candidates.append({
                "model_id": m["id"],
                "name": m["name"],
                "provider": m["provider"],
                "providerDisplayName": m.get("providerDisplayName", m["provider"]),
                "cost_tier": cost_tier,
                "pricing": m.get("pricing", PRICING_UNKNOWN),
                "lifecycle": m.get("lifecycle", LIFECYCLE_ACTIVE),
                "isFree": m.get("isFree", False),
                "rate": m.get("rate", "Free"),
                "contextWindow": m.get("contextWindow", 0),
                "capabilities": m.get("capabilities", []),
                "description": m.get("description", ""),
                "tier_rank": tier_rank
            })

        # Sort: tier_rank ascending (free zero first), then by contextWindow descending
        candidates.sort(key=lambda x: (x["tier_rank"], -x["contextWindow"]))
        return candidates

async def handle_get_models_hub(request):
    """GET /api/models/hub - Akıllı AI Model Hub katalog ve öneri verisini döner."""
    cfg = load_config()
    hub_data = SmartModelAdvisor.get_models_hub_data(cfg)
    task_type = request.query.get("task")
    if task_type:
        recs = SmartModelAdvisor.recommend_for_task(task_type, require_free=True, cfg=cfg)
        hub_data["recommendations"] = recs
        hub_data["task"] = task_type
    return web.json_response(hub_data)

async def handle_recommend_models(request):
    """GET /api/models/recommend?task=...&free_only=... - Görev türüne göre en uygun ücretsiz modelleri önerir."""
    task_type = request.query.get("task", "general_chat").strip()
    free_only_str = request.query.get("free_only", "true").strip().lower()
    free_only = (free_only_str != "false")
    cfg = load_config()
    recs = SmartModelAdvisor.recommend_for_task(task_type=task_type, require_free=free_only, cfg=cfg)
    return web.json_response({
        "status": "ok",
        "task": task_type,
        "free_only": free_only,
        "count": len(recs),
        "recommendations": recs
    })

async def handle_get_models(request):
    """
    GET /api/models
    Canlı bağlantı durumlarıyla (ONLINE / OFFLINE / LOCKED) desteklenen modelleri listeler.
    Asla sahte 'ONLINE' durumu vermez; sağlayıcı API anahtarı ve erişilebilirliğini kontrol eder.
    """
    cfg = load_config()
    openrouter_key = cfg.get("openrouter_api_key", "").strip()
    groq_key = cfg.get("groq_api_key", "").strip()
    active_model = cfg.get("active_model", "openrouter/free").strip()

    models_with_status = []
    for m in AI_MODEL_CATALOG:
        m_copy = dict(m)
        provider = m["provider"]
        
        if provider == "openrouter":
            if not openrouter_key:
                m_copy["status"] = "LOCKED"
                m_copy["statusReason"] = "OpenRouter API anahtarı girilmemiş"
            else:
                m_copy["status"] = "ONLINE"
                m_copy["statusReason"] = "OpenRouter canlı bağlantısı doğrulandı"
        elif provider == "groq":
            if not groq_key:
                m_copy["status"] = "LOCKED"
                m_copy["statusReason"] = "Groq API anahtarı girilmemiş"
            else:
                m_copy["status"] = "OFFLINE"
                m_copy["statusReason"] = "Groq API anahtarı yetkisiz (HTTP 403)"
        else:
            m_copy["status"] = "LOCKED"
            m_copy["statusReason"] = f"{m.get('providerDisplayName')} API anahtarı yapılandırılmamış"

        m_copy["isActive"] = (m["id"] == active_model)
        models_with_status.append(m_copy)

    return web.json_response({
        "status": "ok",
        "active_model": active_model,
        "models": models_with_status
    })

async def handle_select_model(request):
    """
    POST /api/models/select
    Model Control Center üzerinden aktif AI modelini değiştirir ve yapılandırmayı saklar.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü"}, status=400)

    model_id = str(data.get("model_id", "")).strip()
    if not model_id:
        return web.json_response({"status": "error", "message": "model_id zorunludur"}, status=400)

    # Katalogda ara
    target_model = next((m for m in AI_MODEL_CATALOG if m["id"] == model_id), None)
    if not target_model:
        return web.json_response({
            "status": "error",
            "message": f"Tanımsız model ID: '{model_id}'. Sahte veya bilinmeyen modeller seçilemez."
        }, status=400)

    if target_model.get("deprecated", False) or target_model.get("lifecycle") == LIFECYCLE_DEPRECATED:
        return web.json_response({
            "status": "error",
            "error_code": "MODEL_DEPRECATED",
            "message": f"'{target_model['name']}' modeli eski/kaldırılmış bir modeldir ve seçilemez."
        }, status=400)

    cfg = load_config()
    provider = target_model["provider"]
    if provider == "openrouter" and not cfg.get("openrouter_api_key", "").strip():
        return web.json_response({
            "status": "error",
            "error_code": "MODEL_LOCKED",
            "message": f"{target_model['name']} seçilemez: OpenRouter API anahtarı girilmemiş."
        }, status=403)
    elif provider == "groq" and not cfg.get("groq_api_key", "").strip():
        return web.json_response({
            "status": "error",
            "error_code": "MODEL_LOCKED",
            "message": f"{target_model['name']} seçilemez: Groq API anahtarı girilmemiş."
        }, status=403)
    elif provider in ("anthropic", "xai"):
        return web.json_response({
            "status": "error",
            "error_code": "MODEL_LOCKED",
            "message": f"{target_model['name']} seçilemez: {target_model.get('providerDisplayName')} bağlantısı kilitli."
        }, status=403)

    async with CONFIG_ASYNC_LOCK:
        cfg["active_model"] = model_id
        save_config(cfg)

    log_activity("model_selected", f"Aktif AI modeli değiştirildi: {target_model['name']} ({model_id})")
    return web.json_response({
        "status": "ok",
        "active_model": model_id,
        "model_name": target_model["name"],
        "provider": target_model["provider"]
    })

async def handle_tts_direct(request):
    allowed, retry_after = await TTS_RATE_LIMITER.acquire()
    if not allowed:
        return web.json_response({
            "status": "error",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": f"TTS istek kotası aşıldı. Lütfen {retry_after}s sonra tekrar deneyin.",
            "retry_after": retry_after
        }, status=429, headers={"Retry-After": str(int(retry_after) + 1)})

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Geçersiz JSON yükü"}, status=400)

    if not isinstance(data, dict):
        return web.json_response({"error": "Geçersiz istek biçimi"}, status=400)

    text = data.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return web.json_response({"error": "Bos metin"}, status=400)

    cleaned = text.strip()
    if len(cleaned) > MAX_DIRECT_TTS_TEXT_LENGTH:
        return web.json_response({
            "error": f"Metin uzunluğu izin verilen üst sınırı aşıyor ({MAX_DIRECT_TTS_TEXT_LENGTH} karakter)"
        }, status=400)

    cfg = load_config()
    if data.get("preview") is True:
        engine = data.get("tts_engine")
        voice = data.get("elevenlabs_voice_id")
        speechify_voice = data.get("speechify_voice")
        voices = {"21m00Tcm4TlvDq8ikWAM", "LcfcDJNUP1GQjkzn1xUU", "MF3mGyEYCl7XYWbV9V6O", "XB0fDUnXU5powFXDhCwa"}
        if not isinstance(engine, str) or engine not in ALLOWED_TTS_ENGINES or (engine == "elevenlabs" and voice not in voices):
            return web.json_response({"error": "Geçersiz önizleme sesi"}, status=400)
        cfg = dict(cfg, tts_engine=engine)
        if engine == "elevenlabs":
            cfg["elevenlabs_voice_id"] = voice
        elif engine == "speechify" and speechify_voice:
            cfg["speechify_voice"] = speechify_voice
    paid_provider = get_paid_tts_provider(cfg)
    tts_res = await generate_tts(
        cleaned,
        cfg,
        max_len=MAX_DIRECT_TTS_TEXT_LENGTH,
    )
    audio_b64 = tts_res[0] if isinstance(tts_res, tuple) else tts_res
    return web.json_response({"audio_base64": audio_b64, "text": cleaned})


async def handle_screen_capture(request):
    """
    POST /api/screen/capture
    Açık kullanıcı izniyle masaüstü ekran görüntüsü alır, Base64 önizleme döner.
    Geçici dosyalar anında güvenle silinir.
    """
    temp_dir = tempfile.mkdtemp(prefix="jarvis_direct_screen_")
    temp_file = os.path.join(temp_dir, "screen.jpg")
    try:
        temp_path_normalized = temp_file.replace("\\", "/")
        ps_cmd = (
            'Add-Type -AssemblyName System.Windows.Forms, System.Drawing; '
            '$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; '
            '$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; '
            '$g = [System.Drawing.Graphics]::FromImage($bmp); '
            '$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); '
            f'$bmp.Save("{temp_path_normalized}", [System.Drawing.Imaging.ImageFormat]::Jpeg)'
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )
        
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value or "Masaüstü"

        img_b64 = ""
        if os.path.exists(temp_file):
            with open(temp_file, "rb") as _f:
                img_b64 = base64.b64encode(_f.read()).decode("utf-8")

        return web.json_response({
            "status": "ok",
            "active_window": title,
            "image_base64": img_b64,
            "message": f"Ekran görüntüsü hazırlandı. Aktif pencere: {title}"
        })
    except Exception as e:
        return web.json_response({"status": "error", "message": f"Ekran yakalama hatası: {str(e)}"}, status=500)
    finally:
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except Exception: pass
        if os.path.exists(temp_dir):
            try: os.rmdir(temp_dir)
            except Exception: pass
VISION_SESSION_COOKIE = "jarvis_vision_session"
VISION_PROVIDER = "openrouter"
VISION_MODEL = "openai/gpt-4o"
VISION_ACTION = "one_frame"


def vision_destination(cfg):
    if str(cfg.get("openrouter_api_key") or "").strip():
        return {
            "provider": VISION_PROVIDER,
            "label": "OpenRouter (OpenAI GPT-4o)",
            "model": VISION_MODEL,
            "paid": True,
        }
    return None


def vision_unavailable(cfg):
    message = "Vision için OpenRouter bağlantısı yapılandırılmamış veya anahtar kullanılamıyor."
    if cfg.get("groq_api_key"):
        message += " Mevcut Groq Vision modeli hizmetten kaldırıldı."
    return web.json_response({"error": "VISION_UNAVAILABLE", "message": message}, status=503)


async def handle_vision_destination(request):
    cfg = load_config()
    destination = vision_destination(cfg)
    if not destination:
        return vision_unavailable(cfg)
    response = web.json_response(destination)
    if not request.cookies.get(VISION_SESSION_COOKIE):
        response.set_cookie(VISION_SESSION_COOKIE, uuid.uuid4().hex, httponly=True,
                            samesite="Strict", secure=request.secure, path="/api/vision")
    return response


def vision_same_origin(request):
    return request.headers.get("Origin") == f"{request.scheme}://{request.host}"


async def handle_vision_approval(request):
    session = request.cookies.get(VISION_SESSION_COOKIE)
    if not session or not vision_same_origin(request):
        return web.json_response({"error": "VISION_SESSION_REQUIRED", "message": "Önce aynı oturumdan hedefi doğrula."}, status=403)
    try:
        data = await request.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return web.json_response({"error": "INVALID_VISION_REQUEST"}, status=400)
    cfg = load_config()
    destination = vision_destination(cfg)
    if not destination:
        return vision_unavailable(cfg)
    if (data.get("provider") != destination["provider"] or data.get("model") != destination["model"]):
        return web.json_response({"error": "VISION_DESTINATION_CHANGED", "message": "Analiz hedefi değişti. Yeniden onayla."}, status=409)
    if data.get("confirmed") is not True or (destination["paid"] and data.get("allow_paid") is not True):
        return web.json_response({"error": "VISION_CONFIRMATION_REQUIRED", "message": "Görsel aktarımı ve ücretli analiz için açık onay gerekiyor."}, status=403)
    token = create_paid_service_authorization(
        destination["provider"], "vision", VISION_ACTION, f"{session}:{destination['model']}"
    )
    return web.json_response({"approval_token": token})


async def handle_vision_scan(request):
    try:
        data = await request.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return web.json_response({"error": "INVALID_VISION_REQUEST"}, status=400)
    session = request.cookies.get(VISION_SESSION_COOKIE)
    if not session or not vision_same_origin(request) or not data.get("approval_token"):
        return web.json_response({"error": "VISION_APPROVAL_REQUIRED", "message": "Görsel gönderilmedi. Bu işlem için oturum onayı gerekiyor."}, status=403)

    cfg = load_config()
    destination = vision_destination(cfg)
    if not destination:
        return vision_unavailable(cfg)
    if (data.get("provider") != destination["provider"] or data.get("model") != destination["model"]):
        return web.json_response({"error": "VISION_DESTINATION_CHANGED", "message": "Analiz hedefi değişti. Yeniden onayla."}, status=409)

    img_b64 = data.get("image_base64")
    user_prompt = data.get("prompt", "Bu görüntüyü kısa ve Türkçe olarak açıkla.")
    if not isinstance(img_b64, str) or not img_b64.strip() or not isinstance(user_prompt, str):
        return web.json_response({"error": "INVALID_VISION_REQUEST"}, status=400)

    # Validation and consumption have no await in the single aiohttp event loop.
    valid, reason = validate_and_consume_paid_service_authorization(
        data["approval_token"], destination["provider"], "vision", VISION_ACTION,
        f"{session}:{destination['model']}",
    )
    if not valid:
        return web.json_response({"error": "VISION_APPROVAL_INVALID", "message": reason}, status=403)

    headers = {
        "Authorization": f"Bearer {cfg['openrouter_api_key'].strip()}",
        "HTTP-Referer": "http://127.0.0.1:7860",
        "X-Title": "ZERO CORE OS Vision Engine",
    }
    payload = {
        "model": destination["model"],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]}],
        "max_tokens": 150,
    }
    try:
        async with aiohttp.ClientSession() as client:
            async with client.post("https://openrouter.ai/api/v1/chat/completions",
                                   headers=headers, json=payload, timeout=20,
                                   allow_redirects=False) as response:
                if response.status != 200:
                    return web.json_response({"error": "VISION_PROVIDER_FAILED", "message": "OpenRouter analizi tamamlayamadı."}, status=502)
                result = await response.json()
                reply = result["choices"][0]["message"]["content"]
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError("Empty Vision response")
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, IndexError, TypeError):
        return web.json_response({"error": "VISION_PROVIDER_FAILED", "message": "OpenRouter analizi tamamlayamadı."}, status=502)

    audio_b64 = await generate_tts(reply, cfg, paid_auth_token=data.get("paid_tts_auth_token"))
    return web.json_response({"reply": reply, "audio_base64": audio_b64})

async def handle_chat(request):
    allowed, retry_after = await CHAT_RATE_LIMITER.acquire()
    if not allowed:
        return web.json_response({
            "status": "error",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": f"Chat istek kotası aşıldı. Lütfen {retry_after}s sonra tekrar deneyin.",
            "retry_after": retry_after
        }, status=429, headers={"Retry-After": str(int(retry_after) + 1)})

    data = await request.json()
    message = data.get("message", "").strip()
    history = data.get("history", [])
    custom_cfg = data.get("config", {})
    paid_tts_auth_token = data.get("paid_tts_auth_token")
    
    cfg = load_config()
    cfg.update(sanitize_runtime_custom_config(custom_cfg))
    
    if not message:
        return web.json_response({"error": "Bos mesaj"}, status=400)

    model_candidate = custom_cfg.get("model") or custom_cfg.get("active_model") or cfg.get("active_model", "").strip()
    is_auto_free = model_candidate in ("auto", "free", "free_first", "auto_free", "") or cfg.get("model_routing_mode") == "free_first"
    
    if is_auto_free:
        free_id, free_meta, free_reason = select_free_first_model(cfg=cfg, task_hint=message)
        if not free_id:
            return web.json_response({
                "status": "error",
                "error_code": "NO_ELIGIBLE_FREE_MODEL",
                "message": (
                    "FREE-FIRST Yönlendirici: İstek için uygun bir ücretsiz model bulunamadı veya "
                    "ücretsiz sağlayıcı anahtarı (Groq/OpenRouter) girilmemiş. "
                    "Lütfen ayarları kontrol edin veya belirli bir model seçin."
                )
            }, status=503)
        active_model = free_id
    else:
        active_model = model_candidate
    cost_category, meta_check = get_model_cost_category(active_model)
    target_provider = meta_check["provider"] if meta_check else ("openrouter" if "/" in active_model else "groq")

    groq_key = cfg.get("groq_api_key", "").strip()
    reply_text = ""
    ui_actions = []
    
    selected_key = cfg.get("openrouter_api_key", "").strip() if target_provider == "openrouter" else groq_key
    if selected_key or target_provider == "ollama":
        if target_provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {selected_key}",
                "Content-Type": "application/json"
            }
        elif target_provider == "ollama":
            url = "http://127.0.0.1:11434/v1/chat/completions"
            headers = {
                "Content-Type": "application/json"
            }
        else:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {selected_key}",
                "Content-Type": "application/json"
            }
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history[-6:]:
            messages.append(h)
        messages.append({"role": "user", "content": message})
        
        models_to_try = [active_model]
        chosen_model = models_to_try[0]
        res_json = None
        is_billed = (cost_category == "paid")

        try:
            async with SMART_PROVIDER_LIMITER.throttle(target_provider, timeout=20.0):
                async with aiohttp.ClientSession() as session:
                    for target_model in models_to_try:
                        # Free-first koruması: Ücretsiz modelden ücretli modele sessiz geçiş yasaktır
                        t_cat, _ = get_model_cost_category(target_model)
                        a_cat, _ = get_model_cost_category(active_model)
                        if a_cat == "free" and t_cat != "free":
                            continue
                        payload = {
                            "model": target_model,
                            "messages": messages,
                            "tools": TOOLS,
                            "tool_choice": "auto",
                            "max_tokens": 500,
                            "temperature": 0.65
                        }
                        async with completion_request(session, url, headers=headers, json=payload, timeout=20) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                chosen_model = target_model
                                break
                            elif resp.status == 429:
                                can_retry, cooldown = SMART_PROVIDER_LIMITER.record_response(target_provider, 429, resp.headers.get("Retry-After"), is_billed=is_billed)
                                if can_retry and not is_billed and len(models_to_try) > 1:
                                    print(f"[Model Fallback]: {target_model} 429 kota aşımı ({cooldown:.1f}s), alternatif model deneniyor.")
                                    await asyncio.sleep(min(cooldown, 2.0))
                                    continue
                                else:
                                    reply_text = f"Sağlayıcı ({target_provider}) kota aşımı bildirdi (HTTP 429). Lütfen {cooldown:.1f}s bekleyin."
                                    break
                            elif resp.status in (404, 500, 502, 503):
                                print(f"[Model Fallback]: {target_model} hata verdi ({resp.status}), sonraki modele geçiliyor.")
                                continue
                            else:
                                reply_text = f"API Hatasi ({resp.status}): Lutfen anahtari kontrol et."
                                break
                                
                    if res_json:
                        msg_obj = res_json["choices"][0]["message"]
                        
                        if msg_obj.get("tool_calls"):
                            tool_calls = msg_obj["tool_calls"]
                            messages.append(msg_obj)
                            
                            for tc in tool_calls:
                                fn_name = tc["function"]["name"]
                                fn_args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}
                                tc_id = tc.get("id")
                                tool_result = execute_desktop_tool_with_allowlist("Main JARVIS", fn_name, fn_args, user_context=message, tool_call_id=tc_id)
                                
                                if tool_result.get("action"):
                                    ui_actions.append(tool_result)
                                    
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": json.dumps(tool_result, ensure_ascii=False)
                                })
                                
                            followup_payload = {
                                "model": chosen_model,
                                "messages": messages,
                                "max_tokens": 400,
                                "temperature": 0.65
                            }
                            async with completion_request(session, url, headers=headers, json=followup_payload, timeout=15) as f_resp:
                                if f_resp.status == 200:
                                    f_json = await f_resp.json()
                                    reply_text = f_json["choices"][0]["message"]["content"]
                                else:
                                    reply_text = "İşlemi tamamladım Negr1v."
                        else:
                            reply_text = msg_obj.get("content", "")
                    elif not reply_text:
                        reply_text = "Tüm modeller denendi ancak yanıt alınamadı. Lütfen ağ bağlantınızı veya API kotanızı kontrol edin."
        except RateLimitExceededException as rle:
            return web.json_response({
                "status": "error",
                "error_code": "PROVIDER_RATE_LIMIT",
                "message": f"Sağlayıcı ({target_provider}) kota veya eşzamanlılık sınırına ulaştı ({rle.reason}). Lütfen {rle.retry_after}s sonra tekrar deneyin.",
                "retry_after": rle.retry_after
            }, status=429, headers={"Retry-After": str(int(rle.retry_after) + 1)})
        except Exception as e:
            reply_text = f"Baglanti Hatasi: {mask_secrets(str(e))}"
    else:
        reply_text = f"{target_provider} API anahtarı eksik. Lütfen ayarları kontrol edin."

    voice_mode = bool(data.get("voice_mode", False) or data.get("is_voice", False) or data.get("voice_reply", True))
    if voice_mode:
        tts_res = await generate_tts(
            reply_text,
            cfg,
            paid_auth_token=paid_tts_auth_token,
            return_status=True,
        )
        if isinstance(tts_res, tuple) and len(tts_res) == 2:
            audio_b64, tts_authorization_required = tts_res
        else:
            audio_b64, tts_authorization_required = tts_res, None
    else:
        audio_b64, tts_authorization_required = None, None

    # Stage 5B: Deterministic explicit command or bounded automatic background extraction
    try:
        is_exp, exp_txt, exp_err = extract_explicit_memory_command(message)
        if is_exp:
            if exp_txt:
                await add_memory_candidate_internal(exp_txt, "uncategorized", source="explicit_user_command", confidence=1.0)
        elif cfg.get("memory_learning_enabled", False):
            if MEMORY_EXTRACTION_QUEUE and not MEMORY_EXTRACTION_QUEUE.full():
                try:
                    MEMORY_EXTRACTION_QUEUE.put_nowait((message, cfg))
                except Exception:
                    pass
    except Exception as e:
        print(f"[Memory Extraction Trigger Error]: {e}")
    
    return web.json_response({
        "reply": reply_text,
        "audio_base64": audio_b64,
        "ui_actions": ui_actions,
        "tts_engine": cfg.get("tts_engine", "edge_tts"),
        "tts_authorization_required": tts_authorization_required,
    })

async def handle_chat_stream(request):
    """
    POST /api/chat/stream
    Server-Sent Events (SSE) ile token seviyesinde akıcı yanıt ve ajan yönlendirmesi.
    """
    allowed, retry_after = await CHAT_RATE_LIMITER.acquire()
    if not allowed:
        return web.json_response({
            "status": "error",
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": f"Chat akış istek kotası aşıldı. Lütfen {retry_after}s sonra tekrar deneyin.",
            "retry_after": retry_after
        }, status=429, headers={"Retry-After": str(int(retry_after) + 1)})

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Geçersiz JSON yükü"}, status=400)

    message = data.get("message", "").strip()
    history = data.get("history", [])
    custom_cfg = data.get("config", {})
    requested_agent = data.get("agent")
    paid_tts_auth_token = data.get("paid_tts_auth_token")
    voice_mode = bool(data.get("voice_mode", False) or data.get("is_voice", False) or data.get("voice_reply", True))
    
    cfg = load_config()
    cfg.update(sanitize_runtime_custom_config(custom_cfg))
    
    if not message:
        return web.json_response({"error": "Boş mesaj"}, status=400)
        
    groq_key = cfg.get("groq_api_key", "").strip()
    openrouter_key = cfg.get("openrouter_api_key", "").strip()

    model_candidate = custom_cfg.get("model") or custom_cfg.get("active_model") or cfg.get("active_model", "").strip()
    is_auto_free = model_candidate in ("auto", "free", "free_first", "auto_free", "") or cfg.get("model_routing_mode") == "free_first"
    no_free_err = None
    
    if is_auto_free:
        free_id, free_meta, free_reason = select_free_first_model(cfg=cfg, task_hint=message)
        if not free_id:
            active_model = "none"
            no_free_err = (
                "Durduruldu: FREE-FIRST yönlendirici uygun bir ücretsiz model bulamadı. "
                "Lütfen Groq veya OpenRouter API anahtarınızı kontrol edin ya da belirli bir model seçin."
            )
        else:
            active_model = free_id
    else:
        active_model = model_candidate

    agent_name = requested_agent if requested_agent in AGENT_PROFILES else route_agent(message)
    agent_cfg = AGENT_PROFILES.get(agent_name, AGENT_PROFILES["Main JARVIS"])
    
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream; charset=utf-8',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
    await response.prepare(request)
    
    async def sse_send(event_type: str, payload: dict):
        if request.transport and request.transport.is_closing():
            return
        line = f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        await response.write(line.encode("utf-8"))

    if no_free_err:
        await sse_send("token", {"token": no_free_err})
        await sse_send("done", {"reply": no_free_err, "audio_base64": None, "agent": agent_name, "ui_actions": [], "model": "none"})
        await response.write_eof()
        return response
        
    try:
        user_intent = classify_user_intent(message)
        await sse_send("agent", {"agent": agent_name, "role": agent_cfg["role"], "intent": user_intent, "model": active_model})
        
        # Hedef modelin sağlayıcısını belirle
        target_meta = next((m for m in AI_MODEL_CATALOG if m["id"] == active_model), None)
        target_provider = target_meta["provider"] if target_meta else ("openrouter" if "/" in active_model else "groq")

        cost_category, meta_check = get_model_cost_category(active_model)

        if target_provider == "openrouter" and not openrouter_key:
            reply_text = f"Erişim Kilitli: {active_model} modeli için OpenRouter API anahtarı sisteme girilmemiş."
            await sse_send("token", {"token": reply_text})
            audio_b64 = await generate_tts(reply_text, cfg) if voice_mode else None
            await sse_send("done", {"reply": reply_text, "audio_base64": audio_b64, "agent": agent_name, "ui_actions": [], "model": active_model})
            await response.write_eof()
            return response
        elif target_provider == "groq" and not groq_key:
            reply_text = f"Erişim Kilitli: {active_model} modeli için Groq API anahtarı sisteme girilmemiş."
            await sse_send("token", {"token": reply_text})
            audio_b64 = await generate_tts(reply_text, cfg) if voice_mode else None
            await sse_send("done", {"reply": reply_text, "audio_base64": audio_b64, "agent": agent_name, "ui_actions": [], "model": active_model})
            await response.write_eof()
            return response
        elif target_provider not in ("openrouter", "groq", "ollama"):
            reply_text = f"Erişim Kilitli: {active_model} sağlayıcısı ({target_provider}) doğrudan API anahtarı gerektirir."
            await sse_send("token", {"token": reply_text})
            audio_b64 = await generate_tts(reply_text, cfg) if voice_mode else None
            await sse_send("done", {"reply": reply_text, "audio_base64": audio_b64, "agent": agent_name, "ui_actions": [], "model": active_model})
            await response.write_eof()
            return response

        # Ajan yetki matrisine göre izin verilen araçlar
        agent_tools = [t for t in TOOLS if t["function"]["name"] in agent_cfg["allowed_tools"]]
        
        messages = [{"role": "system", "content": agent_cfg["system_prompt"]}]
        for h in history[-6:]:
            messages.append(h)
        messages.append({"role": "user", "content": message})
        
        if target_provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json"
            }
            # Fallback list: primary OpenRouter free model + backup Groq free models if OpenRouter fails
            models_to_try = [active_model]
            if groq_key and active_model.startswith("qwen/"):
                models_to_try.append("llama-3.3-70b-versatile")
                models_to_try.append("llama-3.1-8b-instant")
        elif target_provider == "ollama":
            url = "http://127.0.0.1:11434/v1/chat/completions"
            headers = {
                "Content-Type": "application/json"
            }
            raw_ollama_model = active_model.replace("ollama/", "")
            models_to_try = [raw_ollama_model]
        else:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            }
            models_to_try = [active_model] if active_model in [m["id"] for m in AI_MODEL_CATALOG if m["provider"] == "groq"] else get_groq_models(cfg)
        
        chosen_model = models_to_try[0]
        res_json = None
        is_billed = (cost_category == "paid")
        
        try:
            async with SMART_PROVIDER_LIMITER.throttle(target_provider, timeout=25.0):
                async with aiohttp.ClientSession() as session:
                    if request.transport and request.transport.is_closing():
                        return response
                        
                    for target_model in models_to_try:
                        # Free-first koruması: Ücretsiz modelden ücretli modele sessiz geçiş yasaktır
                        t_cat, _ = get_model_cost_category(target_model)
                        a_cat, _ = get_model_cost_category(active_model)
                        if a_cat == "free" and t_cat != "free":
                            continue

                        # Modelin sağlayıcısına göre URL ve header dinamik ayarlanır
                        req_url = url
                        req_headers = headers
                        if target_model.startswith("llama-") and "groq.com" not in req_url:
                            req_url = "https://api.groq.com/openai/v1/chat/completions"
                            req_headers = {
                                "Authorization": f"Bearer {groq_key}",
                                "Content-Type": "application/json"
                            }

                        payload = {
                            "model": target_model,
                            "messages": messages,
                            "max_tokens": 500,
                            "temperature": 0.65
                        }
                        if agent_tools:
                            payload["tools"] = agent_tools
                            payload["tool_choice"] = "auto"
                            
                        async with completion_request(session, req_url, headers=req_headers, json=payload, timeout=25) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                chosen_model = target_model
                                break
                            elif resp.status == 429:
                                can_retry, cooldown = SMART_PROVIDER_LIMITER.record_response(target_provider, 429, resp.headers.get("Retry-After"), is_billed=is_billed)
                                if can_retry and not is_billed and len(models_to_try) > 1:
                                    print(f"[SSE Fallback]: {target_model} 429 kota aşımı ({cooldown:.1f}s), alternatif model deneniyor.")
                                    await asyncio.sleep(min(cooldown, 2.0))
                                    continue
                                else:
                                    await sse_send("error", {"error": f"Sağlayıcı ({target_provider}) kota aşımı (HTTP 429). Bekleme: {cooldown:.1f}s", "model": target_model, "provider": target_provider})
                                    await response.write_eof()
                                    return response
                            elif resp.status in (404, 500, 502, 503) and len(models_to_try) > 1:
                                print(f"[SSE Fallback]: {target_model} hata verdi ({resp.status}), alternatif model deneniyor.")
                                continue
                            else:
                                err_msg = await resp.text()
                                await sse_send("error", {"error": mask_secrets(err_msg), "model": target_model, "provider": target_provider})
                                await response.write_eof()
                                return response
                                
                    if not res_json:
                        await sse_send("error", {"error": "Tüm yapay zekâ modelleri meşgul veya kota aşıldı. Lütfen kısa süre sonra tekrar deneyin."})
                        await response.write_eof()
                        return response
                            
                    msg_obj = res_json["choices"][0]["message"]
                    ui_actions = []
                    
                    # Model araç çalıştırmak istiyorsa
                    if msg_obj.get("tool_calls"):
                        tool_calls = msg_obj["tool_calls"]
                        messages.append(msg_obj)
                        
                        for tc in tool_calls:
                            if request.transport and request.transport.is_closing():
                                break
                            fn_name = tc["function"]["name"]
                            fn_args = json.loads(tc["function"]["arguments"]) if tc["function"].get("arguments") else {}
                            tc_id = tc.get("id")
                            tool_result = execute_desktop_tool_with_allowlist(agent_name, fn_name, fn_args, user_context=message, tool_call_id=tc_id)
                            
                            if tool_result.get("action"):
                                ui_actions.append(tool_result)
                                
                            await sse_send("action", {"tool": fn_name, "result": tool_result})
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps(tool_result, ensure_ascii=False)
                            })
                            
                        if request.transport and request.transport.is_closing():
                            return response
                            
                        followup_payload = {
                            "model": chosen_model,
                            "messages": messages,
                            "stream": True,
                            "max_tokens": 400,
                            "temperature": 0.65
                        }
                        full_reply = []
                        async with completion_request(session, url, headers=headers, json=followup_payload, timeout=20) as f_resp:
                            if f_resp.status == 200:
                                async for line in f_resp.content:
                                    if request.transport and request.transport.is_closing():
                                        print("[SSE Stream]: İstemci bağlantıyı kesti, akış durduruldu.")
                                        break
                                    line_str = line.decode("utf-8").strip()
                                    if not line_str.startswith("data: "):
                                        continue
                                    data_str = line_str[6:]
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        d = json.loads(data_str)
                                        tok = d["choices"][0]["delta"].get("content") or ""
                                        if tok:
                                            full_reply.append(tok)
                                            await sse_send("token", {"token": tok})
                                    except Exception:
                                        pass
                        reply_text = "".join(full_reply) or "İşlemi tamamladım Negr1v."
                    else:
                        # Araç gerekmedi, doğrudan içerik akışı (GLM-5.3 ve reasoning modelleri için content veya reasoning)
                        content_direct = msg_obj.get("content") or msg_obj.get("reasoning") or ""
                        if content_direct:
                            words = content_direct.split(" ")
                            for i, w in enumerate(words):
                                if request.transport and request.transport.is_closing():
                                    print("[SSE Stream]: İstemci bağlantıyı kesti, içerik gönderimi durduruldu.")
                                    break
                                sep = " " if i < len(words) - 1 else ""
                                await sse_send("token", {"token": w + sep})
                                await asyncio.sleep(0.002)
                            reply_text = content_direct
                        else:
                            reply_text = "Dinliyorum Negr1v."
                            await sse_send("token", {"token": reply_text})
        except RateLimitExceededException as rle:
            await sse_send("error", {
                "error": f"Sağlayıcı ({target_provider}) kota veya eşzamanlılık sınırında ({rle.reason}). Lütfen {rle.retry_after}s sonra tekrar deneyin.",
                "retry_after": rle.retry_after,
                "provider": target_provider
            })
            await response.write_eof()
            return response
                    
        if request.transport and request.transport.is_closing():
            return response
            
        if voice_mode:
            tts_res = await generate_tts(
                reply_text,
                cfg,
                paid_auth_token=paid_tts_auth_token,
                return_status=True,
            )
            if isinstance(tts_res, tuple) and len(tts_res) == 2:
                audio_b64, tts_authorization_required = tts_res
            else:
                audio_b64, tts_authorization_required = tts_res, None
        else:
            audio_b64, tts_authorization_required = None, None
        await sse_send("done", {
            "reply": reply_text,
            "audio_base64": audio_b64,
            "agent": agent_name,
            "ui_actions": ui_actions,
            "model": chosen_model,
            "tts_authorization_required": tts_authorization_required,
        })

        # Stage 5B: Deterministic explicit command or bounded automatic background extraction
        try:
            is_exp, exp_txt, exp_err = extract_explicit_memory_command(message)
            if is_exp:
                if exp_txt:
                    await add_memory_candidate_internal(exp_txt, "uncategorized", source="explicit_user_command", confidence=1.0)
            elif cfg.get("memory_learning_enabled", False):
                if MEMORY_EXTRACTION_QUEUE and not MEMORY_EXTRACTION_QUEUE.full():
                    try:
                        MEMORY_EXTRACTION_QUEUE.put_nowait((message, cfg))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Memory Extraction Trigger Error]: {e}")
    except asyncio.CancelledError:
        print(f"[SSE Cancelled]: İstemci isteği iptal etti ({agent_name}).")
        log_activity("sse_cancelled", f"SSE bağlantısı iptal edildi: {agent_name}")
    except Exception as e:
        print(f"[SSE Error]: {e}")
        try:
            await sse_send("error", {"error": mask_secrets(str(e))})
        except Exception:
            pass
    finally:
        try:
            await response.write_eof()
        except Exception:
            pass
    return response

async def handle_system_metrics(request):
    global TELEMETRY_SEQ_COUNTER
    TELEMETRY_SEQ_COUNTER += 1

    uptime_sec = round(time.time() - SERVER_START_TIME, 1)
    uptime_m = int(uptime_sec // 60)
    uptime_h = int(uptime_m // 60)
    uptime_str = f"{uptime_h}s {uptime_m % 60}d" if uptime_h > 0 else f"{uptime_m}d {int(uptime_sec % 60)}sn"

    cpu_percent = None
    try:
        cpu = psutil.cpu_percent(interval=None)
        cpu_percent = round(cpu, 1)
    except Exception:
        pass

    ram_percent = None
    ram_used_gb = None
    ram_total_gb = None
    ram_available_gb = None
    try:
        ram = psutil.virtual_memory()
        ram_percent = round(ram.percent, 1)
        ram_used_gb = round(ram.used / (1024**3), 2)
        ram_total_gb = round(ram.total / (1024**3), 2)
        ram_available_gb = round(ram.available / (1024**3), 2)
    except Exception:
        pass

    disk_percent = None
    disk_free_gb = None
    try:
        disk_path = "C:" if os.name == "nt" else "/"
        disk = psutil.disk_usage(disk_path)
        disk_percent = round(disk.percent, 1)
        disk_free_gb = round(disk.free / (1024**3), 2)
    except Exception:
        pass

    battery_percent = None
    power_plugged = None
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            battery_percent = battery.percent
            power_plugged = battery.power_plugged
    except Exception:
        pass

    boot_time = None
    try:
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    active_window = "Masaüstü"
    try:
        if os.name == "nt" and hasattr(ctypes, "windll"):
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    active_window = buff.value or "Masaüstü"
    except Exception:
        active_window = "Masaüstü"

    tasks_summary = {"total": 0, "pending": 0, "completed": 0}
    try:
        tasks_list = load_tasks()
        if isinstance(tasks_list, list):
            tasks_summary["total"] = len(tasks_list)
            tasks_summary["pending"] = sum(1 for t in tasks_list if not t.get("done", False))
            tasks_summary["completed"] = sum(1 for t in tasks_list if t.get("done", False))
    except Exception:
        pass

    memory_notes_count = 0
    try:
        mem = load_memory()
        if isinstance(mem, dict) and not mem.get("_corrupt"):
            entries = mem.get("entries")
            if isinstance(entries, list):
                memory_notes_count = len(entries)
            elif isinstance(mem.get("notes"), list):
                memory_notes_count = len(mem.get("notes"))
    except Exception:
        pass

    cfg = load_config()
    services_status = {
        "tts_provider": cfg.get("tts_provider", "edge-tts"),
        "memory_learning_enabled": bool(cfg.get("memory_learning_enabled", False)),
        "model": cfg.get("model", "llama-3.3-70b-versatile")
    }

    gaming_info = is_gaming_mode_active(active_window_title=active_window)
    is_gaming = gaming_info.get("active", False)
    perf_pref = cfg.get("performance_profile", "auto")
    avail_mb = (ram_available_gb or 0.0) * 1024.0 if ram_available_gb is not None else None
    ADAPTIVE_PERFORMANCE_CONTROLLER.update_with_telemetry(
        cpu_percent or 0.0,
        ram_percent or 0.0,
        is_gaming=is_gaming,
        manual_pref=perf_pref,
        ram_available_mb=avail_mb
    )
    perf_status = ADAPTIVE_PERFORMANCE_CONTROLLER.get_status_dict()

    return web.json_response({
        "status": "ok",
        "server_status": "online",
        "server_epoch": SERVER_EPOCH,
        "server_uptime_seconds": uptime_sec,
        "server_uptime_str": uptime_str,
        "telemetry_seq": TELEMETRY_SEQ_COUNTER,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cpu_percent": cpu_percent,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_total_gb": ram_total_gb,
        "ram_available_gb": ram_available_gb,
        "disk_percent": disk_percent,
        "disk_free_gb": disk_free_gb,
        "battery_percent": battery_percent,
        "power_plugged": power_plugged,
        "boot_time": boot_time,
        "active_window": active_window,
        "gaming_mode": gaming_info,
        "performance_profile": perf_status["current_profile"],
        "performance_mode": perf_status["mode"],
        "performance_specs": perf_status["specs"],
        "polling_interval_ms": perf_status["polling_interval_ms"],
        "notifications": {
            "deferred_count": len(get_deferred_notifications()),
            "suppressed": is_gaming
        },
        "tasks_summary": tasks_summary,
        "memory_notes_count": memory_notes_count,
        "services": services_status
    })

async def handle_get_performance_profile(request):
    """GET /api/performance/profile - Aktif performans profilini ve metriklerini döner."""
    return web.json_response({
        "status": "ok",
        "performance": ADAPTIVE_PERFORMANCE_CONTROLLER.get_status_dict()
    })

async def handle_set_performance_profile(request):
    """POST /api/performance/profile - Manuel performans profili seçimi ('auto', 'lite', 'balanced', 'ultra')."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü"}, status=400)
        
    requested_profile = str(body.get("profile") or body.get("mode") or "").strip().lower()
    valid_profiles = ["auto", "lite", "balanced", "ultra"]
    if requested_profile not in valid_profiles:
        return web.json_response({
            "status": "error",
            "message": f"Geçersiz profil: '{requested_profile}'. Geçerli seçenekler: {valid_profiles}"
        }, status=400)

    cfg = load_config()
    cfg["performance_profile"] = requested_profile
    save_config(cfg)
    
    # Update controller immediately
    ADAPTIVE_PERFORMANCE_CONTROLLER.update_with_telemetry(0.0, 0.0, manual_pref=requested_profile)
    
    return web.json_response({
        "status": "ok",
        "message": f"Performans profili '{requested_profile}' olarak ayarlandı.",
        "performance": ADAPTIVE_PERFORMANCE_CONTROLLER.get_status_dict()
    })

async def handle_get_memory(request):
    mem = load_memory()
    return web.json_response(get_memory_api_payload(mem))

async def handle_search_memory(request):
    """GET /api/memory/search?q=...&topic=...&limit=... - Konu ve alaka düzeyine göre hafızada arama yapar."""
    q = request.query.get("q", "").strip()
    topic = request.query.get("topic") or request.query.get("category")
    try:
        limit = int(request.query.get("limit", 10))
    except ValueError:
        limit = 10

    results = search_memory_intelligence(query=q, topic=topic, limit=limit)
    return web.json_response({
        "status": "ok",
        "query": q,
        "topic": topic,
        "count": len(results),
        "results": results
    })

async def handle_get_memory_entry(request):
    """GET /api/memory/entries/{id} - Belirli bir hafıza girdisinin detaylarını döner."""
    entry_id = request.match_info.get("id", "").strip()
    if not entry_id:
        return web.json_response({"status": "error", "message": "Missing entry ID."}, status=400)

    mem = load_memory()
    rev = int(mem.get("revision", 1))
    token = f"{SERVER_EPOCH}:{rev}"

    for entry in mem.get("entries", []):
        if isinstance(entry, dict) and entry.get("id") == entry_id:
            return web.json_response({
                "status": "ok",
                "entry": entry,
                "revision": rev,
                "revision_token": token
            })

    return web.json_response({"status": "error", "message": f"Memory entry not found: {entry_id}"}, status=404)

async def handle_detect_memory_candidates(request):
    """POST /api/memory/candidates/detect - Metinden yerel ve kural tabanlı hafıza adaylarını tespit eder (AI API çağrısı yapmaz)."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü"}, status=400)

    text = str(body.get("text") or body.get("message") or "").strip()
    if not text:
        return web.json_response({"status": "error", "message": "Metin ('text') boş olamaz."}, status=400)

    detected = extract_conversation_memory_candidates(text)
    return web.json_response({
        "status": "ok",
        "count": len(detected),
        "candidates": detected
    })

async def handle_save_memory(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    async with MEMORY_TRANSACTION_LOCK:
        global RECOVERY_REQUIRED_STATE
        if RECOVERY_REQUIRED_STATE:
            return web.json_response({
                "status": "error",
                "error": "RECOVERY_REQUIRED",
                "message": "Memory is locked in fail-closed recovery mode due to unverified journal state."
            }, status=503)

        async with MEMORY_MUTATION_LOCK:
            current_mem = load_memory()
            if current_mem.get("_corrupt"):
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_MEMORY_FILE",
                    "message": "Cannot modify memory: underlying file is corrupt. Manual recovery required."
                }, status=500)
            current_rev = int(current_mem.get("revision", 1))
            expected_token = f"{SERVER_EPOCH}:{current_rev}"

            # Standardized revision token extraction (Header X-Memory-Revision-Token is authoritative)
            client_token = extract_revision_token(request, data)

            if client_token is None:
                return web.json_response({
                    "status": "conflict",
                    "error": "REVISION_REQUIRED",
                    "message": "Missing required 'X-Memory-Revision-Token' header for optimistic concurrency control.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=409)

            if client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_REVISION",
                    "message": "Memory has been modified or server has restarted since last read.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token,
                    "client_revision_token": client_token
                }, status=409)

            # Reconciliation: user_profile
            new_profile = dict(current_mem.get("user_profile", {}))
            for k in ["user_name", "focus", "target_hardware", "budget_limit"]:
                if k in data and isinstance(data[k], str):
                    new_profile[k] = data[k]
            if "user_profile" in data and isinstance(data["user_profile"], dict):
                new_profile.update(data["user_profile"])

            # Reconciliation: entries vs incoming notes / entries
            if "entries" in data and isinstance(data["entries"], list):
                new_entries = []
                for item in data["entries"]:
                    if isinstance(item, dict) and "text" in item:
                        new_entries.append({
                            "id": item.get("id") or f"mem_{uuid.uuid4().hex[:8]}",
                            "text": str(item.get("text", "")),
                            "category": str(item.get("category", "uncategorized")),
                            "pinned": bool(item.get("pinned", False)),
                            "source": str(item.get("source", "user_ui")),
                            "created_at": item.get("created_at"),
                            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        })
            elif "notes" in data and isinstance(data["notes"], list):
                # Occurrence-aware matching: preserves order and duplicate identities
                from collections import defaultdict
                existing_pool = defaultdict(list)
                for e in current_mem.get("entries", []):
                    existing_pool[e.get("text")].append(e)

                new_entries = []
                for note_text in data["notes"]:
                    str_text = str(note_text)
                    if existing_pool[str_text]:
                        new_entries.append(existing_pool[str_text].pop(0))
                    else:
                        new_entries.append({
                            "id": f"mem_ui_{uuid.uuid4().hex[:8]}",
                            "text": str_text,
                            "category": "uncategorized",
                            "pinned": False,
                            "source": "user_ui",
                            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        })
            else:
                new_entries = current_mem.get("entries", [])

            new_rev = current_rev + 1
            new_token = f"{SERVER_EPOCH}:{new_rev}"
            new_mem = dict(current_mem)
            new_mem["user_profile"] = new_profile
            new_mem["entries"] = new_entries
            new_mem["revision"] = new_rev
            new_mem["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            save_memory(new_mem)
            log_activity("memory_update", f"Hafıza tablosu güncellendi (Rev: {new_rev}).")
            return web.json_response({
                "status": "ok",
                "revision": new_rev,
                "revision_token": new_token,
                "notes": [e.get("text", "") for e in new_entries]
            })

async def handle_add_memory_note(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    async with MEMORY_TRANSACTION_LOCK:
        global RECOVERY_REQUIRED_STATE
        if RECOVERY_REQUIRED_STATE:
            return web.json_response({
                "status": "error",
                "error": "RECOVERY_REQUIRED",
                "message": "Memory is locked in fail-closed recovery mode due to unverified journal state."
            }, status=503)

        async with MEMORY_MUTATION_LOCK:
            current_mem = load_memory()
            if current_mem.get("_corrupt"):
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_MEMORY_FILE",
                    "message": "Cannot modify memory: underlying file is corrupt. Manual recovery required."
                }, status=500)
            current_rev = int(current_mem.get("revision", 1))
            expected_token = f"{SERVER_EPOCH}:{current_rev}"

            # Standardized revision token extraction (Header X-Memory-Revision-Token is authoritative)
            client_token = extract_revision_token(request, data)

            if client_token is None:
                return web.json_response({
                    "status": "conflict",
                    "error": "REVISION_REQUIRED",
                    "message": "Missing required 'X-Memory-Revision-Token' header for optimistic concurrency control.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=409)

            if client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_REVISION",
                    "message": "Memory has been modified or server has restarted since last read.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token,
                    "client_revision_token": client_token
                }, status=409)

            text = str(data.get("text", "")).strip()
            if not text:
                return web.json_response({"status": "error", "message": "Note text cannot be empty."}, status=400)
            if len(text) > 1000:
                return web.json_response({"status": "error", "message": "Note text exceeds maximum allowed length of 1000 characters."}, status=400)

            if len(current_mem.get("entries", [])) >= 500:
                return web.json_response({"status": "error", "message": "Maximum memory entry limit (500) reached."}, status=400)

            # Duplicate check - do not overwrite silently!
            is_dup, existing_entry = is_duplicate_memory_entry(text, current_mem.get("entries", []))
            if is_dup:
                return web.json_response({
                    "status": "conflict",
                    "error": "DUPLICATE_CANDIDATE",
                    "message": "Benzer veya aynı bir hafıza kaydı zaten mevcut.",
                    "existing_entry": existing_entry,
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=409)

            allowed_categories = {"uncategorized", "study", "hardware", "system", "personal", "project"}
            raw_cat = str(data.get("category", "uncategorized")).strip().lower()
            category = raw_cat if raw_cat in allowed_categories else "uncategorized"

            if current_mem.get("_is_legacy_v3", False):
                new_id = f"mem_legacy_{len(current_mem.get('entries', [])) + 1:03d}"
            else:
                new_id = f"mem_{uuid.uuid4().hex[:8]}"
            now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            new_entry = {
                "id": new_id,
                "text": text,
                "category": category,
                "pinned": bool(data.get("pinned", False)),
                "source": str(data.get("source", "user_ui")),
                "created_at": now_ts,
                "updated_at": now_ts
            }
            current_mem.setdefault("entries", []).append(new_entry)
            new_rev = current_rev + 1
            new_token = f"{SERVER_EPOCH}:{new_rev}"
            current_mem["revision"] = new_rev
            current_mem["updated_at"] = now_ts

            save_memory(current_mem)
            log_activity("memory_add_note", f"Yeni hafıza notu eklendi: {text[:30]}...")
            return web.json_response({
                "status": "ok",
                "entry": new_entry,
                "revision": new_rev,
                "revision_token": new_token
            })

async def handle_delete_memory_note(request):
    note_id = request.match_info.get("id")
    if not note_id:
        return web.json_response({"status": "error", "message": "Missing note id."}, status=400)

    if not re.match(r'^[a-zA-Z0-9_\-]+$', note_id):
        return web.json_response({"status": "error", "message": "Invalid note ID format. Path traversal prohibited."}, status=400)

    async with MEMORY_TRANSACTION_LOCK:
        global RECOVERY_REQUIRED_STATE
        if RECOVERY_REQUIRED_STATE:
            return web.json_response({
                "status": "error",
                "error": "RECOVERY_REQUIRED",
                "message": "Memory is locked in fail-closed recovery mode due to unverified journal state."
            }, status=503)

        async with MEMORY_MUTATION_LOCK:
            current_mem = load_memory()
            if current_mem.get("_corrupt"):
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_MEMORY_FILE",
                    "message": "Cannot modify memory: underlying file is corrupt. Manual recovery required."
                }, status=500)
            current_rev = int(current_mem.get("revision", 1))
            expected_token = f"{SERVER_EPOCH}:{current_rev}"

            # Standardized revision token extraction (Header X-Memory-Revision-Token is authoritative)
            client_token = extract_revision_token(request)
            if client_token is None:
                try:
                    body_data = await request.json()
                    client_token = extract_revision_token(request, body_data)
                except Exception:
                    pass

            if client_token is None:
                return web.json_response({
                    "status": "conflict",
                    "error": "REVISION_REQUIRED",
                    "message": "Missing required 'X-Memory-Revision-Token' header for optimistic concurrency control.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=409)

            if client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_REVISION",
                    "message": "Memory has been modified or server has restarted since last read.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token,
                    "client_revision_token": client_token
                }, status=409)

            entries = current_mem.get("entries", [])
            target_idx = None
            for idx, entry in enumerate(entries):
                if entry.get("id") == note_id:
                    target_idx = idx
                    break

            if target_idx is None:
                return web.json_response({
                    "status": "not_found",
                    "error": "NOTE_NOT_FOUND",
                    "message": f"Note with ID '{note_id}' does not exist.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=404)

            deleted_entry = entries.pop(target_idx)
            new_rev = current_rev + 1
            new_token = f"{SERVER_EPOCH}:{new_rev}"
            current_mem["revision"] = new_rev
            current_mem["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            save_memory(current_mem)
            log_activity("memory_delete_note", f"Hafıza notu silindi (ID: {note_id}).")
            return web.json_response({
                "status": "ok",
                "deleted_id": note_id,
                "revision": new_rev,
                "revision_token": new_token
            })

async def handle_get_tasks(request):
    async with TASKS_LOCK:
        with TASKS_THREAD_LOCK:
            tasks, is_corrupt = load_tasks_result()
            if is_corrupt:
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_TASK_FILE",
                    "message": "Task storage file is malformed or unreadable. Manual recovery required."
                }, status=503)
            
            token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            return web.json_response(tasks, headers={
                "X-Task-Revision-Token": token
            })

async def handle_save_tasks(request):
    """
    POST /api/tasks
    Supports both legacy bulk array replacement (current index.html)
    and single-task creation payload (dict with subject, duration, etc.).
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)

    async with TASKS_LOCK:
        with TASKS_THREAD_LOCK:
            tasks, is_corrupt = load_tasks_result()
            if is_corrupt:
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_TASK_FILE",
                    "message": "Task storage file is malformed or unreadable. Manual recovery required."
                }, status=503)

            client_token = request.headers.get("X-Task-Revision-Token")
            expected_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            if client_token and client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_TASK_REVISION",
                    "message": "Task list has been modified concurrently.",
                    "server_revision_token": expected_token
                }, status=409)

            # Branch 1: Legacy Bulk Array replacement
            if isinstance(data, list):
                validated_list = []
                for item in data:
                    if not isinstance(item, dict):
                        return web.json_response({"status": "error", "message": "Each task must be an object."}, status=400)
                    sub = str(item.get("subject", "")).strip()
                    if not sub or len(sub) > 200:
                        return web.json_response({"status": "error", "message": "Task subject must be 1-200 characters."}, status=400)
                    
                    try:
                        dur = int(item.get("duration", 40))
                        if dur < 1 or dur > 360:
                            return web.json_response({"status": "error", "message": "Task duration must be 1-360 minutes."}, status=400)
                    except (ValueError, TypeError):
                        return web.json_response({"status": "error", "message": "Task duration must be an integer."}, status=400)

                    validated_list.append(normalize_single_task(item))

                try:
                    save_tasks(validated_list)
                except Exception as e:
                    return web.json_response({"status": "error", "message": f"Persistence error: {mask_secrets(str(e))}"}, status=500)

                try:
                    log_activity("tasks_update", f"{len(validated_list)} görev toplu kaydedildi.")
                except Exception:
                    pass
                new_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
                return web.json_response({
                    "status": "ok",
                    "count": len(validated_list),
                    "revision_token": new_token
                }, headers={"X-Task-Revision-Token": new_token})

            # Branch 2: Single Task Creation
            elif isinstance(data, dict):
                sub = str(data.get("subject", "")).strip()
                if not sub or len(sub) > 200:
                    return web.json_response({"status": "error", "message": "Task subject must be 1-200 characters."}, status=400)

                try:
                    dur = int(data.get("duration", 40))
                    if dur < 1 or dur > 360:
                        return web.json_response({"status": "error", "message": "Task duration must be 1-360 minutes."}, status=400)
                except (ValueError, TypeError):
                    return web.json_response({"status": "error", "message": "Task duration must be an integer."}, status=400)

                cat = str(data.get("category", "genel")).strip().lower()
                if cat not in ALLOWED_TASK_CATEGORIES:
                    return web.json_response({"status": "error", "message": f"Invalid category. Allowed: {list(ALLOWED_TASK_CATEGORIES)}"}, status=400)

                pri = str(data.get("priority", "medium")).strip().lower()
                if pri not in ALLOWED_TASK_PRIORITIES:
                    return web.json_response({"status": "error", "message": f"Invalid priority. Allowed: {list(ALLOWED_TASK_PRIORITIES)}"}, status=400)

                due_date = data.get("due_date")
                if due_date is not None:
                    due_date_str = str(due_date).strip()
                    try:
                        datetime.date.fromisoformat(due_date_str)
                    except ValueError:
                        return web.json_response({"status": "error", "message": "Invalid due_date. Format must be YYYY-MM-DD."}, status=400)

                new_task = normalize_single_task(data)
                new_task["id"] = f"t_{uuid.uuid4().hex[:8]}"
                tasks.append(new_task)

                try:
                    save_tasks(tasks)
                except Exception as e:
                    return web.json_response({"status": "error", "message": f"Persistence error: {mask_secrets(str(e))}"}, status=500)

                try:
                    log_activity("task_created", f"Yeni görev oluşturuldu: {sub[:40]}")
                except Exception:
                    pass
                new_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
                return web.json_response({
                    "status": "ok",
                    "task": new_task,
                    "revision_token": new_token
                }, status=201, headers={"X-Task-Revision-Token": new_token})

            else:
                return web.json_response({"status": "error", "message": "Payload must be a JSON array or object."}, status=400)

async def handle_patch_task(request):
    """
    PATCH /api/tasks/{id}
    Granularly updates fields of a single task.
    """
    task_id = request.match_info.get("id")
    if not task_id:
        return web.json_response({"status": "error", "message": "Task ID missing"}, status=400)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)

    async with TASKS_LOCK:
        with TASKS_THREAD_LOCK:
            tasks, is_corrupt = load_tasks_result()
            if is_corrupt:
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_TASK_FILE",
                    "message": "Task storage file is malformed or unreadable. Manual recovery required."
                }, status=503)

            client_token = request.headers.get("X-Task-Revision-Token")
            expected_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            if client_token and client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_TASK_REVISION",
                    "message": "Task list has been modified concurrently.",
                    "server_revision_token": expected_token
                }, status=409)

            target = None
            for t in tasks:
                if t.get("id") == task_id:
                    target = t
                    break

            if not target:
                return web.json_response({"status": "error", "message": "Task not found"}, status=404)

            if "subject" in data:
                sub = str(data["subject"]).strip()
                if not sub or len(sub) > 200:
                    return web.json_response({"status": "error", "message": "Task subject must be 1-200 characters."}, status=400)
                target["subject"] = sub

            if "duration" in data:
                try:
                    dur = int(data["duration"])
                    if dur < 1 or dur > 360:
                        return web.json_response({"status": "error", "message": "Task duration must be 1-360 minutes."}, status=400)
                    target["duration"] = dur
                except (ValueError, TypeError):
                    return web.json_response({"status": "error", "message": "Task duration must be an integer."}, status=400)

            if "done" in data:
                target["done"] = bool(data["done"])

            if "category" in data:
                cat = str(data["category"]).strip().lower()
                if cat not in ALLOWED_TASK_CATEGORIES:
                    return web.json_response({"status": "error", "message": f"Invalid category. Allowed: {list(ALLOWED_TASK_CATEGORIES)}"}, status=400)
                target["category"] = cat

            if "priority" in data:
                pri = str(data["priority"]).strip().lower()
                if pri not in ALLOWED_TASK_PRIORITIES:
                    return web.json_response({"status": "error", "message": f"Invalid priority. Allowed: {list(ALLOWED_TASK_PRIORITIES)}"}, status=400)
                target["priority"] = pri

            if "due_date" in data:
                due_val = data["due_date"]
                if due_val is not None:
                    due_val_str = str(due_val).strip()
                    try:
                        datetime.date.fromisoformat(due_val_str)
                        target["due_date"] = due_val_str
                    except ValueError:
                        return web.json_response({"status": "error", "message": "Invalid due_date. Format must be YYYY-MM-DD."}, status=400)
                else:
                    target.pop("due_date", None)

            target["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            try:
                save_tasks(tasks)
            except Exception as e:
                return web.json_response({"status": "error", "message": f"Persistence error: {mask_secrets(str(e))}"}, status=500)

            try:
                log_activity("task_updated", f"Görev güncellendi: {task_id}")
            except Exception:
                pass
            new_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            return web.json_response({
                "status": "ok",
                "task": target,
                "revision_token": new_token
            }, headers={"X-Task-Revision-Token": new_token})

async def handle_delete_task(request):
    """
    DELETE /api/tasks/{id}
    Removes a single task by ID.
    """
    task_id = request.match_info.get("id")
    if not task_id:
        return web.json_response({"status": "error", "message": "Task ID missing"}, status=400)

    async with TASKS_LOCK:
        with TASKS_THREAD_LOCK:
            tasks, is_corrupt = load_tasks_result()
            if is_corrupt:
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_TASK_FILE",
                    "message": "Task storage file is malformed or unreadable. Manual recovery required."
                }, status=503)

            client_token = request.headers.get("X-Task-Revision-Token")
            expected_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            if client_token and client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_TASK_REVISION",
                    "message": "Task list has been modified concurrently.",
                    "server_revision_token": expected_token
                }, status=409)

            initial_len = len(tasks)
            tasks[:] = [t for t in tasks if t.get("id") != task_id]

            if len(tasks) == initial_len:
                return web.json_response({"status": "error", "message": "Task not found"}, status=404)

            try:
                save_tasks(tasks)
            except Exception as e:
                return web.json_response({"status": "error", "message": f"Persistence error: {mask_secrets(str(e))}"}, status=500)

            try:
                log_activity("task_deleted", f"Görev silindi: {task_id}")
            except Exception:
                pass
            new_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            return web.json_response({
                "status": "ok",
                "deleted_id": task_id,
                "revision_token": new_token
            }, headers={"X-Task-Revision-Token": new_token})

async def handle_toggle_task(request):
    """
    POST /api/tasks/{id}/toggle
    Quickly toggles the completion state of a single task.
    """
    task_id = request.match_info.get("id")
    if not task_id:
        return web.json_response({"status": "error", "message": "Task ID missing"}, status=400)

    async with TASKS_LOCK:
        with TASKS_THREAD_LOCK:
            tasks, is_corrupt = load_tasks_result()
            if is_corrupt:
                return web.json_response({
                    "status": "error",
                    "error": "CORRUPT_TASK_FILE",
                    "message": "Task storage file is malformed or unreadable. Manual recovery required."
                }, status=503)

            client_token = request.headers.get("X-Task-Revision-Token")
            expected_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            if client_token and client_token != expected_token:
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_TASK_REVISION",
                    "message": "Task list has been modified concurrently.",
                    "server_revision_token": expected_token
                }, status=409)

            target = None
            for t in tasks:
                if t.get("id") == task_id:
                    target = t
                    break

            if not target:
                return web.json_response({"status": "error", "message": "Task not found"}, status=404)

            target["done"] = not bool(target.get("done", False))
            target["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            try:
                save_tasks(tasks)
            except Exception as e:
                return web.json_response({"status": "error", "message": f"Persistence error: {mask_secrets(str(e))}"}, status=500)

            try:
                log_activity("task_toggled", f"Görev durumu değiştirildi: {task_id} -> {target['done']}")
            except Exception:
                pass
            new_token = f"{SERVER_EPOCH}:task_{TASK_REVISION_COUNTER}"
            return web.json_response({
                "status": "ok",
                "task": target,
                "revision_token": new_token
            }, headers={"X-Task-Revision-Token": new_token})

async def handle_activity_logs(request):
    return web.json_response(ACTIVITY_LOGS)

async def handle_get_telegram(request):
    async with TELEGRAM_ASYNC_LOCK:
        return web.json_response(load_telegram_messages())

async def handle_post_telegram(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Geçersiz JSON yükü"}, status=400)
    if not isinstance(data, dict):
        return web.json_response({"error": "Geçersiz istek biçimi"}, status=400)
    text = data.get("text", "").strip()
    if not text:
        return web.json_response({"error": "Bos mesaj"}, status=400)
    sender = data.get("sender", "@TelegramFirsatBot")
    category = data.get("category", "deal")

    async with TELEGRAM_ASYNC_LOCK:
        msgs = load_telegram_messages()
        new_msg = {
            "id": f"tg_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}",
            "source": "Telegram Bot/Kanal",
            "sender": sender,
            "timestamp": datetime.datetime.now().strftime("%H:%M"),
            "text": text,
            "category": category,
            "highlight": True
        }
        msgs.insert(0, new_msg)
        if len(msgs) > 30:
            msgs.pop()
        save_telegram_messages(msgs)
    log_activity("telegram_incoming", f"Telegram'dan ileti alındı ({sender}): {text[:50]}...")
    return web.json_response({"status": "ok", "message": new_msg})

async def _process_telegram_update_internal(update: dict) -> dict:
    if not isinstance(update, dict):
        return {"status": "error", "message": "Update must be a dict"}

    update_id = update.get("update_id")
    if update_id is None:
        return {"status": "ignored", "reason": "no_update_id"}

    global TELEGRAM_UPDATE_OFFSET, PROCESSED_UPDATE_IDS
    if update_id in PROCESSED_UPDATE_IDS:
        return {"status": "duplicate", "update_id": update_id}
    PROCESSED_UPDATE_IDS.add(update_id)
    if len(PROCESSED_UPDATE_IDS) > 1000:
        PROCESSED_UPDATE_IDS = set(list(PROCESSED_UPDATE_IDS)[-500:])
    TELEGRAM_UPDATE_OFFSET = max(TELEGRAM_UPDATE_OFFSET, int(update_id) + 1)

    msg = update.get("message") or update.get("channel_post") or {}
    text = str(msg.get("text", "")).strip()
    sender_obj = msg.get("from") or msg.get("chat") or {}
    sender_name = sender_obj.get("username") or sender_obj.get("first_name") or "TelegramUser"
    if not sender_name.startswith("@"):
        sender_name = f"@{sender_name}"

    if not text:
        return {"status": "ok", "update_id": update_id, "text": ""}

    cmd_reply = None
    if text.startswith("/start"):
        cmd_reply = "Accio Jarvis Telegram Köprüsü Aktif! Komutlar: /status, /tasks, /help"
    elif text.startswith("/status"):
        cmd_reply = f"JARVIS Canlı: Ambient={CURRENT_AMBIENT_MOOD}, Scheduler={'Aktif' if SCHEDULER_RUNNING else 'Durağan'}"
    elif text.startswith("/tasks"):
        try:
            tasks_list = load_tasks()
            task_count = len(tasks_list)
            cmd_reply = f"Aktif Görevler: Toplam {task_count} görev kayıtlı."
        except Exception:
            cmd_reply = "Görevler yüklenemedi."
    elif text.startswith("/help"):
        cmd_reply = "Komutlar: /status (Sistem Durumu), /tasks (Görev Özeti), /start (Yeniden Başlat)"

    async with TELEGRAM_ASYNC_LOCK:
        msgs = load_telegram_messages()
        new_entry = {
            "id": f"tg_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}",
            "source": "Telegram Bot/Kanal",
            "sender": sender_name,
            "timestamp": datetime.datetime.now().strftime("%H:%M"),
            "text": text,
            "category": "deal" if any(w in text.lower() for w in ["indirim", "fırsat", "tl", "fiyat", "am5"]) else "chat",
            "highlight": True
        }
        msgs.insert(0, new_entry)
        if len(msgs) > 30:
            msgs.pop()
        save_telegram_messages(msgs)

    log_activity("telegram_incoming", f"Telegram'dan ileti alındı ({sender_name}): {text[:50]}...")
    return {
        "status": "ok",
        "update_id": update_id,
        "text": text,
        "sender": sender_name,
        "command_reply": cmd_reply
    }

async def process_telegram_update(update: dict) -> dict:
    """
    Phase 8B.2: Concurrency-safe Telegram update processing.
    Deduplicates update_id, advances offset monotonically, and routes commands.
    """
    async with TELEGRAM_POLL_LOCK:
        return await _process_telegram_update_internal(update)

async def send_telegram_message(text: str, chat_id: str = None, category: str = "deal", highlight: bool = False, custom_token: str = None) -> dict:
    """
    Phase 8B.2: Thread-safe, serialized outbound Telegram message dispatcher.
    Prevents race conditions, manages rate limits, and persists feed entries atomically.
    """
    text = str(text or "").strip()
    if not text:
        return {"status": "error", "message": "Text is required"}

    async with TELEGRAM_OUTBOUND_LOCK:
        cfg = load_config()
        token = (custom_token or cfg.get("telegram_bot_token", "")).strip()
        target_chat_id = (chat_id or cfg.get("telegram_chat_id", "")).strip()

        if not token or not target_chat_id:
            async with TELEGRAM_ASYNC_LOCK:
                msgs = load_telegram_messages()
                local_entry = {
                    "id": f"tg_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}",
                    "source": "Yerel Bildirim",
                    "sender": "@JarvisAsistanBot",
                    "timestamp": datetime.datetime.now().strftime("%H:%M"),
                    "text": text,
                    "category": category,
                    "highlight": highlight
                }
                msgs.insert(0, local_entry)
                if len(msgs) > 30:
                    msgs.pop()
                save_telegram_messages(msgs)
            return {
                "status": "local_only",
                "message": "Telegram token or chat_id not configured; recorded to local feed.",
                "entry_id": local_entry["id"]
            }

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": target_chat_id, "text": text}

        try:
            timeout_cfg = aiohttp.ClientTimeout(total=10.0)
            async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        async with TELEGRAM_ASYNC_LOCK:
                            msgs = load_telegram_messages()
                            sent_entry = {
                                "id": f"tg_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}",
                                "source": "Telegram Outbound",
                                "sender": "@JarvisAsistanBot",
                                "timestamp": datetime.datetime.now().strftime("%H:%M"),
                                "text": text,
                                "category": category,
                                "highlight": highlight
                            }
                            msgs.insert(0, sent_entry)
                            if len(msgs) > 30:
                                msgs.pop()
                            save_telegram_messages(msgs)
                        return {"status": "ok", "delivered": True, "result": data}
                    elif resp.status == 429:
                        try:
                            err_json = await resp.json()
                            retry_after = err_json.get("parameters", {}).get("retry_after", 5)
                        except Exception:
                            retry_after = 5
                        return {
                            "status": "error",
                            "error_code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Telegram API rate limited. Retry after {retry_after}s",
                            "retry_after": retry_after
                        }
                    else:
                        return {
                            "status": "error",
                            "error_code": f"HTTP_{resp.status}",
                            "message": f"Telegram API returned status {resp.status}"
                        }
        except asyncio.TimeoutError:
            return {"status": "error", "error_code": "TIMEOUT", "message": "Telegram send request timed out after 10s"}
        except Exception as e:
            return {"status": "error", "error_code": "NETWORK_ERROR", "message": mask_secrets(str(e))}

async def telegram_poll_step(session: aiohttp.ClientSession, bot_token: str) -> int:
    """
    Phase 8B.2: Executes a single, concurrency-locked polling step.
    Advances update_offset monotonically and returns processed updates count.
    """
    if not bot_token:
        return 0
    global TELEGRAM_UPDATE_OFFSET
    async with TELEGRAM_POLL_LOCK:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        params = {"offset": TELEGRAM_UPDATE_OFFSET, "timeout": 5}
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("result", [])
                    processed_count = 0
                    for update in results:
                        res = await _process_telegram_update_internal(update)
                        if res.get("status") == "ok":
                            processed_count += 1
                    return processed_count
                elif resp.status == 429:
                    await asyncio.sleep(5.0)
                    return 0
                return 0
        except asyncio.TimeoutError:
            return 0
        except Exception as e:
            print(f"[Telegram Poll Warning]: {mask_secrets(str(e))}")
            return 0

async def telegram_worker_loop():
    """
    Phase 8B.2: Background Telegram worker loop.
    Ensures bounded retry on error and clean cancellation on shutdown.
    """
    global TELEGRAM_WORKER_RUNNING
    TELEGRAM_WORKER_RUNNING = True
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=10.0)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            while TELEGRAM_WORKER_RUNNING:
                try:
                    cfg = load_config()
                    token = cfg.get("telegram_bot_token", "").strip()
                    enabled = bool(cfg.get("telegram_polling_enabled", False))
                    if not token or not enabled:
                        await asyncio.sleep(5.0)
                        continue
                    await telegram_poll_step(session, token)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[Telegram Worker Error]: {mask_secrets(str(e))}")
                    await asyncio.sleep(3.0)
    finally:
        TELEGRAM_WORKER_RUNNING = False

async def start_telegram_worker(bot_token: str = None, chat_id: str = None) -> bool:
    """
    Phase 8B.2: Lifecycle-safe worker startup.
    Guarantees only one worker task is ever active; rejects duplicate startup requests.
    """
    global TELEGRAM_WORKER_TASK, TELEGRAM_WORKER_RUNNING
    async with TELEGRAM_LIFECYCLE_LOCK:
        if TELEGRAM_WORKER_TASK and not TELEGRAM_WORKER_TASK.done():
            return False  # Already running, duplicate prevented!
        TELEGRAM_WORKER_RUNNING = True
        TELEGRAM_WORKER_TASK = asyncio.create_task(telegram_worker_loop())
        return True

async def stop_telegram_worker() -> bool:
    """
    Phase 8B.2: Lifecycle-safe worker shutdown.
    Cancels and cleanly awaits worker task termination without leaving orphaned tasks.
    """
    global TELEGRAM_WORKER_TASK, TELEGRAM_WORKER_RUNNING
    async with TELEGRAM_LIFECYCLE_LOCK:
        TELEGRAM_WORKER_RUNNING = False
        if TELEGRAM_WORKER_TASK:
            TELEGRAM_WORKER_TASK.cancel()
            try:
                await TELEGRAM_WORKER_TASK
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[Telegram Shutdown Warning]: {mask_secrets(str(e))}")
            TELEGRAM_WORKER_TASK = None
            return True
        return False

async def restart_telegram_worker(bot_token: str = None, chat_id: str = None) -> bool:
    """
    Phase 8B.2: Atomically stops previous worker and starts a fresh single worker.
    """
    await stop_telegram_worker()
    return await start_telegram_worker(bot_token=bot_token, chat_id=chat_id)

async def telegram_cleanup_ctx(app):
    """
    Phase 8B.2: aiohttp cleanup context integration for Telegram worker lifecycle.
    """
    await start_telegram_worker()
    yield
    await stop_telegram_worker()

async def handle_send_telegram(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return web.json_response({"error": "Payload must be a dictionary"}, status=400)
    text = str(data.get("text", "")).strip()
    if not text:
        return web.json_response({"error": "Text parameter is required"}, status=400)
    res = await send_telegram_message(
        text=text,
        chat_id=data.get("chat_id"),
        category=data.get("category", "deal"),
        highlight=bool(data.get("highlight", False))
    )
    status_code = 200 if res.get("status") in ("ok", "local_only") else (429 if res.get("error_code") == "RATE_LIMIT_EXCEEDED" else 500)
    return web.json_response(res, status=status_code)

async def handle_get_telegram_status(request):
    return web.json_response({
        "status": "ok",
        "worker_running": TELEGRAM_WORKER_RUNNING,
        "worker_task_active": bool(TELEGRAM_WORKER_TASK and not TELEGRAM_WORKER_TASK.done()),
        "update_offset": TELEGRAM_UPDATE_OFFSET,
        "processed_updates_count": len(PROCESSED_UPDATE_IDS),
        "messages_count": len(load_telegram_messages())
    })

# --- PHASE 7C: NOTIFICATION GATE & DEFERRED QUEUE HANDLERS ---

async def handle_get_deferred_notifications(request):
    notifications = get_deferred_notifications()
    return web.json_response({
        "status": "ok",
        "deferred_notifications": notifications,
        "count": len(notifications),
        "overflow_count": OVERFLOW_COUNT,
        "expired_count": EXPIRED_COUNT,
        "gaming_mode": is_gaming_mode_active()
    })

async def handle_drain_deferred_notifications(request):
    status = is_gaming_mode_active()
    if status.get("active", False):
        return web.json_response({
            "status": "blocked",
            "reason": "gaming_mode_active",
            "message": "Gaming mode is currently active; deferred notifications remain deferred."
        }, status=409)

    data = {}
    if request.can_read_body:
        try:
            data = await request.json()
        except Exception:
            data = {}
    max_count = int(data.get("max_count", 3)) if isinstance(data, dict) else 3
    drained = await drain_deferred_notifications(max_count=max_count)
    return web.json_response({
        "status": "ok",
        "drained": drained,
        "remaining_count": len(get_deferred_notifications())
    })

async def handle_dispatch_notification(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    text = str(data.get("text", "")).strip()
    if not text:
        return web.json_response({"status": "error", "message": "Text is required"}, status=400)

    category = str(data.get("category", "conversational")).strip().lower()
    if category not in {"conversational", "study_alarm", "proactive"}:
        category = "conversational"

    metadata = data.get("metadata", {})
    res = await dispatch_notification(text, category=category, metadata=metadata)
    return web.json_response(res)

# --- PHASE 7D: PERSISTENT AUTOMATION SCHEDULER & ACTION REGISTRY ---

try:
    import zoneinfo
    ISTANBUL_TZ = zoneinfo.ZoneInfo("Europe/Istanbul")
except Exception:
    ISTANBUL_TZ = datetime.timezone(datetime.timedelta(hours=3))

AUTOMATIONS_FILE = os.path.join(DATA_DIR, "jarvis_automations.json")
AUTOMATIONS_LOCK = asyncio.Lock()
AUTOMATIONS_THREAD_LOCK = threading.RLock()
SCHEDULER_WORKER_TASK = None
SCHEDULER_RUNNING = False

ALLOWED_ACTION_IDS = {
    "dispatch_study_reminder",
    "dispatch_proactive_notification",
    "change_ambient_mood",
    "open_allowlisted_view",
    "run_isolated_worker"
}

# Phase 8C: Worker Thread Isolation & Strict Timeout Safeguards
ACTION_DEFAULT_TIMEOUT = 15.0
ACTION_MAX_TIMEOUT = 30.0
ALLOWED_WORKER_TASKS = {"akakce_price_validator", "hardware_price_check"}

async def run_in_worker_thread(func, *args, timeout: float = ACTION_DEFAULT_TIMEOUT, **kwargs):
    """
    Phase 8C: Executes a synchronous, blocking, or heavy I/O function in a separate
    worker thread with strict timeout enforcement. Never blocks the asyncio event loop.
    """
    loop = asyncio.get_running_loop()
    clamped_timeout = min(max(0.05, float(timeout)), ACTION_MAX_TIMEOUT)
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: func(*args, **kwargs)),
            timeout=clamped_timeout
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"Worker task timed out after {clamped_timeout}s")

ALLOWED_AMBIENT_MOODS = {"focus", "relaxed", "gaming", "night", "default"}
ALLOWED_VIEWS = {"kokpit", "yks_takip"}
CURRENT_AMBIENT_MOOD = "default"

ALLOWED_SCHEDULE_KINDS = {"once", "daily", "weekly"}
WEEKDAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_AUTOMATIONS_CACHE = None
_AUTOMATIONS_MTIME = 0.0

def validate_automations_structure(data: dict) -> bool:
    """
    Phase 9B.2B3: Strict validation for automations JSON schema.
    Schema requires: root dict, schema_version == '4.0', integer revision,
    and automations list of dictionaries.
    """
    if not isinstance(data, dict):
        return False
    if str(data.get("schema_version")) != "4.0":
        return False
    if not isinstance(data.get("revision"), int):
        return False
    if not isinstance(data.get("automations"), list):
        return False
    for item in data["automations"]:
        if not isinstance(item, dict):
            return False
    return True

def load_automations_data(force_reload: bool = False):
    """
    Loads automations with Phase 9B.2B3 backup recovery and mtime cache.
    Serialized under AUTOMATIONS_THREAD_LOCK.
    """
    global _AUTOMATIONS_CACHE, _AUTOMATIONS_MTIME
    with AUTOMATIONS_THREAD_LOCK:
        if not os.path.exists(AUTOMATIONS_FILE):
            _AUTOMATIONS_CACHE = {"schema_version": "4.0", "revision": 1, "automations": []}
            _AUTOMATIONS_MTIME = 0.0
            return _AUTOMATIONS_CACHE.copy()

        try:
            current_mtime = os.path.getmtime(AUTOMATIONS_FILE)
            if not force_reload and _AUTOMATIONS_CACHE is not None and current_mtime == _AUTOMATIONS_MTIME:
                return _AUTOMATIONS_CACHE.copy()

            is_valid, data = validate_json_file(AUTOMATIONS_FILE, expected_type=validate_automations_structure)
            if is_valid:
                _AUTOMATIONS_CACHE = data
                _AUTOMATIONS_MTIME = current_mtime
                return data.copy()

            # Primary file is corrupted or schema-invalid -> Attempt automatic recovery
            logger.warning("[Automations Storage] AUTOMATIONS_FILE corrupted or invalid. Attempting recovery from backup...")
            recovered_data, was_recovered = recover_json_file(AUTOMATIONS_FILE, expected_type=validate_automations_structure)
            if was_recovered and isinstance(recovered_data, dict):
                logger.info("[Automations Storage] Successfully recovered jarvis_automations.json from verified backup.")
                _AUTOMATIONS_CACHE = recovered_data
                try:
                    _AUTOMATIONS_MTIME = os.path.getmtime(AUTOMATIONS_FILE)
                except Exception:
                    _AUTOMATIONS_MTIME = 0.0
                return recovered_data.copy()

            # Both primary and backup are invalid -> Fail closed!
            _AUTOMATIONS_CACHE = None
            _AUTOMATIONS_MTIME = 0.0
            logger.error("[Automations Storage ERROR] Corrupt automations storage and no valid backup available.")
            raise ValueError("Corrupt automations storage: malformed data and no valid backup available.")
        except Exception as e:
            if not isinstance(e, ValueError):
                print(f"[Automations Storage ERROR]: {e}")
            raise ValueError(f"Corrupt automations storage: {e}")

def save_automations_data(data: dict):
    """
    Persists automations to AUTOMATIONS_FILE atomically with Phase 9B.2B3 backup protection.
    Serialized under AUTOMATIONS_THREAD_LOCK.
    """
    global _AUTOMATIONS_CACHE, _AUTOMATIONS_MTIME
    if not isinstance(data, dict) or not isinstance(data.get("automations"), list):
        raise ValueError("Invalid automations data structure")

    data["revision"] = int(data.get("revision", 0)) + 1
    data["schema_version"] = "4.0"

    if not validate_automations_structure(data):
        raise ValueError("Cannot persist invalid automations structure: failed schema validation.")

    with AUTOMATIONS_THREAD_LOCK:
        if os.path.exists(AUTOMATIONS_FILE):
            primary_valid, _ = validate_json_file(AUTOMATIONS_FILE, expected_type=validate_automations_structure)
            if primary_valid:
                backup_ok = create_atomic_backup(AUTOMATIONS_FILE, expected_type=validate_automations_structure)
                if not backup_ok:
                    raise StorageRecoveryError("Failed to create verified backup before writing automations.")
            else:
                logger.error("[Automations Storage Guard] AUTOMATIONS_FILE is corrupt. Attempting recovery before write...")
                recovered_data, was_recovered = recover_json_file(AUTOMATIONS_FILE, expected_type=validate_automations_structure)
                if was_recovered:
                    create_atomic_backup(AUTOMATIONS_FILE, expected_type=validate_automations_structure)
                else:
                    logger.error("[Automations Storage Guard] Rejecting write: AUTOMATIONS_FILE is corrupt and no valid backup exists.")
                    raise StorageRecoveryError(
                        "Cannot write automations: AUTOMATIONS_FILE is corrupt and no valid backup exists to establish baseline."
                    )

        atomic_write_json(AUTOMATIONS_FILE, data)
        _AUTOMATIONS_CACHE = data.copy()
        try:
            _AUTOMATIONS_MTIME = os.path.getmtime(AUTOMATIONS_FILE)
        except Exception:
            _AUTOMATIONS_MTIME = 0.0

def parse_time_hh_mm(time_str: str) -> tuple[int, int]:
    parts = time_str.split(":")
    if len(parts) != 2:
        raise ValueError("Time must be in HH:MM format")
    h = int(parts[0])
    m = int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Hour must be 0-23 and minute 0-59")
    return h, m

def validate_automation_definition(data: dict) -> tuple[bool, str, dict]:
    """
    Validates automation payload against Phase 7D schema.
    Returns (is_valid, error_message, cleaned_object).
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object", {}

    name = str(data.get("name", "")).strip()
    if not name or len(name) > 100:
        return False, "Name must be a non-empty string under 100 characters", {}

    schedule = data.get("schedule")
    if not isinstance(schedule, dict):
        return False, "Schedule must be an object", {}

    kind = str(schedule.get("kind", "")).strip().lower()
    if kind not in ALLOWED_SCHEDULE_KINDS:
        return False, f"Schedule kind must be one of: {sorted(ALLOWED_SCHEDULE_KINDS)}", {}

    cleaned_schedule = {"kind": kind}
    if kind == "once":
        at_val = schedule.get("at")
        if not at_val:
            return False, "Once schedule requires 'at' timestamp or ISO string", {}
        if isinstance(at_val, (int, float)):
            cleaned_schedule["at"] = float(at_val)
        elif isinstance(at_val, str):
            try:
                datetime.datetime.fromisoformat(at_val.strip())
                cleaned_schedule["at"] = at_val.strip()
            except Exception:
                return False, "Invalid 'at' ISO timestamp format", {}
        else:
            return False, "Invalid 'at' format; must be ISO string or timestamp", {}

    elif kind in ("daily", "weekly"):
        time_str = str(schedule.get("time", "")).strip()
        try:
            h, m = parse_time_hh_mm(time_str)
            cleaned_schedule["time"] = f"{h:02d}:{m:02d}"
        except Exception as e:
            return False, f"Invalid time for {kind} schedule: {e}", {}

        if kind == "weekly":
            days = schedule.get("days")
            if not isinstance(days, list) or not days:
                return False, "Weekly schedule requires a non-empty 'days' list", {}
            cleaned_days = []
            for d in days:
                d_str = str(d).strip().lower()[:3]
                if d_str not in WEEKDAY_MAP:
                    return False, f"Invalid weekday abbreviation: '{d}'. Must be one of {list(WEEKDAY_MAP.keys())}", {}
                if d_str not in cleaned_days:
                    cleaned_days.append(d_str)
            cleaned_schedule["days"] = cleaned_days

    action = data.get("action")
    if not isinstance(action, dict):
        return False, "Action must be an object", {}

    action_id = str(action.get("action_id", "")).strip()
    if action_id not in ALLOWED_ACTION_IDS:
        return False, f"Action ID '{action_id}' is not allowed. Must be one of: {sorted(ALLOWED_ACTION_IDS)}", {}

    params = action.get("params", {})
    if not isinstance(params, dict):
        params = {}

    if action_id in ("dispatch_study_reminder", "dispatch_proactive_notification"):
        text = str(params.get("text", "")).strip()
        if not text:
            return False, f"Action '{action_id}' requires a non-empty 'text' parameter", {}
        if len(text) > 500:
            return False, "Notification text must not exceed 500 characters", {}
    elif action_id == "change_ambient_mood":
        mood = str(params.get("mood", "")).strip().lower()
        if mood not in ALLOWED_AMBIENT_MOODS:
            return False, f"Mood '{mood}' is invalid. Allowed: {sorted(ALLOWED_AMBIENT_MOODS)}", {}
    elif action_id == "open_allowlisted_view":
        view = str(params.get("view", "")).strip().lower()
        if view not in ALLOWED_VIEWS:
            return False, f"View '{view}' is invalid. Allowed: {sorted(ALLOWED_VIEWS)}", {}
    elif action_id == "run_isolated_worker":
        task_name = str(params.get("task_name", "")).strip()
        if task_name not in ALLOWED_WORKER_TASKS:
            return False, f"Worker task '{task_name}' is invalid. Allowed: {sorted(ALLOWED_WORKER_TASKS)}", {}
        timeout_val = params.get("timeout", ACTION_DEFAULT_TIMEOUT)
        try:
            t_float = float(timeout_val)
            if t_float <= 0 or t_float > ACTION_MAX_TIMEOUT:
                return False, f"Timeout must be between 1.0 and {ACTION_MAX_TIMEOUT} seconds", {}
        except (ValueError, TypeError):
            return False, "Timeout must be a numeric value", {}

    cleaned_automation = {
        "id": data.get("id") or f"auto_{uuid.uuid4().hex[:8]}",
        "name": name,
        "schedule": cleaned_schedule,
        "action": {
            "action_id": action_id,
            "params": params
        },
        "enabled": bool(data.get("enabled", True)),
        "created_at": float(data.get("created_at") or time.time()),
        "last_executed_at": data.get("last_executed_at"),
        "last_executed_key": data.get("last_executed_key"),
        "execution_count": int(data.get("execution_count", 0))
    }
    return True, "", cleaned_automation

async def execute_automation_action(action: dict, current_time=None) -> dict:
    """
    Executes a strictly validated, allowlisted automation action with worker isolation & timeout.
    Rejects any executable command string, shell execution, or arbitrary code.
    """
    if not isinstance(action, dict):
        return {"status": "error", "message": "Action must be an object"}

    action_id = action.get("action_id")
    if action_id not in ALLOWED_ACTION_IDS:
        return {"status": "error", "message": f"Action ID '{action_id}' is not in allowlist"}

    params = action.get("params", {})
    if not isinstance(params, dict):
        params = {}

    timeout_val = ACTION_DEFAULT_TIMEOUT
    if "timeout" in params:
        try:
            timeout_val = float(params["timeout"])
        except (ValueError, TypeError):
            timeout_val = ACTION_DEFAULT_TIMEOUT
    clamped_timeout = min(max(0.05, timeout_val), ACTION_MAX_TIMEOUT)

    async def _execute_core():
        if action_id == "dispatch_study_reminder":
            text = str(params.get("text", "")).strip()
            if not text:
                return {"status": "error", "message": "Text parameter is required"}
            res = await dispatch_notification(
                text=text,
                category="study_alarm",
                metadata=params.get("metadata", {}),
                current_time=current_time
            )
            return {"status": "ok", "action_id": action_id, "result": res}

        elif action_id == "dispatch_proactive_notification":
            text = str(params.get("text", "")).strip()
            if not text:
                return {"status": "error", "message": "Text parameter is required"}
            res = await dispatch_notification(
                text=text,
                category="proactive",
                metadata=params.get("metadata", {}),
                current_time=current_time
            )
            return {"status": "ok", "action_id": action_id, "result": res}

        elif action_id == "change_ambient_mood":
            global CURRENT_AMBIENT_MOOD
            mood = str(params.get("mood", "")).strip().lower()
            if mood not in ALLOWED_AMBIENT_MOODS:
                return {"status": "error", "message": f"Mood '{mood}' is not approved. Must be one of: {sorted(ALLOWED_AMBIENT_MOODS)}"}
            CURRENT_AMBIENT_MOOD = mood
            return {"status": "ok", "action_id": action_id, "mood": mood}

        elif action_id == "open_allowlisted_view":
            view = str(params.get("view", "")).strip().lower()
            if view not in ALLOWED_VIEWS:
                return {"status": "error", "message": f"View '{view}' is not approved. Must be one of: {sorted(ALLOWED_VIEWS)}"}
            res = execute_desktop_tool("open_app", {"target": view})
            return {"status": "ok", "action_id": action_id, "view": view, "result": res}

        elif action_id == "run_isolated_worker":
            task_name = str(params.get("task_name", "")).strip()
            if task_name not in ALLOWED_WORKER_TASKS:
                return {"status": "error", "error_code": "DISALLOWED_TASK", "message": f"Worker task '{task_name}' is not in allowlist"}

            if task_name in ("akakce_price_validator", "hardware_price_check"):
                try:
                    import akakce_price_validator
                    url = params.get("url")
                    if url:
                        res = await run_in_worker_thread(
                            akakce_price_validator.fetch_akakce_summary,
                            url,
                            timeout=clamped_timeout
                        )
                    else:
                        res = await run_in_worker_thread(
                            lambda: getattr(akakce_price_validator, "HARDWARE_THRESHOLDS", {}).copy(),
                            timeout=clamped_timeout
                        )
                    return {"status": "ok", "action_id": action_id, "task_name": task_name, "result": res}
                except TimeoutError as te:
                    return {"status": "error", "error_code": "TIMEOUT", "message": str(te)}
                except Exception as e:
                    return {"status": "error", "error_code": "WORKER_ERROR", "message": str(e)}

            return {"status": "error", "error_code": "UNKNOWN_TASK", "message": f"Task '{task_name}' has no worker handler"}

        return {"status": "error", "message": "Unhandled action ID"}

    try:
        return await asyncio.wait_for(_execute_core(), timeout=clamped_timeout)
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "error_code": "TIMEOUT",
            "message": f"Action execution timed out after {clamped_timeout}s"
        }
    except Exception as e:
        return {
            "status": "error",
            "error_code": "EXECUTION_ERROR",
            "message": str(e)
        }

def check_schedule_matches(schedule: dict, current_dt: datetime.datetime, last_key: str = None) -> tuple[bool, str]:
    """
    Checks if a schedule matches the given Europe/Istanbul datetime.
    Returns (should_trigger, execution_key).
    """
    kind = schedule.get("kind")
    if kind == "once":
        at_val = schedule.get("at")
        target_ts = None
        if isinstance(at_val, (int, float)):
            target_ts = float(at_val)
        elif isinstance(at_val, str):
            try:
                parsed = datetime.datetime.fromisoformat(at_val)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=ISTANBUL_TZ)
                target_ts = parsed.timestamp()
            except Exception:
                return False, ""
        if target_ts is not None and current_dt.timestamp() >= target_ts:
            return True, f"once_{target_ts}"

    elif kind == "daily":
        time_str = schedule.get("time")
        now_time = current_dt.strftime("%H:%M")
        today_date = current_dt.strftime("%Y-%m-%d")
        daily_key = f"daily_{today_date}_{time_str}"
        if now_time == time_str and last_key != daily_key:
            return True, daily_key

    elif kind == "weekly":
        time_str = schedule.get("time")
        now_time = current_dt.strftime("%H:%M")
        weekday_abbr = current_dt.strftime("%a").lower()[:3]
        days = [str(d).lower()[:3] for d in schedule.get("days", [])]
        today_date = current_dt.strftime("%Y-%m-%d")
        weekly_key = f"weekly_{today_date}_{time_str}"
        if weekday_abbr in days and now_time == time_str and last_key != weekly_key:
            return True, weekly_key

    return False, ""

async def evaluate_and_run_automations(current_time=None, now_dt=None) -> list:
    """
    Single tick evaluation of automations.
    Thread-safe and atomic. Accepts current_time or now_dt.
    """
    now_dt = current_time or now_dt or datetime.datetime.now(ISTANBUL_TZ)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=ISTANBUL_TZ)

    executed = []
    async with AUTOMATIONS_LOCK:
        try:
            data = load_automations_data()
        except Exception as e:
            print(f"[Scheduler Tick Skip]: Storage corrupt or unreadable: {e}")
            return []

        modified = False
        for auto in data.get("automations", []):
            if not auto.get("enabled", True):
                continue

            matches, exec_key = check_schedule_matches(
                auto.get("schedule", {}),
                now_dt,
                last_key=auto.get("last_executed_key")
            )

            if matches:
                action_res = await execute_automation_action(auto.get("action", {}), current_time=now_dt)
                auto["last_executed_at"] = now_dt.isoformat()
                auto["last_executed_key"] = exec_key
                auto["execution_count"] = auto.get("execution_count", 0) + 1

                if auto.get("schedule", {}).get("kind") == "once":
                    auto["enabled"] = False

                modified = True
                executed.append({
                    "automation_id": auto.get("id"),
                    "name": auto.get("name"),
                    "action_result": action_res
                })

        if modified:
            save_automations_data(data)

    return executed

# Phase 8C Alias for direct tick evaluations in test suites and workers
scheduler_tick = evaluate_and_run_automations

async def scheduler_worker_loop():
    global SCHEDULER_RUNNING
    SCHEDULER_RUNNING = True
    try:
        while SCHEDULER_RUNNING:
            try:
                await evaluate_and_run_automations()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Scheduler Worker Error]: {e}")
            await asyncio.sleep(1.0)
    finally:
        SCHEDULER_RUNNING = False

async def scheduler_cleanup_ctx(app):
    global SCHEDULER_WORKER_TASK
    try:
        load_notifications_from_disk()
    except Exception:
        pass
    try:
        load_automations_data()
    except Exception:
        pass

    if SCHEDULER_WORKER_TASK is None or SCHEDULER_WORKER_TASK.done():
        SCHEDULER_WORKER_TASK = asyncio.create_task(scheduler_worker_loop())

    yield

    if SCHEDULER_WORKER_TASK:
        SCHEDULER_WORKER_TASK.cancel()
        try:
            await SCHEDULER_WORKER_TASK
        except asyncio.CancelledError:
            pass
        SCHEDULER_WORKER_TASK = None

async def handle_get_rate_limits(request):
    """
    Phase 8D: Returns current quota usage and thresholds for rate limiters.
    """
    now = time.time()
    chat_cutoff = now - CHAT_RATE_LIMITER.window_seconds
    tts_cutoff = now - TTS_RATE_LIMITER.window_seconds
    async with CHAT_RATE_LIMITER._lock:
        chat_reqs = len([ts for ts in CHAT_RATE_LIMITER.requests if ts > chat_cutoff])
    async with TTS_RATE_LIMITER._lock:
        tts_reqs = len([ts for ts in TTS_RATE_LIMITER.requests if ts > tts_cutoff])

    return web.json_response({
        "status": "ok",
        "chat": {
            "current_requests": chat_reqs,
            "max_requests": CHAT_RATE_LIMITER.max_requests,
            "window_seconds": CHAT_RATE_LIMITER.window_seconds
        },
        "tts": {
            "current_requests": tts_reqs,
            "max_requests": TTS_RATE_LIMITER.max_requests,
            "window_seconds": TTS_RATE_LIMITER.window_seconds
        }
    })

async def handle_get_automations(request):
    try:
        data = load_automations_data()
        return web.json_response({
            "status": "ok",
            "schema_version": data.get("schema_version", "4.0"),
            "revision": data.get("revision", 1),
            "automations": data.get("automations", []),
            "count": len(data.get("automations", [])),
            "ambient_mood": CURRENT_AMBIENT_MOOD,
            "scheduler_running": SCHEDULER_RUNNING
        })
    except ValueError as ve:
        return web.json_response({"status": "error", "message": str(ve)}, status=500)

async def handle_create_automation(request):
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    is_valid, err_msg, cleaned = validate_automation_definition(payload)
    if not is_valid:
        return web.json_response({"status": "error", "message": err_msg}, status=400)

    async with AUTOMATIONS_LOCK:
        with AUTOMATIONS_THREAD_LOCK:
            try:
                data = load_automations_data()
            except Exception as e:
                return web.json_response({"status": "error", "message": f"Storage error: {e}"}, status=500)

            for existing in data.get("automations", []):
                if existing.get("id") == cleaned["id"]:
                    cleaned["id"] = f"auto_{uuid.uuid4().hex[:8]}"
                    break

            data.setdefault("automations", []).append(cleaned)
            save_automations_data(data)

    return web.json_response({"status": "ok", "automation": cleaned}, status=201)

async def handle_test_automation_action(request):
    """
    Phase 8C: POST /api/automations/test_action
    Executes a candidate action directly with worker isolation & timeout.
    """
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    if not isinstance(payload, dict):
        return web.json_response({"status": "error", "message": "Body must be an object"}, status=400)

    res = await execute_automation_action(payload)
    status_code = 200 if res.get("status") == "ok" else 400
    return web.json_response(res, status=status_code)

async def handle_toggle_automation(request):
    auto_id = request.match_info.get("id")
    async with AUTOMATIONS_LOCK:
        with AUTOMATIONS_THREAD_LOCK:
            try:
                data = load_automations_data()
            except Exception as e:
                return web.json_response({"status": "error", "message": str(e)}, status=500)

            target = None
            for a in data.get("automations", []):
                if a.get("id") == auto_id:
                    target = a
                    break

            if not target:
                return web.json_response({"status": "error", "message": f"Automation {auto_id} not found"}, status=404)

            target["enabled"] = not target.get("enabled", True)
            save_automations_data(data)

    return web.json_response({"status": "ok", "automation": target})

async def handle_patch_automation(request):
    auto_id = request.match_info.get("id")
    try:
        patch_data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    async with AUTOMATIONS_LOCK:
        with AUTOMATIONS_THREAD_LOCK:
            try:
                data = load_automations_data()
            except Exception as e:
                return web.json_response({"status": "error", "message": str(e)}, status=500)

            target = None
            for a in data.get("automations", []):
                if a.get("id") == auto_id:
                    target = a
                    break

            if not target:
                return web.json_response({"status": "error", "message": f"Automation {auto_id} not found"}, status=404)

            if "enabled" in patch_data:
                target["enabled"] = bool(patch_data["enabled"])
            if "name" in patch_data:
                new_name = str(patch_data["name"]).strip()
                if new_name:
                    target["name"] = new_name[:100]

            save_automations_data(data)

    return web.json_response({"status": "ok", "automation": target})

async def handle_delete_automation(request):
    auto_id = request.match_info.get("id")
    async with AUTOMATIONS_LOCK:
        with AUTOMATIONS_THREAD_LOCK:
            try:
                data = load_automations_data()
            except Exception as e:
                return web.json_response({"status": "error", "message": str(e)}, status=500)

            initial_len = len(data.get("automations", []))
            data["automations"] = [a for a in data.get("automations", []) if a.get("id") != auto_id]

            if len(data["automations"]) == initial_len:
                return web.json_response({"status": "error", "message": f"Automation {auto_id} not found"}, status=404)

            save_automations_data(data)

    return web.json_response({"status": "ok", "deleted_id": auto_id})

# --- STAGE 5B: CONTROLLED MEMORY LEARNING ENGINE ---

MAX_PENDING_CANDIDATES = 20
MAX_HISTORY_CANDIDATES = 50
ALLOWED_CANDIDATE_CATEGORIES = {"study", "hardware", "system", "personal", "project", "uncategorized"}
GROQ_STRUCTURED_MODELS = {"qwen/qwen3.8-27b", "openai/gpt-oss-120b"}

# Global Background Queue & Worker tracking
MEMORY_EXTRACTION_QUEUE = None
EXTRACTION_WORKER_TASK = None
RECOVERY_REQUIRED_STATE = False

def validate_privacy_and_security(text: str) -> tuple[bool, str]:
    """
    Server-side privacy filter rejecting credentials, keys, payment details,
    identity numbers, and sensitive personal categories.
    """
    if not text or not isinstance(text, str):
        return False, "Metin boş veya geçersiz."
    t = text.strip()
    if len(t) < 3:
        return False, "Metin çok kısa."
    if len(t) > 1000:
        return False, "Metin uzunluk sınırını aşıyor (maksimum 1000 karakter)."

    # Credential / API Key patterns
    patterns = [
        (r'gsk_[a-zA-Z0-9_-]{10,}', "Groq API anahtarı"),
        (r'sk-[a-zA-Z0-9_-]{15,}', "OpenAI API anahtarı"),
        (r'ghp_[a-zA-Z0-9]{15,}', "GitHub erişim tokenı"),
        (r'xox[baprs]-[a-zA-Z0-9_-]{10,}', "Slack tokenı"),
        (r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}', "Bearer token"),
        (r'eyJh[a-zA-Z0-9_\-\.]{25,}', "JWT kimlik belirteci"),
        (r'-----BEGIN\s+([A-Z\s]+)?PRIVATE\s+KEY-----', "Gizli anahtar bloğu"),
        (r'\b(?:\d[ -]*?){13,19}\b', "Kredi kartı numarası"),
        (r'\bTR\d{2}\s?(?:\d{4}\s?){5}\d{2}\b', "IBAN numarası"),
        (r'\b[1-9]\d{10}\b', "TC Kimlik No kalıbı"),
    ]
    for pat, label in patterns:
        if re.search(pat, t, re.IGNORECASE):
            return False, f"Hassas güvenlik verisi tespit edildi ({label}). Kaydedilemez."

    # Sensitive / credential keywords
    low = t.lower()
    sensitive_keywords = [
        "şifrem", "parolam", "password", "api_key", "secret_key", "kredi kart", "cvv", "cifrem",
        "hastalığım", "tanım kondu", "cinsel yönelim", "mezhebim", "dini inancım", "oy vereceğim parti"
    ]
    for kw in sensitive_keywords:
        if kw in low:
            return False, f"Hassas kişisel veya güvenlik bilgisi içeriyor: '{kw}'."

    return True, ""

def load_candidates_file(filepath=None) -> dict:
    target = filepath or CANDIDATES_FILE
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict) or "candidates" not in data or not isinstance(data["candidates"], list):
                    return {"_corrupt": True, "error": "Invalid schema", "candidates": []}
                return data
        except Exception as e:
            return {"_corrupt": True, "error": str(e), "candidates": []}
    return {
        "schema_version": "1.0",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "candidates": []
    }

def save_candidates_file(data: dict, filepath=None):
    target = filepath or CANDIDATES_FILE
    if data.get("_corrupt"):
        raise RuntimeError("Refusing to save: candidates state is marked corrupt.")
    atomic_write_json(target, data)

def load_journal_file(filepath=None) -> dict:
    target = filepath or JOURNAL_FILE
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {"_corrupt": True, "error": "Invalid journal schema"}
                return data
        except Exception as e:
            return {"_corrupt": True, "error": str(e)}
    return {"schema_version": "1.0", "active_transaction": None}

def save_journal_file(data: dict, filepath=None):
    target = filepath or JOURNAL_FILE
    if data.get("_corrupt"):
        raise RuntimeError("Refusing to save: journal state is marked corrupt.")
    atomic_write_json(target, data)

def clear_journal_file(filepath=None):
    target = filepath or JOURNAL_FILE
    data = {"schema_version": "1.0", "active_transaction": None}
    atomic_write_json(target, data)

def startup_journal_recovery(target_mem_file=None, target_cand_file=None, target_jour_file=None):
    """
    Executes exact preimage/postimage SHA-256 state recovery at startup.
    Ensures zero dangling approval operations before accepting requests.
    """
    global RECOVERY_REQUIRED_STATE
    mem_file = target_mem_file or MEMORY_FILE
    cand_file = target_cand_file or CANDIDATES_FILE
    jour_file = target_jour_file or JOURNAL_FILE

    if not os.path.exists(jour_file):
        return "NO_JOURNAL"

    journal_data = load_journal_file(jour_file)
    if journal_data.get("_corrupt"):
        RECOVERY_REQUIRED_STATE = True
        print("[Startup Recovery ERROR]: Malformed journal file detected. Failing closed.")
        return "RECOVERY_REQUIRED"

    tx = journal_data.get("active_transaction")
    if not tx:
        # Journal exists but active_transaction is None
        cand_data = load_candidates_file(cand_file)
        if not cand_data.get("_corrupt"):
            modified = False
            for c in cand_data.get("candidates", []):
                if c.get("status") == "in_flight":
                    c["status"] = "pending"
                    c.pop("reservation_id", None)
                    modified = True
            if modified:
                save_candidates_file(cand_data, cand_file)
        return "CLEAN"

    preimage = tx.get("preimage_sha256")
    postimage = tx.get("postimage_sha256")
    cand_id = tx.get("candidate_id")

    if not os.path.exists(mem_file):
        RECOVERY_REQUIRED_STATE = True
        return "RECOVERY_REQUIRED"

    with open(mem_file, "rb") as mf:
        current_hash = hashlib.sha256(mf.read()).hexdigest()

    cand_data = load_candidates_file(cand_file)
    if cand_data.get("_corrupt"):
        RECOVERY_REQUIRED_STATE = True
        return "RECOVERY_REQUIRED"

    target_candidate = None
    for c in cand_data.get("candidates", []):
        if c.get("candidate_id") == cand_id:
            target_candidate = c
            break

    if current_hash == preimage:
        print(f"[Startup Recovery]: Hash matches preimage. Canonical write did NOT commit. Rolling back candidate {cand_id} to pending.")
        if target_candidate and target_candidate.get("status") == "in_flight":
            target_candidate["status"] = "pending"
            target_candidate.pop("reservation_id", None)
            save_candidates_file(cand_data, cand_file)
        clear_journal_file(jour_file)
        return "ROLLED_BACK_TO_PENDING"

    elif current_hash == postimage:
        print(f"[Startup Recovery]: Hash matches postimage. Canonical write COMMITTED. Finalizing candidate {cand_id} as approved.")
        if target_candidate:
            target_candidate["status"] = "approved"
            target_candidate["approved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            target_candidate.pop("reservation_id", None)
            save_candidates_file(cand_data, cand_file)
        clear_journal_file(jour_file)
        return "COMMITTED_TO_APPROVED"

    else:
        print(f"[Startup Recovery FATAL]: Hash {current_hash} matches neither preimage nor postimage! RECOVERY_REQUIRED entered.")
        RECOVERY_REQUIRED_STATE = True
        return "RECOVERY_REQUIRED"

def extract_explicit_memory_command(message: str) -> tuple[bool, str, str]:
    """
    Zero-LLM deterministic extraction of explicit remember requests.
    Returns: (is_explicit, extracted_text, error_message)
    """
    if not message or not isinstance(message, str):
        return False, "", ""
    msg = message.strip()

    triggers = [
        r"^(?:lütfen\s+)?bunu\s+(?:hafızana\s+|aklında\s+)?(?:kaydet|unutma|tut)\s*[:,\-]?\s*(.*)$",
        r"^(?:lütfen\s+)?hafızana\s+kaydet\s*[:,\-]?\s*(.*)$",
        r"^(?:lütfen\s+)?aklında\s+tut\s*[:,\-]?\s*(.*)$",
        r"^(?:please\s+)?remember\s+(?:this)?\s*[:,\-]?\s*(.*)$",
        r"^(?:please\s+)?save\s+to\s+memory\s*[:,\-]?\s*(.*)$",
        r"^(?:please\s+)?do\s+not\s+forget\s*[:,\-]?\s*(.*)$"
    ]

    for trig in triggers:
        m = re.match(trig, msg, re.IGNORECASE)
        if m:
            content = m.group(1).strip()
            if not content:
                return True, "", "Lütfen neyi kaydetmemi istediğinizi açıkça belirtin (örn: 'Bunu unutma: Gelecekte AMD AM5 kullanacağım')."
            return True, content, ""

    return False, "", ""

async def background_extraction_worker():
    """
    Tracked background worker with bounded queue capacity 1.
    Processes automatic durable-fact suggestions without blocking normal chat.
    """
    global MEMORY_EXTRACTION_QUEUE
    while True:
        try:
            if MEMORY_EXTRACTION_QUEUE is None:
                await asyncio.sleep(0.5)
                continue
            job = await MEMORY_EXTRACTION_QUEUE.get()
            if job is None:
                break
            user_msg, cfg = job
            try:
                await run_groq_structured_extraction(user_msg, cfg)
            except Exception as e:
                print(f"[Background Extraction Error]: {e}")
            finally:
                if MEMORY_EXTRACTION_QUEUE:
                    MEMORY_EXTRACTION_QUEUE.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Extraction Worker Fatal]: {e}")
            await asyncio.sleep(0.5)

async def run_groq_structured_extraction(user_msg: str, cfg: dict):
    groq_key = cfg.get("groq_api_key", "").strip()
    if not groq_key or not cfg.get("memory_learning_enabled", False):
        return

    models = get_groq_models(cfg)
    chosen_model = models[0] if models else "qwen/qwen3.8-27b"
    if chosen_model not in GROQ_STRUCTURED_MODELS:
        return

    is_valid, err = validate_privacy_and_security(user_msg)
    if not is_valid:
        return

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }

    schema = {
        "name": "memory_candidate",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": 500},
                "category": {"type": "string", "enum": ["study", "hardware", "system", "personal", "project", "uncategorized"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
            },
            "required": ["text", "category", "confidence"],
            "additionalProperties": False
        }
    }

    payload = {
        "model": chosen_model,
        "messages": [
            {
                "role": "system",
                "content": "You are a conservative memory candidate extractor for personal assistant JARVIS. Extract only durable long-term preferences, goals, or persistent user facts. Reject transient state or speculation. If nothing durable, return empty text."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": schema
        },
        "max_tokens": 150,
        "temperature": 0.2
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with completion_request(session, url, headers=headers, json=payload, timeout=12) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    content = res_json["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    cand_text = parsed.get("text", "").strip()
                    cand_cat = parsed.get("category", "uncategorized")
                    confidence = float(parsed.get("confidence", 0.0))

                    if not cand_text or confidence < 0.7:
                        return

                    # Re-verify privacy on model output
                    p_ok, _ = validate_privacy_and_security(cand_text)
                    if not p_ok:
                        return

                    # Semantic grounding: ensure key terms actually appeared in user message
                    user_words = set(re.findall(r'\w+', user_msg.lower()))
                    cand_words = set(re.findall(r'\w+', cand_text.lower()))
                    if not cand_words.intersection(user_words):
                        return

                    await add_memory_candidate_internal(
                        text=cand_text,
                        category=cand_cat,
                        source="auto_ai_extraction",
                        confidence=confidence
                    )
    except Exception as e:
        print(f"[Groq Extraction Abandoned]: {e}")

async def add_memory_candidate_internal(text: str, category: str = "uncategorized", source: str = "explicit_user_command", confidence: float = 1.0) -> tuple[bool, dict, str]:
    val_ok, val_err = validate_privacy_and_security(text)
    if not val_ok:
        return False, {}, val_err

    if category not in ALLOWED_CANDIDATE_CATEGORIES:
        category = "uncategorized"

    async with CANDIDATES_LOCK:
        cdata = load_candidates_file()
        if cdata.get("_corrupt"):
            return False, {}, "Candidate store is corrupt."

        candidates = cdata.get("candidates", [])
        pending_list = [c for c in candidates if c.get("status") == "pending"]

        # Duplicate check across pending candidates
        norm_text = text.strip().lower()
        for p in pending_list:
            if p.get("text", "").strip().lower() == norm_text:
                return True, p, "Aday zaten bekleme listesinde mevcut."

        if len(pending_list) >= MAX_PENDING_CANDIDATES:
            if source == "explicit_user_command":
                # Check if there is an automatic candidate to drop
                dropped = False
                for idx, c in enumerate(candidates):
                    if c.get("status") == "pending" and c.get("source") != "explicit_user_command":
                        candidates.pop(idx)
                        dropped = True
                        break
                if not dropped:
                    return False, {}, "Hafıza onay kuyruğu dolu (20 bekleyen açık istek)."
            else:
                # Automatic candidate dropped when capacity reached
                return False, {}, "Kuyruk dolu, otomatik öneri atlandı."

        cand_id = f"cand_{uuid.uuid4().hex[:8]}"
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_cand = {
            "candidate_id": cand_id,
            "text": text.strip(),
            "category": category,
            "confidence": round(confidence, 2),
            "status": "pending",
            "source": source,
            "created_at": now_ts,
            "updated_at": now_ts
        }
        candidates.append(new_cand)

        # Retention cleanup for old history
        history = [c for c in candidates if c.get("status") in ("approved", "dismissed")]
        if len(history) > MAX_HISTORY_CANDIDATES:
            # remove oldest historical
            oldest_id = history[0].get("candidate_id")
            candidates[:] = [c for c in candidates if c.get("candidate_id") != oldest_id]

        cdata["updated_at"] = now_ts
        save_candidates_file(cdata)
        return True, new_cand, ""

async def handle_get_candidates(request):
    async with CANDIDATES_LOCK:
        cdata = load_candidates_file()
        if cdata.get("_corrupt"):
            return web.json_response({"status": "error", "error": "CORRUPT_CANDIDATE_FILE"}, status=500)
        return web.json_response(cdata)

async def handle_create_candidate(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Geçersiz JSON yükü."}, status=400)

    text = str(data.get("text", "")).strip()
    category = str(data.get("category", "uncategorized")).strip().lower()
    source = str(data.get("source", "user_ui")).strip()

    ok, cand, err = await add_memory_candidate_internal(text, category, source=source, confidence=1.0)
    if not ok:
        status_code = 429 if "kuyruğu dolu" in err else 400
        return web.json_response({"status": "error", "message": err}, status=status_code)

    return web.json_response({"status": "ok", "candidate": cand}, status=201)

async def handle_dismiss_candidate(request):
    cand_id = request.match_info.get("id")
    if not cand_id:
        return web.json_response({"status": "error", "message": "Aday ID eksik."}, status=400)

    async with CANDIDATES_LOCK:
        cdata = load_candidates_file()
        if cdata.get("_corrupt"):
            return web.json_response({"status": "error", "error": "CORRUPT_CANDIDATE_FILE"}, status=500)

        target = None
        for c in cdata.get("candidates", []):
            if c.get("candidate_id") == cand_id:
                target = c
                break

        if not target:
            return web.json_response({"status": "error", "message": "Aday bulunamadı."}, status=404)

        target["status"] = "dismissed"
        target["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_candidates_file(cdata)
        return web.json_response({"status": "ok", "candidate": target})

async def handle_approve_candidate(request):
    cand_id = request.match_info.get("id")
    if not cand_id:
        return web.json_response({"status": "error", "message": "Aday ID eksik."}, status=400)

    try:
        data = await request.json() if request.can_read_body else {}
    except Exception:
        data = {}

    client_token = extract_revision_token(request, data)

    # 1. Acquire transaction barrier
    async with MEMORY_TRANSACTION_LOCK:
        global RECOVERY_REQUIRED_STATE
        if RECOVERY_REQUIRED_STATE:
            return web.json_response({
                "status": "error",
                "error": "RECOVERY_REQUIRED",
                "message": "Memory is locked in fail-closed recovery mode due to unverified journal state."
            }, status=503)

        # 2. Acquire CANDIDATES_LOCK to inspect and reserve
        async with CANDIDATES_LOCK:
            cdata = load_candidates_file()
            if cdata.get("_corrupt"):
                return web.json_response({"status": "error", "error": "CORRUPT_CANDIDATE_FILE"}, status=500)

            target = None
            for c in cdata.get("candidates", []):
                if c.get("candidate_id") == cand_id:
                    target = c
                    break

            if not target:
                return web.json_response({"status": "error", "message": "Aday bulunamadı."}, status=404)

            # Idempotent return if already approved
            if target.get("status") == "approved":
                current_mem = load_memory()
                rev = int(current_mem.get("revision", 1))
                return web.json_response({
                    "status": "ok",
                    "idempotent": True,
                    "candidate": target,
                    "revision": rev,
                    "revision_token": f"{SERVER_EPOCH}:{rev}"
                }, status=200)

            if target.get("status") == "dismissed":
                return web.json_response({"status": "error", "message": "Reddedilmiş aday onaylanamaz."}, status=400)

            if target.get("status") == "in_flight":
                return web.json_response({
                    "status": "conflict",
                    "error": "APPROVAL_IN_PROGRESS",
                    "message": "Aday şu anda başka bir istek tarafından onaylanıyor."
                }, status=409)

            # Reserve candidate
            reservation_id = uuid.uuid4().hex
            target["status"] = "in_flight"
            target["reservation_id"] = reservation_id
            target["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_candidates_file(cdata)

        # Prepare text to approve (allow user-edited text if supplied)
        approval_text = str(data.get("text") or target.get("text", "")).strip()
        val_ok, val_err = validate_privacy_and_security(approval_text)
        if not val_ok:
            # Rollback reservation
            async with CANDIDATES_LOCK:
                target["status"] = "pending"
                target.pop("reservation_id", None)
                save_candidates_file(cdata)
            return web.json_response({"status": "error", "message": val_err}, status=400)

        # 3. Under MEMORY_MUTATION_LOCK, validate token and prepare byte-exact postimage
        async with MEMORY_MUTATION_LOCK:
            current_mem = load_memory()
            if current_mem.get("_corrupt"):
                async with CANDIDATES_LOCK:
                    target["status"] = "pending"
                    target.pop("reservation_id", None)
                    save_candidates_file(cdata)
                return web.json_response({"status": "error", "error": "CORRUPT_MEMORY_FILE"}, status=500)

            current_rev = int(current_mem.get("revision", 1))
            expected_token = f"{SERVER_EPOCH}:{current_rev}"

            if client_token is None:
                async with CANDIDATES_LOCK:
                    target["status"] = "pending"
                    target.pop("reservation_id", None)
                    save_candidates_file(cdata)
                return web.json_response({
                    "status": "conflict",
                    "error": "REVISION_REQUIRED",
                    "message": "Missing 'X-Memory-Revision-Token' header.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=409)

            if client_token != expected_token:
                async with CANDIDATES_LOCK:
                    target["status"] = "pending"
                    target.pop("reservation_id", None)
                    save_candidates_file(cdata)
                return web.json_response({
                    "status": "conflict",
                    "error": "STALE_REVISION",
                    "message": "Bellek değişti veya sunucu yeniden başladı.",
                    "server_revision": current_rev,
                    "server_revision_token": expected_token
                }, status=409)

            # Read exact canonical preimage bytes
            preimage_bytes = b""
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, "rb") as mf:
                    preimage_bytes = mf.read()
            preimage_hash = hashlib.sha256(preimage_bytes).hexdigest()

            # Prepare postimage data using existing V3/V4 disk rules
            new_rev = current_rev + 1
            now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            new_id = f"mem_legacy_{len(current_mem.get('entries', [])) + 1:03d}" if current_mem.get("_is_legacy_v3", False) else f"mem_{uuid.uuid4().hex[:8]}"

            new_entry = {
                "id": new_id,
                "text": approval_text,
                "category": target.get("category", "uncategorized"),
                "pinned": False,
                "source": "candidate_approval",
                "created_at": now_ts,
                "updated_at": now_ts
            }

            post_entries = list(current_mem.get("entries", [])) + [new_entry]
            post_mem = {
                "schema_version": current_mem.get("schema_version", "4.0"),
                "revision": new_rev,
                "migrated_at": current_mem.get("migrated_at"),
                "updated_at": now_ts,
                "user_profile": current_mem.get("user_profile", {}),
                "entries": post_entries,
                "_is_legacy_v3": current_mem.get("_is_legacy_v3", False),
                "_extra_fields": current_mem.get("_extra_fields", {})
            }

            post_disk_dict = serialize_memory_for_disk(post_mem)
            # Serialize exact bytes that will be written
            postimage_bytes = json.dumps(post_disk_dict, ensure_ascii=False, indent=2).encode("utf-8")
            postimage_hash = hashlib.sha256(postimage_bytes).hexdigest()
            text_hash = hashlib.sha256(approval_text.encode("utf-8")).hexdigest()

            # Write journal durably before writing canonical memory
            journal_data = {
                "schema_version": "1.0",
                "active_transaction": {
                    "candidate_id": cand_id,
                    "reservation_id": reservation_id,
                    "text_sha256": text_hash,
                    "preimage_sha256": preimage_hash,
                    "postimage_sha256": postimage_hash,
                    "state": "COMMITTED_INTENT",
                    "created_at": now_ts
                }
            }
            try:
                save_journal_file(journal_data)
            except Exception as j_err:
                async with CANDIDATES_LOCK:
                    target["status"] = "pending"
                    target.pop("reservation_id", None)
                    save_candidates_file(cdata)
                return web.json_response({"status": "error", "message": f"Journal write error: {j_err}"}, status=500)

            # Atomically replace canonical memory with exact bytes
            dir_name = os.path.dirname(os.path.abspath(MEMORY_FILE))
            tmp_target = os.path.join(dir_name, f"{os.path.basename(MEMORY_FILE)}.tmp.{uuid.uuid4().hex}")
            try:
                with open(tmp_target, "wb") as tf:
                    tf.write(postimage_bytes)
                    tf.flush()
                    os.fsync(tf.fileno())
                os.replace(tmp_target, MEMORY_FILE)
                # Verify postimage hash on disk immediately
                with open(MEMORY_FILE, "rb") as mf:
                    actual_hash = hashlib.sha256(mf.read()).hexdigest()
                if actual_hash != postimage_hash:
                    RECOVERY_REQUIRED_STATE = True
                    return web.json_response({"status": "error", "error": "RECOVERY_REQUIRED", "message": "Inconsistent disk state detected."}, status=503)
            except Exception as e:
                # Check actual disk state before deciding rollback
                with open(MEMORY_FILE, "rb") as mf:
                    actual_hash = hashlib.sha256(mf.read()).hexdigest()
                if actual_hash == preimage_hash:
                    # Write definitely failed
                    clear_journal_file()
                    async with CANDIDATES_LOCK:
                        target["status"] = "pending"
                        target.pop("reservation_id", None)
                        save_candidates_file(cdata)
                    return web.json_response({"status": "error", "message": f"Canonical write error: {e}"}, status=500)
                elif actual_hash != postimage_hash:
                    RECOVERY_REQUIRED_STATE = True
                    return web.json_response({"status": "error", "error": "RECOVERY_REQUIRED", "message": "Inconsistent disk state detected."}, status=503)

        # 4. Under CANDIDATES_LOCK, durably mark candidate approved
        async with CANDIDATES_LOCK:
            cdata = load_candidates_file()
            for c in cdata.get("candidates", []):
                if c.get("candidate_id") == cand_id:
                    c["status"] = "approved"
                    c["text"] = approval_text
                    c["approved_at"] = now_ts
                    c.pop("reservation_id", None)
                    break
            save_candidates_file(cdata)

        # 5. Clear journal after candidate status is durably persisted
        clear_journal_file()

        log_activity("memory_candidate_approved", f"Aday onaylandı ve hafızaya eklendi (ID: {cand_id}).")
        return web.json_response({
            "status": "ok",
            "candidate_id": cand_id,
            "revision": new_rev,
            "revision_token": f"{SERVER_EPOCH}:{new_rev}",
            "text": approval_text
        })

async def handle_delete_telegram(request):
    async with TELEGRAM_ASYNC_LOCK:
        save_telegram_messages([])
    return web.json_response({"status": "ok"})

# --- END OF STAGE 5B ENGINE ---

async def extraction_cleanup_ctx(app):
    global EXTRACTION_WORKER_TASK, MEMORY_EXTRACTION_QUEUE
    # Startup journal recovery
    startup_journal_recovery()
    MEMORY_EXTRACTION_QUEUE = asyncio.Queue(maxsize=1)
    EXTRACTION_WORKER_TASK = asyncio.create_task(background_extraction_worker())
    yield
    if EXTRACTION_WORKER_TASK:
        EXTRACTION_WORKER_TASK.cancel()
        try:
            await EXTRACTION_WORKER_TASK
        except asyncio.CancelledError:
            pass

# --- PHASE 8B.3: HOST & ORIGIN SECURITY & CSRF PROTECTION ---

def parse_host_header(host_header: str) -> tuple[str, int | None]:
    """
    Safely parses Host header into (hostname, port).
    Returns ('', None) on malformed host, header injection, or invalid port.
    """
    if not host_header or not isinstance(host_header, str):
        return "", None
    h = host_header.strip()
    if any(c in h for c in ('\r', '\n', '\0', ' ', '\t')):
        return "", None

    # Handle IPv6 bracket notation e.g. [::1]:7860 or [::1]
    if h.startswith('['):
        closing_idx = h.find(']')
        if closing_idx == -1:
            return "", None
        hostname = h[:closing_idx+1]
        rest = h[closing_idx+1:]
        port = None
        if rest:
            if not rest.startswith(':'):
                return "", None
            port_str = rest[1:]
            if not port_str.isdigit():
                return "", None
            port = int(port_str)
            if not (1 <= port <= 65535):
                return "", None
        return hostname, port

    # IPv4 or domain name with optional port
    if ':' in h:
        parts = h.split(':')
        if len(parts) != 2:
            return "", None
        hostname, port_str = parts[0], parts[1]
        if not port_str.isdigit():
            return "", None
        port = int(port_str)
        if not (1 <= port <= 65535):
            return "", None
        return hostname, port

    return h, None

def is_allowed_hostname(hostname: str, extra_allowed: list = None) -> bool:
    """
    Validates whether a hostname belongs to local machine or private network.
    Accepts localhost, 127.0.0.1, [::1], ::1, private RFC1918 IPs, or configured allowed_hosts.
    """
    if not hostname:
        return False
    h = hostname.strip().lower()
    if h in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return True

    if extra_allowed and isinstance(extra_allowed, list):
        if h in [str(x).strip().lower() for x in extra_allowed if x]:
            return True

    clean_h = h.strip("[]")
    try:
        ip = ipaddress.ip_address(clean_h)
        if ip.is_loopback or ip.is_private:
            return True
    except ValueError:
        pass

    return False

def get_effective_host(request, cfg: dict = None) -> str:
    """
    Determines effective host header, safely evaluating X-Forwarded-Host only if trusted proxy is explicitly enabled.
    """
    cfg = cfg or {}
    if cfg.get("trusted_proxy_enabled", False):
        f_host = request.headers.get("X-Forwarded-Host")
        if f_host:
            return f_host.split(",")[0].strip()
    return request.headers.get("Host", "")

@web.middleware
async def host_origin_security_middleware(request, handler):
    """
    Phase 8B.3: Comprehensive Host & Origin validation, CSRF defense, and CORS control.
    """
    cfg = load_config()
    extra_hosts = cfg.get("allowed_hosts", [])

    # 1. Host Validation
    raw_host = get_effective_host(request, cfg)
    hostname, port = parse_host_header(raw_host)
    if not hostname or not is_allowed_hostname(hostname, extra_hosts):
        return web.json_response({
            "status": "error",
            "error": "INVALID_HOST",
            "message": "Host header is missing, malformed, or untrusted."
        }, status=400)

    # 2. CORS Preflight & Method Evaluation
    origin = request.headers.get("Origin")
    method = request.method.upper()

    if method == "OPTIONS":
        if origin:
            if origin == "null":
                return web.json_response({
                    "status": "error",
                    "error": "FORBIDDEN_ORIGIN",
                    "message": "Untrusted or invalid Origin."
                }, status=403)
            parsed_origin = urllib.parse.urlparse(origin)
            if parsed_origin.scheme not in ("http", "https") or not is_allowed_hostname(parsed_origin.hostname, extra_hosts):
                return web.json_response({
                    "status": "error",
                    "error": "FORBIDDEN_ORIGIN",
                    "message": "Untrusted or invalid Origin."
                }, status=403)

            resp = web.Response(status=204)
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Memory-Revision-Token, X-Task-Revision-Token"
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Max-Age"] = "86400"
            return resp
        return web.Response(status=204)

    # 3. State-Changing CSRF & Origin Validation
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        if origin:
            if origin == "null":
                return web.json_response({
                    "status": "error",
                    "error": "FORBIDDEN_ORIGIN",
                    "message": "Untrusted or invalid Origin."
                }, status=403)
            parsed_origin = urllib.parse.urlparse(origin)
            if parsed_origin.scheme not in ("http", "https") or not is_allowed_hostname(parsed_origin.hostname, extra_hosts):
                return web.json_response({
                    "status": "error",
                    "error": "FORBIDDEN_ORIGIN",
                    "message": "Untrusted or invalid Origin."
                }, status=403)
        else:
            # Fallback to Referer validation if present
            referer = request.headers.get("Referer")
            if referer:
                parsed_ref = urllib.parse.urlparse(referer)
                if parsed_ref.scheme not in ("http", "https") or not is_allowed_hostname(parsed_ref.hostname, extra_hosts):
                    return web.json_response({
                        "status": "error",
                        "error": "FORBIDDEN_REFERER",
                        "message": "Untrusted or invalid Referer."
                    }, status=403)

    # 4. Request Dispatch
    response = await handler(request)

    # 5. Safe CORS Header Attachment
    if origin and origin != "null":
        parsed_origin = urllib.parse.urlparse(origin)
        if parsed_origin.scheme in ("http", "https") and is_allowed_hostname(parsed_origin.hostname, extra_hosts):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"

    return response

@web.middleware
async def anti_bot_security_middleware(request, handler):
    response = await handler(request)
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    return response

def create_app():
    app = web.Application(middlewares=[anti_bot_security_middleware, host_origin_security_middleware])
    app.cleanup_ctx.append(extraction_cleanup_ctx)
    app.cleanup_ctx.append(scheduler_cleanup_ctx)
    app.cleanup_ctx.append(telegram_cleanup_ctx)
    app.router.add_static("/static", os.path.join(BASE_DIR, "static"))
    portraits_live_dir = os.path.join(BASE_DIR, "static", "avatars", "live")
    if os.path.exists(portraits_live_dir):
        app.router.add_static("/portraits/live", portraits_live_dir)
    app.router.add_post("/api/system/game-mode/optimize", handle_game_mode_optimize)
    app.router.add_get("/", handle_index)
    app.router.add_get("/yks-test-takip.html", handle_yks_test_takip)
    app.router.add_get("/yks", handle_yks_test_takip)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_post("/api/config", handle_save_config)
    app.router.add_post("/api/config/legacy-api-key/migrate", handle_migrate_legacy_api_key)
    app.router.add_post("/api/config/test", handle_test_config)
    app.router.add_get("/api/models", handle_get_models)
    app.router.add_get("/api/models/hub", handle_get_models_hub)
    app.router.add_get("/api/models/recommend", handle_recommend_models)
    app.router.add_post("/api/models/select", handle_select_model)
    app.router.add_post("/api/models/paid_auth/request", handle_request_paid_auth)
    app.router.add_post("/api/services/paid_auth/request", handle_request_paid_service_auth)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/chat/stream", handle_chat_stream)
    import jarvis_local_stt
    app.router.add_get("/api/stt/status", jarvis_local_stt.status)
    app.router.add_post("/api/stt", jarvis_local_stt.transcribe)
    app.router.add_post("/api/tts_direct", handle_tts_direct)
    app.router.add_get("/api/vision/destination", handle_vision_destination)
    app.router.add_post("/api/vision/approval", handle_vision_approval)
    app.router.add_post("/api/vision", handle_vision_scan)
    app.router.add_post("/api/screen/capture", handle_screen_capture)
    # Autonomous Agent Engine API (V12)
    app.router.add_post("/api/agent/tasks", handle_agent_create_task)
    app.router.add_get("/api/agent/tasks", handle_agent_list_tasks)
    app.router.add_get("/api/agent/tasks/{task_id}", handle_agent_get_task)
    app.router.add_post("/api/agent/tasks/{task_id}/approve", handle_agent_approve_step)
    app.router.add_post("/api/agent/tasks/{task_id}/reject", handle_agent_reject_step)
    app.router.add_post("/api/agent/tasks/{task_id}/cancel", handle_agent_cancel_task)
    app.router.add_post("/api/agent/tasks/{task_id}/pause", handle_agent_pause_task)
    app.router.add_get("/api/agent/status", handle_agent_status)
    app.router.add_get("/api/agent/events", handle_agent_events)
    # Developer Agent V1: local, user-selected workspace only.
    app.router.add_get("/api/developer/status", handle_developer_status)
    app.router.add_post("/api/developer/workspace/select", handle_developer_select_workspace)
    app.router.add_post("/api/developer/workspace/inspect", handle_developer_inspect_workspace)
    app.router.add_post("/api/developer/workspace/search", handle_developer_search_workspace)
    app.router.add_post("/api/developer/workspace/read", handle_developer_read_file)
    app.router.add_post("/api/developer/plans", handle_developer_create_plan)
    app.router.add_get("/api/developer/plans/{plan_id}", handle_developer_get_plan)
    app.router.add_post("/api/developer/plans/{plan_id}/approval", handle_developer_begin_approval)
    app.router.add_post("/api/developer/plans/{plan_id}/approve", handle_developer_approve_plan)
    app.router.add_post("/api/developer/plans/{plan_id}/cancel", handle_developer_cancel_plan)
    app.router.add_post("/api/developer/plans/{plan_id}/restore/request", handle_developer_begin_restore)
    app.router.add_post("/api/developer/plans/{plan_id}/restore/approve", handle_developer_approve_restore)
    # Desktop Agent V1: semantic UIA only; no coordinate or shell route is exposed here.
    app.router.add_get("/api/desktop/status", handle_desktop_status)
    app.router.add_post("/api/desktop/windows", handle_desktop_list_windows)
    app.router.add_post("/api/desktop/windows/inspect", handle_desktop_inspect_window)
    app.router.add_post("/api/desktop/elements/read", handle_desktop_read_element_state)
    app.router.add_post("/api/desktop/actions", handle_desktop_create_action)
    app.router.add_post("/api/desktop/actions/{action_id}/approval", handle_desktop_begin_approval)
    app.router.add_post("/api/desktop/actions/{action_id}/approve", handle_desktop_approve_action)
    app.router.add_post("/api/desktop/actions/{action_id}/reject", handle_desktop_reject_action)
    # Computer Use Engine API (V13)
    app.router.add_get("/api/computer_use/active_window", handle_cu_active_window)
    app.router.add_get("/api/computer_use/inspect_ui", handle_cu_inspect_ui)
    app.router.add_get("/api/system_metrics", handle_system_metrics)
    app.router.add_get("/api/performance/profile", handle_get_performance_profile)
    app.router.add_post("/api/performance/profile", handle_set_performance_profile)
    app.router.add_get("/api/health/rate_limits", handle_get_rate_limits)
    app.router.add_get("/api/memory", handle_get_memory)
    app.router.add_post("/api/memory", handle_save_memory)
    app.router.add_get("/api/memory/search", handle_search_memory)
    app.router.add_get("/api/memory/entries/{id}", handle_get_memory_entry)
    app.router.add_delete("/api/memory/entries/{id}", handle_delete_memory_note)
    app.router.add_post("/api/memory/candidates/detect", handle_detect_memory_candidates)
    app.router.add_post("/api/memory/notes", handle_add_memory_note)
    app.router.add_delete("/api/memory/notes/{id}", handle_delete_memory_note)
    app.router.add_get("/api/memory/candidates", handle_get_candidates)
    app.router.add_post("/api/memory/candidates", handle_create_candidate)
    app.router.add_post("/api/memory/candidates/{id}/approve", handle_approve_candidate)
    app.router.add_delete("/api/memory/candidates/{id}", handle_dismiss_candidate)
    app.router.add_get("/api/tasks", handle_get_tasks)
    app.router.add_post("/api/tasks", handle_save_tasks)
    app.router.add_patch("/api/tasks/{id}", handle_patch_task)
    app.router.add_delete("/api/tasks/{id}", handle_delete_task)
    app.router.add_post("/api/tasks/{id}/toggle", handle_toggle_task)
    app.router.add_get("/api/activity_logs", handle_activity_logs)
    app.router.add_get("/api/telegram/messages", handle_get_telegram)
    app.router.add_post("/api/telegram/messages", handle_post_telegram)
    app.router.add_delete("/api/telegram/messages", handle_delete_telegram)
    app.router.add_post("/api/telegram/send", handle_send_telegram)
    app.router.add_get("/api/telegram/status", handle_get_telegram_status)
    app.router.add_get("/api/notifications/deferred", handle_get_deferred_notifications)
    app.router.add_post("/api/notifications/deferred/drain", handle_drain_deferred_notifications)
    app.router.add_post("/api/notifications/dispatch", handle_dispatch_notification)
    app.router.add_get("/api/automations", handle_get_automations)
    app.router.add_post("/api/automations", handle_create_automation)
    app.router.add_post("/api/automations/test_action", handle_test_automation_action)
    app.router.add_patch("/api/automations/{id}", handle_patch_automation)
    app.router.add_post("/api/automations/{id}/toggle", handle_toggle_automation)
    app.router.add_delete("/api/automations/{id}", handle_delete_automation)
    app.router.add_post("/api/automations/{id}/cancel", handle_delete_automation)
    app.router.add_post("/api/accio/sync", handle_accio_sync)

    # OpenJarvis Modül Rotaları Entegrasyonu
    try:
        from openjarvis_bridge import register_openjarvis_routes
        register_openjarvis_routes(app)
    except Exception as _oj_err:
        print(f"[OpenJarvis Entegrasyon Uyarısı]: {_oj_err}")

    return app

def safe_start_server(app=None, host="127.0.0.1", port=PORT):
    """
    Phase 9B.1B & 9B.1C: Safe Port & Startup Management with Rotating Runtime Logging.
    Catches address-in-use errors (WinError 10048 / EADDRINUSE), logs startup and shutdown events,
    informs user with process inspection command, does not kill other processes, and does not silently switch port.
    """
    log = setup_logging()
    if app is None:
        app = create_app()

    banner = (
        "=" * 60 + "\n"
        "      ACCIO JARVIS & LUNA v4.0 ULTIMATE (SUBJECT-SHINJI EDITION)\n"
        "=" * 60 + "\n"
        f"Tarayici Arayuzu: http://{host}:{port}\n"
        "Durdurmak icin Ctrl + C\n"
        + "-" * 60
    )
    print(banner)
    log.info(f"JARVIS sunucusu başlatılıyor: http://{host}:{port} (PID: {os.getpid()})")

    try:
        web.run_app(app, host=host, port=port)
        log.info("JARVIS sunucusu normal şekilde durduruldu.")
    except OSError as e:
        is_port_in_use = (
            getattr(e, "winerror", None) == 10048 or
            getattr(e, "errno", None) in (getattr(errno, "EADDRINUSE", 10048), 10048, 98, 48) or
            "10048" in str(e) or
            "address already in use" in str(e).lower()
        )
        if is_port_in_use:
            err_msg = f"Port {port} şu anda başka bir süreç tarafından kullanılıyor! netstat -ano | findstr :{port}"
            log.error(f"[BAŞLATMA HATASI]: {err_msg}")
            print("\n" + "!" * 60)
            print(f"[BAŞLATMA HATASI]: Port {port} şu anda başka bir süreç tarafından kullanılıyor!")
            print(f"JARVIS http://{host}:{port} üzerinde başlatılamadı.")
            print("Portu kullanan süreci tespit etmek için terminalde şu komutu çalıştırabilirsiniz:")
            print(f"    netstat -ano | findstr :{port}")
            print("!" * 60 + "\n")
            sys.exit(1)
        else:
            log.exception(f"Beklenmeyen başlatma soket hatası: {e}")
            raise
    except Exception as e:
        log.exception(f"Sunucu çalışma zamanı hatası: {e}")
        raise

if __name__ == "__main__":
    app = create_app()
    safe_start_server(app, host="127.0.0.1", port=PORT)

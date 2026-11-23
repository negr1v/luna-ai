"""ACCIO LUNA ULTRA Developer Agent V1.

This module is deliberately a narrow local-workspace change pipeline.  It does
not expose a shell, install packages, use the network, operate Git, or infer a
workspace without an explicit user selection.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Tuple

from luna_agent_engine import AgentController, AgentTask, PermissionLevel, TaskState, TaskStep, ToolDefinition


class DeveloperAgentError(Exception):
    """Safe, user-presentable error used by the Developer Agent."""


class DeveloperTestFailed(DeveloperAgentError):
    """Raised after a patch is retained but its approved focused test fails."""


MAX_FILE_BYTES = 256 * 1024
MAX_READ_CHARS = 64 * 1024
MAX_PATCH_CHARS = 32 * 1024
MAX_DIFF_CHARS = 64 * 1024
MAX_OUTPUT_CHARS = 12 * 1024
MAX_WORKSPACE_ENTRIES = 120
MAX_SEARCH_RESULTS = 50
MAX_PATCH_FILES = 3
TEST_TIMEOUT_SECONDS = 45

_SKIPPED_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env"}
_SECRET_EXACT_NAMES = {
    ".env", "api_key.txt", "apikey.txt", "credentials.json", "credential.json",
    "secrets.json", "secret.json", "token.json", "tokens.json", "luna_config.json",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}
_SECRET_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".kdbx")
_TEXT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml"}


def _safe_message(error: Exception) -> str:
    """Keep errors actionable without returning local details outside the workspace."""
    text = str(error).strip()
    return text[:400] if text else "İşlem güvenlik denetiminde durduruldu."


def _is_secret_name(path: str) -> bool:
    name = os.path.basename(path).lower()
    if name in _SECRET_EXACT_NAMES or name.startswith(".env."):
        return True
    if name.endswith(_SECRET_SUFFIXES):
        return True
    # Common credential stores are excluded, while source files such as
    # luna_secret_store.py remain inspectable.
    stem, ext = os.path.splitext(name)
    return ext in {".json", ".txt", ".ini", ".cfg"} and any(token in stem for token in ("credential", "secret", "token", "api_key", "apikey"))


def _is_text_candidate(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _TEXT_SUFFIXES or os.path.basename(path).lower() in {"agents.md", "readme", "license"}


def _bounded_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "\n… çıktı sınırı …"


class WorkspaceGuard:
    """Canonical-path and secret-file guard for one explicitly selected root."""

    def __init__(self, root: str):
        if not isinstance(root, str) or not root.strip():
            raise DeveloperAgentError("Bir proje klasörü seçilmelidir.")
        requested = os.path.abspath(os.path.expanduser(root.strip()))
        if not os.path.isdir(requested):
            raise DeveloperAgentError("Seçilen proje klasörü bulunamadı.")
        self.root = os.path.realpath(requested)
        if not os.path.isdir(self.root):
            raise DeveloperAgentError("Seçilen proje klasörü çözümlenemedi.")

    def relative_path(self, path: str) -> str:
        return os.path.relpath(path, self.root).replace("\\", "/")

    def resolve(self, relative_path: str, *, must_exist: bool = True, allow_secret: bool = False) -> str:
        if not isinstance(relative_path, str) or not relative_path.strip() or "\x00" in relative_path:
            raise DeveloperAgentError("Geçerli bir göreli dosya yolu gerekli.")
        if os.path.isabs(relative_path):
            raise DeveloperAgentError("Mutlak dosya yollarına izin verilmez.")
        parts = [part.lower() for part in relative_path.replace("\\", "/").split("/") if part]
        if any(part in {".git", ".hg", ".svn"} for part in parts):
            raise DeveloperAgentError("Sürüm kontrol metaverisi Developer Agent kapsamı dışındadır.")
        candidate = os.path.realpath(os.path.join(self.root, relative_path))
        try:
            within = os.path.commonpath([os.path.normcase(self.root), os.path.normcase(candidate)]) == os.path.normcase(self.root)
        except ValueError:
            within = False
        if not within:
            raise DeveloperAgentError("Çalışma alanı dışına çıkan yol reddedildi.")
        if not allow_secret and _is_secret_name(candidate):
            raise DeveloperAgentError("Gizli olabilecek dosyalar Developer Agent tarafından okunamaz veya değiştirilemez.")
        if must_exist and not os.path.isfile(candidate):
            raise DeveloperAgentError("Seçilen dosya çalışma alanında bulunamadı.")
        return candidate

    def read_text(self, relative_path: str, *, max_chars: int = MAX_READ_CHARS) -> str:
        path = self.resolve(relative_path)
        if os.path.getsize(path) > MAX_FILE_BYTES:
            raise DeveloperAgentError("Dosya güvenli okuma sınırını aşıyor.")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return _bounded_text(handle.read(max_chars + 1), max_chars)
        except UnicodeDecodeError:
            raise DeveloperAgentError("Yalnızca metin dosyaları okunabilir.")
        except OSError:
            raise DeveloperAgentError("Dosya güvenle okunamadı.")


@dataclass
class PlanRecord:
    plan_id: str
    workspace_root: str
    request: str
    files: List[str]
    before: Dict[str, str]
    after: Dict[str, str]
    diff: str
    patch_fingerprint: str
    test_spec: Dict[str, Any]
    test_command: str
    instruction_paths: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    task_id: Optional[str] = None
    state: str = "PLANNED"
    test_status: str = "NOT_RUN"
    test_output: str = ""
    applied: bool = False
    restored: bool = False
    cancel_requested: bool = False


class _HtmlCheckParser(HTMLParser):
    def error(self, message):  # pragma: no cover - HTMLParser currently does not call this
        raise ValueError(message)


class DeveloperAgent:
    """Stateful, single-user local developer workflow built on AgentController approvals."""

    def __init__(self, data_dir: Optional[str] = None):
        self.guard: Optional[WorkspaceGuard] = None
        self.plans: Dict[str, PlanRecord] = {}
        self._lock = threading.RLock()
        audit_dir = data_dir or tempfile.gettempdir()
        self.engine = AgentController(project_dir=os.getcwd(), data_dir=audit_dir)
        self._register_tools()

    # ---------- Workspace selection and read-only tools ----------

    async def select_workspace(self, root: str) -> Dict[str, Any]:
        guard = WorkspaceGuard(root)
        with self._lock:
            self.guard = guard
        inspection = await self.inspect_workspace({"max_depth": 2, "max_entries": 60})
        return {
            "status": "ok",
            "workspace": {"name": os.path.basename(guard.root) or guard.root, "path": guard.root},
            "inspection": inspection,
        }

    def _require_guard(self) -> WorkspaceGuard:
        if not self.guard:
            raise DeveloperAgentError("Önce proje kök klasörünü seçin.")
        return self.guard

    async def _execute_read_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        validation = self.engine.registry.validate_arguments(name, arguments)
        if not validation["valid"]:
            raise DeveloperAgentError("Araç girdisi geçersiz: " + ", ".join(item["code"] for item in validation["errors"]))
        tool = self.engine.registry.get(name)
        if not tool:
            raise DeveloperAgentError("İstenen geliştirme aracı kayıtlı değil.")
        return await tool.handler(arguments)

    async def inspect_workspace(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_read_tool("workspace.inspect", arguments)

    async def search_workspace(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_read_tool("workspace.search", arguments)

    async def read_workspace_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_read_tool("workspace.read_file", arguments)

    def _iter_workspace_files(self, guard: WorkspaceGuard, max_depth: int, max_entries: int) -> Iterable[Tuple[str, str]]:
        yielded = 0
        for current, dirs, files in os.walk(guard.root, followlinks=False):
            rel_dir = os.path.relpath(current, guard.root)
            depth = 0 if rel_dir == "." else len(rel_dir.split(os.sep))
            dirs[:] = [d for d in dirs if d.lower() not in _SKIPPED_DIRS and not os.path.islink(os.path.join(current, d))]
            if depth > max_depth:
                dirs[:] = []
                continue
            for filename in files:
                if yielded >= max_entries:
                    return
                full = os.path.join(current, filename)
                if os.path.islink(full) or _is_secret_name(full) or not _is_text_candidate(full):
                    continue
                try:
                    resolved = guard.resolve(guard.relative_path(full))
                except DeveloperAgentError:
                    continue
                yielded += 1
                yield guard.relative_path(resolved), resolved

    async def _tool_workspace_inspect(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        guard = self._require_guard()
        max_depth = int(arguments.get("max_depth", 2))
        max_entries = int(arguments.get("max_entries", 60))
        files = []
        languages = set()
        entry_points = []
        tests = []
        instructions = []
        for relative, full in self._iter_workspace_files(guard, max_depth, min(max_entries, MAX_WORKSPACE_ENTRIES)):
            suffix = os.path.splitext(relative)[1].lower()
            language = {".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".html": "HTML", ".css": "CSS", ".json": "JSON"}.get(suffix)
            if language:
                languages.add(language)
            name = os.path.basename(relative).lower()
            if name in {"main.py", "app.py", "server.py", "index.js", "index.html", "package.json", "pyproject.toml"}:
                entry_points.append(relative)
            if name.startswith("test_") or name.endswith(".test.js") or name.endswith(".spec.js"):
                tests.append(relative)
            if name in {"agents.md", "instructions.md"}:
                try:
                    content = guard.read_text(relative, max_chars=16 * 1024)
                    instructions.append({"path": relative, "content": content})
                except DeveloperAgentError:
                    pass
            files.append(relative)
        return {
            "status": "ok", "workspace": {"name": os.path.basename(guard.root), "path": guard.root},
            "files": files, "languages": sorted(languages), "entry_points": entry_points[:12],
            "test_files": tests[:20], "instructions": instructions,
            "truncated": len(files) >= min(max_entries, MAX_WORKSPACE_ENTRIES),
        }

    async def _tool_workspace_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        guard = self._require_guard()
        query = arguments["query"].strip()
        max_results = int(arguments.get("max_results", 20))
        results = []
        for relative, full in self._iter_workspace_files(guard, max_depth=4, max_entries=MAX_WORKSPACE_ENTRIES):
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
                with open(full, "r", encoding="utf-8") as handle:
                    for number, line in enumerate(handle, start=1):
                        if query.lower() in line.lower():
                            results.append({"path": relative, "line": number, "preview": _bounded_text(line.strip(), 220)})
                            if len(results) >= max_results:
                                return {"status": "ok", "results": results, "truncated": True}
            except (OSError, UnicodeDecodeError):
                continue
        return {"status": "ok", "results": results, "truncated": False}

    async def _tool_workspace_read_file(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        guard = self._require_guard()
        relative = arguments["path"]
        return {"status": "ok", "path": relative.replace("\\", "/"), "content": guard.read_text(relative)}

    # ---------- Planning and structured patch preparation ----------

    @staticmethod
    def _path_from_diff_marker(value: str) -> str:
        value = value.strip().split("\t", 1)[0].strip()
        if value in {"/dev/null", "NUL"}:
            raise DeveloperAgentError("Developer Agent V1 yeni dosya oluşturma veya silme işlemi yapmaz.")
        if value.startswith("a/") or value.startswith("b/"):
            value = value[2:]
        return value.replace("\\", "/")

    def _parse_unified_patch(self, guard: WorkspaceGuard, patch: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        if not patch or len(patch) > MAX_PATCH_CHARS:
            raise DeveloperAgentError("Yama boş veya güvenli boyut sınırının üzerinde.")
        lines = patch.splitlines(keepends=True)
        index = 0
        before: Dict[str, str] = {}
        after: Dict[str, str] = {}
        while index < len(lines):
            if not lines[index].startswith("--- "):
                raise DeveloperAgentError("Yama yalnızca standart birleşik diff biçiminde olmalıdır.")
            old_path = self._path_from_diff_marker(lines[index][4:])
            index += 1
            if index >= len(lines) or not lines[index].startswith("+++ "):
                raise DeveloperAgentError("Birleşik diff içinde yeni dosya satırı eksik.")
            new_path = self._path_from_diff_marker(lines[index][4:])
            index += 1
            if old_path != new_path:
                raise DeveloperAgentError("Developer Agent V1 dosya yeniden adlandırmayı desteklemez.")
            full = guard.resolve(old_path)
            original = guard.read_text(old_path, max_chars=MAX_FILE_BYTES)
            source_lines = original.splitlines(keepends=True)
            output_lines: List[str] = []
            source_index = 0
            saw_hunk = False
            while index < len(lines) and not lines[index].startswith("--- "):
                header = lines[index]
                match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
                if not match:
                    raise DeveloperAgentError("Geçersiz birleşik diff hunk başlığı.")
                saw_hunk = True
                old_start = int(match.group(1)) - 1
                if old_start < source_index or old_start > len(source_lines):
                    raise DeveloperAgentError("Yama hunk sırası geçersiz.")
                output_lines.extend(source_lines[source_index:old_start])
                source_index = old_start
                index += 1
                while index < len(lines) and not lines[index].startswith("@@ ") and not lines[index].startswith("--- "):
                    item = lines[index]
                    if item.startswith("\\ No newline"):
                        index += 1
                        continue
                    if not item or item[0] not in {" ", "+", "-"}:
                        raise DeveloperAgentError("Geçersiz birleşik diff satırı.")
                    content = item[1:]
                    if item[0] == " ":
                        if source_index >= len(source_lines) or source_lines[source_index] != content:
                            raise DeveloperAgentError("Yama bağlamı dosyanın güncel içeriğiyle uyuşmuyor.")
                        output_lines.append(content)
                        source_index += 1
                    elif item[0] == "-":
                        if source_index >= len(source_lines) or source_lines[source_index] != content:
                            raise DeveloperAgentError("Yama silme bağlamı dosyanın güncel içeriğiyle uyuşmuyor.")
                        source_index += 1
                    else:
                        output_lines.append(content)
                    index += 1
            if not saw_hunk:
                raise DeveloperAgentError("Yama en az bir hunk içermelidir.")
            output_lines.extend(source_lines[source_index:])
            before[old_path] = original
            after[old_path] = "".join(output_lines)
            if len(before) > MAX_PATCH_FILES:
                raise DeveloperAgentError("Bir planda en fazla üç dosya değiştirilebilir.")
        if not before:
            raise DeveloperAgentError("Yamada değiştirilebilir dosya bulunamadı.")
        return before, after

    def _prepare_replace_text(self, guard: WorkspaceGuard, proposal: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
        path = proposal.get("path")
        find = proposal.get("find")
        replace = proposal.get("replace")
        if not isinstance(path, str) or not isinstance(find, str) or not isinstance(replace, str):
            raise DeveloperAgentError("Metin değiştirme için dosya, eski metin ve yeni metin gerekli.")
        if not find or len(find) > 8 * 1024 or len(replace) > 8 * 1024:
            raise DeveloperAgentError("Metin değiştirme boyutu güvenli sınırda olmalıdır.")
        original = guard.read_text(path, max_chars=MAX_FILE_BYTES)
        matches = original.count(find)
        if matches != 1:
            raise DeveloperAgentError("Eski metin hedef dosyada tam olarak bir kez bulunmalıdır.")
        relative = guard.relative_path(guard.resolve(path))
        return {relative: original}, {relative: original.replace(find, replace, 1)}

    def _read_applicable_instructions(self, guard: WorkspaceGuard, files: List[str]) -> List[str]:
        """Read project-local instruction files without treating them as authority over this agent's policy."""
        found = []
        seen = set()
        for relative in files:
            folder = os.path.dirname(relative)
            components = [] if not folder or folder == "." else folder.replace("\\", "/").split("/")
            for depth in range(len(components) + 1):
                prefix = "/".join(components[:depth])
                for name in ("AGENTS.md", "INSTRUCTIONS.md"):
                    candidate = f"{prefix}/{name}" if prefix else name
                    if candidate in seen:
                        continue
                    try:
                        guard.resolve(candidate)
                        # The contents are intentionally read but not executed,
                        # parsed as directives, or allowed to weaken V1 policy.
                        guard.read_text(candidate, max_chars=16 * 1024)
                    except DeveloperAgentError:
                        continue
                    seen.add(candidate)
                    found.append(candidate)
        return found

    def _validate_test_spec(self, guard: WorkspaceGuard, test_spec: Optional[Dict[str, Any]], files: List[str]) -> Dict[str, Any]:
        if test_spec is None:
            suffixes = {os.path.splitext(path)[1].lower() for path in files}
            if suffixes == {".py"}:
                return {"kind": "python_py_compile", "targets": files}
            if suffixes.issubset({".js", ".mjs", ".cjs"}):
                return {"kind": "node_check", "targets": files}
            if suffixes == {".json"}:
                return {"kind": "json_parse", "targets": files}
            if suffixes.issubset({".html", ".htm"}):
                return {"kind": "html_parse", "targets": files}
            if suffixes == {".css"}:
                return {"kind": "css_basic_check", "targets": files}
            raise DeveloperAgentError("Bu dosya türü için açık ve yapılandırılmış bir odaklı test seçin.")
        if not isinstance(test_spec, dict):
            raise DeveloperAgentError("Odaklı test tanımı geçersiz.")
        kind = test_spec.get("kind")
        targets = test_spec.get("targets")
        if kind not in {"python_unittest", "python_py_compile", "node_check", "json_parse", "html_parse", "css_basic_check"}:
            raise DeveloperAgentError("İzinli olmayan test türü istendi.")
        if not isinstance(targets, list) or not targets or len(targets) > 4 or not all(isinstance(item, str) for item in targets):
            raise DeveloperAgentError("Odaklı test için 1-4 göreli hedef dosya gerekli.")
        normalized = []
        for target in targets:
            normalized.append(guard.relative_path(guard.resolve(target)))
        return {"kind": kind, "targets": normalized}

    @staticmethod
    def _format_test_command(test_spec: Dict[str, Any]) -> str:
        targets = " ".join(test_spec["targets"])
        kind = test_spec["kind"]
        return {
            "python_unittest": f"python -m unittest -q {targets}",
            "python_py_compile": f"python -m py_compile {targets}",
            "node_check": f"node --check {targets}",
            "json_parse": f"ACCIO structured JSON parse: {targets}",
            "html_parse": f"ACCIO structured HTML parse: {targets}",
            "css_basic_check": f"ACCIO structured CSS basic check: {targets}",
        }[kind]

    @staticmethod
    def _make_diff(before: Dict[str, str], after: Dict[str, str]) -> str:
        chunks = []
        for path in sorted(before):
            chunks.extend(difflib.unified_diff(
                before[path].splitlines(keepends=True), after[path].splitlines(keepends=True),
                fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="",
            ))
        diff = "\n".join(chunks)
        if not diff:
            raise DeveloperAgentError("Yama dosya içeriğinde bir değişiklik üretmedi.")
        return _bounded_text(diff, MAX_DIFF_CHARS)

    async def _tool_create_plan(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        guard = self._require_guard()
        request = arguments["request"].strip()
        proposal = arguments["proposal"]
        if proposal.get("kind") == "replace_text":
            before, after = self._prepare_replace_text(guard, proposal)
        elif proposal.get("kind") == "unified_patch":
            before, after = self._parse_unified_patch(guard, proposal.get("patch", ""))
        else:
            raise DeveloperAgentError("Developer Agent V1 yalnızca yapılandırılmış metin değiştirme veya birleşik diff önerisi kabul eder.")
        files = sorted(before)
        instruction_paths = self._read_applicable_instructions(guard, files)
        test_spec = self._validate_test_spec(guard, arguments.get("test_spec"), files)
        diff = self._make_diff(before, after)
        fingerprint = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        plan = PlanRecord(
            plan_id="dev_plan_" + uuid.uuid4().hex[:12], workspace_root=guard.root,
            request=request, files=files, before=before, after=after, diff=diff,
            patch_fingerprint=fingerprint, test_spec=test_spec,
            test_command=self._format_test_command(test_spec), instruction_paths=instruction_paths,
        )
        with self._lock:
            self.plans[plan.plan_id] = plan
        return self.plan_view(plan.plan_id, include_diff=True)

    async def create_plan(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._execute_read_tool("developer.create_plan", arguments)

    # ---------- Approved write / test / restore tools ----------

    def _binding_for_plan(self, plan: PlanRecord) -> Dict[str, Any]:
        return {
            "workspace_root": plan.workspace_root,
            "plan_id": plan.plan_id,
            "files": plan.files,
            "patch_fingerprint": plan.patch_fingerprint,
            "test_spec": plan.test_spec,
            "test_command": plan.test_command,
        }

    @staticmethod
    def _bindings_match(expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
        return json.dumps(expected, sort_keys=True, ensure_ascii=False) == json.dumps(actual, sort_keys=True, ensure_ascii=False)

    async def begin_plan_approval(self, plan_id: str) -> Dict[str, Any]:
        plan = self._get_plan(plan_id)
        guard = self._require_guard()
        if plan.workspace_root != guard.root or plan.state not in {"PLANNED", "AWAITING_APPROVAL"}:
            raise DeveloperAgentError("Plan artık seçili çalışma alanı için onaylanabilir değil.")
        binding = self._binding_for_plan(plan)
        task = AgentTask(
            task_id="dev_task_" + uuid.uuid4().hex[:12], user_request=plan.request,
            description="Developer Agent onaylı küçük yama ve odaklı test",
            steps=[TaskStep(1, "Önizlemesi yapılan yamayı uygula ve gösterilen odaklı testi çalıştır", "developer.apply_patch", binding, PermissionLevel.USER_APPROVAL)],
            state=TaskState.CREATED,
        )
        self.engine.tasks[task.task_id] = task
        plan.task_id = task.task_id
        await self.engine.execute_task(task.task_id)
        plan.state = "AWAITING_APPROVAL"
        task_view = self.engine.to_dict(task.task_id) or {}
        step = task_view.get("steps", [{}])[0]
        return {"status": "ok", "plan": self.plan_view(plan_id, include_diff=True), "approval": {
            "task_id": task.task_id, "step_id": 1, "approval_id": step.get("approval_id"),
            "expires_at": step.get("approval_expires_at"), "files": plan.files,
            "test_command": plan.test_command, "patch_fingerprint": plan.patch_fingerprint,
        }}

    async def approve_plan(self, plan_id: str, approval_id: str) -> Dict[str, Any]:
        plan = self._get_plan(plan_id)
        if not isinstance(approval_id, str) or not approval_id or not plan.task_id:
            raise DeveloperAgentError("Geçerli tek kullanımlık onay kimliği gerekli.")
        if not self.engine.approve_step(plan.task_id, 1, approval_id):
            raise DeveloperAgentError("Onay geçersiz, süresi dolmuş veya plan değişmiş. Yeni önizleme gerekli.")
        await self.engine.execute_task(plan.task_id)
        task = self.engine.to_dict(plan.task_id) or {}
        if plan.test_status == "PASSED":
            plan.state = "SUCCEEDED"
        elif plan.test_status == "FAILED":
            plan.state = "TEST_FAILED"
        elif plan.test_status == "CANCELLED":
            plan.state = "CANCELLED"
        elif task.get("state") == TaskState.FAILED.value:
            plan.state = "FAILED"
        return {"status": "ok" if plan.state == "SUCCEEDED" else "error", "plan": self.plan_view(plan_id, include_diff=True), "task": task}

    def cancel_plan(self, plan_id: str) -> Dict[str, Any]:
        plan = self._get_plan(plan_id)
        plan.cancel_requested = True
        if plan.task_id:
            self.engine.cancel_task(plan.task_id)
        plan.state = "CANCELLED"
        if plan.test_status == "NOT_RUN":
            plan.test_status = "CANCELLED"
        return self.plan_view(plan_id, include_diff=True)

    async def begin_restore_approval(self, plan_id: str) -> Dict[str, Any]:
        plan = self._get_plan(plan_id)
        if not plan.applied or plan.restored:
            raise DeveloperAgentError("Geri alınabilecek onaylı bir yama bulunamadı.")
        task = AgentTask(
            task_id="dev_restore_" + uuid.uuid4().hex[:12], user_request="Developer Agent yamasını geri al",
            description="Son onaylı Developer Agent yamasını geri al",
            steps=[TaskStep(1, "Yalnızca bu planın değiştirdiği dosyaları önceki içeriklerine döndür", "developer.restore_patch", {
                "workspace_root": plan.workspace_root, "plan_id": plan.plan_id,
                "files": plan.files, "patch_fingerprint": plan.patch_fingerprint,
            }, PermissionLevel.USER_APPROVAL)], state=TaskState.CREATED,
        )
        self.engine.tasks[task.task_id] = task
        await self.engine.execute_task(task.task_id)
        view = self.engine.to_dict(task.task_id) or {}
        step = view.get("steps", [{}])[0]
        return {"status": "ok", "plan": self.plan_view(plan_id, include_diff=True), "approval": {
            "task_id": task.task_id, "step_id": 1, "approval_id": step.get("approval_id"), "files": plan.files,
        }}

    async def approve_restore(self, plan_id: str, task_id: str, approval_id: str) -> Dict[str, Any]:
        plan = self._get_plan(plan_id)
        if not self.engine.approve_step(task_id, 1, approval_id):
            raise DeveloperAgentError("Geri alma onayı geçersiz veya süresi dolmuş.")
        await self.engine.execute_task(task_id)
        task = self.engine.to_dict(task_id) or {}
        if task.get("state") != TaskState.COMPLETED.value:
            raise DeveloperAgentError("Geri alma tamamlanamadı; dosyalar değiştirilmedi veya güvenlik denetimi durdurdu.")
        plan.restored = True
        plan.state = "RESTORED"
        return {"status": "ok", "plan": self.plan_view(plan_id, include_diff=True), "task": task}

    def _get_plan(self, plan_id: str) -> PlanRecord:
        plan = self.plans.get(plan_id)
        if not plan:
            raise DeveloperAgentError("Developer Agent planı bulunamadı.")
        guard = self._require_guard()
        if plan.workspace_root != guard.root:
            raise DeveloperAgentError("Plan, şu anda seçili olmayan bir çalışma alanına ait.")
        return plan

    def _atomic_write_text(self, path: str, content: str) -> None:
        directory = os.path.dirname(path)
        fd, temp_path = tempfile.mkstemp(prefix=".accio_dev_", suffix=".tmp", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    async def _tool_apply_patch(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._get_plan(arguments["plan_id"])
        if not self._bindings_match(self._binding_for_plan(plan), arguments):
            raise DeveloperAgentError("Yama, dosya listesi, çalışma alanı veya test komutu onay önizlemesinden değişti.")
        if plan.applied or plan.state not in {"AWAITING_APPROVAL", "PLANNED"}:
            raise DeveloperAgentError("Bu plan artık uygulanabilir değil.")
        guard = self._require_guard()
        resolved = {}
        for relative in plan.files:
            path = guard.resolve(relative)
            current = guard.read_text(relative, max_chars=MAX_FILE_BYTES)
            if current != plan.before[relative]:
                raise DeveloperAgentError("Dosya önizlemeden sonra değişti; yeni plan ve onay gerekli.")
            resolved[relative] = path
        written = []
        try:
            for relative in plan.files:
                self._atomic_write_text(resolved[relative], plan.after[relative])
                written.append(relative)
        except Exception:
            for relative in reversed(written):
                try:
                    self._atomic_write_text(resolved[relative], plan.before[relative])
                except Exception:
                    pass
            raise DeveloperAgentError("Yama güvenle uygulanamadı; yazılan dosyalar geri yüklenmeye çalışıldı.")
        plan.applied = True
        plan.state = "TEST_RUNNING"
        # The nested focused-test tool receives the same binding and is
        # validated by the shared ToolRegistry before any process is started.
        test_validation = self.engine.registry.validate_arguments("developer.run_focused_test", arguments)
        if not test_validation["valid"]:
            raise DeveloperAgentError("Odaklı test sözleşmesi doğrulanamadı.")
        test_result = await self._tool_run_focused_test(arguments)
        plan.test_status = test_result["test_status"]
        plan.test_output = test_result["output"]
        if test_result["test_status"] != "PASSED":
            plan.state = "CANCELLED" if test_result["test_status"] == "CANCELLED" else "TEST_FAILED"
            raise DeveloperTestFailed("Yama uygulandı ancak odaklı test başarılı olmadı. Geri alma seçeneği kullanılabilir.")
        plan.state = "SUCCEEDED"
        return {"status": "ok", "changed_files": plan.files, "test_status": "PASSED"}

    async def _tool_run_focused_test(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._get_plan(arguments["plan_id"])
        expected = self._binding_for_plan(plan)
        for key in ("workspace_root", "plan_id", "patch_fingerprint", "test_spec", "test_command"):
            if arguments.get(key) != expected.get(key):
                raise DeveloperAgentError("Odaklı test onaylanan planla uyuşmuyor.")
        return await self._run_approved_test(arguments)

    async def _run_approved_test(self, binding: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._get_plan(binding["plan_id"])
        if not plan.applied:
            raise DeveloperAgentError("Odaklı test yalnızca onaylı yama uygulandıktan sonra çalıştırılabilir.")
        guard = self._require_guard()
        spec = plan.test_spec
        targets = [guard.resolve(path) for path in spec["targets"]]
        kind = spec["kind"]
        if plan.cancel_requested:
            return {"status": "error", "test_status": "CANCELLED", "output": "Test kullanıcı tarafından iptal edildi."}
        if kind == "json_parse":
            try:
                for path in targets:
                    with open(path, "r", encoding="utf-8") as handle:
                        json.load(handle)
                return {"status": "ok", "test_status": "PASSED", "output": "Yapılandırılmış JSON ayrıştırma başarılı."}
            except Exception:
                return {"status": "error", "test_status": "FAILED", "output": "Yapılandırılmış JSON ayrıştırma başarısız."}
        if kind == "html_parse":
            try:
                for path in targets:
                    with open(path, "r", encoding="utf-8") as handle:
                        _HtmlCheckParser().feed(handle.read())
                return {"status": "ok", "test_status": "PASSED", "output": "Yapılandırılmış HTML ayrıştırma başarılı."}
            except Exception:
                return {"status": "error", "test_status": "FAILED", "output": "Yapılandırılmış HTML ayrıştırma başarısız."}
        if kind == "css_basic_check":
            try:
                for path in targets:
                    with open(path, "r", encoding="utf-8") as handle:
                        content = handle.read()
                    if content.count("{") != content.count("}"):
                        raise ValueError("unbalanced braces")
                return {"status": "ok", "test_status": "PASSED", "output": "Temel CSS denetimi başarılı."}
            except Exception:
                return {"status": "error", "test_status": "FAILED", "output": "Temel CSS denetimi başarısız."}

        if kind == "python_unittest":
            command = [sys.executable, "-m", "unittest", "-q", *spec["targets"]]
        elif kind == "python_py_compile":
            command = [sys.executable, "-m", "py_compile", *targets]
        elif kind == "node_check":
            command = ["node", "--check", *targets]
        else:  # defensive; _validate_test_spec prevents this
            raise DeveloperAgentError("Bilinmeyen odaklı test türü.")
        try:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=guard.root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
        except OSError:
            return {"status": "error", "test_status": "FAILED", "output": "İzinli test çalıştırıcısı bu bilgisayarda kullanılamıyor."}
        output_task = asyncio.create_task(process.communicate())
        started = time.monotonic()
        while not output_task.done():
            if plan.cancel_requested:
                process.terminate()
                await output_task
                return {"status": "error", "test_status": "CANCELLED", "output": "Odaklı test kullanıcı tarafından iptal edildi."}
            if time.monotonic() - started > TEST_TIMEOUT_SECONDS:
                process.terminate()
                await output_task
                return {"status": "error", "test_status": "FAILED", "output": "Odaklı test güvenli süre sınırını aştı."}
            await asyncio.sleep(0.05)
        stdout, _ = await output_task
        output = _bounded_text((stdout or b"").decode("utf-8", errors="replace").strip(), MAX_OUTPUT_CHARS)
        if process.returncode == 0:
            return {"status": "ok", "test_status": "PASSED", "output": output or "Odaklı test başarılı."}
        return {"status": "error", "test_status": "FAILED", "output": output or "Odaklı test başarısız."}

    async def _tool_restore_patch(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._get_plan(arguments["plan_id"])
        expected = {
            "workspace_root": plan.workspace_root, "plan_id": plan.plan_id,
            "files": plan.files, "patch_fingerprint": plan.patch_fingerprint,
        }
        if not self._bindings_match(expected, arguments):
            raise DeveloperAgentError("Geri alma eylemi onay önizlemesinden değişti.")
        if not plan.applied or plan.restored:
            raise DeveloperAgentError("Geri alınacak onaylı yama bulunamadı.")
        guard = self._require_guard()
        for relative in plan.files:
            if guard.read_text(relative, max_chars=MAX_FILE_BYTES) != plan.after[relative]:
                raise DeveloperAgentError("Dosya yama sonrasında değişmiş; güvenli geri alma için yeni inceleme gerekli.")
        for relative in plan.files:
            self._atomic_write_text(guard.resolve(relative), plan.before[relative])
        return {"status": "ok", "restored_files": plan.files}

    async def _tool_show_diff(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        plan = self._get_plan(arguments["plan_id"])
        return {"status": "ok", "plan_id": plan.plan_id, "files": plan.files, "diff": plan.diff}

    def plan_view(self, plan_id: str, *, include_diff: bool = False) -> Dict[str, Any]:
        plan = self._get_plan(plan_id)
        view = {
            "plan_id": plan.plan_id, "workspace": {"name": os.path.basename(plan.workspace_root), "path": plan.workspace_root},
            "request": plan.request, "files": plan.files, "state": plan.state,
            "patch_fingerprint": plan.patch_fingerprint, "test_command": plan.test_command,
            "test_status": plan.test_status, "test_output": plan.test_output,
            "can_restore": plan.applied and not plan.restored,
            "summary": {
                "problem": plan.request,
                "intended_behavior": "Yalnızca önizlemedeki yerel dosyalar değişir; ardından gösterilen odaklı test çalışır.",
                "risks": ["Yama önizleme sonrası dosya değişirse uygulama reddedilir.", "Odaklı test başarısız olursa yama otomatik olarak başarılı sayılmaz."],
                "instruction_files": plan.instruction_paths,
            },
        }
        if include_diff:
            view["diff"] = plan.diff
        return view

    # ---------- Registry registration ----------

    def _register_tools(self):
        object_schema = {"type": "object"}
        self.engine.registry.register(ToolDefinition(
            "workspace.inspect", "Seçilen çalışma alanının sınırlı yapısını ve yerel talimatlarını inceler.", PermissionLevel.READ_ONLY, 4.0,
            self._tool_workspace_inspect,
            {"type": "object", "properties": {"max_depth": {"type": "integer", "minimum": 0, "maximum": 4}, "max_entries": {"type": "integer", "minimum": 1, "maximum": MAX_WORKSPACE_ENTRIES}}, "additionalProperties": False},
        ))
        self.engine.registry.register(ToolDefinition(
            "workspace.search", "Seçilen çalışma alanında gizli dosyalar hariç sınırlı metin araması yapar.", PermissionLevel.READ_ONLY, 6.0,
            self._tool_workspace_search,
            {"type": "object", "properties": {"query": {"type": "string", "maxLength": 200}, "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS}}, "required": ["query"], "additionalProperties": False},
        ))
        self.engine.registry.register(ToolDefinition(
            "workspace.read_file", "Seçilen çalışma alanındaki tek bir güvenli metin dosyasını okur.", PermissionLevel.READ_ONLY, 4.0,
            self._tool_workspace_read_file,
            {"type": "object", "properties": {"path": {"type": "string", "maxLength": 400}}, "required": ["path"], "additionalProperties": False},
        ))
        self.engine.registry.register(ToolDefinition(
            "developer.create_plan", "Küçük, kesin bir yerel yama için değişiklik planı ve odaklı test hazırlar.", PermissionLevel.READ_ONLY, 6.0,
            self._tool_create_plan,
            {"type": "object", "properties": {"request": {"type": "string", "maxLength": 1200}, "proposal": object_schema, "test_spec": object_schema}, "required": ["request", "proposal"], "additionalProperties": False},
        ))
        binding_schema = {
            "type": "object", "properties": {
                "workspace_root": {"type": "string", "maxLength": 800}, "plan_id": {"type": "string", "maxLength": 80},
                "files": {"type": "array", "maxItems": MAX_PATCH_FILES, "items": {"type": "string", "maxLength": 400}},
                "patch_fingerprint": {"type": "string", "maxLength": 128}, "test_spec": object_schema,
                "test_command": {"type": "string", "maxLength": 1200},
            }, "required": ["workspace_root", "plan_id", "files", "patch_fingerprint", "test_spec", "test_command"], "additionalProperties": False,
        }
        self.engine.registry.register(ToolDefinition(
            "developer.apply_patch", "Onaylanan küçük yamayı uygular ve aynı onayda bağlı odaklı testi çalıştırır.", PermissionLevel.USER_APPROVAL, 90.0,
            self._tool_apply_patch, binding_schema,
        ))
        self.engine.registry.register(ToolDefinition(
            "developer.run_focused_test", "Yalnızca onaylı planın gösterilen odaklı testini çalıştırır.", PermissionLevel.USER_APPROVAL, 60.0,
            self._tool_run_focused_test, binding_schema,
        ))
        restore_schema = {
            "type": "object", "properties": {
                "workspace_root": {"type": "string", "maxLength": 800}, "plan_id": {"type": "string", "maxLength": 80},
                "files": {"type": "array", "maxItems": MAX_PATCH_FILES, "items": {"type": "string", "maxLength": 400}},
                "patch_fingerprint": {"type": "string", "maxLength": 128},
            }, "required": ["workspace_root", "plan_id", "files", "patch_fingerprint"], "additionalProperties": False,
        }
        self.engine.registry.register(ToolDefinition(
            "developer.restore_patch", "Son onaylı yamanın yalnızca değiştirdiği dosyaları geri alır.", PermissionLevel.USER_APPROVAL, 20.0,
            self._tool_restore_patch, restore_schema,
        ))
        self.engine.registry.register(ToolDefinition(
            "developer.show_diff", "Son planın yalnızca değişen dosyaları için okunabilir diff üretir.", PermissionLevel.READ_ONLY, 3.0,
            self._tool_show_diff,
            {"type": "object", "properties": {"plan_id": {"type": "string", "maxLength": 80}}, "required": ["plan_id"], "additionalProperties": False},
        ))

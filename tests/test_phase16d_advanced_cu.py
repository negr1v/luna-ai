"""
Focused Unit & Mocked Test Suite for Phase 16D: Safe Advanced Computer Use
Validates UIAutomation action controller, InvokePattern & ValuePattern execution gates,
USER_APPROVAL enforcement, sensitive field blocking, allowlist gates, duplicate prevention,
terminal denial halts, and script integrity.
"""

import os
import unittest
import asyncio
from unittest.mock import patch, MagicMock

BASE_DIR = r"C:\Users\negr1\Projeler\ACCIO-JARVIS"

class TestPhase16DAdvancedComputerUse(unittest.TestCase):

    def setUp(self):
        self.backup_cu = os.path.join(BASE_DIR, "jarvis_computer_use.py.bak_phase16d_20261114")
        self.backup_agent = os.path.join(BASE_DIR, "jarvis_agent_engine.py.bak_phase16d_20261114")
        self.action_ps1 = os.path.join(BASE_DIR, "jarvis_uia_action.ps1")

    def test_01_backup_verification(self):
        """Doğrulama 1: jarvis_computer_use.py ve jarvis_agent_engine.py yedekleri mevcut."""
        self.assertTrue(os.path.exists(self.backup_cu), "Backup for jarvis_computer_use.py missing")
        self.assertTrue(os.path.exists(self.backup_agent), "Backup for jarvis_agent_engine.py missing")
        self.assertGreater(os.path.getsize(self.backup_cu), 8000)
        self.assertGreater(os.path.getsize(self.backup_agent), 20000)

    def test_02_tool_definitions_and_permissions(self):
        """Doğrulama 2: Araç izin seviyeleri (READ_ONLY vs USER_APPROVAL) titizlikle korunuyor."""
        from jarvis_agent_engine import AgentController, PermissionLevel

        controller = AgentController(BASE_DIR)
        registry = controller.registry

        # Read-only araçlar
        inspect_tool = registry.get("inspect_window_ui")
        self.assertIsNotNone(inspect_tool)
        self.assertEqual(inspect_tool.permission_level, PermissionLevel.READ_ONLY)

        preview_tool = registry.get("preview_ui_action")
        self.assertIsNotNone(preview_tool)
        self.assertEqual(preview_tool.permission_level, PermissionLevel.READ_ONLY)

        # Onay gerektiren araçlar (USER_APPROVAL zorunlu)
        invoke_tool = registry.get("invoke_ui_element")
        self.assertIsNotNone(invoke_tool)
        self.assertEqual(invoke_tool.permission_level, PermissionLevel.USER_APPROVAL)

        set_val_tool = registry.get("set_ui_element_value")
        self.assertIsNotNone(set_val_tool)
        self.assertEqual(set_val_tool.permission_level, PermissionLevel.USER_APPROVAL)

        type_tool = registry.get("type_text_into_window")
        self.assertIsNotNone(type_tool)
        self.assertEqual(type_tool.permission_level, PermissionLevel.USER_APPROVAL)

    def test_03_allowlist_and_blocked_apps(self):
        """Doğrulama 3: Güvenlik kısıtlamalı uygulamalar (powershell, cmd, regedit) engelleniyor."""
        from jarvis_computer_use import UIAutomationActionController

        with patch("jarvis_computer_use.DesktopAwareness.get_foreground_window_info") as mock_fg:
            # PowerShell engellenmeli
            mock_fg.return_value = {
                "status": "ok",
                "process_name": "powershell.exe",
                "title": "Windows PowerShell",
                "is_allowed": False
            }
            res = UIAutomationActionController.execute_ui_action(hwnd=1234, action="Invoke", automation_id="btnTest")
            self.assertEqual(res.get("status"), "blocked")
            self.assertEqual(res.get("reason"), "security_restricted_app")

            # İzinli olmayan bilinmeyen uygulama engellenmeli
            mock_fg.return_value = {
                "status": "ok",
                "process_name": "unknown_hacker_tool.exe",
                "title": "Unknown",
                "is_allowed": False
            }
            res2 = UIAutomationActionController.execute_ui_action(hwnd=1234, action="Invoke", automation_id="btnTest")
            self.assertEqual(res2.get("status"), "blocked")
            self.assertEqual(res2.get("reason"), "app_not_allowed")

    def test_04_password_and_sensitive_field_protection(self):
        """Doğrulama 4: Parola, PIN ve kimlik kontrol alanlarına müdahale kesinlikle engelleniyor."""
        from jarvis_computer_use import UIAutomationActionController

        with patch("jarvis_computer_use.DesktopAwareness.get_foreground_window_info") as mock_fg:
            mock_fg.return_value = {
                "status": "ok",
                "process_name": "notepad.exe",
                "title": "Untitled - Notepad",
                "is_allowed": True
            }

            sensitive_targets = [
                "txtPassword", "UserPinInput", "secret_key_field",
                "ParolaAlani", "SifreGir", "cvv_number", "auth_token_box"
            ]

            for target in sensitive_targets:
                res = UIAutomationActionController.execute_ui_action(
                    hwnd=5678,
                    action="SetValue",
                    automation_id=target,
                    value="123456"
                )
                self.assertEqual(res.get("status"), "blocked", f"Target {target} should be blocked")
                self.assertEqual(res.get("reason"), "sensitive_field")

    def test_05_destructive_command_blocking(self):
        """Doğrulama 5: Yıkıcı silme veya sistem kapatma komutları ValuePattern ile engelleniyor."""
        from jarvis_computer_use import UIAutomationActionController

        with patch("jarvis_computer_use.DesktopAwareness.get_foreground_window_info") as mock_fg:
            mock_fg.return_value = {
                "status": "ok",
                "process_name": "notepad.exe",
                "title": "Notepad",
                "is_allowed": True
            }

            destructive_values = [
                "rm -rf /", "del C:\\Windows", "format D:", "shutdown /s /t 0", "drop table users"
            ]

            for val in destructive_values:
                res = UIAutomationActionController.execute_ui_action(
                    hwnd=9999,
                    action="SetValue",
                    automation_id="txtNotes",
                    value=val
                )
                self.assertEqual(res.get("status"), "blocked")
                self.assertEqual(res.get("reason"), "destructive_command_blocked")

    def test_06_duplicate_action_prevention(self):
        """Doğrulama 6: Aynı eylemin peş peşe mükerrer yürütülmesi engelleniyor."""
        from jarvis_computer_use import UIAutomationActionController

        # Önbelleğe simüle edilmiş yürütülmüş token ekle
        test_token = "unique_action_token_123"
        UIAutomationActionController._record_execution(test_token)

        self.assertTrue(UIAutomationActionController._is_duplicate(test_token))

        with patch("jarvis_computer_use.DesktopAwareness.get_foreground_window_info") as mock_fg:
            mock_fg.return_value = {
                "status": "ok",
                "process_name": "notepad.exe",
                "title": "Notepad",
                "is_allowed": True
            }

            res = UIAutomationActionController.execute_ui_action(
                hwnd=1111,
                action="Invoke",
                automation_id="btnSave",
                action_token=test_token
            )
            self.assertEqual(res.get("status"), "blocked")
            self.assertEqual(res.get("reason"), "duplicate_action")

    def test_07_agent_engine_user_approval_workflow(self):
        """Doğrulama 7: Ajan planlayıcı USER_APPROVAL gerektirir; onay verilmeden çalışmaz."""
        from jarvis_agent_engine import AgentController, TaskState, PermissionLevel

        controller = AgentController(BASE_DIR)
        task = controller.create_task("hesap makinesinde butona tıkla")

        # Plan adımlarını doğrula
        self.assertGreaterEqual(len(task.steps), 2)
        step_preview = task.steps[0]
        step_invoke = task.steps[1]

        self.assertEqual(step_preview.tool_name, "preview_ui_action")
        self.assertEqual(step_preview.permission_level, PermissionLevel.READ_ONLY)

        self.assertEqual(step_invoke.tool_name, "invoke_ui_element")
        self.assertEqual(step_invoke.permission_level, PermissionLevel.USER_APPROVAL)

        # İlk yürütme: Step 1 (READ_ONLY) biter, Step 2'de AWAITING_APPROVAL'a geçer
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(controller.execute_task(task.task_id))
            self.assertEqual(task.state, TaskState.AWAITING_APPROVAL)
            self.assertFalse(step_invoke.approval_granted)

            # Kullanıcı REDDEDERSE: Terminal Denial olmalı
            controller.reject_step(task.task_id, step_id=step_invoke.step_id, reason="Güvenlik nedeniyle onaylanmadı")
            self.assertEqual(task.state, TaskState.TERMINAL_DENIED)
            self.assertIn("invoke_ui_element", task.denied_tools)

            # Reddedilen görev bir daha çalıştırılamaz
            loop.run_until_complete(controller.execute_task(task.task_id))
            self.assertEqual(task.state, TaskState.TERMINAL_DENIED)
        finally:
            loop.close()

    def test_08_ps1_script_exists_and_contains_patterns(self):
        """Doğrulama 8: jarvis_uia_action.ps1 betiği mevcut ve gerekli güvenlik kalıplarını içeriyor."""
        self.assertTrue(os.path.exists(self.action_ps1))
        with open(self.action_ps1, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("InvokePattern", content)
        self.assertIn("ValuePattern", content)
        self.assertIn("TogglePattern", content)
        self.assertIn("sensitiveTokens", content)
        self.assertIn("IsPassword", content)
        self.assertIn("TimeoutSec", content)

if __name__ == "__main__":
    unittest.main()

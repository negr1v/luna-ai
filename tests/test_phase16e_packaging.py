"""
Focused Test Suite for Phase 16E: Personal Windows Packaging
Validates package structure, application/data separation, secret sanitization,
portable path resolution, status/recovery execution, and Agent Engine safety.
"""

import os
import sys
import json
import unittest
import subprocess

BASE_DIR = r"C:\Users\negr1\Projeler\LUNA-AI"
PACKAGE_DIR = os.path.join(BASE_DIR, "dist", "LUNA-AI-PORTABLE")

class TestPhase16EPackaging(unittest.TestCase):

    def setUp(self):
        self.backup_server = os.path.join(BASE_DIR, "luna_server.py.bak_phase16e_20261114")
        self.backup_agent = os.path.join(BASE_DIR, "luna_agent_engine.py.bak_phase16e_20261114")
        self.backup_start = os.path.join(BASE_DIR, "start_luna.ps1.bak_phase16e_20261114")

    def test_01_backup_verification(self):
        """Doğrulama 1: luna_server.py, luna_agent_engine.py ve start_luna.ps1 yedekleri mevcut."""
        self.assertTrue(os.path.exists(self.backup_server), "Server backup missing")
        self.assertTrue(os.path.exists(self.backup_agent), "Agent backup missing")
        self.assertTrue(os.path.exists(self.backup_start), "Start script backup missing")
        self.assertGreater(os.path.getsize(self.backup_server), 300000)
        self.assertGreater(os.path.getsize(self.backup_agent), 25000)
        self.assertGreater(os.path.getsize(self.backup_start), 10000)

    def test_02_package_structure_and_files(self):
        """Doğrulama 2: Taşınabilir paket klasör hiyerarşisi ve gerekli tüm dosyalar eksiksiz."""
        self.assertTrue(os.path.exists(PACKAGE_DIR), "Package directory missing")

        app_dir = os.path.join(PACKAGE_DIR, "app")
        data_dir = os.path.join(PACKAGE_DIR, "data")
        self.assertTrue(os.path.exists(app_dir), "app/ directory missing")
        self.assertTrue(os.path.exists(data_dir), "data/ directory missing")

        required_app_files = [
            "index.html",
            "luna_server.py",
            "luna_agent_engine.py",
            "luna_computer_use.py",
            "luna_tray.ps1",
            "luna_uia_inspect.ps1",
            "luna_uia_action.ps1",
            "start_luna.ps1"
        ]
        for f in required_app_files:
            p = os.path.join(app_dir, f)
            self.assertTrue(os.path.exists(p), f"Missing app file: {f}")
            self.assertGreater(os.path.getsize(p), 0, f"Empty app file: {f}")

        required_data_files = [
            "luna_memory.json",
            "luna_config.json",
            "luna_tasks.json",
            "luna_notifications.json"
        ]
        for f in required_data_files:
            p = os.path.join(data_dir, f)
            self.assertTrue(os.path.exists(p), f"Missing data file: {f}")

        required_launchers = [
            "START-LUNA.bat",
            "START-TRAY.bat",
            "STATUS-LUNA.bat",
            "STOP-LUNA.bat",
            "RECOVER-LUNA.bat",
            "start_portable.ps1",
            "README.txt"
        ]
        for f in required_launchers:
            p = os.path.join(PACKAGE_DIR, f)
            self.assertTrue(os.path.exists(p), f"Missing launcher/doc file: {f}")

    def test_03_data_separation_and_secret_sanitization(self):
        """Doğrulama 3: data/ altındaki yapılandırmada gizli API anahtarları temizlenmiş."""
        cfg_path = os.path.join(PACKAGE_DIR, "data", "luna_config.json")
        with open(cfg_path, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)

        secret_keys = ["groq_api_key", "openrouter_api_key", "elevenlabs_api_key", "openai_api_key", "telegram_bot_token"]
        for k in secret_keys:
            val = cfg.get(k, "")
            self.assertEqual(val, "", f"Secret key {k} should be sanitized in package")

        mem_path = os.path.join(PACKAGE_DIR, "data", "luna_memory.json")
        with open(mem_path, "r", encoding="utf-8-sig") as f:
            mem = json.load(f)
        self.assertIn("user_name", mem)
        self.assertIn("notes", mem)

    def test_04_path_resolution_with_custom_data_dir(self):
        """Doğrulama 4: LUNA_DATA_DIR ortam değişkeni server ve agent motoru tarafından benimsenir."""
        custom_data_dir = os.path.join(PACKAGE_DIR, "data")
        env_copy = os.environ.copy()
        env_copy["LUNA_DATA_DIR"] = custom_data_dir

        # Test script running python code to verify DATA_DIR resolution
        code = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{os.path.join(PACKAGE_DIR, 'app')}')\n"
            "import luna_server\n"
            "print('DATA_DIR:', luna_server.DATA_DIR)\n"
            "print('MEMORY_FILE:', luna_server.MEMORY_FILE)\n"
            f"assert luna_server.DATA_DIR == r'{custom_data_dir}'\n"
            f"assert luna_server.MEMORY_FILE == os.path.join(r'{custom_data_dir}', 'luna_memory.json')\n"
        )

        res = subprocess.run([sys.executable, "-c", code], env=env_copy, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Python path resolution failed: {res.stderr}")
        self.assertIn(custom_data_dir, res.stdout)

    def test_05_portable_powershell_status(self):
        """Doğrulama 5: start_portable.ps1 -Action Status başarıyla yürütülüyor."""
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", os.path.join(PACKAGE_DIR, "start_portable.ps1"),
            "-Action", "Status"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(res.returncode, 0)
        self.assertIn("ACCIO LUNA V16", res.stdout)
        self.assertIn("Durum", res.stdout)

    def test_06_portable_powershell_recovery(self):
        """Doğrulama 6: start_portable.ps1 -Action Recover güvenli şekilde tamamlanıyor."""
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", os.path.join(PACKAGE_DIR, "start_portable.ps1"),
            "-Action", "Recover"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(res.returncode, 0)
        self.assertIn("KURTARMA PROSEDURU", res.stdout)
        self.assertIn("saglam", res.stdout.lower())

    def test_07_agent_engine_user_approval_in_packaged_mode(self):
        """Doğrulama 7: Paketlenmiş app modülünde USER_APPROVAL kısıtlamaları korunuyor."""
        app_path = os.path.join(PACKAGE_DIR, "app")
        data_path = os.path.join(PACKAGE_DIR, "data")

        code = (
            "import os, sys\n"
            f"sys.path.insert(0, r'{app_path}')\n"
            "from luna_agent_engine import AgentController, PermissionLevel\n"
            f"ctrl = AgentController(r'{app_path}', data_dir=r'{data_path}')\n"
            "tool_invoke = ctrl.registry.get('invoke_ui_element')\n"
            "tool_set = ctrl.registry.get('set_ui_element_value')\n"
            "assert tool_invoke.permission_level == PermissionLevel.USER_APPROVAL\n"
            "assert tool_set.permission_level == PermissionLevel.USER_APPROVAL\n"
            "print('SECURITY_OK')\n"
        )

        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Packaged AgentController security check failed: {res.stderr}")
        self.assertIn("SECURITY_OK", res.stdout)

if __name__ == "__main__":
    unittest.main()

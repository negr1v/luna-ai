#!/usr/bin/env python3
"""
ACCIO LUNA V4.0 — Faz 9C.1B Test Modülü
test_phase9c_launcher.py

Güvenli Başlatıcı ve Süreç Yöneticisi Doğrulama Testleri:
- Statik script bütünlüğü ve yasaklı komut denetimi (taskkill / Stop-Process yasağı)
- Yönetilen Python yolu ve sabit port (127.0.0.1:7860) kuralları
- 4'lü kimlik doğrulama ve PID reuse kalkanı
- Yabancı süreç koruması ve port dinleyicisi teyidi
- Güvenli durdurma ve kontrollü Ctrl+C fallback mantığı

NOT: Bu test dosyası gerçek LUNA sunucusunu başlatmaz veya durdurmaz.
Tüm kontroller statik dosya analizi ve izole mantıksal simülasyonlardır.
"""

import os
import re
import json
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPECTED_PYTHON_EXE = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python\python.exe"

class TestPhase9CLauncherStatic(unittest.TestCase):
    """Başlatıcı ve durdurucu betiklerinin statik bütünlük ve güvenlik denetimleri."""

    def test_01_launcher_files_exist(self):
        """Üç başlatıcı scripti ve bu test dosyası eksiksiz mevcut olmalıdır."""
        files = ["start_luna.bat", "start_luna.ps1", "stop_luna.bat", "test_phase9c_launcher.py"]
        for f in files:
            path = os.path.join(PROJECT_DIR, f)
            self.assertTrue(os.path.isfile(path), f"Gerekli dosya eksik: {f}")

    def test_02_managed_python_path_validity(self):
        """start_luna.ps1 içindeki Python executable hedefi birebir doğru yönetilen yol olmalıdır."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        self.assertIn(EXPECTED_PYTHON_EXE, content, "start_luna.ps1 doğru yönetilen Python yolunu içermelidir.")
        self.assertTrue(os.path.isfile(EXPECTED_PYTHON_EXE), "Yönetilen Python executable diskte fiziksel olarak mevcut olmalıdır.")

    def test_03_fixed_host_and_port(self):
        """Host kesinlikle 127.0.0.1 ve Port kesinlikle 7860 olmalıdır; dinamik port değiştirilemez."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('$HostAddr = "127.0.0.1"', content)
        self.assertIn('$Port = 7860', content)
        # Otomatik port artırma / fallback olmamalı
        self.assertNotIn('$Port++', content)
        self.assertNotIn('$Port + 1', content)

    def test_04_batch_wrapper_relative_paths(self):
        """Batch dosyaları %~dp0 kullanarak boşluklu yolları güvenle çözmeli ve yetki istememelidir."""
        start_bat = os.path.join(PROJECT_DIR, "start_luna.bat")
        stop_bat = os.path.join(PROJECT_DIR, "stop_luna.bat")

        for bat_file in [start_bat, stop_bat]:
            with open(bat_file, "r", encoding="utf-8") as f:
                c = f.read()
            self.assertIn("%~dp0", c)
            self.assertNotIn("runas", c.lower())

    def test_05_strictly_forbidden_force_kill_commands(self):
        """KIRMIZI ÇİZGİ: Scriptlerde taskkill, Stop-Process veya Process.Kill kesinlikle bulunmamalıdır."""
        forbidden_patterns = [
            r"taskkill\s+/im\s+python",
            r"taskkill\s+/f",
            r"\bStop-Process\b",
            r"\.Kill\(",
            r"/f\s+/im"
        ]
        
        script_files = ["start_luna.bat", "start_luna.ps1", "stop_luna.bat"]
        for s in script_files:
            path = os.path.join(PROJECT_DIR, s)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            for pattern in forbidden_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                self.assertIsNone(match, f"YASAKLI KOMUT TESPİT EDİLDİ ({pattern}) dosya: {s}")

    def test_06_foreign_process_protection(self):
        """Port 7860'ta yabancı bir süreç varsa başlatma iptal edilmeli, sürece dokunulmamalıdır."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Port $Port baska bir yabanci surec tarafindan kullaniliyor", content)
        self.assertIn("yabanci sureclere dokunulmaz", content)

    def test_07_metadata_schema_and_fields(self):
        """Runtime metadata dosyası şeması 4'lü kimlik doğrulamayı (PID, Başlangıç, Exe, Script) içermelidir."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_meta_keys = [
            "schema",
            "pid",
            "creationTimeUtc",
            "executablePath",
            "scriptPath",
            "host",
            "port"
        ]
        for key in required_meta_keys:
            self.assertIn(key, content, f"Metadata anahtarı eksik: {key}")

    def test_08_pid_reuse_protection_and_fail_closed(self):
        """PID reuse durumunda veya kimlik uyuşmazlığında işlem durdurulmalı ve sürece dokunulmamalıdır."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("PID Reuse veya Kimlik Uyusmazligi", content)
        self.assertIn("yabanci surece dokunulamaz", content)

    def test_09_healthcheck_and_browser_open_condition(self):
        """Tarayıcı ancak 200 OK ve listener PID eşleşmesi doğrulandığında açılmalıdır."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Start-Process \"http://$HostAddr`:$Port\"", content)
        self.assertIn("$currListener -eq $pidLaunched", content)
        self.assertIn("StatusCode -eq 200", content)

    def test_10_safe_stop_manual_ctrl_c_fallback(self):
        """Durdurma işleminde zorla kapatma yapılmamalı; konsolda kontrollü manuel Ctrl+C talimatı bulunmalıdır."""
        ps1_path = os.path.join(PROJECT_DIR, "start_luna.ps1")
        with open(ps1_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Zorla sonlandirma (kill) veri butunlugu geregi engellenmistir", content)
        self.assertIn("Ctrl + C", content)


class TestPhase9CLauncherLogic(unittest.TestCase):
    """Launcher ve Stop mantığının izole simülasyon testleri."""

    def test_11_metadata_structure_serialization(self):
        """Metadata JSON serileştirmesi ve deserialization doğrulaması."""
        sample_meta = {
            "schema": "luna_launcher_v1",
            "pid": 99999,
            "creationTimeUtc": "2026-11-09T18:00:00.0000000Z",
            "executablePath": EXPECTED_PYTHON_EXE,
            "scriptPath": os.path.join(PROJECT_DIR, "luna_server.py"),
            "host": "127.0.0.1",
            "port": 7860,
            "launchedAt": "2026-11-09T18:00:00.0000000Z"
        }
        serialized = json.dumps(sample_meta)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["schema"], "luna_launcher_v1")
        self.assertEqual(deserialized["port"], 7860)
        self.assertEqual(deserialized["executablePath"], EXPECTED_PYTHON_EXE)

    def test_12_no_backend_shutdown_endpoint(self):
        """Güvenlik ilkesi: luna_server.py içinde harici shutdown API'si eklenmemelidir."""
        server_path = os.path.join(PROJECT_DIR, "luna_server.py")
        with open(server_path, "r", encoding="utf-8") as f:
            server_code = f.read()
        self.assertNotIn('"/api/shutdown"', server_code)
        self.assertNotIn("'/api/shutdown'", server_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)

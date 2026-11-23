# -*- coding: utf-8 -*-
"""
LUNA-AI V15 - PHASE 15B ADAPTIVE PERFORMANCE TESTS
Verifies:
1. Default performance profile (BALANCED).
2. Auto-scaling to LITE under sustained high CPU/RAM load.
3. Anti-flapping hysteresis / cooldown guards against rapid switching.
4. Auto-recovery to BALANCED when resource load normalizes.
5. Gaming mode preservation (active gaming forces LITE footprint).
6. Manual profile override (LITE / BALANCED / ULTRA) and reset to AUTO.
7. HTTP endpoints /api/system_metrics and /api/performance/profile return valid specs.
"""
import os
import sys
import time
import unittest
from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import web

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from luna_server import (
    ADAPTIVE_PERFORMANCE_CONTROLLER,
    PerformanceProfile,
    AdaptivePerformanceController,
    handle_system_metrics,
    handle_get_performance_profile,
    handle_set_performance_profile
)

class TestAdaptivePerformanceUnit(unittest.TestCase):
    def setUp(self):
        self.ctrl = AdaptivePerformanceController()
        self.ctrl.switch_cooldown_seconds = 0.5  # Short cooldown for test speed

    def test_01_default_profile_is_balanced_on_current_hardware(self):
        """Mevcut i5-8250U / 8GB donanımında başlangıç profilinin BALANCED (60 FPS, 32 partikül) olduğunu doğrula."""
        self.assertEqual(self.ctrl.current_profile, PerformanceProfile.BALANCED)
        status = self.ctrl.get_status_dict()
        self.assertEqual(status["current_profile"], "BALANCED")
        self.assertEqual(status["mode"], "auto")
        self.assertEqual(status["polling_interval_ms"], 3000)
        self.assertEqual(status["orb_particles"], 32)
        self.assertEqual(status["orb_fps_limit"], 60)

    def test_02_auto_downshift_to_lite_under_sustained_load_or_memory(self):
        """Yüksek CPU, RAM % veya düşük boş RAM (<800 MB) durumunda ardışık örneklerle LITE'a geçiş."""
        # 1. örnek (smoothing devrede)
        prof1 = self.ctrl.update_with_telemetry(cpu_percent=88.0, ram_percent=60.0, ram_available_mb=600.0)
        self.assertEqual(prof1, PerformanceProfile.BALANCED)
        
        # 2. ardışık yüksek örnek -> LITE'a geçmeli
        prof2 = self.ctrl.update_with_telemetry(cpu_percent=85.0, ram_percent=60.0, ram_available_mb=600.0)
        self.assertEqual(prof2, PerformanceProfile.LITE)
        self.assertEqual(self.ctrl.get_status_dict()["polling_interval_ms"], 6000)
        self.assertEqual(self.ctrl.get_status_dict()["orb_particles"], 16)

    def test_03_hysteresis_anti_flapping_guard(self):
        """Cooldown süresi dolmadan profilin anlık dalgalanmayla değişmediğini doğrula."""
        # LITE'a düşür
        self.ctrl.update_with_telemetry(cpu_percent=90.0, ram_percent=90.0, ram_available_mb=400.0)
        self.ctrl.update_with_telemetry(cpu_percent=90.0, ram_percent=90.0, ram_available_mb=400.0)
        self.assertEqual(self.ctrl.current_profile, PerformanceProfile.LITE)

        # Hemen ardından düşük yük gelse bile cooldown koruması nedeniyle değişmemeli
        prof = self.ctrl.update_with_telemetry(cpu_percent=20.0, ram_percent=30.0, ram_available_mb=3000.0)
        self.assertEqual(prof, PerformanceProfile.LITE)

    def test_04_auto_recovery_when_resources_normalize(self):
        """Sistem yükü normale döndüğünde ve cooldown dolduğunda BALANCED baseline'ına geri dönüş."""
        # LITE'a düşür
        self.ctrl.update_with_telemetry(cpu_percent=90.0, ram_percent=90.0, ram_available_mb=400.0)
        self.ctrl.update_with_telemetry(cpu_percent=90.0, ram_percent=90.0, ram_available_mb=400.0)
        self.assertEqual(self.ctrl.current_profile, PerformanceProfile.LITE)

        # Cooldown bekle
        time.sleep(0.6)

        # 3 ardışık normal yük örneği (CPU <= 65%, RAM <= 75%, Avail >= 1200 MB)
        self.ctrl.update_with_telemetry(cpu_percent=55.0, ram_percent=70.0, ram_available_mb=1500.0)
        self.ctrl.update_with_telemetry(cpu_percent=55.0, ram_percent=70.0, ram_available_mb=1500.0)
        final_prof = self.ctrl.update_with_telemetry(cpu_percent=55.0, ram_percent=70.0, ram_available_mb=1500.0)
        self.assertEqual(final_prof, PerformanceProfile.BALANCED)

    def test_05_dynamic_headroom_boost_to_ultra(self):
        """Yeterli donanım boşluğu tespit edildiğinde (CPU <= 45%, Boş RAM >= 2500 MB) ULTRA'ya yükseltme."""
        self.ctrl.current_profile = PerformanceProfile.BALANCED
        time.sleep(0.6)
        
        # 3 ardışık yüksek boşluk örneği
        self.ctrl.update_with_telemetry(cpu_percent=25.0, ram_percent=45.0, ram_available_mb=3200.0)
        self.ctrl.update_with_telemetry(cpu_percent=25.0, ram_percent=45.0, ram_available_mb=3200.0)
        final_prof = self.ctrl.update_with_telemetry(cpu_percent=25.0, ram_percent=45.0, ram_available_mb=3200.0)
        self.assertEqual(final_prof, PerformanceProfile.ULTRA)
        self.assertEqual(self.ctrl.get_status_dict()["orb_particles"], 64)

    def test_06_gaming_mode_forces_lite_footprint(self):
        """Oyun modu aktif olduğunda kaynakların oyuna kalması için profilin LITE yapılması."""
        prof = self.ctrl.update_with_telemetry(cpu_percent=20.0, ram_percent=40.0, is_gaming=True)
        self.assertEqual(prof, PerformanceProfile.LITE)

    def test_07_manual_profile_override_and_reset(self):
        """Kullanıcı manuel olarak profil seçtiğinde otomatik telemetrinin bunu ezemediğini doğrula."""
        self.ctrl.update_with_telemetry(cpu_percent=10.0, ram_percent=20.0, manual_pref="ULTRA")
        self.assertEqual(self.ctrl.current_profile, PerformanceProfile.ULTRA)
        self.assertEqual(self.ctrl.get_status_dict()["mode"], "manual")
        self.assertEqual(self.ctrl.get_status_dict()["polling_interval_ms"], 1500)

        # Yüksek yük gelse bile manuel override korunur
        prof_under_load = self.ctrl.update_with_telemetry(cpu_percent=95.0, ram_percent=95.0, ram_available_mb=300.0)
        self.assertEqual(prof_under_load, PerformanceProfile.ULTRA)

        # Manuel override kaldırıldığında (AUTO) normale döner
        self.ctrl.update_with_telemetry(cpu_percent=30.0, ram_percent=30.0, manual_pref="AUTO")
        self.assertIsNone(self.ctrl.manual_override)


class TestAdaptivePerformanceHTTP(AioHTTPTestCase):
    async def get_application(self):
        app = web.Application()
        app.router.add_get("/api/system_metrics", handle_system_metrics)
        app.router.add_get("/api/performance/profile", handle_get_performance_profile)
        app.router.add_post("/api/performance/profile", handle_set_performance_profile)
        return app

    async def test_07_http_api_endpoints(self):
        """HTTP API üzerinden profil sorgulama ve güncelleme doğrulaması."""
        # 1. GET /api/performance/profile
        resp = await self.client.get("/api/performance/profile")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("performance", data)
        self.assertIn("current_profile", data["performance"])

        # 2. POST /api/performance/profile (Manuel Seçim: lite)
        resp_post = await self.client.post("/api/performance/profile", json={"profile": "lite"})
        self.assertEqual(resp_post.status, 200)
        post_data = await resp_post.json()
        self.assertEqual(post_data["status"], "ok")
        self.assertEqual(post_data["performance"]["current_profile"], "LITE")
        self.assertEqual(post_data["performance"]["mode"], "manual")

        # 3. GET /api/system_metrics içinde profil ve polling aralığının görünmesi
        resp_metrics = await self.client.get("/api/system_metrics")
        self.assertEqual(resp_metrics.status, 200)
        metrics_data = await resp_metrics.json()
        self.assertIn("performance_profile", metrics_data)
        self.assertIn("polling_interval_ms", metrics_data)
        self.assertEqual(metrics_data["performance_profile"], "LITE")

        # 4. Profil AUTO'ya geri alınsın
        await self.client.post("/api/performance/profile", json={"profile": "auto"})


if __name__ == "__main__":
    unittest.main()

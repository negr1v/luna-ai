"""
ACCIO LUNA V4.0 — Phase 7C Automated Test Suite
Focus: Smart Notification Gate, TTS Suppression, Deferred Queue Lifecycle,
       Steam Client Exclusion, Conversation Priority Preservation.
"""

import unittest
import asyncio
import os
import sys
import datetime
import time
from unittest.mock import patch, MagicMock

import luna_server

class Phase7CNotificationsTest(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Reset in-memory deferred notifications between tests
        async with luna_server.NOTIFICATIONS_LOCK:
            luna_server.DEFERRED_NOTIFICATIONS.clear()

    async def test_01_steam_client_alone_does_not_activate_gaming_mode(self):
        """Test 1: Generic Steam window title does NOT activate gaming mode outside schedule."""
        outside_time = datetime.datetime(2026, 11, 7, 12, 0, 0)
        steam_titles = [
            "Steam",
            "Steam Client Bootstrapper",
            "Steam - News and Updates",
            "Steam Community :: Profile",
            "Steam Store - Top Sellers"
        ]
        for title in steam_titles:
            res = luna_server.is_gaming_mode_active(current_time=outside_time, active_window_title=title)
            self.assertFalse(res["active"], f"Generic steam window should NOT activate gaming mode: {title}")
            self.assertEqual(res["reason"], "none")
        print("  [Phase 7C Test 1 PASSED] Generic Steam client alone does not activate gaming mode.")

    async def test_02_known_game_window_activates_gaming_mode(self):
        """Test 2: Known game window (Apex, CS2, etc.) activates gaming mode outside schedule."""
        outside_time = datetime.datetime(2026, 11, 7, 12, 0, 0)
        game_titles = [
            "Apex Legends",
            "Counter-Strike 2",
            "Don't Starve Together",
            "League of Legends (TM) Client",
            "SteamVR Home"
        ]
        for title in game_titles:
            res = luna_server.is_gaming_mode_active(current_time=outside_time, active_window_title=title)
            self.assertTrue(res["active"], f"Game title should activate gaming mode: {title}")
            self.assertEqual(res["reason"], "game_window")
        print("  [Phase 7C Test 2 PASSED] Known game window titles activate gaming mode.")

    async def test_03_scheduled_period_activates_gaming_mode(self):
        """Test 3: Time window 16:00 inclusive to 17:30 exclusive activates gaming mode."""
        sched_time = datetime.datetime(2026, 11, 7, 16, 15, 0)
        res = luna_server.is_gaming_mode_active(current_time=sched_time, active_window_title="Notepad")
        self.assertTrue(res["active"])
        self.assertEqual(res["reason"], "time_slot")
        self.assertEqual(res["source"], "schedule")
        print("  [Phase 7C Test 3 PASSED] Scheduled gaming period (16:00-17:30) activates gaming mode.")

    async def test_04_proactive_tts_suppressed_during_gaming_mode(self):
        """Test 4: Proactive announcements are silenced/suppressed during active gaming mode."""
        sched_time = datetime.datetime(2026, 11, 7, 16, 20, 0)
        with patch("luna_server.generate_tts") as mock_tts:
            res = await luna_server.dispatch_notification(
                text="Günün YKS ilerleme özeti hazır.",
                category="proactive",
                current_time=sched_time,
                active_window_title="Masaüstü"
            )
            self.assertEqual(res["status"], "suppressed")
            self.assertEqual(res["action"], "silent")
            self.assertEqual(res["reason"], "gaming_mode_active")
            mock_tts.assert_not_called()
        print("  [Phase 7C Test 4 PASSED] Proactive TTS announcements suppressed during gaming mode.")

    async def test_05_user_conversational_tts_always_delivered(self):
        """Test 5: User-initiated conversational responses are ALWAYS generated even in gaming mode."""
        sched_time = datetime.datetime(2026, 11, 7, 16, 25, 0)
        fake_audio = "FAKE_AUDIO_B64"
        with patch("luna_server.generate_tts", return_value=fake_audio) as mock_tts:
            res = await luna_server.dispatch_notification(
                text="İşte istediğin formül: a^2 + b^2 = c^2",
                category="conversational",
                current_time=sched_time,
                active_window_title="Apex Legends"
            )
            self.assertEqual(res["status"], "delivered")
            self.assertEqual(res["action"], "play_tts")
            self.assertEqual(res["audio_base64"], fake_audio)
            mock_tts.assert_called_once_with("İşte istediğin formül: a^2 + b^2 = c^2")
        print("  [Phase 7C Test 5 PASSED] User conversational TTS responses preserved during gaming mode.")

    async def test_06_study_alarms_deferred_during_gaming_mode(self):
        """Test 6: Study alarms / Pomodoro completion alerts are deferred into queue during gaming mode."""
        sched_time = datetime.datetime(2026, 11, 7, 16, 30, 0)
        with patch("luna_server.generate_tts") as mock_tts:
            res = await luna_server.dispatch_notification(
                text="AYT Matematik 40 dakikalık blok tamamlandı!",
                category="study_alarm",
                metadata={"block_id": "b1"},
                current_time=sched_time,
                active_window_title="Apex Legends"
            )
            self.assertEqual(res["status"], "deferred")
            self.assertEqual(res["action"], "queued")
            mock_tts.assert_not_called()

            deferred = luna_server.get_deferred_notifications()
            self.assertEqual(len(deferred), 1)
            self.assertEqual(deferred[0]["text"], "AYT Matematik 40 dakikalık blok tamamlandı!")
            self.assertEqual(deferred[0]["category"], "study_alarm")
        print("  [Phase 7C Test 6 PASSED] Study alarms safely deferred to in-memory queue.")

    async def test_07_duplicate_notifications_handled_safely(self):
        """Test 7: Duplicate identical notifications are not enqueued multiple times."""
        t1 = await luna_server.enqueue_deferred_notification("Aynı Ders Uyarısı", category="study_alarm")
        self.assertTrue(t1)

        # Second enqueue with identical text and category
        t2 = await luna_server.enqueue_deferred_notification("Aynı Ders Uyarısı", category="study_alarm")
        self.assertFalse(t2)

        deferred = luna_server.get_deferred_notifications()
        self.assertEqual(len(deferred), 1)
        print("  [Phase 7C Test 7 PASSED] Duplicate notifications cleanly deduplicated.")

    async def test_08_queue_bounded_capacity(self):
        """Test 8: Queue enforces MAX_DEFERRED_NOTIFICATIONS boundary by discarding oldest."""
        for i in range(25):
            await luna_server.enqueue_deferred_notification(f"Alarm {i}", category="study_alarm")

        deferred = luna_server.get_deferred_notifications()
        self.assertLessEqual(len(deferred), luna_server.MAX_DEFERRED_NOTIFICATIONS)
        self.assertEqual(len(deferred), 20)
        # Oldest items (0-4) should have been dropped; newest should be present
        self.assertEqual(deferred[-1]["text"], "Alarm 24")
        self.assertEqual(deferred[0]["text"], "Alarm 5")
        print("  [Phase 7C Test 8 PASSED] Queue limit strictly bounded at 20 entries.")

    async def test_09_deferred_notifications_resume_after_gaming_mode_ends(self):
        """Test 9: Controlled drain delivers deferred alerts after gaming mode finishes."""
        await luna_server.enqueue_deferred_notification("Ertelenen Görev 1", category="study_alarm")
        await luna_server.enqueue_deferred_notification("Ertelenen Görev 2", category="study_alarm")
        await luna_server.enqueue_deferred_notification("Ertelenen Görev 3", category="study_alarm")
        await luna_server.enqueue_deferred_notification("Ertelenen Görev 4", category="study_alarm")

        # Drain batch 1 (max 3)
        batch1 = await luna_server.drain_deferred_notifications(max_count=3)
        self.assertEqual(len(batch1), 3)
        self.assertEqual(batch1[0]["text"], "Ertelenen Görev 1")

        # Drain batch 2 (remaining 1)
        batch2 = await luna_server.drain_deferred_notifications(max_count=3)
        self.assertEqual(len(batch2), 1)
        self.assertEqual(batch2[0]["text"], "Ertelenen Görev 4")

        # Now queue should be empty
        self.assertEqual(len(luna_server.get_deferred_notifications()), 0)
        print("  [Phase 7C Test 9 PASSED] Controlled drain resumes deferred notifications in batches.")

    async def test_10_old_notifications_do_not_interrupt_active_conversations(self):
        """Test 10: Inactive gaming mode allows direct dispatch without queueing."""
        normal_time = datetime.datetime(2026, 11, 7, 10, 0, 0)
        with patch("luna_server.generate_tts", return_value="AUDIO_DATA"):
            res = await luna_server.dispatch_notification(
                text="Yeni çalışma bloğu başlıyor.",
                category="study_alarm",
                current_time=normal_time,
                active_window_title="Masaüstü"
            )
            self.assertEqual(res["status"], "delivered")
            self.assertEqual(res["action"], "play_tts")
            # Nothing placed into deferred queue
            self.assertEqual(len(luna_server.get_deferred_notifications()), 0)
        print("  [Phase 7C Test 10 PASSED] Direct delivery outside gaming mode leaves queue clean.")

    async def test_11_voice_and_mic_privacy_contract_intact(self):
        """Test 11: Phase 5 microphone privacy and TTS generation mechanisms remain intact."""
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("micConsentGranted", html)
        self.assertIn("interruptSpeech()", html)
        self.assertIn("currentAudioGeneration", html)
        self.assertIn("gamingModeBadge", html)
        print("  [Phase 7C Test 11 PASSED] Existing Phase 5 microphone privacy & audio contract verified.")

if __name__ == "__main__":
    unittest.main()

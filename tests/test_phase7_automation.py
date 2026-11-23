"""
ACCIO LUNA V4.0 — Phase 7B Automated Test Suite
Focus: Safe Automation Foundation, Process Sandboxing, Temporary File Lifecycle,
       Gaming Mode Detection, Protected Path Boundary Policy.
"""

import unittest
import os
import sys
import tempfile
import datetime
from unittest.mock import patch, MagicMock

import luna_server

class Phase7AutomationTest(unittest.TestCase):

    def test_01_open_app_approved_targets_popen_argument_list(self):
        """Test 1: Approved executable targets (calculator, notepad) use argument lists and shell=False."""
        with patch("subprocess.Popen") as mock_popen:
            res_calc = luna_server.execute_desktop_tool("open_app", {"target": "calculator"})
            self.assertEqual(res_calc["status"], "ok")
            mock_popen.assert_called_with(["calc.exe"], shell=False)

            mock_popen.reset_mock()
            res_note = luna_server.execute_desktop_tool("open_app", {"target": "notepad"})
            self.assertEqual(res_note["status"], "ok")
            mock_popen.assert_called_with(["notepad.exe"], shell=False)
        print("  [Phase 7B Test 1 PASSED] Approved executables launch with explicit arg-list and shell=False.")

    def test_02_open_app_approved_browser_targets(self):
        """Test 2: Approved HTML targets (kokpit, yks_takip) use webbrowser.open without shell execution."""
        with patch("webbrowser.open") as mock_wb:
            res_kokpit = luna_server.execute_desktop_tool("open_app", {"target": "kokpit"})
            self.assertEqual(res_kokpit["status"], "ok")
            self.assertTrue(mock_wb.called)
            called_url = mock_wb.call_args[0][0]
            self.assertTrue(called_url.startswith("file:///"))
            self.assertIn("LUNA-AI-KOKPIT.html", called_url)

            mock_wb.reset_mock()
            res_yks = luna_server.execute_desktop_tool("open_app", {"target": "yks_takip"})
            self.assertEqual(res_yks["status"], "ok")
            self.assertTrue(mock_wb.called)
            called_url2 = mock_wb.call_args[0][0]
            self.assertTrue(called_url2.startswith("file:///"))
            self.assertIn("yks-test-takip.html", called_url2)
        print("  [Phase 7B Test 2 PASSED] Approved web targets launch via webbrowser.open safely.")

    def test_03_open_app_unapproved_targets_and_injections_rejected(self):
        """Test 3: Arbitrary targets, shell commands, and path injections are strictly rejected."""
        malicious_inputs = [
            {"target": "cmd.exe"},
            {"target": "powershell.exe"},
            {"target": "calc.exe; rm -rf /"},
            {"target": "notepad & whoami"},
            {"target": "../../../Windows/System32/cmd.exe"},
            {"target": "unknown_app"},
            {"target": ""},
            {}
        ]
        with patch("subprocess.Popen") as mock_popen, patch("webbrowser.open") as mock_wb:
            for bad_args in malicious_inputs:
                res = luna_server.execute_desktop_tool("open_app", bad_args)
                self.assertEqual(res["status"], "error")
                self.assertIn("Yetkisiz veya geçersiz", res["message"])
                self.assertFalse(mock_popen.called)
                self.assertFalse(mock_wb.called)
        print("  [Phase 7B Test 3 PASSED] Unapproved targets and command injections rejected.")

    def test_04_screenshot_temp_file_cleanup_on_success(self):
        """Test 4: Screenshot temporary files and directory are cleaned up after successful capture."""
        created_dirs = []

        real_mkdtemp = tempfile.mkdtemp
        def spy_mkdtemp(*args, **kwargs):
            d = real_mkdtemp(*args, **kwargs)
            created_dirs.append(d)
            return d

        with patch("tempfile.mkdtemp", side_effect=spy_mkdtemp), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            res = luna_server.execute_desktop_tool("capture_screen_analysis", {})
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["action"], "screen_captured")

            # Verify PowerShell was invoked with shell=False
            self.assertTrue(mock_run.called)
            call_kwargs = mock_run.call_args[1]
            self.assertFalse(call_kwargs.get("shell", True), "Subprocess must use shell=False")

            # Verify temp directory was removed
            self.assertEqual(len(created_dirs), 1)
            temp_dir = created_dirs[0]
            self.assertFalse(os.path.exists(temp_dir), "Temporary directory must be cleaned up on success")
        print("  [Phase 7B Test 4 PASSED] Temporary screenshot directory cleaned up on success.")

    def test_05_screenshot_temp_file_cleanup_on_failure(self):
        """Test 5: Screenshot temporary files are guaranteed cleaned up even on exception/failure."""
        created_dirs = []

        real_mkdtemp = tempfile.mkdtemp
        def spy_mkdtemp(*args, **kwargs):
            d = real_mkdtemp(*args, **kwargs)
            created_dirs.append(d)
            return d

        with patch("tempfile.mkdtemp", side_effect=spy_mkdtemp), \
             patch("subprocess.run", side_effect=RuntimeError("Simulated PowerShell failure")):
            with self.assertRaises(RuntimeError):
                luna_server.execute_desktop_tool("capture_screen_analysis", {})

            self.assertEqual(len(created_dirs), 1)
            temp_dir = created_dirs[0]
            self.assertFalse(os.path.exists(temp_dir), "Temporary directory must be cleaned up even on failure")
        print("  [Phase 7B Test 5 PASSED] Temporary screenshot directory cleaned up on failure.")

    def test_06_gaming_mode_time_window_boundary_detection(self):
        """Test 6: Gaming mode activates between 16:00 and 17:30, deactivates at 17:30."""
        # 15:59:59 -> Inactive
        t_before = datetime.datetime(2026, 11, 7, 15, 59, 59)
        res_before = luna_server.is_gaming_mode_active(current_time=t_before, active_window_title="Desktop")
        self.assertFalse(res_before["active"])
        self.assertEqual(res_before["reason"], "none")

        # 16:00:00 -> Active (Boundary Start)
        t_start = datetime.datetime(2026, 11, 7, 16, 0, 0)
        res_start = luna_server.is_gaming_mode_active(current_time=t_start, active_window_title="Desktop")
        self.assertTrue(res_start["active"])
        self.assertEqual(res_start["reason"], "time_slot")
        self.assertEqual(res_start["source"], "schedule")

        # 16:45:00 -> Active (Middle)
        t_mid = datetime.datetime(2026, 11, 7, 16, 45, 0)
        res_mid = luna_server.is_gaming_mode_active(current_time=t_mid, active_window_title="Desktop")
        self.assertTrue(res_mid["active"])
        self.assertEqual(res_mid["reason"], "time_slot")

        # 17:29:59 -> Active (Boundary End minus 1s)
        t_end_minus = datetime.datetime(2026, 11, 7, 17, 29, 59)
        res_end_minus = luna_server.is_gaming_mode_active(current_time=t_end_minus, active_window_title="Desktop")
        self.assertTrue(res_end_minus["active"])

        # 17:30:00 -> Inactive (Boundary End exclusive)
        t_end = datetime.datetime(2026, 11, 7, 17, 30, 0)
        res_end = luna_server.is_gaming_mode_active(current_time=t_end, active_window_title="Desktop")
        self.assertFalse(res_end["active"])
        self.assertEqual(res_end["reason"], "none")
        print("  [Phase 7B Test 6 PASSED] Gaming mode schedule time boundaries verified (16:00-17:30).")

    def test_07_gaming_mode_game_window_title_detection(self):
        """Test 7: Known game titles activate gaming mode regardless of time of day."""
        t_outside = datetime.datetime(2026, 11, 7, 12, 0, 0)

        known_titles = [
            "Apex Legends",
            "Apex Legends - Season 23",
            "r5apex.exe - Vulkan",
            "Don't Starve Together",
            "League of Legends (TM) Client",
            "Counter-Strike 2",
            "Steam VR Home"
        ]
        for title in known_titles:
            res = luna_server.is_gaming_mode_active(current_time=t_outside, active_window_title=title)
            self.assertTrue(res["active"], f"Failed to activate gaming mode for: {title}")
            self.assertEqual(res["reason"], "game_window")
            self.assertEqual(res["source"], "active_window")

        unrelated_titles = [
            "Visual Studio Code",
            "Google Chrome - YKS Matematik 3D",
            "Discord - Genel",
            "Spotify Free",
            "Masaüstü",
            "Notepad - Formüller"
        ]
        for title in unrelated_titles:
            res = luna_server.is_gaming_mode_active(current_time=t_outside, active_window_title=title)
            self.assertFalse(res["active"], f"Falsely activated gaming mode for: {title}")
            self.assertEqual(res["reason"], "none")
        print("  [Phase 7B Test 7 PASSED] Allowlisted game window titles detected accurately.")

    def test_08_protected_path_policy_enforcement(self):
        """Test 8: Protected path helper accurately matches steamapps/downloading/12210 and descendants."""
        blocked_paths = [
            r"C:\Program Files (x86)\Steam\steamapps\downloading\12210",
            r"D:\SteamLibrary\steamapps\downloading\12210\GTAIV.exe",
            r"E:\Games\steamapps\downloading\12210\pc\data\cdimages\vehicles.img",
            r"steamapps/downloading/12210",
            r"steamapps/downloading/12210/nested/subfolder/file.bin",
            r"C:\Steam\steamapps\common\..\downloading\12210",
            r"C:\steamapps\downloading\12210\sub\..\file.txt"
        ]
        for p in blocked_paths:
            self.assertTrue(luna_server.is_protected_path(p), f"Should be protected: {p}")

        allowed_paths = [
            r"C:\Program Files (x86)\Steam\steamapps\downloading\12210_backup",
            r"C:\Program Files (x86)\Steam\steamapps\downloading\12210.old",
            r"C:\Program Files (x86)\Steam\steamapps\common\GTAIV",
            r"C:\Users\negr1\Projeler\LUNA-AI\luna_tasks.json",
            r"C:\Users\negr1\Desktop\12210",
            r"C:\Users\negr1\Downloads\12210.zip",
            "",
            None
        ]
        for p in allowed_paths:
            self.assertFalse(luna_server.is_protected_path(p), f"Should NOT be protected: {p}")
        print("  [Phase 7B Test 8 PASSED] Protected path boundary helper matches strictly without false positives.")

    def test_09_media_control_allowlist_preservation(self):
        """Test 9: Media control accepts only play_pause, volume_up, volume_down, mute."""
        valid_actions = ["play_pause", "volume_up", "volume_down", "mute"]
        with patch("ctypes.windll.user32.keybd_event"):
            for act in valid_actions:
                res = luna_server.execute_desktop_tool("media_control", {"action": act})
                self.assertEqual(res["status"], "ok")

        invalid_actions = ["skip", "stop", "next", "eject", "reboot", "", None]
        for act in invalid_actions:
            res = luna_server.execute_desktop_tool("media_control", {"action": act})
            # Does not perform keybd_event and reports error or None
            self.assertNotEqual(res.get("status"), "ok")
        print("  [Phase 7B Test 9 PASSED] Media control 4-action allowlist strictly enforced.")

    def test_10_ambient_mood_validation_preservation(self):
        """Test 10: set_ambient_mood preserves valid moods and defaults safely."""
        valid_moods = ["angry_red", "focus_purple", "calm_cyan", "happy_emerald"]
        for m in valid_moods:
            res = luna_server.execute_desktop_tool("set_ambient_mood", {"mood": m})
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["mood"], m)

        # Default fallback on missing
        res_empty = luna_server.execute_desktop_tool("set_ambient_mood", {})
        self.assertEqual(res_empty["status"], "ok")
        self.assertEqual(res_empty["mood"], "calm_cyan")
        print("  [Phase 7B Test 10 PASSED] Ambient mood parameter handling verified.")

    def test_11_zero_shell_execution_or_process_kill_tools(self):
        """Test 11: Verification that no arbitrary shell or process termination tools exist in TOOLS."""
        tool_names = [t["function"]["name"] for t in luna_server.TOOLS if "function" in t]
        forbidden_keywords = ["bash", "shell", "cmd", "exec", "eval", "kill", "terminate", "taskkill"]
        for name in tool_names:
            for kw in forbidden_keywords:
                self.assertNotIn(kw, name.lower(), f"Forbidden tool capability detected: {name}")
        print("  [Phase 7B Test 11 PASSED] Zero arbitrary shell or process termination tools confirmed.")

if __name__ == "__main__":
    unittest.main()

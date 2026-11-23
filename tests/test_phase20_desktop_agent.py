"""Focused, fully mocked coverage for Desktop Agent V1 (71010).

No test calls Windows UI Automation or opens a real user application.
"""

import copy
import os
import tempfile
import unittest

from luna_desktop_agent import DesktopAgent, DesktopAgentError


class FakeDesktopBackend:
    def __init__(self):
        self.window = {
            "status": "ok", "hwnd": 101, "process_id": 501, "process_name": "notepad.exe",
            "title": "Harmless draft - Notepad", "is_allowed": True,
        }
        self.foreground_hwnd = 101
        self.elements = [
            {"control_type": "Edit", "name": "Document", "automation_id": "Editor", "is_enabled": True, "is_password": False},
            {"control_type": "Button", "name": "Safe action", "automation_id": "SafeAction", "is_enabled": True, "is_password": False},
        ]
        self.inspect_calls = 0
        self.execute_calls = 0
        self.value_matches = True
        self.next_execution = {"status": "ok", "pattern": "InvokePattern"}

    def list_windows(self):
        return [copy.deepcopy(self.window)]

    def get_window_info(self, _hwnd):
        return copy.deepcopy(self.window)

    def get_foreground_window_info(self):
        data = copy.deepcopy(self.window)
        data["hwnd"] = self.foreground_hwnd
        return data

    def inspect_window(self, _hwnd):
        self.inspect_calls += 1
        return copy.deepcopy(self.elements)

    def focus_window(self, hwnd):
        self.foreground_hwnd = hwnd
        return True

    def execute_element(self, _target, _element, action, _text):
        self.execute_calls += 1
        result = copy.deepcopy(self.next_execution)
        result["status"] = result.get("status", "ok")
        if action == "set_text":
            result["value_matches"] = self.value_matches
        return result


class DesktopAgentV1Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.backend = FakeDesktopBackend()
        self.agent = DesktopAgent(data_dir=self.temp_dir.name, backend=self.backend)

    def tearDown(self):
        self.temp_dir.cleanup()

    async def _listed_and_inspected(self):
        listed = await self.agent.list_windows()
        self.assertEqual(len(listed["windows"]), 1)
        window_id = listed["windows"][0]["window_id"]
        inspected = await self.agent.inspect_window({"window_id": window_id})
        self.assertEqual(inspected["status"], "ok")
        return window_id, inspected

    @staticmethod
    def _element_id(inspected, control_type):
        return next(item["element_id"] for item in inspected["elements"] if item["control_type"] == control_type and item["element_id"])

    async def _preview_and_approval(self, action="set_text", text="güvenli deneme"):
        window_id, inspected = await self._listed_and_inspected()
        payload = {"window_id": window_id, "action": action}
        if action != "focus_window":
            payload["element_id"] = self._element_id(inspected, "Edit" if action == "set_text" else "Button")
        if action == "set_text":
            payload["text"] = text
        preview = (await self.agent.create_action_preview(payload))["preview"]
        approval = await self.agent.begin_action_approval(preview["action_id"])
        return preview, approval["approval"]

    async def test_filters_windows_and_returns_minimal_metadata(self):
        self.backend.window["process_name"] = "chrome.exe"
        self.assertEqual((await self.agent.list_windows())["windows"], [])
        self.backend.window["process_name"] = "notepad.exe"
        listed = await self.agent.list_windows()
        self.assertEqual(set(listed["windows"][0]), {"window_id", "process_name", "title"})
        self.assertNotIn("hwnd", listed["windows"][0])

    async def test_ambiguous_window_never_auto_selects_and_ambiguous_element_is_unusable(self):
        duplicate = copy.deepcopy(self.backend.window)
        duplicate["hwnd"] = 102
        self.backend.list_windows = lambda: [copy.deepcopy(self.backend.window), duplicate]
        listed = await self.agent.list_windows()
        self.assertEqual(len(listed["windows"]), 2)
        with self.assertRaises(DesktopAgentError):
            await self.agent.inspect_window({"window_id": "not-a-window-id"})

        self.backend.list_windows = lambda: [copy.deepcopy(self.backend.window)]
        self.backend.elements = [
            {"control_type": "Button", "name": "Same", "automation_id": "", "is_enabled": True, "is_password": False},
            {"control_type": "Button", "name": "Same", "automation_id": "", "is_enabled": True, "is_password": False},
        ]
        _, inspected = await self._listed_and_inspected()
        self.assertTrue(all(item["ambiguous"] and not item["element_id"] for item in inspected["elements"]))

    async def test_schema_validation_happens_before_uia(self):
        listed = await self.agent.list_windows()
        window_id = listed["windows"][0]["window_id"]
        with self.assertRaises(DesktopAgentError):
            await self.agent.inspect_window({"window_id": window_id, "x": 1})
        self.assertEqual(self.backend.inspect_calls, 0)
        with self.assertRaises(DesktopAgentError):
            await self.agent.create_action_preview({"window_id": window_id, "action": "click_element", "x": 30})
        self.assertEqual(self.backend.inspect_calls, 0)

    async def test_approval_is_bound_and_single_use(self):
        preview, approval = await self._preview_and_approval("set_text", "tam değer")
        result = await self.agent.approve_action(preview["action_id"], approval["approval_id"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["preview"]["state"], "SUCCEEDED")
        self.assertEqual(result["preview"]["result"]["verification"]["status"], "verified")
        with self.assertRaises(DesktopAgentError):
            await self.agent.approve_action(preview["action_id"], approval["approval_id"])
        self.assertEqual(self.backend.execute_calls, 1)

    async def test_focus_click_and_limited_state_use_exact_registered_tools(self):
        window_id, inspected = await self._listed_and_inspected()
        for name in (
            "desktop.list_windows", "desktop.inspect_window", "desktop.focus_window",
            "desktop.click_element", "desktop.set_text", "desktop.read_element_state",
        ):
            self.assertIsNotNone(self.agent.engine.registry.get(name))
        state = await self.agent.read_element_state({"window_id": window_id, "element_id": self._element_id(inspected, "Edit")})
        self.assertTrue(state["present"])

        focus_preview = (await self.agent.create_action_preview({"window_id": window_id, "action": "focus_window"}))["preview"]
        focus_approval = await self.agent.begin_action_approval(focus_preview["action_id"])
        self.backend.foreground_hwnd = 999
        self.assertEqual((await self.agent.approve_action(focus_preview["action_id"], focus_approval["approval"]["approval_id"]))["status"], "ok")

        click_preview = (await self.agent.create_action_preview({
            "window_id": window_id, "action": "click_element", "element_id": self._element_id(inspected, "Button"),
        }))["preview"]
        click_approval = await self.agent.begin_action_approval(click_preview["action_id"])
        self.assertEqual((await self.agent.approve_action(click_preview["action_id"], click_approval["approval"]["approval_id"]))["status"], "ok")
        self.assertEqual(self.backend.execute_calls, 1)

    async def test_changed_bound_values_invalidate_before_execution(self):
        mutations = {
            "title": lambda: self.backend.window.update(title="Changed title"),
            "handle": lambda: self.backend.window.update(hwnd=202),
            "process": lambda: self.backend.window.update(process_name="mspaint.exe"),
            "element": lambda: self.backend.elements.__setitem__(0, {"control_type": "Edit", "name": "Changed", "automation_id": "Editor", "is_enabled": True, "is_password": False}),
            "value": lambda: setattr(next(iter(self.agent.actions.values())), "text", "different value"),
        }
        for index, (name, mutate) in enumerate(mutations.items()):
            with self.subTest(name=name):
                if index:
                    self.tearDown()
                    self.setUp()
                preview, approval = await self._preview_and_approval()
                mutate()
                result = await self.agent.approve_action(preview["action_id"], approval["approval_id"])
                self.assertEqual(result["status"], "error")
                self.assertEqual(self.backend.execute_calls, 0)

    async def test_sensitive_and_unsafe_controls_are_refused(self):
        window_id, _ = await self._listed_and_inspected()
        self.backend.elements = [{"control_type": "Edit", "name": "Password", "automation_id": "PasswordBox", "is_enabled": True, "is_password": True}]
        inspected = await self.agent.inspect_window({"window_id": window_id})
        self.assertFalse(inspected["elements"][0]["safe_for_action"])
        self.assertEqual(inspected["elements"][0]["element_id"], "")
        self.backend.elements = [{"control_type": "Button", "name": "Send", "automation_id": "Send", "is_enabled": True, "is_password": False}]
        inspected = await self.agent.inspect_window({"window_id": window_id})
        self.assertIn("kapsamında değildir", inspected["elements"][0]["safety_reason"])

    async def test_text_must_be_exactly_previewed_and_verification_failure_is_reported(self):
        preview, approval = await self._preview_and_approval("set_text", "ilk değer")
        self.agent.actions[preview["action_id"]].text = "başka değer"
        result = await self.agent.approve_action(preview["action_id"], approval["approval_id"])
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.backend.execute_calls, 0)

        self.tearDown()
        self.setUp()
        self.backend.value_matches = False
        preview, approval = await self._preview_and_approval("set_text", "doğrulanacak")
        result = await self.agent.approve_action(preview["action_id"], approval["approval_id"])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["preview"]["state"], "VERIFICATION_FAILED")
        self.assertEqual(self.backend.execute_calls, 1)

    async def test_legacy_computer_use_is_not_used_as_a_desktop_v1_fallback(self):
        with open(os.path.join(os.path.dirname(__file__), "luna_desktop_agent.py"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("SendMessageW", source)
        self.assertNotIn("send_safe_text", source)
        self.assertIn("luna_desktop_uia_action.ps1", source)


if __name__ == "__main__":
    unittest.main()

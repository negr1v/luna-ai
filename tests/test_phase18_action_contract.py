"""Focused Phase 18 checks for action contracts, approval binding, and legacy secret migration."""

import asyncio
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

import luna_server
from luna_agent_engine import AgentController, AgentTask, PermissionLevel, TaskState, TaskStep, ToolDefinition
from luna_computer_use import UIAutomationActionController


class ActionContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="luna_phase18_agent_")
        self.controller = AgentController(self.temp_dir, data_dir=self.temp_dir)
        self.calls = []

        async def echo_handler(arguments):
            self.calls.append(dict(arguments))
            return {"status": "ok"}

        self.controller.registry.register(ToolDefinition(
            name="contract_echo",
            description="Test-only schema tool",
            permission_level=PermissionLevel.READ_ONLY,
            timeout_sec=1.0,
            handler=echo_handler,
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "maxLength": 8}},
                "required": ["text"],
                "additionalProperties": False,
            },
        ))
        self.controller.registry.register(ToolDefinition(
            name="approval_action",
            description="Test-only approved action",
            permission_level=PermissionLevel.USER_APPROVAL,
            timeout_sec=1.0,
            handler=echo_handler,
            input_schema={
                "type": "object",
                "properties": {
                    "value": {"type": "string", "maxLength": 32},
                    "path": {"type": "string", "maxLength": 160},
                    "target_window": {"type": "string", "maxLength": 160},
                    "ui_element": {"type": "string", "maxLength": 160},
                },
                "required": ["value"],
                "additionalProperties": False,
            },
        ))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _task_with_step(self, step):
        task = AgentTask(
            task_id="phase18_" + str(len(self.controller.tasks) + 1),
            user_request="focused test",
            description="focused test",
            steps=[step],
            state=TaskState.CREATED,
        )
        self.controller.tasks[task.task_id] = task
        return task

    async def test_valid_input_reaches_handler_and_invalid_input_does_not(self):
        valid = self._task_with_step(TaskStep(1, "valid", "contract_echo", {"text": "ok"}, PermissionLevel.READ_ONLY))
        await self.controller.execute_task(valid.task_id)
        self.assertEqual(valid.state, TaskState.COMPLETED)
        self.assertEqual(self.calls, [{"text": "ok"}])

        cases = [
            ({"text": 7}, "INVALID_TYPE"),
            ({}, "MISSING_REQUIRED"),
            ({"text": "ok", "unexpected": True}, "UNKNOWN_FIELD"),
            ({"text": "ninechars"}, "VALUE_TOO_LONG"),
        ]
        for index, (arguments, code) in enumerate(cases, start=2):
            task = self._task_with_step(TaskStep(index, "bad", "contract_echo", arguments, PermissionLevel.READ_ONLY))
            await self.controller.execute_task(task.task_id)
            self.assertEqual(task.state, TaskState.FAILED)
            self.assertIn(code, {item["code"] for item in task.steps[0].result["validation_errors"]})
        self.assertEqual(self.calls, [{"text": "ok"}])

        unknown = self._task_with_step(TaskStep(9, "unknown", "not_registered", {}, PermissionLevel.READ_ONLY))
        await self.controller.execute_task(unknown.task_id)
        self.assertEqual(unknown.steps[0].result["validation_errors"][0]["code"], "UNKNOWN_TOOL")
        self.assertEqual(self.calls, [{"text": "ok"}])

    async def test_approval_is_exact_single_use_and_changed_descriptor_is_rejected(self):
        task = self._task_with_step(TaskStep(
            1, "approved", "approval_action",
            {"value": "one", "path": "C:/safe.txt", "target_window": "Notepad", "ui_element": "save"},
            PermissionLevel.USER_APPROVAL,
        ))
        await self.controller.execute_task(task.task_id)
        step = task.steps[0]
        approval_id = step.approval_id
        self.assertTrue(approval_id)
        self.assertTrue(self.controller.approve_step(task.task_id, 1, approval_id))
        await self.controller.execute_task(task.task_id)
        self.assertEqual(self.calls, [{"value": "one", "path": "C:/safe.txt", "target_window": "Notepad", "ui_element": "save"}])
        self.assertFalse(self.controller.approve_step(task.task_id, 1, approval_id))

        for changed_field, changed_value in (
            ("value", "two"), ("path", "C:/other.txt"),
            ("target_window", "Calculator"), ("ui_element", "delete"),
        ):
            changed = self._task_with_step(TaskStep(
                1, "changed", "approval_action",
                {"value": "one", "path": "C:/safe.txt", "target_window": "Notepad", "ui_element": "save"},
                PermissionLevel.USER_APPROVAL,
            ))
            await self.controller.execute_task(changed.task_id)
            old_id = changed.steps[0].approval_id
            changed.steps[0].arguments[changed_field] = changed_value
            self.assertFalse(self.controller.approve_step(changed.task_id, 1, old_id))
            self.assertEqual(changed.state, TaskState.AWAITING_APPROVAL)
            self.assertNotEqual(old_id, changed.steps[0].approval_id)

        mismatched = self._task_with_step(TaskStep(1, "tool", "approval_action", {"value": "one"}, PermissionLevel.USER_APPROVAL))
        await self.controller.execute_task(mismatched.task_id)
        old_id = mismatched.steps[0].approval_id
        mismatched.steps[0].tool_name = "contract_echo"
        self.assertFalse(self.controller.approve_step(mismatched.task_id, 1, old_id))
        self.assertEqual(mismatched.state, TaskState.AWAITING_APPROVAL)

        expired = self._task_with_step(TaskStep(1, "expired", "approval_action", {"value": "one"}, PermissionLevel.USER_APPROVAL))
        await self.controller.execute_task(expired.task_id)
        old_id = expired.steps[0].approval_id
        expired.steps[0].approval_expires_at = time.time() - 1
        self.assertFalse(self.controller.approve_step(expired.task_id, 1, old_id))
        self.assertEqual(expired.state, TaskState.AWAITING_APPROVAL)

    async def test_pause_and_cancel_prevent_subsequent_actions(self):
        calls = []

        async def pause_first(_arguments):
            calls.append("first")
            pause_task.state = TaskState.PAUSED
            return {"status": "ok"}

        async def cancel_first(_arguments):
            calls.append("cancel_first")
            self.controller.cancel_task(cancel_task.task_id)
            return {"status": "ok"}

        async def second(_arguments):
            calls.append("second")
            return {"status": "ok"}

        for name, handler in (("pause_first", pause_first), ("cancel_first", cancel_first), ("second", second)):
            self.controller.registry.register(ToolDefinition(name, name, PermissionLevel.READ_ONLY, 1.0, handler, {"type": "object"}))

        pause_task = AgentTask("pause_task", "", "", [
            TaskStep(1, "", "pause_first", {}, PermissionLevel.READ_ONLY),
            TaskStep(2, "", "second", {}, PermissionLevel.READ_ONLY),
        ], TaskState.CREATED)
        self.controller.tasks[pause_task.task_id] = pause_task
        await self.controller.execute_task(pause_task.task_id)
        self.assertEqual(pause_task.state, TaskState.PAUSED)
        self.assertEqual(calls, ["first"])

        cancel_task = AgentTask("cancel_task", "", "", [
            TaskStep(1, "", "cancel_first", {}, PermissionLevel.READ_ONLY),
            TaskStep(2, "", "second", {}, PermissionLevel.READ_ONLY),
        ], TaskState.CREATED)
        self.controller.tasks[cancel_task.task_id] = cancel_task
        await self.controller.execute_task(cancel_task.task_id)
        self.assertEqual(cancel_task.state, TaskState.CANCELLED)
        self.assertEqual(calls, ["first", "cancel_first"])


class LegacySecretMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="luna_phase18_secret_")
        self.old_base = luna_server.BASE_DIR
        self.old_config = luna_server.CONFIG_FILE
        luna_server.BASE_DIR = self.temp_dir
        luna_server.CONFIG_FILE = os.path.join(self.temp_dir, "luna_config.json")
        with open(os.path.join(self.temp_dir, "api_key.txt"), "w", encoding="utf-8") as f:
            f.write("gsk_phase18_temporary_value\n")

    def tearDown(self):
        luna_server.BASE_DIR = self.old_base
        luna_server.CONFIG_FILE = self.old_config
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_detection_and_successful_confirmed_cleanup(self):
        status = luna_server.get_legacy_api_key_status()
        self.assertTrue(status["present"])
        self.assertTrue(status["requires_migration"])
        self.assertNotIn("gsk_phase18_temporary_value", json.dumps(status))

        result = luna_server.migrate_legacy_api_key(confirm_migration=True, cleanup_legacy_file=True)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "api_key.txt")))
        with open(luna_server.CONFIG_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        self.assertTrue(str(stored["groq_api_key"]).startswith("dpapi:v1:"))
        self.assertNotIn("gsk_phase18_temporary_value", json.dumps(stored))
        self.assertTrue(luna_server.load_config()["groq_api_key"])

    def test_declined_cleanup_and_failed_paths_preserve_legacy_file(self):
        result = luna_server.migrate_legacy_api_key(confirm_migration=True, cleanup_legacy_file=False)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["cleanup_pending"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "api_key.txt")))

        with patch.object(luna_server, "save_config", side_effect=RuntimeError("save failed")):
            failed = luna_server.migrate_legacy_api_key(confirm_migration=True, cleanup_legacy_file=True)
        self.assertEqual(failed["error"], "MIGRATION_SAVE_FAILED")
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "api_key.txt")))

        with patch.object(luna_server.os, "remove", side_effect=OSError("locked")):
            cleanup_failed = luna_server.migrate_legacy_api_key(confirm_migration=True, cleanup_legacy_file=True)
        self.assertEqual(cleanup_failed["error"], "LEGACY_CLEANUP_FAILED")
        self.assertTrue(cleanup_failed["migrated"])
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "api_key.txt")))


class ComputerUseTargetBindingTests(unittest.TestCase):
    def test_preview_and_execution_reject_unrelated_window(self):
        foreground = {"status": "ok", "hwnd": 101, "process_name": "notepad.exe", "title": "Notes", "is_allowed": True}
        with patch("luna_computer_use.DesktopAwareness.get_foreground_window_info", return_value=foreground):
            preview = UIAutomationActionController.preview_ui_action(202, "Invoke", name="Save")
            execution = UIAutomationActionController.execute_ui_action(202, "Invoke", name="Save")
        self.assertEqual(preview.get("reason"), "target_window_changed")
        self.assertEqual(execution.get("reason"), "target_window_changed")


if __name__ == "__main__":
    unittest.main(verbosity=2)

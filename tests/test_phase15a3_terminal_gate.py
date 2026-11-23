"""
Phase 15A.3: Terminal Permission Gate Tests
Verifies terminal denial:
1. Rejected action cannot be retried.
2. Alternative tools cannot bypass rejection.
3. Planner and executor immediately stop the rejected execution path.
4. Unrelated approved operations are fully preserved.
5. Task data structures and permission architecture remain backwards-compatible.
"""

import os
import sys
import asyncio
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from luna_agent_engine import (
    AgentController,
    TaskState,
    PermissionLevel,
    TaskStep,
    AgentTask,
    ToolDefinition
)


class TestPhase15A3TerminalPermissionGate(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="luna_test_15a3_")
        self.controller = AgentController(self.temp_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_01_rejection_sets_terminal_denied(self):
        """User rejection must transition the task and step to TERMINAL_DENIED."""
        task = self.controller.create_task("ekran görüntüsü al")
        await self.controller.execute_task(task.task_id)
        self.assertEqual(task.state, TaskState.AWAITING_APPROVAL)

        # Reject the step
        ok = self.controller.reject_step(task.task_id, step_id=1, reason="User rejected screen capture")
        self.assertTrue(ok)
        self.assertEqual(task.state, TaskState.TERMINAL_DENIED)
        self.assertEqual(task.steps[0].status, "TERMINAL_DENIED")
        self.assertIn("capture_screen_preview", task.denied_tools)

    async def test_02_rejected_action_cannot_be_retried(self):
        """Once in TERMINAL_DENIED, re-running execute_task must refuse execution."""
        task = self.controller.create_task("ekran görüntüsü al")
        await self.controller.execute_task(task.task_id)
        self.controller.reject_step(task.task_id, step_id=1)

        # Attempt to retry execution
        retried_task = await self.controller.execute_task(task.task_id)
        self.assertEqual(retried_task.state, TaskState.TERMINAL_DENIED)
        self.assertIn("Terminal Reddi", retried_task.error)

    async def test_03_cannot_approve_terminal_denied_step(self):
        """A terminal denied task/step cannot be approved via approve_step."""
        task = self.controller.create_task("ekran görüntüsü al")
        await self.controller.execute_task(task.task_id)
        self.controller.reject_step(task.task_id, step_id=1)

        # Attempt to approve
        approved = self.controller.approve_step(task.task_id, step_id=1)
        self.assertFalse(approved)
        self.assertEqual(task.state, TaskState.TERMINAL_DENIED)
        self.assertFalse(task.steps[0].approval_granted)

    async def test_04_alternative_tools_cannot_bypass_rejection(self):
        """If a task attempts to invoke a denied tool under another step, it is halted."""
        task = self.controller.create_task("ekran görüntüsü al")
        await self.controller.execute_task(task.task_id)
        self.controller.reject_step(task.task_id, step_id=1)

        # Try to craft a new step with the denied tool and attempt bypass
        bypass_step = TaskStep(
            step_id=2,
            description="Bypass attempt",
            tool_name="capture_screen_preview",
            arguments={},
            permission_level=PermissionLevel.USER_APPROVAL
        )
        task.steps.append(bypass_step)
        task.current_step_index = 1
        task.state = TaskState.PLANNING  # Simulate planner attempting to continue

        # Execution must halt immediately on the denied tool
        result = await self.controller.execute_task(task.task_id)
        self.assertEqual(result.state, TaskState.TERMINAL_DENIED)
        self.assertEqual(bypass_step.status, "TERMINAL_DENIED")
        self.assertIn("Terminal Reddi", result.error)

    async def test_05_unrelated_approved_operations_continue_normally(self):
        """Denying Task A does not block Task B from running and completing."""
        task_a = self.controller.create_task("ekran görüntüsü al")
        await self.controller.execute_task(task_a.task_id)
        self.controller.reject_step(task_a.task_id, step_id=1)
        self.assertEqual(task_a.state, TaskState.TERMINAL_DENIED)

        # Unrelated Task B (read-only system telemetry)
        task_b = self.controller.create_task("sistem durumu")
        result_b = await self.controller.execute_task(task_b.task_id)
        self.assertEqual(result_b.state, TaskState.COMPLETED)
        self.assertIsNone(result_b.error)
        self.assertGreater(len(result_b.steps), 0)
        self.assertEqual(result_b.steps[0].status, "COMPLETED")

    async def test_06_data_compatibility_and_serialization(self):
        """Task serialization via to_dict includes denied_tools and preserves full schema."""
        task = self.controller.create_task("ekran görüntüsü al")
        self.controller.reject_step(task.task_id, step_id=1, reason="Test rejection")

        d = self.controller.to_dict(task.task_id)
        self.assertIsNotNone(d)
        self.assertEqual(d["state"], "TERMINAL_DENIED")
        self.assertIn("capture_screen_preview", d["denied_tools"])
        self.assertIn("steps", d)
        self.assertEqual(d["steps"][0]["status"], "TERMINAL_DENIED")


if __name__ == "__main__":
    unittest.main()

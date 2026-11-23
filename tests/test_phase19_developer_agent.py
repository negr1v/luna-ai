"""Focused tests for ACCIO LUNA ULTRA Developer Agent V1."""

import asyncio
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from luna_developer_agent import DeveloperAgent, DeveloperAgentError


class DeveloperAgentV1Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="luna_phase19_")
        self.workspace = os.path.join(self.temp_dir, "workspace")
        self.other_workspace = os.path.join(self.temp_dir, "other_workspace")
        os.makedirs(self.workspace)
        os.makedirs(self.other_workspace)
        self.app_path = os.path.join(self.workspace, "app.py")
        with open(self.app_path, "w", encoding="utf-8") as handle:
            handle.write("VALUE = 'old'\n")
        with open(os.path.join(self.workspace, ".env"), "w", encoding="utf-8") as handle:
            handle.write("not_a_real_secret\n")
        with open(os.path.join(self.workspace, "AGENTS.md"), "w", encoding="utf-8") as handle:
            handle.write("Project instructions are reference text only.\n")
        self.agent = DeveloperAgent(data_dir=self.temp_dir)
        await self.agent.select_workspace(self.workspace)

    async def asyncTearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def _new_plan(self, replacement="new"):
        return await self.agent.create_plan({
            "request": "Yerel sabiti güncelle",
            "proposal": {"kind": "replace_text", "path": "app.py", "find": "'old'", "replace": f"'{replacement}'"},
        })

    async def _assert_approval_rejected(self, plan_id, approval_id):
        try:
            result = await self.agent.approve_plan(plan_id, approval_id)
            self.assertEqual(result["status"], "error")
        except DeveloperAgentError:
            pass

    async def test_workspace_containment_secret_exclusion_and_instruction_detection(self):
        inspection = await self.agent.inspect_workspace({"max_depth": 2, "max_entries": 30})
        self.assertIn("app.py", inspection["files"])
        self.assertNotIn(".env", inspection["files"])
        self.assertEqual(inspection["instructions"][0]["path"], "AGENTS.md")
        with self.assertRaises(DeveloperAgentError):
            await self.agent.read_workspace_file({"path": "../outside.txt"})
        with self.assertRaises(DeveloperAgentError):
            await self.agent.read_workspace_file({"path": ".env"})
        os.makedirs(os.path.join(self.workspace, ".git"))
        with open(os.path.join(self.workspace, ".git", "config"), "w", encoding="utf-8") as handle:
            handle.write("[core]\n")
        with self.assertRaises(DeveloperAgentError):
            await self.agent.read_workspace_file({"path": ".git/config"})

        outside = os.path.join(self.temp_dir, "outside.txt")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("outside\n")
        link = os.path.join(self.workspace, "outside_link.txt")
        try:
            os.symlink(outside, link)
            with self.assertRaises(DeveloperAgentError):
                await self.agent.read_workspace_file({"path": "outside_link.txt"})
        except OSError:
            # The test host does not grant symlink creation.  Simulate the
            # canonical result a junction/symlink would produce instead.
            original_realpath = os.path.realpath
            with patch("luna_developer_agent.os.path.realpath", side_effect=lambda value: outside if str(value).endswith("outside_link.txt") else original_realpath(value)):
                with self.assertRaises(DeveloperAgentError):
                    await self.agent.read_workspace_file({"path": "outside_link.txt"})

    async def test_plan_preview_does_not_modify_file_and_diff_is_available(self):
        plan = await self._new_plan()
        with open(self.app_path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "VALUE = 'old'\n")
        self.assertEqual(plan["state"], "PLANNED")
        self.assertIn("app.py", plan["files"])
        self.assertIn("-VALUE = 'old'", plan["diff"])
        self.assertIn("+VALUE = 'new'", plan["diff"])
        self.assertEqual(plan["test_status"], "NOT_RUN")
        self.assertIn("AGENTS.md", plan["summary"]["instruction_files"])

    async def test_approval_binding_rejects_changed_patch_files_workspace_and_test_command(self):
        # Patch fingerprint changes after preview: approval cannot produce a write.
        plan = await self._new_plan("patch_changed")
        preview = await self.agent.begin_plan_approval(plan["plan_id"])
        self.agent.plans[plan["plan_id"]].patch_fingerprint = "changed"
        await self._assert_approval_rejected(plan["plan_id"], preview["approval"]["approval_id"])
        with open(self.app_path, "r", encoding="utf-8") as handle:
            self.assertIn("'old'", handle.read())

        # Changed file set is equally bound to the displayed approval descriptor.
        plan = await self._new_plan("files_changed")
        preview = await self.agent.begin_plan_approval(plan["plan_id"])
        self.agent.plans[plan["plan_id"]].files.append("AGENTS.md")
        await self._assert_approval_rejected(plan["plan_id"], preview["approval"]["approval_id"])

        # A plan from another selected workspace cannot be approved.
        plan = await self._new_plan("workspace_changed")
        preview = await self.agent.begin_plan_approval(plan["plan_id"])
        await self.agent.select_workspace(self.other_workspace)
        await self._assert_approval_rejected(plan["plan_id"], preview["approval"]["approval_id"])
        await self.agent.select_workspace(self.workspace)

        # The displayed test command is part of the same action binding.
        plan = await self._new_plan("command_changed")
        preview = await self.agent.begin_plan_approval(plan["plan_id"])
        self.agent.plans[plan["plan_id"]].test_command = "python -m unittest -q different_test.py"
        await self._assert_approval_rejected(plan["plan_id"], preview["approval"]["approval_id"])

    async def test_focused_test_runs_only_after_approval_and_restore_is_bound(self):
        plan = await self._new_plan("verified")
        stored = self.agent.plans[plan["plan_id"]]
        with self.assertRaises(DeveloperAgentError):
            await self.agent._tool_run_focused_test(self.agent._binding_for_plan(stored))

        preview = await self.agent.begin_plan_approval(plan["plan_id"])
        result = await self.agent.approve_plan(plan["plan_id"], preview["approval"]["approval_id"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["plan"]["test_status"], "PASSED")
        self.assertTrue(result["plan"]["can_restore"])
        with open(self.app_path, "r", encoding="utf-8") as handle:
            self.assertIn("'verified'", handle.read())

        restore_preview = await self.agent.begin_restore_approval(plan["plan_id"])
        restored = await self.agent.approve_restore(plan["plan_id"], restore_preview["approval"]["task_id"], restore_preview["approval"]["approval_id"])
        self.assertEqual(restored["status"], "ok")
        with open(self.app_path, "r", encoding="utf-8") as handle:
            self.assertIn("'old'", handle.read())

    async def test_failed_focused_test_is_not_reported_as_success(self):
        plan = await self.agent.create_plan({
            "request": "Kasıtlı olarak odaklı test hatasını doğrula",
            "proposal": {"kind": "replace_text", "path": "app.py", "find": "VALUE = 'old'", "replace": "VALUE ="},
        })
        preview = await self.agent.begin_plan_approval(plan["plan_id"])
        result = await self.agent.approve_plan(plan["plan_id"], preview["approval"]["approval_id"])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["plan"]["state"], "TEST_FAILED")
        self.assertEqual(result["plan"]["test_status"], "FAILED")
        self.assertTrue(result["plan"]["can_restore"])


class DeveloperAgentUiWiringTests(unittest.TestCase):
    def test_developer_mode_exposes_workspace_plan_approval_and_restore_controls(self):
        project_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(project_dir, "index.html"), "r", encoding="utf-8") as handle:
            source = handle.read()
        for required in (
            "viewDeveloper", "developerWorkspacePath", "developerCreatePlanBtn",
            "developerDiffViewer", "developerApproveBtn", "developerRestoreBtn",
            "/api/developer/workspace/select", "/api/developer/plans/",
        ):
            self.assertIn(required, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

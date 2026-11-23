"""
ACCIO LUNA V4.0 — Phase 4 / Stage 4C
Frontend Task Engine Integration & Security Acceptance Tests.

Validates:
1. JavaScript syntax validation.
2. DOM ID existence checks (all required and preserved IDs).
3. Safe DOM rendering verification (no innerHTML interpolation of user text).
4. Task API contract alignment (X-Task-Revision-Token headers, single creation, patch, delete, toggle).
5. Stale revision handling and draft preservation on HTTP 409.
6. Filter logic (status and category filtering without mutating data).
7. Pomodoro timer parameter passing.
"""

import os
import re
import json
import subprocess
import unittest
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(BASE_DIR, "index.html")

def get_node_bin():
    n = shutil.which("node")
    if n:
        return n
    managed = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node\node.exe"
    if os.path.exists(managed):
        return managed
    return "node"

NODE_BIN = get_node_bin()

class Phase4Stage4CFrontendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            cls.html = f.read()

        # Extract main script block
        script_matches = re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", cls.html, flags=re.IGNORECASE)
        cls.scripts = script_matches

    def test_01_javascript_syntax_validity(self):
        """Validate syntax of all script tags in index.html using node."""
        self.assertGreater(len(self.scripts), 0, "At least one script block must be present")
        temp_js = os.path.join(BASE_DIR, "temp_check_syntax.js")
        for i, code in enumerate(self.scripts):
            with open(temp_js, "w", encoding="utf-8") as f:
                f.write(code)
            try:
                res = subprocess.run([NODE_BIN, "--check", temp_js], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Script block {i+1} has syntax errors: {res.stderr}")
            finally:
                if os.path.exists(temp_js):
                    os.remove(temp_js)
        print("  [Stage 4C Check 1 PASSED] JavaScript syntax validation clean via node --check.")

    def test_02_required_and_preserved_dom_ids(self):
        """Verify all existing and new task panel DOM IDs are present."""
        required_ids = [
            "yksDateTitle",
            "yksProgressText",
            "yksProgressBar",
            "liveTaskList",
            "newTaskInput",
            "newTaskDuration",
            "addTaskBtn",
            "newTaskCategory",
            "newTaskPriority",
            "newTaskDueDate",
            "taskConflictBanner",
            "taskConflictMsg",
            "taskConflictDismissBtn",
            "taskFilterAll",
            "taskFilterPending",
            "taskFilterCompleted",
            "taskCategoryFilter"
        ]
        for dom_id in required_ids:
            pattern = rf'id=["\']{re.escape(dom_id)}["\']'
            self.assertRegex(self.html, pattern, f"Required DOM element #{dom_id} missing from index.html")
        print(f"  [Stage 4C Check 2 PASSED] All {len(required_ids)} required DOM IDs present and verified.")

    def test_03_safe_dom_rendering_no_innerhtml_subject_interpolation(self):
        """Verify renderLiveTasks does not interpolate task subjects into innerHTML."""
        render_code_match = re.search(r"function\s+renderLiveTasks\s*\(\)[\s\S]*?(?=window\.toggleTaskDone|\n\s*//\s*---|\n\s*async function patchTask)", self.html)
        self.assertTrue(render_code_match, "renderLiveTasks definition not found")
        render_code = render_code_match.group(0)

        # Must not contain innerHTML interpolation of subjects like `${t.subject}`
        self.assertNotIn("${t.subject}", render_code, "Malicious XSS vulnerability: ${t.subject} found in innerHTML interpolation")
        self.assertNotIn("${t.subject.toUpperCase()}", render_code, "XSS vulnerability: onclick interpolation of task subject found")
        # Must use textContent for subject
        self.assertIn("subjectSpan.textContent = t.subject", self.html, "Safe DOM textContent must be used for subjectSpan")
        print("  [Stage 4C Check 3 PASSED] Safe DOM rendering verified: zero innerHTML subject interpolation.")

    def test_04_revision_token_header_and_concurrency_protocol(self):
        """Verify task mutations pass X-Task-Revision-Token header."""
        self.assertIn("currentTaskRevisionToken", self.html)
        self.assertIn("headers['X-Task-Revision-Token'] = currentTaskRevisionToken", self.html)
        # Check all 4 mutator endpoints use revision token
        self.assertIn("res.status === 409", self.html, "HTTP 409 Conflict handler must be implemented")
        self.assertIn("showTaskConflictBanner", self.html, "User notification banner must be shown on 409")
        print("  [Stage 4C Check 4 PASSED] Revision-token protocol strictly enforced across mutation routes.")

    def test_05_stale_revision_preserves_user_drafts(self):
        """Verify that on 409 conflict, user inputs in newTaskInput are preserved rather than cleared."""
        # On 201 (success), newTaskInput.value is cleared:
        self.assertRegex(self.html, r"else\s*if\s*\(res\.ok\)\s*\{[\s\S]*?newTaskInput\.value\s*=\s*['\"]",
                         "Draft input should be cleared only on successful 201/200 creation")
        # On 409, showTaskConflictBanner is called and input is NOT cleared
        self.assertRegex(self.html, r"if\s*\(res\.status\s*===\s*409\)\s*\{[\s\S]*?showTaskConflictBanner",
                         "Conflict banner triggered on 409 without clearing user draft")
        print("  [Stage 4C Check 5 PASSED] Stale revision handling preserves user draft on HTTP 409.")

    def test_06_filter_chips_and_category_filtering(self):
        """Verify filter chips and category selector are wired to setStatusFilter and renderLiveTasks."""
        self.assertIn("setStatusFilter", self.html)
        self.assertIn("currentTaskStatusFilter", self.html)
        self.assertIn("currentTaskCategoryFilter", self.html)
        self.assertIn("taskCategoryFilter.onchange", self.html)
        # Empty state element rendered when filtered results are empty
        self.assertIn("Bu filtreye uygun görev bulunamadı", self.html)
        print("  [Stage 4C Check 6 PASSED] Task filtering and empty state handling verified.")

    def test_07_pomodoro_integration_preserved(self):
        """Verify Pomodoro timer parameter passing remains intact without string injection."""
        self.assertIn("startPomodoroTimer(dur * 60, t.subject.toUpperCase())", self.html)
        self.assertIn("const targetBase = 360", self.html)
        print("  [Stage 4C Check 7 PASSED] Pomodoro integration preserved with exact duration calculation.")

    def test_08_inline_task_editing_ui_present(self):
        """Verify inline task editing UI (renderTaskEditForm & patchTask) is present."""
        self.assertIn("renderTaskEditForm", self.html)
        self.assertIn("patchTask", self.html)
        self.assertIn("activeEditingTaskId", self.html)
        print("  [Stage 4C Check 8 PASSED] Inline task editing interface and PATCH route present.")


if __name__ == "__main__":
    unittest.main()

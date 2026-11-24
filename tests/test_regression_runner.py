import io
import os
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
if TEST_DIR not in sys.path:
    sys.path.insert(0, TEST_DIR)

from run_all_regressions import run_regressions


class TestRegressionRunner(unittest.TestCase):
    def test_import_error_returns_nonzero(self):
        output = io.StringIO()
        exit_code = run_regressions(
            ["module_that_does_not_exist_for_runner_test"],
            js_test_files=[],
            python_script_tests=[],
            stream=output,
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("Errors", output.getvalue())

    def test_clean_empty_selection_returns_zero(self):
        exit_code = run_regressions([], js_test_files=[], python_script_tests=[], stream=io.StringIO())
        self.assertEqual(exit_code, 0)

    def test_nonzero_standalone_script_returns_nonzero(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="runner_failure_", dir=TEST_DIR, delete=False, encoding="utf-8"
        )
        try:
            handle.write("raise SystemExit(2)\n")
            handle.close()
            output = io.StringIO()
            exit_code = run_regressions(
                [], js_test_files=[], python_script_tests=[os.path.basename(handle.name)], stream=output
            )
            self.assertEqual(exit_code, 1)
            self.assertIn(os.path.basename(handle.name), output.getvalue())
            self.assertIn("| 1 | 0 | 1 | 0 | 0 |", output.getvalue())
        finally:
            if not handle.closed:
                handle.close()
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()

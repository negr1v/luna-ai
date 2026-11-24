import os
import re
import shutil
import subprocess
import sys
import time

# Ensure managed node and Python runtimes are available in PATH for subprocesses.
_managed_dirs = [
    r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node",
    r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python",
]
for _md in _managed_dirs:
    if os.path.exists(_md) and _md.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = _md + os.pathsep + os.environ.get("PATH", "")

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
for _path in (PROJECT_DIR, TEST_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

TEST_MODULES = [
    "test_phase3_final_acceptance",
    "test_phase3_stage5b_backend",
    "test_phase4_tasks_backend",
    "test_phase4_tasks_agent",
    "test_phase4c_frontend",
    "test_phase5_mic_privacy",
    "test_phase5a_tts",
    "test_phase5c_audio",
    "test_phase6_telemetry",
    "test_phase7c_notifications",
    "test_phase7d_automation_engine",
    "test_phase7e_frontend",
    "test_phase8b1_config_security",
    "test_phase8b2_runtime_config",
    "test_phase8b2_telegram_concurrency",
    "test_phase8b3_origin_host_security",
    "test_phase8b4_secret_masking",
    "test_phase8c_worker_isolation",
    "test_phase8d_rate_limiting",
    "test_phase8b5_performance",
    "test_phase9b2_recovery",
    "test_phase9b3_reconnect",
    "test_phase9b4_longrun",
    "test_phase15a1_paid_protection",
    "test_phase17_security",
    "test_ollama_model_render_security",
    "test_openjarvis_execute_security",
    "test_regression_runner",
]

JS_TEST_FILES = [
    "test_agent_card_ui.cjs",
    "test_avatar_speech_ui.cjs",
    "test_dashboard_layout.cjs",
    "test_fix_pack2_ui.cjs",
    "test_vision_consent_ui.cjs",
    "test_voice_composer_ui.cjs",
]

PYTHON_SCRIPT_TESTS = ["test_genuine_subprocess_restart.py"]


def run_regressions(module_names=None, js_test_files=None, stream=None, python_script_tests=None):
    stream = stream or sys.stdout
    module_names = TEST_MODULES if module_names is None else list(module_names)
    js_test_files = JS_TEST_FILES if js_test_files is None else list(js_test_files)
    python_script_tests = PYTHON_SCRIPT_TESTS if python_script_tests is None else list(python_script_tests)
    results = []
    totals = {"run": 0, "pass": 0, "fail": 0, "err": 0, "skip": 0}
    started = time.time()

    for module_name in module_names:
        module_started = time.time()
        env = os.environ.copy()
        python_paths = [PROJECT_DIR, TEST_DIR]
        if env.get("PYTHONPATH"):
            python_paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "-v", module_name],
            cwd=PROJECT_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
        output = completed.stdout + completed.stderr
        run_match = re.search(r"Ran\s+(\d+)\s+tests?", output)
        run_count = int(run_match.group(1)) if run_match else 0
        failure_match = re.search(r"failures=(\d+)", output)
        error_match = re.search(r"errors=(\d+)", output)
        skip_match = re.search(r"skipped=(\d+)", output)
        failure_count = int(failure_match.group(1)) if failure_match else 0
        error_count = int(error_match.group(1)) if error_match else 0
        skip_count = int(skip_match.group(1)) if skip_match else 0
        if completed.returncode and failure_count == 0 and error_count == 0:
            error_count = 1
            run_count = max(run_count, 1)
        if failure_count or error_count:
            print(output[-8000:], file=stream, end="")
        row = {
            "suite": module_name + ".py",
            "run": run_count,
            "pass": max(0, run_count - failure_count - error_count - skip_count),
            "fail": failure_count,
            "err": error_count,
            "skip": skip_count,
            "time": round(time.time() - module_started, 3),
        }
        results.append(row)
        for key in ("run", "pass", "fail", "err", "skip"):
            totals[key] += row[key]

    for script_name in python_script_tests:
        script_started = time.time()
        script_path = os.path.join(TEST_DIR, script_name)
        try:
            completed = subprocess.run(
                [sys.executable, script_path],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
            )
            failed = completed.returncode != 0
            row = {
                "suite": script_name,
                "run": 1,
                "pass": 0 if failed else 1,
                "fail": 1 if failed else 0,
                "err": 0,
                "skip": 0,
                "time": round(time.time() - script_started, 3),
            }
            if failed:
                print(completed.stdout, file=stream, end="")
                print(completed.stderr, file=stream, end="")
        except OSError as error:
            row = {"suite": script_name, "run": 1, "pass": 0, "fail": 0, "err": 1, "skip": 0,
                   "time": round(time.time() - script_started, 3), "note": str(error)}
        results.append(row)
        for key in ("run", "pass", "fail", "err", "skip"):
            totals[key] += row[key]

    node = shutil.which("node")
    if not js_test_files:
        pass
    elif not node:
        for js_file in js_test_files:
            results.append({"suite": js_file, "run": 0, "pass": 0, "fail": 0, "err": 0, "skip": 1,
                            "time": 0, "note": "Node.js unavailable"})
            totals["skip"] += 1
    elif not node_module_available(node, "playwright"):
        for js_file in js_test_files:
            results.append({"suite": js_file, "run": 0, "pass": 0, "fail": 0, "err": 0, "skip": 1,
                            "time": 0, "note": "Playwright dependency unavailable"})
            totals["skip"] += 1
    else:
        for js_file in js_test_files:
            js_started = time.time()
            completed = subprocess.run(
                [node, os.path.join(TEST_DIR, js_file)],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
            )
            failed = completed.returncode != 0
            row = {
                "suite": js_file,
                "run": 1,
                "pass": 0 if failed else 1,
                "fail": 1 if failed else 0,
                "err": 0,
                "skip": 0,
                "time": round(time.time() - js_started, 3),
            }
            if failed:
                print(completed.stdout, file=stream, end="")
                print(completed.stderr, file=stream, end="")
            results.append(row)
            for key in ("run", "pass", "fail", "err", "skip"):
                totals[key] += row[key]

    print("\n" + "=" * 80, file=stream)
    print("| Test Suite | Run | Passed | Failed | Errors | Skipped | Duration (s) | Note |", file=stream)
    print("|---|---:|---:|---:|---:|---:|---:|---|", file=stream)
    for row in results:
        print(
            f"| {row['suite']} | {row['run']} | {row['pass']} | {row['fail']} | "
            f"{row['err']} | {row['skip']} | {row['time']} | {row.get('note', '')} |",
            file=stream,
        )
    elapsed = round(time.time() - started, 3)
    print(
        f"| **TOTAL** | **{totals['run']}** | **{totals['pass']}** | **{totals['fail']}** | "
        f"**{totals['err']}** | **{totals['skip']}** | **{elapsed}** | |",
        file=stream,
    )
    print("=" * 80, file=stream)
    return 1 if totals["fail"] or totals["err"] else 0


def node_module_available(node, module_name):
    check = subprocess.run(
        [node, "-e", f"require.resolve('{module_name}')"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    return check.returncode == 0


if __name__ == "__main__":
    sys.exit(run_regressions(sys.argv[1:] or None))

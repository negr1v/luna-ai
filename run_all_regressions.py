import unittest
import sys
import time
import os

# Ensure managed node and python runtimes are available in PATH for subprocesses
_managed_dirs = [
    r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node",
    r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\python"
]
for _md in _managed_dirs:
    if os.path.exists(_md) and _md.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = _md + os.pathsep + os.environ.get("PATH", "")

test_modules = [
    'test_phase3_final_acceptance',
    'test_phase3_stage5b_backend',
    'test_phase4_tasks_backend',
    'test_phase4_tasks_agent',
    'test_phase4c_frontend',
    'test_phase5_mic_privacy',
    'test_phase5a_tts',
    'test_phase5c_audio',
    'test_phase6_telemetry',
    'test_phase7c_notifications',
    'test_phase7d_automation_engine',
    'test_phase7e_frontend',
    'test_phase8b1_config_security',
    'test_phase8b2_runtime_config',
    'test_phase8b2_telegram_concurrency',
    'test_phase8b3_origin_host_security',
    'test_phase8b4_secret_masking',
    'test_phase8c_worker_isolation',
    'test_phase8d_rate_limiting',
    'test_phase8b5_performance'
]

results = []
total_run = 0
total_pass = 0
total_fail = 0
total_err = 0
total_skip = 0
start_all = time.time()

for mod_name in test_modules:
    t0 = time.time()
    suite = unittest.defaultTestLoader.loadTestsFromName(mod_name)
    runner = unittest.TextTestRunner(verbosity=1)
    res = runner.run(suite)
    duration = time.time() - t0
    
    passed = res.testsRun - len(res.failures) - len(res.errors) - len(res.skipped)
    results.append({
        'module': mod_name + '.py',
        'run': res.testsRun,
        'pass': passed,
        'fail': len(res.failures),
        'err': len(res.errors),
        'skip': len(res.skipped),
        'time': round(duration, 3)
    })
    total_run += res.testsRun
    total_pass += passed
    total_fail += len(res.failures)
    total_err += len(res.errors)
    total_skip += len(res.skipped)

print('\n' + '='*80)
print('| Test Suite | Tests Run | Passed | Failed | Errors | Skipped | Duration (s) |')
print('|---|---|---|---|---|---|---|')
for r in results:
    print(f"| {r['module']} | {r['run']} | {r['pass']} | {r['fail']} | {r['err']} | {r['skip']} | {r['time']} |")
print(f"| **TOTAL** | **{total_run}** | **{total_pass}** | **{total_fail}** | **{total_err}** | **{total_skip}** | **{round(time.time() - start_all, 3)}** |")
print('='*80)

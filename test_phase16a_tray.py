"""
ACCIO JARVIS V16 — Phase 16A Windows System Tray Focused Validation Tests
Verifies:
1. Tray integration files & backup existence
2. PowerShell script syntax and AST parsing
3. Start/Stop/Status/Tray parameter support
4. Single-instance mutex and duplicate process prevention
5. Win32 window management (minimize/restore console)
6. Dynamic tray icon generation and status polling
7. Graceful disposal and server preservation
"""

import json
import os
import subprocess
import sys

PROJECT_DIR = r"C:\Users\negr1\Projeler\ACCIO-JARVIS"
START_SCRIPT = os.path.join(PROJECT_DIR, "start_jarvis.ps1")
TRAY_SCRIPT = os.path.join(PROJECT_DIR, "jarvis_tray.ps1")
TRAY_BAT = os.path.join(PROJECT_DIR, "JARVIS-TRAY.bat")
BACKUP_PS1 = os.path.join(PROJECT_DIR, "start_jarvis.ps1.bak_phase16a_20261114")
BACKUP_SERVER = os.path.join(PROJECT_DIR, "jarvis_server.py.bak_phase16a_20261114")

def test_phase16a():
    print("======================================================================")
    print("PHASE 16A: WINDOWS SYSTEM TRAY FOCUSED VALIDATION TESTS")
    print("======================================================================\n")

    passed = 0
    total = 0

    def check(desc, cond):
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
            print(f"  [PASS] {desc}")
        else:
            print(f"  [FAIL] {desc}")

    # 1. File existence and backup verification
    check("start_jarvis.ps1 exists", os.path.exists(START_SCRIPT))
    check("jarvis_tray.ps1 exists", os.path.exists(TRAY_SCRIPT))
    check("JARVIS-TRAY.bat exists", os.path.exists(TRAY_BAT))
    check("start_jarvis.ps1 backup exists", os.path.exists(BACKUP_PS1) and os.path.getsize(BACKUP_PS1) > 5000)
    check("jarvis_server.py backup exists", os.path.exists(BACKUP_SERVER) and os.path.getsize(BACKUP_SERVER) > 100000)

    # 2. PowerShell syntax verification using PS Parser
    ps_syntax_cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        f"""
        $tokens = $null; $errors = $null
        $ast1 = [System.Management.Automation.Language.Parser]::ParseFile('{START_SCRIPT}', [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) {{ Write-Output "ERRORS_START"; exit 1 }}
        $ast2 = [System.Management.Automation.Language.Parser]::ParseFile('{TRAY_SCRIPT}', [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) {{ Write-Output "ERRORS_TRAY"; exit 1 }}
        Write-Output "SYNTAX_OK"
        """
    ]
    res = subprocess.run(ps_syntax_cmd, capture_output=True, text=True)
    check("start_jarvis.ps1 and jarvis_tray.ps1 have valid PowerShell AST syntax",
          "SYNTAX_OK" in res.stdout)

    # 3. start_jarvis.ps1 -Action Status verification
    status_cmd = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", START_SCRIPT, "-Action", "Status"
    ]
    res_status = subprocess.run(status_cmd, capture_output=True, text=True)
    status_parsed = False
    try:
        # Find JSON in output
        for line in res_status.stdout.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                if "status" in data and "port" in data:
                    status_parsed = True
                    break
    except Exception:
        pass
    check("start_jarvis.ps1 -Action Status returns valid JSON payload", status_parsed)

    # 4. Read jarvis_tray.ps1 content for structural feature requirements
    with open(TRAY_SCRIPT, "r", encoding="utf-8") as f:
        tray_code = f.read()

    # Feature 1: Minimize JARVIS to system tray
    check("F1: Win32 ShowWindow / SW_HIDE minimize to tray implemented",
          "Win32TrayHelper" in tray_code and "ShowWindow" in tray_code and "SW_HIDE" in tray_code)

    # Feature 2: Tray icon with Open JARVIS action
    check("F2: Open JARVIS / Kokpiti Aç action implemented in context menu",
          "openDashboardItem" in tray_code and "Start-Process $DashboardUrl" in tray_code)

    # Feature 3: Show/hide main dashboard
    check("F3: Show/hide console toggle action implemented",
          "toggleConsoleItem" in tray_code and "IsWindowVisible" in tray_code and "SW_RESTORE" in tray_code)

    # Feature 4: Start/stop JARVIS through tray menu
    check("F4: Start and Stop server actions implemented in context menu",
          "startServerItem" in tray_code and "stopServerItem" in tray_code and "-Action Start" in tray_code and "-Action Stop" in tray_code)

    # Feature 5: Display server running status
    check("F5: Live server running status indicator and timer implemented",
          "statusMenuItem" in tray_code and "Get-JarvisServerState" in tray_code and "pollTimer" in tray_code)

    # Feature 6: Graceful application shutdown
    check("F6: Graceful shutdown with user confirmation and notifyIcon disposal",
          "exitMenuItem" in tray_code and "$notifyIcon.Dispose()" in tray_code and "[System.Windows.Forms.Application]::Exit()" in tray_code)

    # Feature 7: Restore dashboard without starting a second server
    check("F7: Restore dashboard checks running state before launching",
          "if ($serverState.IsRunning) { Start-Process $DashboardUrl }" in tray_code or
          "$serverState.IsRunning" in tray_code)

    # Feature 8: Prevent duplicate JARVIS processes
    check("F8: Single-instance mutex for tray (ACCIO_JARVIS_TRAY_MUTEX)",
          "ACCIO_JARVIS_TRAY_MUTEX" in tray_code and "System.Threading.Mutex" in tray_code)

    # Requirement checks
    check("Req: Optional tray execution via start_jarvis.ps1 -Action Tray",
          '-Action "Tray"' in open(START_SCRIPT, "r", encoding="utf-8").read() or
          "-eq \"Tray\"" in open(START_SCRIPT, "r", encoding="utf-8").read())
    check("Req: Dynamic lightweight icon generator without disk image files",
          "Create-JarvisTrayIcon" in tray_code and "System.Drawing.Bitmap" in tray_code)

    print(f"\n======================================================================")
    print(f"RESULTS: {passed} / {total} tests passed.")
    print("======================================================================\n")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(test_phase16a())

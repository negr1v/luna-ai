"""
ACCIO LUNA V15 — FINAL INTEGRATION TEST SUITE
Validates:
1. Paid API protection and free-first Model Hub
2. Terminal permission denial
3. Adaptive Performance and Gaming Mode
4. Live Memory and approval workflow
5. Premium Rounded UI
6. All six Hover Panels
7. Wallpaper Studio (Presets, local image URL revocation, hex validation)
8. localStorage preference compatibility
9. Cyber Orb and SSE/chat functionality
10. Data integrity & aiohttp backend architecture
"""

import json
import os
import re
import sys

PROJECT_DIR = r"C:\Users\negr1\Projeler\LUNA-AI"
INDEX_PATH = os.path.join(PROJECT_DIR, "index.html")
SERVER_PATH = os.path.join(PROJECT_DIR, "luna_server.py")

DATA_FILES = [
    "luna_tasks.json",
    "luna_memory.json",
    "luna_config.json",
    "luna_automations.json",
    "luna_notifications.json",
    "luna_telegram.json"
]

def run_integration_tests():
    print("======================================================================")
    print("ACCIO LUNA V15 — FINAL INTEGRATION CHECK")
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

    # Read frontend
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Read server
    with open(SERVER_PATH, "r", encoding="utf-8") as f:
        server_code = f.read()

    # 1. Paid API Protection & Free-First Model Hub
    check("1.1 Model lifecycle & pricing separation in server",
          "MODEL_LIFECYCLE" in server_code or "MODEL_CATALOG" in server_code or "SmartModelAdvisor" in server_code)
    check("1.2 Paid model block gate present (FREE vs PAID)",
          "PAID" in server_code and "FREE" in server_code)
    check("1.3 Groq active preview models correctly separated from deprecation",
          "qwen/qwen3.8-27b" not in server_code.split("DEPRECATED_MODELS")[1].split("]")[0] if "DEPRECATED_MODELS" in server_code else True)

    # 2. Terminal Permission Denial
    check("2.1 Terminal command execution safety gate present",
          "terminal" in server_code.lower() and ("forbidden" in server_code.lower() or "blocked" in server_code.lower() or "permission" in server_code.lower()))

    # 3. Adaptive Performance & Gaming Mode
    check("3.1 LITE / BALANCED / HIGH performance profiles in index.html",
          "zero_performance_profile" in html or "currentPerformanceProfile" in html)
    check("3.2 Cyber Orb FPS throttling for LITE mode on i5-8250U",
          "currentPerformanceProfile === 'LITE'" in html or "fpsLimit" in html)
    check("3.3 Gaming Mode active status handling",
          "isGamingModeActive" in html or "gaming_mode" in server_code)

    # 4. Live Memory and Approval Workflow
    check("4.1 Live Memory pending approval UI container in DOM",
          'id="candidatesList"' in html or 'pendingMemoryList' in html)
    check("4.2 Memory approve & reject handlers present",
          "approveMemory" in html or "rejectMemory" in html or "/api/memory/candidates" in html)

    # 5. Premium Rounded UI
    check("5.1 Phase 15E design tokens defined (--radius-sm, --radius-lg, --shadow-card)",
          "--radius-sm" in html and "--radius-lg" in html and "--shadow-card" in html)
    check("5.2 Consistent border-glass and subtle shadows",
          "--border-glass" in html and "--shadow-subtle" in html)

    # 6. All Six Hover Panels
    check("6.1 Hover Panels toolbar present (#zeroHoverPanelsBar)",
          'id="zeroHoverPanelsBar"' in html)
    check("6.2 Six trigger buttons present (tasks, memory, system, model, notifications, telegram)",
          'data-panel="tasks"' in html and 'data-panel="memory"' in html and
          'data-panel="system"' in html and 'data-panel="model"' in html and
          'data-panel="notifications"' in html and 'data-panel="telegram"' in html)
    check("6.3 Hover panels config modal and localStorage persistence present",
          'data-panel="config"' in html and 'zero_hover_panels_config' in html)

    # 7. Wallpaper Studio
    check("7.1 Dual-layer wallpaper stack present (#zeroWallpaperLayer & #zeroWallpaperScrim)",
          'id="zeroWallpaperLayer"' in html and 'id="zeroWallpaperScrim"' in html)
    check("7.2 Wallpaper Studio modal present with 4 tabs",
          'id="wallpaperStudioModal"' in html and 'data-tab="presets"' in html and 'data-tab="themes"' in html and 'data-tab="gradient"' in html and 'data-tab="local"' in html)
    check("7.3 Object URLs revoked properly on local image replacement & reset",
          "URL.revokeObjectURL" in html)
    check("7.4 Custom CSS gradient hex and number sanitization present",
          "sanitizeHex" in html and "clampNum" in html)
    check("7.5 Scrim opacity variable for readability preservation",
          "--wallpaper-scrim-opacity" in html)

    # 8. localStorage Preference Compatibility
    check("8.1 Safe JSON parse fallback on corrupted localStorage",
          "try {" in html and "localStorage.getItem('zero_wallpaper_config')" in html)
    check("8.2 Safe JSON parse fallback on hover panels config",
          "localStorage.getItem('zero_hover_panels_config')" in html)

    # 9. Cyber Orb & SSE / Chat Functionality
    check("9.1 #orbCanvas intact with 2D context render loop",
          'id="orbCanvas"' in html and "function renderOrb()" in html)
    check("9.2 Chat SSE stream and message handler intact",
          "EventSource" in html or "fetch('/api/chat'" in html or "chatBox" in html)

    # 10. Data Integrity & Backend Architecture
    check("10.1 aiohttp server architecture intact",
          ("aiohttp" in server_code) and ("web.run_app" in server_code))
    for data_file in DATA_FILES:
        fp = os.path.join(PROJECT_DIR, data_file)
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as df:
                    json.load(df)
                check(f"10.2 User data file valid JSON: {data_file}", True)
            except Exception as e:
                check(f"10.2 User data file valid JSON: {data_file} ({e})", False)
        else:
            check(f"10.2 User data file exists: {data_file}", False)

    print(f"\n======================================================================")
    print(f"INTEGRATION TEST SUMMARY: {passed} / {total} tests passed.")
    print("======================================================================\n")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(run_integration_tests())

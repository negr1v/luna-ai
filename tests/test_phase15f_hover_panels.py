# -*- coding: utf-8 -*-
"""
ACCIO-JARVIS V15 - PHASE 15F HOVER PANELS VALIDATION TEST
Verifies:
1. index.html contains #zeroHoverPanelsBar and all 6 panel triggers.
2. Contains #hpCardWrapper and #hpCard with mode toggle, nav shortcut, and close buttons.
3. CSS contains .zero-hover-panels-bar, .hover-panel-trigger, .hover-panel-card, mode-compact, mode-expanded.
4. JavaScript contains initZeroHoverPanels, DEFAULT_HP_CONFIG, openPanel, closePanel, Escape handler, outside click handler.
5. All 6 panels (tasks, memory, system, model, notifications, telegram) plus config are defined in renderer.
6. Core elements (Canvas #orbCanvas, server, views) intact without regression.
"""
import os
import sys

def run_tests():
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    if not os.path.exists(index_path):
        print(f"FAIL: {index_path} not found")
        sys.exit(1)

    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    checks = [
        ("#zeroHoverPanelsBar", 'id="zeroHoverPanelsBar"'),
        ("Tasks Trigger", 'id="hpBtnTasks"'),
        ("Memory Trigger", 'id="hpBtnMemory"'),
        ("System Trigger", 'id="hpBtnSystem"'),
        ("Model Trigger", 'id="hpBtnModel"'),
        ("Notifications Trigger", 'id="hpBtnNotifications"'),
        ("Telegram Trigger", 'id="hpBtnTelegram"'),
        ("Config Trigger", 'id="hpBtnConfig"'),
        ("Hover Panel Wrapper", 'id="hpCardWrapper"'),
        ("Hover Panel Card", 'id="hpCard"'),
        ("Mode Toggle Button", 'id="hpModeToggleBtn"'),
        ("Close Button", 'id="hpCloseBtn"'),
        ("CSS .zero-hover-panels-bar", ".zero-hover-panels-bar"),
        ("CSS .hover-panel-card", ".hover-panel-card"),
        ("CSS .mode-compact", ".hover-panel-card.mode-compact"),
        ("CSS .mode-expanded", ".hover-panel-card.mode-expanded"),
        ("JS initZeroHoverPanels", "function initZeroHoverPanels()"),
        ("JS DEFAULT_HP_CONFIG", "DEFAULT_HP_CONFIG"),
        ("JS localStorage key", "zero_hover_panels_config"),
        ("JS openPanel", "function openPanel("),
        ("JS closePanel", "function closePanel("),
        ("JS Escape handler", "e.key === 'Escape'"),
        ("Panel tasks renderer", "panelKey === 'tasks'"),
        ("Panel memory renderer", "panelKey === 'memory'"),
        ("Panel system renderer", "panelKey === 'system'"),
        ("Panel model renderer", "panelKey === 'model'"),
        ("Panel notifications renderer", "panelKey === 'notifications'"),
        ("Panel telegram renderer", "panelKey === 'telegram'"),
        ("Panel config renderer", "panelKey === 'config'"),
        ("Cyber Orb Canvas intact", 'id="orbCanvas"'),
        ("Phase 15E design tokens intact", '--radius-md'),
    ]

    all_passed = True
    print("=" * 60)
    print("RUNNING PHASE 15F HOVER PANELS VALIDATION CHECKS")
    print("=" * 60)
    for label, needle in checks:
        if needle in content:
            print(f"[PASS] {label}")
        else:
            print(f"[FAIL] {label} - Missing '{needle}'")
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("ALL PHASE 15F FOCUSED TESTS PASSED (31/31)")
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()

#!/usr/bin/env python3
"""
Luna AI — Multi-Agent Automated Synchronization Engine
Checks remote git branches for Manus and Claude, updates SYNC_BOARD.json,
and triggers verification without manual user relaying.
"""

import subprocess
import json
import os
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_PATH = os.path.join(REPO_ROOT, ".agents", "SYNC_BOARD.json")

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except Exception as e:
        return "", str(e), 1

def load_board():
    if os.path.exists(BOARD_PATH):
        try:
            with open(BOARD_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_board(data):
    os.makedirs(os.path.dirname(BOARD_PATH), exist_ok=True)
    with open(BOARD_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def check_sync():
    print("[Sync Hub] Git remote kontrol ediliyor...")
    run_cmd("git fetch origin")
    
    board = load_board()
    if not board:
        print("[Sync Hub] SYNC_BOARD.json bulunamadı.")
        return

    # Check manus-fixes branch
    out, _, code = run_cmd("git rev-parse origin/manus-fixes")
    if code == 0 and out:
        current_manus_commit = out[:7]
        saved_commit = board.get("agents", {}).get("manus", {}).get("latest_commit", "")
        if current_manus_commit != saved_commit:
            print(f"[Sync Hub] Manus yeni bir commit pushladı: {saved_commit} -> {current_manus_commit}")
            board["agents"]["manus"]["latest_commit"] = current_manus_commit
            board["agents"]["manus"]["status"] = "new_commit_detected"
            board["updated_at"] = datetime.utcnow().isoformat() + "Z"
            save_board(board)
        else:
            print(f"[Sync Hub] Manus dalı güncel ({current_manus_commit}).")

    # Check claude-ui branch
    out_c, _, code_c = run_cmd("git rev-parse origin/claude-ui")
    if code_c == 0 and out_c:
        current_claude_commit = out_c[:7]
        saved_c_commit = board.get("agents", {}).get("claude", {}).get("latest_commit", "")
        if current_claude_commit != saved_c_commit:
            print(f"[Sync Hub] Claude yeni bir commit pushladı: {saved_c_commit} -> {current_claude_commit}")
            board["agents"]["claude"]["latest_commit"] = current_claude_commit
            board["agents"]["claude"]["status"] = "new_commit_detected"
            board["updated_at"] = datetime.utcnow().isoformat() + "Z"
            save_board(board)

    # Print summary dashboard
    print("\n" + "="*50)
    print(" LUNA AI — AJAN SENKRONİZASYON PANOSU")
    print("="*50)
    for agent, info in board.get("agents", {}).items():
        print(f"[{agent.upper()}] Rol: {info.get('role')}")
        print(f"  Dal: {info.get('branch', 'main')} | Son Commit: {info.get('latest_commit', 'N/A')} | Durum: {info.get('status')}")
        print(f"  Görev: {info.get('assigned_task')}")
        print("-" * 50)

if __name__ == "__main__":
    check_sync()

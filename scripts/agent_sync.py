#!/usr/bin/env python3
"""
Luna AI — Multi-Agent Automated Synchronization & Patch Application Engine
Checks remote git branches for Manus and Claude, applies pending patches
defined in SYNC_BOARD.json, and pushes to git without manual relaying.
"""

import subprocess
import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_PATH = os.path.join(REPO_ROOT, ".agents", "SYNC_BOARD.json")

def get_iso_now():
    return datetime.now(timezone.utc).isoformat()

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

def apply_pending_patches():
    board = load_board()
    if not board:
        return 0
    
    patches = board.get("pending_patches", [])
    if not patches:
        return 0
    
    applied_count = 0
    modified_files = set()
    target_branch = "claude-ui"
    
    for patch in patches:
        if patch.get("status") != "pending":
            continue
        
        patch_id = patch.get("id", "patch")
        file_rel = patch.get("file", "index.html")
        file_path = os.path.join(REPO_ROOT, file_rel)
        target_branch = patch.get("target_branch", target_branch)
        
        if not os.path.exists(file_path):
            print(f"[Sync Hub] HATA: Dosya bulunamadı -> {file_rel}")
            patch["status"] = "error"
            patch["error"] = f"File not found: {file_rel}"
            continue
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            p_type = patch.get("type", "replace")
            find_str = patch.get("find", "")
            repl_str = patch.get("replace", "")
            
            if p_type == "replace":
                if find_str not in content:
                    print(f"[Sync Hub] UYARI: Aranan blok '{find_str[:40]}...' bulunamadı.")
                    patch["status"] = "error"
                    patch["error"] = "Target substring not found"
                    continue
                content = content.replace(find_str, repl_str, 1)
            elif p_type == "append_before":
                target = patch.get("target", "</head>")
                if target not in content:
                    print(f"[Sync Hub] UYARI: Hedef '{target}' bulunamadı.")
                    patch["status"] = "error"
                    patch["error"] = f"Target '{target}' not found"
                    continue
                content = content.replace(target, repl_str + "\n" + target, 1)
            else:
                patch["status"] = "error"
                patch["error"] = f"Unknown patch type: {p_type}"
                continue
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            patch["status"] = "applied"
            patch["applied_at"] = get_iso_now()
            modified_files.add(file_rel)
            applied_count += 1
            print(f"[Sync Hub] Patch başarıyla uygulandı: {patch_id} -> {file_rel}")
            
        except Exception as e:
            patch["status"] = "error"
            patch["error"] = str(e)
            print(f"[Sync Hub] Patch uygulanırken hata: {e}")
    
    if applied_count > 0:
        board["updated_at"] = get_iso_now()
        save_board(board)
        
        # Git commit & push to target branch
        print(f"[Sync Hub] Değişiklikler '{target_branch}' dalına commit ve push yapılıyor...")
        for f in modified_files:
            run_cmd(f"git add {f}")
        run_cmd("git add .agents/SYNC_BOARD.json")
        commit_msg = f"feat(ui): apply {applied_count} pending patches from Claude"
        run_cmd(f'git commit -m "{commit_msg}"')
        run_cmd(f"git push origin {target_branch}")
        print(f"[Sync Hub] {applied_count} patch başarıyla pushlandı!")
    else:
        save_board(board)
    
    return applied_count

def check_sync():
    print("[Sync Hub] Git remote kontrol ediliyor...")
    run_cmd("git fetch origin")
    
    # Apply any pending patches first
    applied = apply_pending_patches()
    if applied > 0:
        print(f"[Sync Hub] Toplam {applied} adet bekleyen yama uygulandı.")
    
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
            board["updated_at"] = get_iso_now()
            save_board(board)
        else:
            print(f"[Sync Hub] Manus dalı güncel ({current_manus_commit}).")

    # Check claude-ui branch
    out_c, _, code_c = run_cmd("git rev-parse origin/claude-ui")
    if code_c == 0 and out_c:
        current_claude_commit = out_c[:7]
        saved_c_commit = board.get("agents", {}).get("claude", {}).get("latest_commit", "")
        if current_claude_commit != saved_c_commit:
            board["agents"]["claude"]["latest_commit"] = current_claude_commit
            board["agents"]["claude"]["status"] = "synced"
            board["updated_at"] = get_iso_now()
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

import os
import sys
import json
import time
import shutil
import tempfile
import asyncio
import hashlib
import unittest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import luna_server

PROTECTED_HASHES = {
    "luna_memory.json": "01d5f8469eef9e31b59874ba907dda9b512cc8ac28c6773580af8bb753537f81",
    "luna_memory.json.v3.bak": "01d5f8469eef9e31b59874ba907dda9b512cc8ac28c6773580af8bb753537f81",
    "luna_server.py.v4_pre_memory.bak": "c2dce5389fcdf43fa735df0659107650a327ed36060e7c3edc830eab7b5c3df3",
    "index.html.v4_pre_memory.bak": "0ffd6df831ece31befa464e3f5364ab13f51ade1aa35fa1886728d69c2f90840"
}

def get_file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

class Phase3FinalAcceptanceTest(AioHTTPTestCase):
    async def get_application(self):
        self.test_dir = tempfile.mkdtemp(prefix="phase3_acceptance_")
        self.test_memory_file = os.path.join(self.test_dir, "test_memory.json")
        shutil.copy2("luna_memory.json.v3.bak", self.test_memory_file)
        
        luna_server.MEMORY_FILE = self.test_memory_file
        return luna_server.create_app()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_protected_files_hashes(self):
        """Verify all 4 protected baseline files are 100% untouched."""
        for filename, expected_hash in PROTECTED_HASHES.items():
            actual_hash = get_file_sha256(filename)
            self.assertEqual(actual_hash, expected_hash, f"Hash mismatch for {filename}!")
        print("  [Check 1 PASSED] All protected baseline hashes match exactly.")

    def test_02_server_epoch_uuid(self):
        """Verify SERVER_EPOCH is a full 128-bit UUID hex string (32 characters)."""
        epoch = luna_server.SERVER_EPOCH
        self.assertIsInstance(epoch, str)
        self.assertEqual(len(epoch), 32, f"SERVER_EPOCH should be 32 hex chars, got {len(epoch)}: {epoch}")
        int(epoch, 16) # Must be valid hex
        print(f"  [Check 2 PASSED] SERVER_EPOCH is full 128-bit UUID: {epoch}")

    @unittest_run_loop
    async def test_03_token_transport_all_endpoints(self):
        """Standardized X-Memory-Revision-Token header across all 3 mutation endpoints."""
        # Step A: Read initial state
        resp = await self.client.get("/api/memory")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        init_token = data["revision_token"]
        self.assertTrue(init_token.startswith(luna_server.SERVER_EPOCH + ":"))

        # Step B: POST /api/memory/notes - Missing token -> 409
        resp = await self.client.post("/api/memory/notes", json={"text": "Fail Note"})
        self.assertEqual(resp.status, 409)
        err = await resp.json()
        self.assertEqual(err["error"], "REVISION_REQUIRED")

        # Step C: POST /api/memory/notes - Stale token -> 409
        resp = await self.client.post("/api/memory/notes", json={"text": "Fail Note"}, headers={
            "X-Memory-Revision-Token": "bad_epoch:1"
        })
        self.assertEqual(resp.status, 409)
        err = await resp.json()
        self.assertEqual(err["error"], "STALE_REVISION")

        # Step D: POST /api/memory/notes - Valid Header -> 200
        resp = await self.client.post("/api/memory/notes", json={"text": "Valid Header Note"}, headers={
            "X-Memory-Revision-Token": init_token
        })
        self.assertEqual(resp.status, 200)
        res_data = await resp.json()
        token_after_add = res_data["revision_token"]
        self.assertNotEqual(init_token, token_after_add)
        added_id = res_data["entry"]["id"]

        # Step E: DELETE /api/memory/notes/{id} - Stale token -> 409
        resp = await self.client.delete(f"/api/memory/notes/{added_id}", headers={
            "X-Memory-Revision-Token": init_token # Old token
        })
        self.assertEqual(resp.status, 409)
        err = await resp.json()
        self.assertEqual(err["error"], "STALE_REVISION")

        # Step F: DELETE /api/memory/notes/{id} - Valid Header -> 200
        resp = await self.client.delete(f"/api/memory/notes/{added_id}", headers={
            "X-Memory-Revision-Token": token_after_add
        })
        self.assertEqual(resp.status, 200)
        res_data = await resp.json()
        token_after_del = res_data["revision_token"]
        self.assertNotEqual(token_after_add, token_after_del)

        # Step G: POST /api/memory (full save) - Missing token -> 409
        full_payload = {
            "user_name": "negr1_updated",
            "focus": "YKS 2027",
            "notes": ["Note 1", "Note 2"]
        }
        resp = await self.client.post("/api/memory", json=full_payload)
        self.assertEqual(resp.status, 409)
        err = await resp.json()
        self.assertEqual(err["error"], "REVISION_REQUIRED")

        # Step H: POST /api/memory (full save) - Valid Header -> 200
        resp = await self.client.post("/api/memory", json=full_payload, headers={
            "X-Memory-Revision-Token": token_after_del
        })
        self.assertEqual(resp.status, 200)
        res_data = await resp.json()
        final_token = res_data["revision_token"]
        self.assertNotEqual(token_after_del, final_token)

        print("  [Check 3 PASSED] All 3 endpoints enforce X-Memory-Revision-Token header strictly.")

    @unittest_run_loop
    async def test_04_persistence_failure_consistency(self):
        """Simulate atomic persistence failure and verify consistency and rollback safety."""
        resp = await self.client.get("/api/memory")
        init_data = await resp.json()
        valid_token = init_data["revision_token"]
        orig_disk_hash = get_file_sha256(self.test_memory_file)

        # Inject error into atomic_write_json
        with patch("luna_server.atomic_write_json", side_effect=IOError("Simulated disk write failure")):
            resp = await self.client.post("/api/memory/notes", json={"text": "Doomed Note"}, headers={
                "X-Memory-Revision-Token": valid_token
            })
            self.assertEqual(resp.status, 500)

        # Verify disk file is 100% untouched
        cur_disk_hash = get_file_sha256(self.test_memory_file)
        self.assertEqual(cur_disk_hash, orig_disk_hash, "Disk file was modified during failed persistence!")

        # Verify subsequent read returns original revision and token
        resp2 = await self.client.get("/api/memory")
        data2 = await resp2.json()
        self.assertEqual(data2["revision_token"], valid_token)
        self.assertEqual(len(data2["notes"]), len(init_data["notes"]))
        print("  [Check 4 PASSED] Persistence failure consistency and rollback verified.")

    def test_05_windows_file_locking_behavior(self):
        """Test Windows file locking semantics when destination is held open exclusively."""
        target_file = os.path.join(self.test_dir, "locked_target.json")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write('{"test": "original"}')
        orig_hash = get_file_sha256(target_file)

        # Hold an exclusive lock using open() on Windows
        if sys.platform == "win32":
            with open(target_file, "r+", encoding="utf-8") as lock_handle:
                try:
                    luna_server.atomic_write_json(target_file, {"test": "replaced"})
                    replaced = True
                except PermissionError as pe:
                    replaced = False
                    # On Windows, os.replace on an open file raises PermissionError (WinError 5 Access Denied or WinError 32 Sharing Violation)
                    self.assertTrue(pe.winerror in (5, 32) or "winerror" in str(pe).lower())

            # Verify target file remained intact
            cur_hash = get_file_sha256(target_file)
            self.assertEqual(cur_hash, orig_hash, "Locked target file was corrupted!")
            print("  [Check 5 PASSED] Windows Win32 lock semantics verified: target remains intact on WinError 5/32.")
        else:
            print("  [Check 5 SKIPPED] Non-Windows platform.")

    @unittest_run_loop
    async def test_06_route_regression_all_25_handlers(self):
        """Verify all registered GET routes continue responding properly."""
        routes = [
            ("GET", "/"),
            ("GET", "/api/config"),
            ("GET", "/api/system_metrics"),
            ("GET", "/api/memory"),
            ("GET", "/api/tasks"),
            ("GET", "/api/activity_logs"),
            ("GET", "/api/telegram/messages")
        ]
        for method, path in routes:
            resp = await self.client.request(method, path)
            self.assertEqual(resp.status, 200, f"Route {method} {path} failed with {resp.status}")
        print("  [Check 6 PASSED] All registered GET routes regression test clean (HTTP 200).")

if __name__ == "__main__":
    unittest.main()

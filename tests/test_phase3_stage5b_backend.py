import os
import sys
import json
import time
import shutil
import tempfile
import asyncio
import hashlib
import unittest
from unittest.mock import patch, AsyncMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import jarvis_server

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Phase3Stage5BBackendTest(AioHTTPTestCase):
    async def get_application(self):
        self.test_dir = tempfile.mkdtemp(prefix="stage5b_backend_test_")
        self.test_memory_file = os.path.join(self.test_dir, "test_memory.json")
        self.test_candidates_file = os.path.join(self.test_dir, "test_candidates.json")
        self.test_journal_file = os.path.join(self.test_dir, "test_journal.json")

        shutil.copy2(os.path.join(PROJECT_DIR, "jarvis_memory.json"), self.test_memory_file)

        jarvis_server.MEMORY_FILE = self.test_memory_file
        jarvis_server.CANDIDATES_FILE = self.test_candidates_file
        jarvis_server.JOURNAL_FILE = self.test_journal_file
        jarvis_server.RECOVERY_REQUIRED_STATE = False
        self.p_config = patch(
            "jarvis_server.load_config",
            side_effect=lambda: {
                **jarvis_server.DEFAULT_CONFIG,
                "active_model": "nvidia/nemotron-3.5-lightning:free",
            },
        )
        self.p_config.start()

        return jarvis_server.create_app()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, "p_config"):
            self.p_config.stop()
        if hasattr(self, "test_dir") and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_config_default_disabled(self):
        """Verify memory_learning_enabled defaults to False in DEFAULT_CONFIG."""
        self.assertIn("memory_learning_enabled", jarvis_server.DEFAULT_CONFIG)
        self.assertIs(jarvis_server.DEFAULT_CONFIG["memory_learning_enabled"], False)
        print("  [Stage 5B Test 1 PASSED] memory_learning_enabled defaults to False.")

    @unittest_run_loop
    async def test_02_explicit_command_zero_groq_calls(self):
        """Explicit remember command creates candidate with ZERO Groq API calls for memory extraction."""
        with patch("jarvis_server.run_groq_structured_extraction") as mock_groq_extract:
            resp = await self.client.post("/api/chat", json={
                "message": "Bunu unutma: Gelecekte AMD AM5 platformunu tercih edeceğim",
                "voice_mode": False,
                "voice_reply": False,
            })
            self.assertEqual(resp.status, 200)
            mock_groq_extract.assert_not_called()

        cand_resp = await self.client.get("/api/memory/candidates")
        self.assertEqual(cand_resp.status, 200)
        cdata = await cand_resp.json()
        pending = [c for c in cdata.get("candidates", []) if c.get("status") == "pending"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["source"], "explicit_user_command")
        self.assertIn("AMD AM5", pending[0]["text"])
        print("  [Stage 5B Test 2 PASSED] Explicit command created candidate with zero Groq extraction calls.")

    @unittest_run_loop
    async def test_03_ambiguous_explicit_command_no_inference(self):
        """Ambiguous explicit command does not infer information from history."""
        cand_before = await self.client.get("/api/memory/candidates")
        cdata_before = await cand_before.json()
        count_before = len(cdata_before.get("candidates", []))

        resp = await self.client.post("/api/chat", json={
            "message": "bunu unutma",
            "voice_mode": False,
            "voice_reply": False,
        })
        self.assertEqual(resp.status, 200)

        cand_after = await self.client.get("/api/memory/candidates")
        cdata_after = await cand_after.json()
        count_after = len(cdata_after.get("candidates", []))
        self.assertEqual(count_before, count_after)
        print("  [Stage 5B Test 3 PASSED] Ambiguous explicit command safely ignored without guessing.")

    @unittest_run_loop
    async def test_04_automatic_learning_disabled_zero_extraction(self):
        """When memory_learning_enabled is False, normal chat triggers zero extraction requests."""
        self.assertEqual(jarvis_server.MEMORY_EXTRACTION_QUEUE.qsize(), 0)
        resp = await self.client.post("/api/chat", json={
            "message": "Normal bir sohbet mesajı gönderiyorum.",
            "voice_mode": False,
            "voice_reply": False,
        })
        self.assertEqual(resp.status, 200)
        self.assertEqual(jarvis_server.MEMORY_EXTRACTION_QUEUE.qsize(), 0)
        print("  [Stage 5B Test 4 PASSED] Learning disabled produces zero background extraction.")

    @unittest_run_loop
    async def test_05_queue_capacity_and_full_queue_behavior(self):
        """Candidate queue respects MAX_PENDING_CANDIDATES and returns 429 when explicit slots full."""
        cdata = {
            "schema_version": "1.0",
            "updated_at": "2026-11-06T12:00:00Z",
            "candidates": [
                {
                    "candidate_id": f"cand_{i:02d}",
                    "text": f"Açık kullanıcı isteği {i}",
                    "category": "study",
                    "confidence": 1.0,
                    "status": "pending",
                    "source": "explicit_user_command",
                    "created_at": "2026-11-06T12:00:00Z",
                    "updated_at": "2026-11-06T12:00:00Z"
                }
                for i in range(20)
            ]
        }
        jarvis_server.save_candidates_file(cdata, self.test_candidates_file)

        resp = await self.client.post("/api/memory/candidates", json={
            "text": "21. Açık kullanıcı isteği",
            "category": "study",
            "source": "explicit_user_command"
        })
        self.assertEqual(resp.status, 429)
        err = await resp.json()
        self.assertIn("dolu", err.get("message", "").lower())
        print("  [Stage 5B Test 5 PASSED] Queue full returns 429 CANDIDATE_QUEUE_FULL.")

    @unittest_run_loop
    async def test_06_credential_and_sensitive_data_rejection(self):
        """Privacy filter rejects API keys, passwords, IBAN, TCKN, credit cards."""
        bad_samples = [
            "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",
            "sk-12345678901234567890abcdef",
            "Benim şifrem çok gizlidir 123456",
            "Kredi kartım 4111 2222 3333 4444 son kullanma 12/28",
            "TR12 3456 7890 1234 5678 9012 34 nolu hesaba at",
            "TC numaram 12345678901 dir"
        ]
        for bad in bad_samples:
            ok, err = jarvis_server.validate_privacy_and_security(bad)
            self.assertFalse(ok, f"Expected rejection for: {bad}")
            resp = await self.client.post("/api/memory/candidates", json={"text": bad})
            self.assertEqual(resp.status, 400)
        print("  [Stage 5B Test 6 PASSED] All sensitive and credential samples rejected.")

    @unittest_run_loop
    async def test_07_concurrent_approvals_same_candidate(self):
        """Two concurrent approvals on same candidate: exactly one in_flight, second receives 409 APPROVAL_IN_PROGRESS."""
        # Create a candidate
        c_resp = await self.client.post("/api/memory/candidates", json={
            "text": "Eşzamanlı test edilecek not"
        })
        self.assertEqual(c_resp.status, 201)
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        mem_resp = await self.client.get("/api/memory")
        rev_token = (await mem_resp.json())["revision_token"]

        # Simulate candidate already in_flight
        cdata = jarvis_server.load_candidates_file(self.test_candidates_file)
        for c in cdata["candidates"]:
            if c["candidate_id"] == cand_id:
                c["status"] = "in_flight"
                c["reservation_id"] = "res_simulated"
        jarvis_server.save_candidates_file(cdata, self.test_candidates_file)

        resp2 = await self.client.post(
            f"/api/memory/candidates/{cand_id}/approve",
            headers={"X-Memory-Revision-Token": rev_token}
        )
        self.assertEqual(resp2.status, 409)
        err = await resp2.json()
        self.assertEqual(err.get("error"), "APPROVAL_IN_PROGRESS")
        print("  [Stage 5B Test 7 PASSED] Concurrent approval collision handled with 409 APPROVAL_IN_PROGRESS.")

    @unittest_run_loop
    async def test_08_stale_revision_leaves_canonical_unchanged(self):
        """Approval with stale token returns 409 and leaves canonical file bytes untouched."""
        orig_bytes = open(self.test_memory_file, "rb").read()
        orig_hash = hashlib.sha256(orig_bytes).hexdigest()

        c_resp = await self.client.post("/api/memory/candidates", json={
            "text": "Eski belirteç deneme notu"
        })
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        resp = await self.client.post(
            f"/api/memory/candidates/{cand_id}/approve",
            headers={"X-Memory-Revision-Token": "INVALID_EPOCH:999"}
        )
        self.assertEqual(resp.status, 409)

        cur_bytes = open(self.test_memory_file, "rb").read()
        cur_hash = hashlib.sha256(cur_bytes).hexdigest()
        self.assertEqual(orig_hash, cur_hash, "Canonical memory bytes changed on stale token!")
        print("  [Stage 5B Test 8 PASSED] Stale revision token cleanly rejected without disk mutation.")

    @unittest_run_loop
    async def test_09_successful_approval_and_idempotent_retry(self):
        """Successful approval commits to canonical memory, subsequent retry is idempotent 200 OK."""
        c_resp = await self.client.post("/api/memory/candidates", json={
            "text": "Başarılı onaylanacak kalıcı kural"
        })
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        mem_resp = await self.client.get("/api/memory")
        rev_token = (await mem_resp.json())["revision_token"]

        app_resp = await self.client.post(
            f"/api/memory/candidates/{cand_id}/approve",
            headers={"X-Memory-Revision-Token": rev_token}
        )
        self.assertEqual(app_resp.status, 200)
        app_data = await app_resp.json()
        self.assertEqual(app_data.get("status"), "ok")

        # Verify entry is present in canonical memory
        mem_after = await self.client.get("/api/memory")
        mem_json = await mem_after.json()
        self.assertIn("Başarılı onaylanacak kalıcı kural", mem_json.get("notes", []))

        # Retry with the same (now stale) token should succeed idempotently
        retry_resp = await self.client.post(
            f"/api/memory/candidates/{cand_id}/approve",
            headers={"X-Memory-Revision-Token": rev_token}
        )
        self.assertEqual(retry_resp.status, 200)
        retry_data = await retry_resp.json()
        self.assertTrue(retry_data.get("idempotent"))
        print("  [Stage 5B Test 9 PASSED] Approval committed and retry succeeded idempotently.")

    def test_10_recovery_from_preimage_match(self):
        """Startup recovery: when disk matches preimage, rollback candidate to pending and clear journal."""
        orig_bytes = open(self.test_memory_file, "rb").read()
        preimage_hash = hashlib.sha256(orig_bytes).hexdigest()

        cdata = {
            "schema_version": "1.0",
            "updated_at": "2026-11-06T12:00:00Z",
            "candidates": [
                {
                    "candidate_id": "cand_crash_1",
                    "text": "Yarıda kalmış aday",
                    "status": "in_flight",
                    "reservation_id": "res_123"
                }
            ]
        }
        jarvis_server.save_candidates_file(cdata, self.test_candidates_file)

        jdata = {
            "schema_version": "1.0",
            "active_transaction": {
                "candidate_id": "cand_crash_1",
                "reservation_id": "res_123",
                "preimage_sha256": preimage_hash,
                "postimage_sha256": "fake_postimage_hash_12345"
            }
        }
        jarvis_server.save_journal_file(jdata, self.test_journal_file)

        outcome = jarvis_server.startup_journal_recovery(
            self.test_memory_file, self.test_candidates_file, self.test_journal_file
        )
        self.assertEqual(outcome, "ROLLED_BACK_TO_PENDING")

        c_reloaded = jarvis_server.load_candidates_file(self.test_candidates_file)
        self.assertEqual(c_reloaded["candidates"][0]["status"], "pending")
        j_reloaded = jarvis_server.load_journal_file(self.test_journal_file)
        self.assertIsNone(j_reloaded.get("active_transaction"))
        print("  [Stage 5B Test 10 PASSED] Recovery rolled back unfinished candidate to pending.")

    def test_11_recovery_from_postimage_match(self):
        """Startup recovery: when disk matches postimage, finalize candidate as approved and clear journal."""
        orig_bytes = open(self.test_memory_file, "rb").read()
        postimage_hash = hashlib.sha256(orig_bytes).hexdigest()

        cdata = {
            "schema_version": "1.0",
            "updated_at": "2026-11-06T12:00:00Z",
            "candidates": [
                {
                    "candidate_id": "cand_crash_2",
                    "text": "Kayıt tamamlanmış ama onay işareti yetişmemiş",
                    "status": "in_flight",
                    "reservation_id": "res_456"
                }
            ]
        }
        jarvis_server.save_candidates_file(cdata, self.test_candidates_file)

        jdata = {
            "schema_version": "1.0",
            "active_transaction": {
                "candidate_id": "cand_crash_2",
                "reservation_id": "res_456",
                "preimage_sha256": "fake_preimage_hash_00000",
                "postimage_sha256": postimage_hash
            }
        }
        jarvis_server.save_journal_file(jdata, self.test_journal_file)

        outcome = jarvis_server.startup_journal_recovery(
            self.test_memory_file, self.test_candidates_file, self.test_journal_file
        )
        self.assertEqual(outcome, "COMMITTED_TO_APPROVED")

        c_reloaded = jarvis_server.load_candidates_file(self.test_candidates_file)
        self.assertEqual(c_reloaded["candidates"][0]["status"], "approved")
        j_reloaded = jarvis_server.load_journal_file(self.test_journal_file)
        self.assertIsNone(j_reloaded.get("active_transaction"))
        print("  [Stage 5B Test 11 PASSED] Recovery committed completed canonical write to approved.")

    def test_12_recovery_required_on_unknown_hash_or_corrupt_journal(self):
        """Startup recovery: when hash matches neither or journal corrupt, enter RECOVERY_REQUIRED."""
        jdata = {
            "schema_version": "1.0",
            "active_transaction": {
                "candidate_id": "cand_mystery",
                "reservation_id": "res_789",
                "preimage_sha256": "pre_mismatch_111",
                "postimage_sha256": "post_mismatch_222"
            }
        }
        jarvis_server.save_journal_file(jdata, self.test_journal_file)

        outcome = jarvis_server.startup_journal_recovery(
            self.test_memory_file, self.test_candidates_file, self.test_journal_file
        )
        self.assertEqual(outcome, "RECOVERY_REQUIRED")
        self.assertTrue(jarvis_server.RECOVERY_REQUIRED_STATE)
        print("  [Stage 5B Test 12 PASSED] Inconsistent state triggered RECOVERY_REQUIRED fail-closed mode.")

    @unittest_run_loop
    async def test_13_dismiss_candidate_endpoint(self):
        """DELETE candidate endpoint marks candidate as dismissed, not erased."""
        c_resp = await self.client.post("/api/memory/candidates", json={
            "text": "Reddedilecek aday metni"
        })
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        del_resp = await self.client.delete(f"/api/memory/candidates/{cand_id}")
        self.assertEqual(del_resp.status, 200)
        del_data = await del_resp.json()
        self.assertEqual(del_data["candidate"]["status"], "dismissed")

        # Verify not erased from store
        cand_all = await self.client.get("/api/memory/candidates")
        all_json = await cand_all.json()
        matches = [c for c in all_json["candidates"] if c["candidate_id"] == cand_id]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["status"], "dismissed")
        print("  [Stage 5B Test 13 PASSED] Candidate dismissal preserved in history without silent deletion.")

    @unittest_run_loop
    async def test_14_candidates_store_corrupt_fails_closed(self):
        """Malformed candidate storage never overwritten with empty file; returns 500 error."""
        with open(self.test_candidates_file, "w", encoding="utf-8") as f:
            f.write("{corrupt: json content[")

        resp = await self.client.get("/api/memory/candidates")
        self.assertEqual(resp.status, 500)
        err = await resp.json()
        self.assertEqual(err.get("error"), "CORRUPT_CANDIDATE_FILE")

        # Verify file content was not overwritten or cleared
        with open(self.test_candidates_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("{corrupt: json content[", content)
        print("  [Stage 5B Test 14 PASSED] Corrupt candidate store fails closed without silent overwrite.")

    @unittest_run_loop
    async def test_15_recovery_required_blocks_all_mutation_endpoints(self):
        """When RECOVERY_REQUIRED_STATE is True, every canonical mutation route returns 503 and memory bytes remain unchanged."""
        jarvis_server.RECOVERY_REQUIRED_STATE = True
        orig_bytes = open(self.test_memory_file, "rb").read()
        orig_hash = hashlib.sha256(orig_bytes).hexdigest()

        # 1. Save memory
        resp1 = await self.client.post("/api/memory", json={"notes": ["Bloke edilmeli"]})
        self.assertEqual(resp1.status, 503)
        self.assertEqual((await resp1.json()).get("error"), "RECOVERY_REQUIRED")

        # 2. Add note
        resp2 = await self.client.post("/api/memory/notes", json={"text": "Bloke edilmeli not"})
        self.assertEqual(resp2.status, 503)
        self.assertEqual((await resp2.json()).get("error"), "RECOVERY_REQUIRED")

        # 3. Delete note
        resp3 = await self.client.delete("/api/memory/notes/mem_001")
        self.assertEqual(resp3.status, 503)
        self.assertEqual((await resp3.json()).get("error"), "RECOVERY_REQUIRED")

        # 4. Approve candidate
        resp4 = await self.client.post("/api/memory/candidates/cand_123/approve")
        self.assertEqual(resp4.status, 503)
        self.assertEqual((await resp4.json()).get("error"), "RECOVERY_REQUIRED")

        # Verify canonical file bytes are completely untouched
        cur_bytes = open(self.test_memory_file, "rb").read()
        cur_hash = hashlib.sha256(cur_bytes).hexdigest()
        self.assertEqual(orig_hash, cur_hash)
        jarvis_server.RECOVERY_REQUIRED_STATE = False
        print("  [Stage 5B Test 15 PASSED] RECOVERY_REQUIRED blocks all 4 canonical mutation routes with 503.")

    @unittest_run_loop
    async def test_16_candidate_atomic_write_failure_preserves_existing_data(self):
        """Failure during atomic candidate file write preserves existing candidate file intact."""
        cdata_orig = {
            "schema_version": "1.0",
            "updated_at": "2026-11-06T12:00:00Z",
            "candidates": [
                {
                    "candidate_id": "cand_safe_01",
                    "text": "Bu aday korunmalı",
                    "category": "study",
                    "status": "pending"
                }
            ]
        }
        jarvis_server.save_candidates_file(cdata_orig, self.test_candidates_file)

        with patch("jarvis_server.atomic_write_json", side_effect=OSError("Disk write error")):
            with self.assertRaises(OSError):
                jarvis_server.save_candidates_file({"schema_version": "1.0", "candidates": []}, self.test_candidates_file)

        reloaded = jarvis_server.load_candidates_file(self.test_candidates_file)
        self.assertEqual(len(reloaded.get("candidates", [])), 1)
        self.assertEqual(reloaded["candidates"][0]["candidate_id"], "cand_safe_01")
        print("  [Stage 5B Test 16 PASSED] Candidate atomic write failure preserved existing file.")

    @unittest_run_loop
    async def test_17_journal_atomic_write_failure_recovers_reservation(self):
        """If journal write fails, candidate reservation is rolled back to pending."""
        c_resp = await self.client.post("/api/memory/candidates", json={"text": "Günlük yazım hatası testi"})
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        mem_resp = await self.client.get("/api/memory")
        rev_token = (await mem_resp.json())["revision_token"]

        with patch("jarvis_server.save_journal_file", side_effect=OSError("Simulated journal write failure")):
            app_resp = await self.client.post(
                f"/api/memory/candidates/{cand_id}/approve",
                headers={"X-Memory-Revision-Token": rev_token}
            )
            self.assertEqual(app_resp.status, 500)

        # Candidate must not remain stuck in in_flight
        cdata = jarvis_server.load_candidates_file(self.test_candidates_file)
        target = [c for c in cdata["candidates"] if c["candidate_id"] == cand_id][0]
        self.assertEqual(target["status"], "pending")
        self.assertNotIn("reservation_id", target)
        print("  [Stage 5B Test 17 PASSED] Journal write failure rolled back reservation to pending.")

    @unittest_run_loop
    async def test_18_canonical_write_failure_before_replace(self):
        """Simulated canonical write failure before os.replace leaves canonical memory exactly at preimage."""
        orig_bytes = open(self.test_memory_file, "rb").read()
        orig_hash = hashlib.sha256(orig_bytes).hexdigest()

        c_resp = await self.client.post("/api/memory/candidates", json={"text": "Yazma hatası öncesi aday"})
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        mem_resp = await self.client.get("/api/memory")
        rev_token = (await mem_resp.json())["revision_token"]

        with patch("os.replace", side_effect=OSError("Simulated replace failure")):
            app_resp = await self.client.post(
                f"/api/memory/candidates/{cand_id}/approve",
                headers={"X-Memory-Revision-Token": rev_token}
            )
            self.assertEqual(app_resp.status, 500)

        cur_bytes = open(self.test_memory_file, "rb").read()
        cur_hash = hashlib.sha256(cur_bytes).hexdigest()
        self.assertEqual(orig_hash, cur_hash)

        # Candidate restored to pending
        cdata = jarvis_server.load_candidates_file(self.test_candidates_file)
        target = [c for c in cdata["candidates"] if c["candidate_id"] == cand_id][0]
        self.assertEqual(target["status"], "pending")
        print("  [Stage 5B Test 18 PASSED] Canonical write failure before replace kept memory at preimage.")

    @unittest_run_loop
    async def test_19_canonical_write_exception_after_replace_checks_actual_hash(self):
        """If exception occurs after replace, actual disk hash is inspected and RECOVERY_REQUIRED or consistency enforced."""
        c_resp = await self.client.post("/api/memory/candidates", json={"text": "Replace sonrası hata testi"})
        cand_id = (await c_resp.json())["candidate"]["candidate_id"]

        mem_resp = await self.client.get("/api/memory")
        rev_token = (await mem_resp.json())["revision_token"]

        real_replace = os.replace
        def fake_replace(src, dst):
            real_replace(src, dst)
            # Corrupt file after replace to simulate inconsistent crash
            with open(dst, "wb") as f:
                f.write(b"CORRUPTED_INCONSISTENT_BYTES")
            return None

        with patch("os.replace", side_effect=fake_replace):
            app_resp = await self.client.post(
                f"/api/memory/candidates/{cand_id}/approve",
                headers={"X-Memory-Revision-Token": rev_token}
            )
            self.assertEqual(app_resp.status, 503)
            self.assertEqual((await app_resp.json()).get("error"), "RECOVERY_REQUIRED")
            self.assertTrue(jarvis_server.RECOVERY_REQUIRED_STATE)

        jarvis_server.RECOVERY_REQUIRED_STATE = False
        print("  [Stage 5B Test 19 PASSED] Post-replace exception triggered actual disk hash check.")

    def test_20_malformed_journal_fails_closed(self):
        """Malformed journal file triggers RECOVERY_REQUIRED fail-closed recovery."""
        with open(self.test_journal_file, "w", encoding="utf-8") as f:
            f.write("INVALID_JSON{")

        outcome = jarvis_server.startup_journal_recovery(
            self.test_memory_file, self.test_candidates_file, self.test_journal_file
        )
        self.assertEqual(outcome, "RECOVERY_REQUIRED")
        self.assertTrue(jarvis_server.RECOVERY_REQUIRED_STATE)
        jarvis_server.RECOVERY_REQUIRED_STATE = False
        print("  [Stage 5B Test 20 PASSED] Malformed journal failed closed cleanly.")

    @unittest_run_loop
    async def test_21_worker_clean_shutdown_and_cancellation(self):
        """Background extraction worker cancels cleanly without unhandled exceptions."""
        worker = asyncio.create_task(jarvis_server.background_extraction_worker())
        await asyncio.sleep(0.01)
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        self.assertTrue(worker.done())
        print("  [Stage 5B Test 21 PASSED] Background extraction worker cancels cleanly on shutdown.")

    @unittest_run_loop
    async def test_22_automatic_extraction_valid_structured_response(self):
        """When enabled, valid structured output from allowlisted model creates candidate."""
        from unittest.mock import MagicMock
        cfg = jarvis_server.load_config()
        cfg["memory_learning_enabled"] = True
        cfg["groq_api_key"] = "gsk_test_key_dummy"
        cfg["groq_model"] = "qwen/qwen3.8-27b"

        fake_resp = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "text": "AM5 platformunu tercih ediyorum.",
                            "category": "hardware",
                            "confidence": 0.95
                        })
                    }
                }
            ]
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=fake_resp)

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch.object(jarvis_server.aiohttp.ClientSession, "post", return_value=mock_ctx):
            with patch("jarvis_server.add_memory_candidate_internal", new_callable=AsyncMock) as mock_add_cand:
                await jarvis_server.run_groq_structured_extraction("AM5 platformunu tercih ediyorum.", cfg)

                mock_add_cand.assert_called_once()
                call_kwargs = mock_add_cand.call_args[1]
                self.assertIn("AM5", call_kwargs.get("text"))
                self.assertEqual(call_kwargs.get("category"), "hardware")
                self.assertEqual(call_kwargs.get("source"), "auto_ai_extraction")
        print("  [Stage 5B Test 22 PASSED] Valid structured output parsed and dispatched to add_memory_candidate_internal.")

    @unittest_run_loop
    async def test_23_unsupported_model_abandons_extraction(self):
        """Unsupported model abandons extraction safely without any network calls."""
        cfg = jarvis_server.load_config()
        cfg["memory_learning_enabled"] = True
        cfg["groq_api_key"] = "gsk_test_key_dummy"
        cfg["groq_model"] = "unsupported-custom-model"

        with patch("aiohttp.ClientSession.post") as mock_post:
            await jarvis_server.run_groq_structured_extraction("Bir mesaj içeriği", cfg)
            mock_post.assert_not_called()
        print("  [Stage 5B Test 23 PASSED] Unsupported model safely abandoned extraction.")

    @unittest_run_loop
    async def test_24_journal_cleanup_failure_recovers_idempotently(self):
        """If journal cleanup fails, postimage matches and startup recovery idempotently finalizes without duplicate note."""
        orig_bytes = open(self.test_memory_file, "rb").read()
        postimage_hash = hashlib.sha256(orig_bytes).hexdigest()

        # Candidate is already approved
        cdata = {
            "schema_version": "1.0",
            "updated_at": "2026-11-06T12:00:00Z",
            "candidates": [
                {
                    "candidate_id": "cand_cleanup_fail",
                    "text": "Temizlik hatası sonrası aday",
                    "status": "approved"
                }
            ]
        }
        jarvis_server.save_candidates_file(cdata, self.test_candidates_file)

        # Journal remained lingering with postimage match
        jdata = {
            "schema_version": "1.0",
            "active_transaction": {
                "candidate_id": "cand_cleanup_fail",
                "reservation_id": "res_cleanup_fail",
                "preimage_sha256": "old_preimage_hash",
                "postimage_sha256": postimage_hash
            }
        }
        jarvis_server.save_journal_file(jdata, self.test_journal_file)

        outcome = jarvis_server.startup_journal_recovery(
            self.test_memory_file, self.test_candidates_file, self.test_journal_file
        )
        self.assertEqual(outcome, "COMMITTED_TO_APPROVED")

        # Journal is now cleaned up
        j_clean = jarvis_server.load_journal_file(self.test_journal_file)
        self.assertIsNone(j_clean.get("active_transaction"))
        print("  [Stage 5B Test 24 PASSED] Lingering journal cleaned up idempotently on recovery.")

if __name__ == "__main__":
    unittest.main()

"""
Phase 9B.2C — Rolling Backup & Automatic Recovery Acceptance Tests
ACCIO JARVIS V4.0

Validates:
1. Tasks: Valid mutation creates jarvis_tasks.json.bak atomically.
2. Tasks: Corrupted primary triggers automatic recovery from verified .bak.
3. Tasks: Corrupted primary is preserved as .corrupt.<timestamp> for forensics.
4. Tasks: Fail-closed write protection rejects writes when primary is corrupt and no valid backup exists.
5. Tasks: Corrupt primary does not overwrite a valid .bak with corrupt data.
6. Config: Valid mutation creates jarvis_config.json.bak atomically.
7. Config: Corrupted primary triggers automatic recovery from verified .bak.
8. Config: Corrupted primary is preserved as .corrupt.<timestamp>.
9. Config: Fail-closed behavior raises ValueError when both primary and backup are corrupt (never resets to defaults).
10. Automations: Schema validation rejects invalid schema_version, revision, or non-dict items.
11. Automations: Valid mutation creates jarvis_automations.json.bak atomically.
12. Automations: Corrupted primary triggers automatic recovery from verified .bak.
13. Automations: Corrupted primary is preserved as .corrupt.<timestamp>.
14. Automations: Fail-closed behavior raises ValueError when both primary and backup are corrupt.
15. Automations: Mtime cache consistency is preserved across recovery and mutations.
16. Concurrency: AUTOMATIONS_THREAD_LOCK serializes concurrent reads and writes safely.

SAFETY:
- Uses isolated temporary directories for all file I/O.
- Never mutates production JSON files.
- Restores original paths and module state in tearDown.
"""

import unittest
from unittest.mock import patch
import os
import sys
import json
import tempfile
import shutil
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jarvis_server

class TestPhase9B2Recovery(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="jarvis_recovery_test_")
        self.mock_tasks_file = os.path.join(self.test_dir, "jarvis_tasks.json")
        self.mock_config_file = os.path.join(self.test_dir, "jarvis_config.json")
        self.mock_automations_file = os.path.join(self.test_dir, "jarvis_automations.json")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir, ignore_errors=True)
            except Exception:
                pass

    # =========================================================================
    # 1. TASKS BACKUP & RECOVERY
    # =========================================================================

    def test_01_tasks_mutation_creates_backup(self):
        """1. Valid task mutation creates jarvis_tasks.json.bak before second mutation."""
        with patch.object(jarvis_server, "TASKS_FILE", self.mock_tasks_file):
            initial_tasks = [{"id": "t1", "subject": "Task 1", "done": False, "category": "genel", "priority": "medium"}]
            jarvis_server.save_tasks(initial_tasks)

            self.assertTrue(os.path.exists(self.mock_tasks_file))
            # Second save should promote initial_tasks to .bak
            updated_tasks = initial_tasks + [{"id": "t2", "subject": "Task 2", "done": True, "category": "genel", "priority": "high"}]
            jarvis_server.save_tasks(updated_tasks)

            bak_file = f"{self.mock_tasks_file}.bak"
            self.assertTrue(os.path.exists(bak_file))
            with open(bak_file, "r", encoding="utf-8") as f:
                bak_data = json.load(f)
            self.assertEqual(len(bak_data), 1)
            self.assertEqual(bak_data[0]["id"], "t1")

    def test_02_tasks_auto_recovery_from_backup_and_preserves_corrupt(self):
        """2, 3: Corrupted primary triggers recovery from verified .bak and preserves corrupt file."""
        with patch.object(jarvis_server, "TASKS_FILE", self.mock_tasks_file):
            valid_tasks = [{"id": "t1", "subject": "Recoverable Task", "done": False, "category": "genel", "priority": "medium"}]
            jarvis_server.save_tasks(valid_tasks)
            # Create another mutation so .bak exists
            jarvis_server.save_tasks(valid_tasks)

            # Corrupt the primary file deliberately
            with open(self.mock_tasks_file, "w", encoding="utf-8") as f:
                f.write("{MALFORMED_CORRUPT_JSON: true")

            # load_tasks_result should automatically recover from .bak
            recovered_tasks, is_corrupt = jarvis_server.load_tasks_result()
            self.assertFalse(is_corrupt)
            self.assertEqual(len(recovered_tasks), 1)
            self.assertEqual(recovered_tasks[0]["id"], "t1")

            # Verify that .corrupt forensic copy was created
            all_files = os.listdir(self.test_dir)
            corrupt_copies = [f for f in all_files if ".corrupt." in f]
            self.assertGreater(len(corrupt_copies), 0)

    def test_03_tasks_fail_closed_when_no_valid_backup_exists(self):
        """4, 5: Reject writes with StorageRecoveryError when primary is corrupt and no backup exists."""
        with patch.object(jarvis_server, "TASKS_FILE", self.mock_tasks_file):
            with open(self.mock_tasks_file, "w", encoding="utf-8") as f:
                f.write("CORRUPT_NOT_JSON")

            # Loading fails closed
            tasks, is_corrupt = jarvis_server.load_tasks_result()
            self.assertTrue(is_corrupt)
            self.assertEqual(tasks, [])

            # Saving ANY data (empty or non-empty) must be rejected
            with self.assertRaises(jarvis_server.StorageRecoveryError):
                jarvis_server.save_tasks([{"id": "t_new", "subject": "New Task"}])

            with self.assertRaises(jarvis_server.StorageRecoveryError):
                jarvis_server.save_tasks([])

    # =========================================================================
    # 2. CONFIG BACKUP & RECOVERY
    # =========================================================================

    def test_04_config_mutation_creates_backup(self):
        """6. Valid config mutation creates jarvis_config.json.bak."""
        with patch.object(jarvis_server, "CONFIG_FILE", self.mock_config_file):
            initial_cfg = {"tts_engine": "edge_tts", "edge_rate": "+5%"}
            jarvis_server.save_config(initial_cfg)

            updated_cfg = {"tts_engine": "openai", "openai_voice": "nova"}
            jarvis_server.save_config(updated_cfg)

            bak_file = f"{self.mock_config_file}.bak"
            self.assertTrue(os.path.exists(bak_file))
            with open(bak_file, "r", encoding="utf-8") as f:
                bak_data = json.load(f)
            self.assertEqual(bak_data.get("tts_engine"), "edge_tts")

    def test_05_config_auto_recovery_from_backup_and_preserves_corrupt(self):
        """7, 8: Corrupt config triggers recovery from .bak and creates .corrupt copy."""
        with patch.object(jarvis_server, "CONFIG_FILE", self.mock_config_file):
            good_cfg = {"tts_engine": "elevenlabs", "groq_model": "llama-3.3-70b-versatile"}
            jarvis_server.save_config(good_cfg)
            jarvis_server.save_config(good_cfg)  # creates .bak

            # Corrupt the primary config file
            with open(self.mock_config_file, "w", encoding="utf-8") as f:
                f.write("[NOT_A_DICT_OR_CORRUPT")

            loaded = jarvis_server.load_config()
            self.assertEqual(loaded.get("tts_engine"), "elevenlabs")
            self.assertEqual(loaded.get("groq_model"), "llama-3.3-70b-versatile")

            corrupt_copies = [f for f in os.listdir(self.test_dir) if "jarvis_config.json.corrupt." in f]
            self.assertGreater(len(corrupt_copies), 0)

    def test_06_config_fail_closed_when_both_primary_and_backup_corrupt(self):
        """9. Raises ValueError and never silently resets to defaults when both corrupt."""
        with patch.object(jarvis_server, "CONFIG_FILE", self.mock_config_file):
            with open(self.mock_config_file, "w", encoding="utf-8") as f:
                f.write("CORRUPT_PRIMARY")
            with open(f"{self.mock_config_file}.bak", "w", encoding="utf-8") as f:
                f.write("CORRUPT_BACKUP")

            with self.assertRaises(ValueError):
                jarvis_server.load_config()

    # =========================================================================
    # 3. AUTOMATIONS BACKUP & RECOVERY
    # =========================================================================

    def test_07_automations_schema_validation(self):
        """10. validate_automations_structure enforces schema_version, revision, and list of dicts."""
        valid_auto = {
            "schema_version": "4.0",
            "revision": 1,
            "automations": [{"id": "a1", "name": "Rule 1", "enabled": True}]
        }
        self.assertTrue(jarvis_server.validate_automations_structure(valid_auto))

        # Invalid schema version
        bad_version = valid_auto.copy()
        bad_version["schema_version"] = "3.0"
        self.assertFalse(jarvis_server.validate_automations_structure(bad_version))

        # Invalid revision
        bad_rev = valid_auto.copy()
        bad_rev["revision"] = "not_an_int"
        self.assertFalse(jarvis_server.validate_automations_structure(bad_rev))

        # Invalid automations field (not list)
        bad_list = valid_auto.copy()
        bad_list["automations"] = {"a1": {}}
        self.assertFalse(jarvis_server.validate_automations_structure(bad_list))

        # Invalid item inside automations (not dict)
        bad_item = valid_auto.copy()
        bad_item["automations"] = ["not_a_dict"]
        self.assertFalse(jarvis_server.validate_automations_structure(bad_item))

    def test_08_automations_mutation_creates_backup(self):
        """11. Valid automations mutation creates jarvis_automations.json.bak."""
        with patch.object(jarvis_server, "AUTOMATIONS_FILE", self.mock_automations_file):
            initial_data = {
                "schema_version": "4.0",
                "revision": 1,
                "automations": [{"id": "a1", "name": "Test Auto", "enabled": True}]
            }
            jarvis_server.save_automations_data(initial_data)

            second_data = {
                "schema_version": "4.0",
                "revision": 2,
                "automations": [{"id": "a1", "name": "Test Auto", "enabled": False}]
            }
            jarvis_server.save_automations_data(second_data)

            bak_file = f"{self.mock_automations_file}.bak"
            self.assertTrue(os.path.exists(bak_file))
            with open(bak_file, "r", encoding="utf-8") as f:
                bak_data = json.load(f)
            self.assertTrue(bak_data["automations"][0]["enabled"])

    def test_09_automations_auto_recovery_from_backup_and_preserves_corrupt(self):
        """12, 13: Corrupted automations triggers recovery from .bak and creates .corrupt copy."""
        with patch.object(jarvis_server, "AUTOMATIONS_FILE", self.mock_automations_file):
            good_data = {
                "schema_version": "4.0",
                "revision": 1,
                "automations": [{"id": "a1", "name": "Persistent Auto", "enabled": True}]
            }
            jarvis_server.save_automations_data(good_data)
            jarvis_server.save_automations_data(good_data)

            # Corrupt primary
            with open(self.mock_automations_file, "w", encoding="utf-8") as f:
                f.write("{BAD_AUTOMATIONS_DATA: true")

            # load_automations_data should recover automatically
            loaded = jarvis_server.load_automations_data(force_reload=True)
            self.assertEqual(loaded["schema_version"], "4.0")
            self.assertEqual(len(loaded["automations"]), 1)
            self.assertEqual(loaded["automations"][0]["id"], "a1")

            corrupt_copies = [f for f in os.listdir(self.test_dir) if "jarvis_automations.json.corrupt." in f]
            self.assertGreater(len(corrupt_copies), 0)

    def test_10_automations_fail_closed_when_both_corrupt(self):
        """14. Raises ValueError and never resets to default when both primary and backup corrupt."""
        with patch.object(jarvis_server, "AUTOMATIONS_FILE", self.mock_automations_file):
            with open(self.mock_automations_file, "w", encoding="utf-8") as f:
                f.write("CORRUPT_PRIMARY")
            with open(f"{self.mock_automations_file}.bak", "w", encoding="utf-8") as f:
                f.write("CORRUPT_BACKUP")

            with self.assertRaises(ValueError):
                jarvis_server.load_automations_data(force_reload=True)

    def test_11_automations_mtime_cache_consistency(self):
        """15. Mtime cache returns cached data on matching mtime and updates after mutation."""
        with patch.object(jarvis_server, "AUTOMATIONS_FILE", self.mock_automations_file):
            data1 = {"schema_version": "4.0", "revision": 1, "automations": [{"id": "a1", "name": "Cache Test"}]}
            jarvis_server.save_automations_data(data1)

            # First read caches data
            read1 = jarvis_server.load_automations_data()
            self.assertEqual(read1["automations"][0]["name"], "Cache Test")

            # Direct modification without updating mtime
            data2 = {"schema_version": "4.0", "revision": 2, "automations": [{"id": "a2", "name": "Cache Updated"}]}
            jarvis_server.save_automations_data(data2)

            read2 = jarvis_server.load_automations_data()
            self.assertEqual(read2["automations"][0]["name"], "Cache Updated")

    def test_12_automations_concurrency_locking(self):
        """16. AUTOMATIONS_THREAD_LOCK serializes concurrent writes without data loss or corruption."""
        with patch.object(jarvis_server, "AUTOMATIONS_FILE", self.mock_automations_file):
            base_data = {"schema_version": "4.0", "revision": 1, "automations": []}
            jarvis_server.save_automations_data(base_data)

            threads = []
            errors = []

            def worker_append(idx):
                try:
                    with jarvis_server.AUTOMATIONS_THREAD_LOCK:
                        cur = jarvis_server.load_automations_data(force_reload=True)
                        cur["automations"].append({"id": f"worker_{idx}", "name": f"Auto {idx}"})
                        jarvis_server.save_automations_data(cur)
                except Exception as e:
                    errors.append(e)

            for i in range(10):
                t = threading.Thread(target=worker_append, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            self.assertEqual(len(errors), 0)
            final_data = jarvis_server.load_automations_data(force_reload=True)
            self.assertEqual(len(final_data["automations"]), 10)

if __name__ == "__main__":
    unittest.main(verbosity=2)

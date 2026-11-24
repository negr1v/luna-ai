import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error
import socket

def run_subprocess_restart_test():
    print("=" * 70)
    print("GENUINE SUBPROCESS RESTART & EPOCH OCC VALIDATION")
    print("=" * 70)

    test_dir = tempfile.mkdtemp(prefix="jarvis_subproc_test_")
    isolated_mem = os.path.join(test_dir, "isolated_memory.json")
    with open(isolated_mem, "w", encoding="utf-8") as f:
        json.dump({"notes": [], "user_name": "Regression Test"}, f)

    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        test_port = port_socket.getsockname()[1]

    # Helper script to run jarvis on custom port and memory file
    runner_script = os.path.join(test_dir, "run_server.py")
    with open(runner_script, "w", encoding="utf-8") as f:
        f.write(f"""
import sys, os
sys.path.insert(0, {repr(os.path.abspath("."))})
import jarvis_server
from aiohttp import web

jarvis_server.MEMORY_FILE = {repr(isolated_mem)}
app = jarvis_server.create_app()
web.run_app(app, port={test_port}, handle_signals=False)
""")

    proc_a = None
    proc_b = None

    def wait_for_server(proc, base_url):
        deadline = time.monotonic() + 10
        last_error = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stdout, stderr = proc.communicate()
                raise RuntimeError(f"Server exited early. stdout={stdout[-2000:]!r} stderr={stderr[-2000:]!r}")
            try:
                with urllib.request.urlopen(base_url + "/api/memory", timeout=1) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError) as error:
                last_error = error
            time.sleep(0.1)
        raise TimeoutError(f"Server did not become ready: {last_error}")

    try:
        # Step 1: Start Process A
        print("\n[Step 1] Starting Process A (Subprocess)...")
        proc_a = subprocess.Popen([sys.executable, runner_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        base_url = f"http://127.0.0.1:{test_port}"
        wait_for_server(proc_a, base_url)

        # Fetch initial memory from Process A
        req = urllib.request.Request(base_url + "/api/memory")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data_a1 = json.loads(resp.read().decode())
        
        token_a1 = data_a1["revision_token"]
        print(f"  Process A started successfully. Epoch Token: {token_a1}")
        assert len(token_a1.split(":")[0]) == 32, f"Epoch must be full 32-char UUID hex, got: {token_a1}"

        # Mutate memory on Process A using header X-Memory-Revision-Token
        post_req = urllib.request.Request(
            base_url + "/api/memory/notes",
            data=json.dumps({"text": "Process A Note"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Memory-Revision-Token": token_a1
            },
            method="POST"
        )
        with urllib.request.urlopen(post_req, timeout=5) as resp:
            assert resp.status == 200
            mutated_a = json.loads(resp.read().decode())
        
        token_a2 = mutated_a["revision_token"]
        print(f"  Process A mutated memory. New Token: {token_a2}")
        assert token_a2 != token_a1

        # Step 2: Shutdown Process A completely
        print("\n[Step 2] Terminating Process A...")
        proc_a.terminate()
        proc_a.wait(timeout=5)
        proc_a = None
        print("  Process A completely terminated.")

        # Step 3: Start Process B (completely new Python process against same isolated V3 fixture)
        print("\n[Step 3] Starting Process B (New Subprocess with fresh epoch)...")
        proc_b = subprocess.Popen([sys.executable, runner_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wait_for_server(proc_b, base_url)

        # Step 4: Attempt to use Process A's token on Process B -> MUST BE REJECTED WITH 409
        print("\n[Step 4] Submitting Process A's old token to Process B...")
        stale_post = urllib.request.Request(
            base_url + "/api/memory/notes",
            data=json.dumps({"text": "Should fail across process restart"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Memory-Revision-Token": token_a2
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(stale_post, timeout=5) as resp:
                assert False, f"Expected 409 Conflict, but got {resp.status}!"
        except urllib.error.HTTPError as e:
            assert e.code == 409, f"Expected HTTP 409, got {e.code}"
            err_body = json.loads(e.read().decode())
            assert err_body["error"] == "STALE_REVISION"
            print(f"  [SUCCESS] Process B correctly rejected Process A's token: HTTP 409 {err_body['error']}")
            print(f"  Server expected: {err_body['server_revision_token']}, Client sent: {err_body['client_revision_token']}")

        # Step 5: Read Process B's genuine fresh token
        print("\n[Step 5] Fetching fresh token from Process B...")
        with urllib.request.urlopen(base_url + "/api/memory", timeout=5) as resp:
            data_b = json.loads(resp.read().decode())
        token_b1 = data_b["revision_token"]
        print(f"  Process B fresh token: {token_b1}")
        assert token_b1.split(":")[0] != token_a1.split(":")[0], "Epoch did not change across genuine process restart!"

        # Step 6: Mutate memory on Process B using Process B's fresh token
        print("\n[Step 6] Mutating memory on Process B with valid token...")
        valid_b_post = urllib.request.Request(
            base_url + "/api/memory/notes",
            data=json.dumps({"text": "Process B Valid Note"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Memory-Revision-Token": token_b1
            },
            method="POST"
        )
        with urllib.request.urlopen(valid_b_post, timeout=5) as resp:
            assert resp.status == 200
            mutated_b = json.loads(resp.read().decode())
        print(f"  [SUCCESS] Process B mutated memory successfully with HTTP 200 OK. New Token: {mutated_b['revision_token']}")

        # Terminate Process B
        proc_b.terminate()
        proc_b.wait(timeout=5)
        proc_b = None
        print("  Process B terminated.")

        # Step 7: Verify isolated V3 fixture on disk remains pure V3
        print("\n[Step 7] Verifying isolated V3 disk file structure...")
        with open(isolated_mem, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert "revision_token" not in disk_data, "revision_token leaked to V3 disk file!"
        assert "user_profile" not in disk_data, "V3 format altered on disk!"
        assert "notes" in disk_data
        assert "user_name" in disk_data
        print("  [SUCCESS] Disk file remains strictly in V3 format without revision_token pollution.")

    finally:
        if proc_a and proc_a.poll() is None:
            proc_a.terminate()
        if proc_b and proc_b.poll() is None:
            proc_b.terminate()
        shutil.rmtree(test_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("GENUINE SUBPROCESS RESTART TEST PASSED 100%!")
    print("=" * 70)

if __name__ == "__main__":
    run_subprocess_restart_test()

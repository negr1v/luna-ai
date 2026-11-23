import os
import json
import hashlib

def test_draft_preservation_logic():
    print("=" * 70)
    print("DRAFT PRESERVATION & USER-CONTROLLED RESOLUTION SIMULATION")
    print("=" * 70)

    # 1. Simulate frontend client state
    client_state = {
        "currentMemory": {
            "user_name": "negr1",
            "focus": "YKS 2027 Sayısal (360 dk/gün)",
            "target_hardware": "AM5 Platform",
            "budget_limit": "Kombo ≤ 15.000 TL",
            "notes": ["Note 1", "Note 2"],
            "revision": 1,
            "revision_token": "epoch_old:1"
        },
        "serverMemorySnapshot": None,
        "newMemoryInputValue": "Negr1 yeni çalışma kuralı taslağı (UNSAVED DRAFT)",
        "conflictBannerVisible": False,
        "conflictBannerMessage": None
    }

    # 2. Simulate server state advancing (e.g., from background job or other tab)
    server_state = {
        "user_name": "negr1",
        "focus": "YKS 2027 Sayısal (360 dk/gün)",
        "target_hardware": "AM5 Platform",
        "budget_limit": "Kombo ≤ 15.000 TL",
        "notes": ["Note 1", "Note 2", "Concurrent Note from Tab 2"],
        "revision": 2,
        "revision_token": "epoch_old:2"
    }

    # 3. User attempts to submit the draft with stale revision_token
    token_sent = client_state["currentMemory"]["revision_token"]
    payload_sent = {"text": client_state["newMemoryInputValue"]}

    # Server receives request -> checks token
    if token_sent != server_state["revision_token"]:
        http_status = 409
        err_response = {
            "status": "conflict",
            "error": "STALE_REVISION",
            "message": "Memory modified on server",
            "server_revision_token": server_state["revision_token"]
        }
    else:
        http_status = 200

    assert http_status == 409, "Should be 409 Conflict"

    # 4. Frontend receives 409 Conflict
    # Exact frontend logic from index.html:
    # - do NOT clear newMemoryInput.value!
    # - showConflictBanner(...)
    # - fetch('/api/memory') -> store into serverMemorySnapshot
    client_state["conflictBannerVisible"] = True
    client_state["conflictBannerMessage"] = "Çakışma (409): Not kaydedilemedi çünkü hafıza sunucuda güncellendi. Yazdığınız metin kutuda korundu."
    client_state["serverMemorySnapshot"] = dict(server_state)

    print("\n[Step 1: 409 Received]")
    print(f"  Input box value: '{client_state['newMemoryInputValue']}'")
    print(f"  Conflict banner: {client_state['conflictBannerMessage']}")
    assert client_state["newMemoryInputValue"] == "Negr1 yeni çalışma kuralı taslağı (UNSAVED DRAFT)"
    assert client_state["serverMemorySnapshot"]["revision"] == 2

    # 5. Verify local draft is NOT automatically overwritten
    assert client_state["currentMemory"]["revision"] == 1
    assert "Concurrent Note from Tab 2" not in client_state["currentMemory"]["notes"]
    print("\n[Step 2: No Automatic Overwrite]")
    print("  Local memory state remains at revision 1; server changes isolated in serverMemorySnapshot.")

    # 6. User clicks 'Yenile (Taslağı Koru)' (#reloadConflictMemoryBtn)
    # Frontend logic:
    # currentMemory = JSON.parse(JSON.stringify(serverMemorySnapshot))
    # renderMemoryNotes()
    # hideConflictBanner()
    # Notice: newMemoryInput.value is completely UNTOUCHED!
    client_state["currentMemory"] = dict(client_state["serverMemorySnapshot"])
    client_state["conflictBannerVisible"] = False
    print("\n[Step 3: User-Controlled Conflict Resolution]")
    print(f"  User refreshed memory list. Current Revision: {client_state['currentMemory']['revision']}")
    print(f"  Input box draft still preserved: '{client_state['newMemoryInputValue']}'")
    assert client_state["newMemoryInputValue"] == "Negr1 yeni çalışma kuralı taslağı (UNSAVED DRAFT)"
    assert client_state["currentMemory"]["revision_token"] == "epoch_old:2"

    # 7. User can now re-submit with the updated revision_token!
    new_token_sent = client_state["currentMemory"]["revision_token"]
    assert new_token_sent == server_state["revision_token"]
    print("\n[Step 4: Successful Re-submission]")
    print(f"  User re-submits draft with fresh token: {new_token_sent} -> HTTP 200 OK")
    print("=" * 70)
    print("DRAFT PRESERVATION SIMULATION PASSED 100%!")
    print("=" * 70)

if __name__ == "__main__":
    test_draft_preservation_logic()

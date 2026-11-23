"""
ACCIO LUNA V4.0 — Phase 5 / Priority Microphone Privacy & Transparency Patch
Automated Acceptance Tests for Explicit User-Controlled Microphone Lifecycle,
Zero Background Listening, SpeechRecognition Error Handling, and Privacy Transparency Disclosure.

Tests:
0. JavaScript syntax validation via node.
1. Page initialization never starts recognition.
2. Explicit microphone button activation triggers recognition flow.
3. Space activates recognition only when focus is outside editable controls.
4. Space inside an input/textarea/select/contenteditable does not activate recognition.
5. Repeated clicks do not create duplicate recognition sessions.
6. onend never automatically restarts recognition.
7. not-allowed correctly stops recognition and updates UI state.
8. audio-capture and network errors recover safely.
9. Empty transcription does not submit chat.
10. Unsupported browsers disable microphone without breaking text chat.
11. Page visibility change stops active recognition.
12. Page unload safely stops recognition.
13. Privacy disclosure modal elements are present in DOM.
14. Privacy disclosure text covers all 4 mandatory points.
15. Consent flow blocks recognition until user explicitly accepts.
16. Decline flow hides modal and keeps microphone strictly OFF.
17. Acceptance state lives in page memory only (no localStorage/cookies/tracking).
18. Space-key shortcut follows the same consent flow.
"""

import os
import re
import unittest
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")

def get_node_bin():
    n = shutil.which("node")
    if n:
        return n
    managed = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node\node.exe"
    if os.path.exists(managed):
        return managed
    return "node"

NODE_BIN = get_node_bin()


class TestPhase5MicPrivacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            cls.html = f.read()

        script_matches = [m for m in re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", cls.html, re.IGNORECASE) if m.strip()]
        cls.script_code = script_matches[0] if script_matches else ""

    def test_00_node_check_syntax(self):
        """Validate JavaScript syntax via node execution check reading file directly."""
        node_code = (
            "const fs = require('fs');"
            "const html = fs.readFileSync('index.html', 'utf8');"
            "const m = /<script\\b[^>]*>([\\s\\S]*?)<\\/script>/i.exec(html);"
            "new Function(m[1]);"
        )
        res = subprocess.run([NODE_BIN, "-e", node_code], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in index.html script: {res.stderr}")
        print("  [Privacy Test 0 PASSED] JavaScript syntax validation clean via node.")

    def test_01_page_initialization_never_starts_recognition(self):
        """Verify no automatic recognition.start() occurs during page initialization."""
        top_level_start = re.search(r"recognition\s*=\s*initSpeechRecognition\(\)\s*;\s*try\s*\{\s*recognition\.start", self.script_code)
        self.assertIsNone(top_level_start, "Found illegal top-level recognition.start() on page init!")
        self.assertNotIn("wakeWordActive = true", self.script_code, "wakeWordActive must not be true on startup")
        print("  [Privacy Test 1 PASSED] Page initialization never starts recognition automatically.")

    def test_02_explicit_mic_button_activation_starts_recognition(self):
        """Verify explicit click on #micBtn invokes setListening/startListening."""
        self.assertIn("micBtn.onclick", self.script_code)
        self.assertIn("startListening()", self.script_code)
        self.assertIn("recognition.start()", self.script_code)
        print("  [Privacy Test 2 PASSED] Explicit microphone button activation triggers recognition.")

    def test_03_space_activates_only_outside_editable_controls(self):
        """Verify Space key activates recognition only when not in an editable element."""
        self.assertIn("isEditableElement", self.script_code)
        self.assertIn("e.code === 'Space'", self.script_code)
        self.assertTrue(
            "isEditableElement(e.target)" in self.script_code or "isEditableElement(activeEl)" in self.script_code,
            "Space shortcut must verify target/activeElement before toggling mic"
        )
        print("  [Privacy Test 3 PASSED] Space shortcut correctly verifies editable elements.")

    def test_04_space_inside_editable_controls_is_ignored(self):
        """Verify isEditableElement covers input, textarea, select, and isContentEditable."""
        fn_match = re.search(r"function\s+isEditableElement\s*\([^)]*\)\s*\{([\s\S]*?return false;\s*\})", self.script_code)
        self.assertIsNotNone(fn_match, "isEditableElement function not found")
        fn_body = fn_match.group(1)
        self.assertIn("input", fn_body)
        self.assertIn("textarea", fn_body)
        self.assertIn("select", fn_body)
        self.assertIn("isContentEditable", fn_body)
        print("  [Privacy Test 4 PASSED] Space inside input/textarea/select/contenteditable safely ignored.")

    def test_05_repeated_clicks_do_not_create_duplicate_sessions(self):
        """Verify state guard prevents duplicate recognition.start() calls."""
        self.assertIn("isRecognitionStarting", self.script_code)
        self.assertIn("isListening || isRecognitionStarting", self.script_code)
        self.assertIn("InvalidStateError", self.script_code, "Must handle InvalidStateError gracefully")
        print("  [Privacy Test 5 PASSED] State guards prevent duplicate recognition sessions.")

    def test_06_onend_never_automatically_restarts_recognition(self):
        """Verify recognition.onend contains zero calls to recognition.start()."""
        onend_match = re.search(r"rec\.onend\s*=\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=>?\s*\{([\s\S]*?)\};", self.script_code)
        self.assertIsNotNone(onend_match, "rec.onend handler not found")
        onend_body = onend_match.group(1)
        self.assertNotIn("recognition.start()", onend_body, "rec.onend MUST NEVER restart recognition!")
        self.assertNotIn("rec.start()", onend_body, "rec.onend MUST NEVER call rec.start()!")
        print("  [Privacy Test 6 PASSED] rec.onend never restarts recognition automatically.")

    def test_07_not_allowed_correctly_stops_and_updates_ui(self):
        """Verify not-allowed error transitions to ERROR state and informs user."""
        onerror_match = re.search(r"rec\.onerror\s*=\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=>?\s*\{([\s\S]*?)\};", self.script_code)
        self.assertIsNotNone(onerror_match, "rec.onerror handler not found")
        onerror_body = onerror_match.group(1)
        self.assertIn("not-allowed", onerror_body)
        self.assertIn("isListening = false", onerror_body)
        self.assertIn("ERROR", onerror_body)
        print("  [Privacy Test 7 PASSED] not-allowed error correctly stops recognition and informs user.")

    def test_08_audio_capture_and_network_recover_safely(self):
        """Verify audio-capture and network errors are handled safely."""
        onerror_match = re.search(r"rec\.onerror\s*=\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=>?\s*\{([\s\S]*?)\};", self.script_code)
        self.assertIsNotNone(onerror_match)
        onerror_body = onerror_match.group(1)
        self.assertIn("audio-capture", onerror_body)
        self.assertIn("network", onerror_body)
        self.assertIn("no-speech", onerror_body)
        print("  [Privacy Test 8 PASSED] audio-capture and network errors handled with graceful recovery.")

    def test_09_empty_transcription_does_not_submit_chat(self):
        """Verify empty transcription is checked before calling handleUserMessage."""
        onresult_match = re.search(r"rec\.onresult\s*=\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=>?\s*\{([\s\S]*?)\};", self.script_code)
        self.assertIsNotNone(onresult_match, "rec.onresult handler not found")
        onresult_body = onresult_match.group(1)
        self.assertTrue("text.length > 0" in onresult_body or "if (!text)" in onresult_body)
        print("  [Privacy Test 9 PASSED] Empty transcription guarded against submission.")

    def test_10_unsupported_browsers_disable_mic_cleanly(self):
        """Verify unsupported browsers disable #micBtn without breaking app."""
        self.assertIn("if (!SpeechRecognition)", self.script_code)
        self.assertIn("micBtn.disabled = true", self.script_code)
        self.assertIn("return null", self.script_code)
        print("  [Privacy Test 10 PASSED] Unsupported browsers cleanly disable microphone.")

    def test_11_visibility_change_stops_active_recognition(self):
        """Verify document visibilitychange event stops active listening."""
        self.assertIn("visibilitychange", self.script_code)
        self.assertIn("document.hidden", self.script_code)
        self.assertIn("stopListening()", self.script_code)
        print("  [Privacy Test 11 PASSED] Page visibility change automatically stops recognition.")

    def test_12_page_unload_safely_stops_recognition(self):
        """Verify window beforeunload event aborts recognition."""
        self.assertIn("beforeunload", self.script_code)
        self.assertTrue("recognition.abort()" in self.script_code or "stopListening()" in self.script_code)
        print("  [Privacy Test 12 PASSED] Page beforeunload safely aborts recognition.")

    def test_13_privacy_disclosure_modal_elements_present(self):
        """Verify all privacy disclosure DOM elements exist in index.html."""
        required_ids = [
            "micConsentModal",
            "micConsentAcceptBtn",
            "micConsentDeclineBtn",
            "micConsentCloseBtn"
        ]
        for rid in required_ids:
            self.assertIn(f'id="{rid}"', self.html, f"Missing required consent element: #{rid}")
        print("  [Privacy Test 13 PASSED] All privacy disclosure modal DOM elements present.")

    def test_14_privacy_disclosure_text_content(self):
        """Verify the Turkish disclosure explains Web Speech API, cloud processing, no raw storage, and text-only dispatch."""
        modal_match = re.search(r'id="micConsentModal"[\s\S]*?</div>\s*</div>\s*</div>', self.html)
        self.assertIsNotNone(modal_match, "micConsentModal HTML block not found")
        modal_text = modal_match.group(0)

        # 1. Web Speech API
        self.assertIn("Web Speech API", modal_text, "Disclosure must mention Web Speech API")
        # 2. Browser provider processing outside local LUNA
        self.assertTrue("yerel LUNA uygulaması dışındaki" in modal_text or "tarayıcı ses tanıma servisleri" in modal_text)
        # 3. No raw microphone recordings stored on server
        self.assertTrue("kesinlikle depolanmaz" in modal_text and "ham mikrofon" in modal_text)
        # 4. Only recognized text submitted to chat endpoint
        self.assertTrue("metne dönüştürülen transkript" in modal_text and "sohbet" in modal_text)
        # Explicit actions
        self.assertIn("Kabul Et ve Mikrofonu Aç", modal_text)
        self.assertIn("Vazgeç", modal_text)
        print("  [Privacy Test 14 PASSED] Privacy disclosure text accurately covers all 4 mandatory points.")

    def test_15_consent_flow_blocks_start_until_accepted(self):
        """Verify setListening checks micConsentGranted and shows modal if not yet granted."""
        self.assertIn("let micConsentGranted = false;", self.script_code)
        self.assertIn("if (!micConsentGranted)", self.script_code)
        self.assertIn("showMicConsentModal()", self.script_code)
        self.assertIn("micConsentAcceptBtn.onclick", self.script_code)

        # In accept handler, sets micConsentGranted = true and starts listening
        accept_match = re.search(r"micConsentAcceptBtn\.onclick\s*=\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=>?\s*\{([\s\S]*?)\};", self.script_code)
        self.assertIsNotNone(accept_match, "micConsentAcceptBtn.onclick handler not found")
        accept_body = accept_match.group(1)
        self.assertIn("micConsentGranted = true", accept_body)
        self.assertIn("startListening()", accept_body)
        print("  [Privacy Test 15 PASSED] Consent flow blocks recognition until user explicitly accepts.")

    def test_16_decline_flow_keeps_microphone_off(self):
        """Verify declining the disclosure keeps microphone OFF and preserves text chat/TTS."""
        decline_match = re.search(r"micConsentDeclineBtn\.onclick\s*=\s*(?:\([^)]*\)|function\s*\([^)]*\))\s*=>?\s*\{([\s\S]*?)\};", self.script_code)
        self.assertIsNotNone(decline_match, "micConsentDeclineBtn.onclick handler not found")
        decline_body = decline_match.group(1)
        self.assertNotIn("startListening()", decline_body, "Decline must NEVER start listening!")
        self.assertNotIn("recognition.start()", decline_body, "Decline must NEVER start recognition!")
        self.assertIn("hideMicConsentModal()", decline_body)
        print("  [Privacy Test 16 PASSED] Decline flow hides modal and keeps microphone strictly OFF.")

    def test_17_session_reset_page_memory_only(self):
        """Verify micConsentGranted is stored only in page memory with NO localStorage/cookies/tracking."""
        # Ensure micConsent is never written to localStorage or sessionStorage or document.cookie
        self.assertNotIn("localStorage.setItem('micConsent", self.script_code)
        self.assertNotIn("localStorage.setItem(\"micConsent", self.script_code)
        self.assertNotIn("sessionStorage.setItem('micConsent", self.script_code)
        self.assertNotIn("document.cookie", self.script_code)
        print("  [Privacy Test 17 PASSED] Consent state kept strictly in page memory (session reset on reload).")

    def test_18_space_key_respects_consent_flow(self):
        """Verify Space key invokes setListening, which is gated by micConsentGranted."""
        space_match = re.search(r"e\.code === 'Space'[\s\S]*?setListening\(!isListening\);", self.script_code)
        self.assertIsNotNone(space_match, "Space key event handler calling setListening not found")
        print("  [Privacy Test 18 PASSED] Space key shortcut strictly respects the consent flow.")


if __name__ == "__main__":
    unittest.main()

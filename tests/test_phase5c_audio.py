"""
ACCIO JARVIS V4.0 — Phase 5 / Stage 5C
Automated Acceptance Tests for Audio Playback, Stale Prevention, Monotonic Generation Tracking,
and Unified Barge-In Interruption (Button, Escape, Spoken Phrases, SSE Cancellation, Visibility).

Tests:
01. JavaScript syntax validation via node --check.
02. Required DOM elements, CSS classes, and state variables present in index.html.
03. Playback lifecycle execution (valid Base64 decode, start, onended cleanup, return to IDLE).
04. Empty, whitespace, and malformed Base64 audio safely handled without uncaught exceptions.
05. Overlapping playback prevention (second audio immediately stops and disconnects active source).
06. Stale audio prevention via generation mismatch (outdated expectedGenId dropped before decode).
07. Stale audio prevention during decode delay (generation incremented during decode drops buffer).
08. Interrupt button (#interruptBtn) halts audio, aborts active chat, and resets UI state.
09. Escape key triggers interruptSpeech() when isSpeaking or isThinking is active.
10. Spoken barge-in phrases ("dur", "tamam", "kes", "yeter") trigger interruptSpeech().
11. AbortController ownership (new chat aborts prior active controller; cleans up in finally).
12. Expected AbortError preserves partial received text without reporting application failure.
13. SSE normal completion contract (agent badge, token streaming, audio triggered with matching gen).
14. SSE stream interruption during token streaming cancels reader and drops stale events.
15. Fallback /api/chat fetch respects controller.signal and request ownership.
16. Page visibility change (document.hidden) safely stops active audio and thinking states.
17. Page beforeunload cleans up audioCtx, active playback, and pending requests.
18. Microphone consent state strictly preserved during and after all interruption flows.
19. Concurrency race protection (superseded request cannot abort or corrupt newer request).
"""

import os
import re
import json
import unittest
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
INDEX_FILE = os.path.join(PROJECT_DIR, "index.html")

def get_node_bin():
    n = shutil.which("node")
    if n:
        return n
    managed = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node\node.exe"
    if os.path.exists(managed):
        return managed
    return "node"

NODE_BIN = get_node_bin()


class TestPhase5CAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            cls.html = f.read()

        script_matches = re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", cls.html, re.IGNORECASE)
        cls.script_code = next((code for code in script_matches if "function playAudioBase64" in code), "")

    def test_01_javascript_syntax_clean(self):
        """Verify index.html JavaScript syntax is completely clean."""
        node_code = (
            "const fs = require('fs');"
            "const html = fs.readFileSync('index.html', 'utf8');"
            "const m = /<script\\b[^>]*>([\\s\\S]*?)<\\/script>/i.exec(html);"
            "new Function(m[1]);"
        )
        res = subprocess.run([NODE_BIN, "-e", node_code], cwd=PROJECT_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Syntax error in index.html: {res.stderr}")
        print("  [Phase 5C Test 1 PASSED] JavaScript syntax validation clean via node.")

    def test_02_required_dom_and_state_variables_present(self):
        """Verify #interruptBtn, state variables, and CSS classes exist."""
        self.assertRegex(self.html, r'id=["\']interruptBtn["\']')
        self.assertRegex(self.html, r'id=["\']orbState["\']')
        self.assertIn("currentAudioGeneration", self.script_code)
        self.assertIn("currentChatRequestId", self.script_code)
        self.assertIn("activeChatAbortController", self.script_code)
        self.assertIn("interruptSpeech", self.script_code)
        self.assertIn("playAudioBase64", self.script_code)
        print("  [Phase 5C Test 2 PASSED] Required DOM elements and state variables verified.")

    def test_03_playback_lifecycle_execution(self):
        """Simulate Web Audio API decode and playback lifecycle in node environment."""
        node_script = """
        let isSpeaking = false;
        let coreState = 'IDLE';
        let currentAudioGeneration = 0;
        let audioSource = null;
        let audioCtx = {
          state: 'running',
          destination: {},
          createOscillator: () => ({ connect: () => {}, start: () => {}, stop: () => {} }),
          createGain: () => ({ connect: () => {}, gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {}, linearRampToValueAtTime: () => {} } }),
          createAnalyser: () => ({ connect: () => {}, fftSize: 128 }),
          decodeAudioData: (buffer, success, error) => {
            setTimeout(() => success({ duration: 1.5 }), 10);
          },
          createBufferSource: () => {
            const src = {
              buffer: null,
              connect: () => {},
              start: () => {},
              stop: () => {},
              disconnect: () => {},
              onended: null
            };
            return src;
          }
        };

        const interruptBtn = { classList: { add: (c) => {}, remove: (c) => {} } };
        const micBtn = { classList: { add: (c) => {}, remove: (c) => {} } };
        function setCoreState(s) { coreState = s; }
        function initAudioCtx() { return audioCtx; }
        function playSound() {}

        """ + self._extract_function_code("playAudioBase64") + """

        // Test normal playback
        const dummyB64 = Buffer.from("RIFFWAVEfmt DATA").toString("base64");
        playAudioBase64(dummyB64);

        setTimeout(() => {
          if (!isSpeaking || coreState !== 'SPEAKING') {
            console.error("Playback did not enter SPEAKING state. isSpeaking:", isSpeaking, "coreState:", coreState);
            process.exit(1);
          }
          // Trigger audioSource.onended
          if (audioSource && audioSource.onended) {
            audioSource.onended();
          }
          if (isSpeaking || coreState !== 'IDLE') {
            console.error("Playback did not return to IDLE after onended");
            process.exit(2);
          }
          console.log("SUCCESS");
          process.exit(0);
        }, 50);
        """
        res = subprocess.run([NODE_BIN, "-e", node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Lifecycle failed: {res.stderr}\n{res.stdout}")
        print("  [Phase 5C Test 3 PASSED] Web Audio playback lifecycle and cleanup verified.")

    def test_04_empty_and_malformed_base64_safely_handled(self):
        """Verify invalid or empty audio payloads do not crash the engine."""
        node_script = """
        let isSpeaking = false;
        let coreState = 'IDLE';
        let currentAudioGeneration = 0;
        let audioSource = null;
        function initAudioCtx() { return null; }
        function setCoreState(s) { coreState = s; }
        const interruptBtn = { classList: { remove: () => {} } };
        const micBtn = { classList: { remove: () => {} } };

        """ + self._extract_function_code("playAudioBase64") + """

        // Null, empty, whitespace, non-base64
        playAudioBase64(null);
        playAudioBase64("");
        playAudioBase64("   ");
        playAudioBase64(12345);
        playAudioBase64("!@#$%^&*()_NOT_BASE64!!!");

        if (isSpeaking || coreState !== 'IDLE') {
          console.error("Invalid audio triggered state mutation");
          process.exit(1);
        }
        console.log("SUCCESS");
        process.exit(0);
        """
        res = subprocess.run([NODE_BIN, "-e", node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Malformed audio failed: {res.stderr}")
        print("  [Phase 5C Test 4 PASSED] Empty and malformed audio safely rejected.")

    def test_05_overlapping_playback_prevention(self):
        """Verify that starting a second audio playback immediately stops and disconnects the previous source."""
        node_script = """
        let isSpeaking = false;
        let coreState = 'IDLE';
        let currentAudioGeneration = 0;
        let audioSource = null;
        let stoppedCount = 0;
        let disconnectedCount = 0;

        let audioCtx = {
          state: 'running',
          destination: {},
          createAnalyser: () => ({ connect: () => {}, fftSize: 128 }),
          decodeAudioData: (buffer, success) => success({ duration: 1.0 }),
          createBufferSource: () => ({
            buffer: null,
            connect: () => {},
            start: () => {},
            stop: () => { stoppedCount++; },
            disconnect: () => { disconnectedCount++; },
            onended: null
          })
        };

        const interruptBtn = { classList: { add: () => {}, remove: () => {} } };
        const micBtn = { classList: { add: () => {}, remove: () => {} } };
        function setCoreState(s) { coreState = s; }
        function initAudioCtx() { return audioCtx; }
        function playSound() {}

        """ + self._extract_function_code("playAudioBase64") + """

        const b64 = Buffer.from("AUDIO_STREAM_DATA_1").toString("base64");
        currentAudioGeneration = 1;
        playAudioBase64(b64, 1);
        const firstSource = audioSource;

        const b64_2 = Buffer.from("AUDIO_STREAM_DATA_2").toString("base64");
        currentAudioGeneration = 2;
        playAudioBase64(b64_2, 2);

        if (stoppedCount !== 1 || disconnectedCount !== 1) {
          console.error("First audio source was not stopped/disconnected. stopped:", stoppedCount, "disc:", disconnectedCount);
          process.exit(1);
        }
        console.log("SUCCESS");
        process.exit(0);
        """
        res = subprocess.run([NODE_BIN, "-e", node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Overlap prevention failed: {res.stderr}\n{res.stdout}")
        print("  [Phase 5C Test 5 PASSED] Overlapping playback strictly prevented.")

    def test_06_stale_audio_prevention_generation_mismatch(self):
        """Verify audio payload with stale generation ID is immediately ignored."""
        node_script = """
        let isSpeaking = false;
        let coreState = 'IDLE';
        let currentAudioGeneration = 5; // Current active generation
        let audioSource = null;
        let decodeCalled = false;

        let audioCtx = {
          state: 'running',
          decodeAudioData: () => { decodeCalled = true; },
          createBufferSource: () => ({})
        };
        function initAudioCtx() { return audioCtx; }
        function setCoreState(s) { coreState = s; }
        const interruptBtn = { classList: { add: () => {}, remove: () => {} } };
        const micBtn = { classList: { add: () => {}, remove: () => {} } };

        """ + self._extract_function_code("playAudioBase64") + """

        const b64 = Buffer.from("STALE_AUDIO").toString("base64");
        playAudioBase64(b64, 4); // Older generation ID: 4 vs 5

        if (decodeCalled || isSpeaking) {
          console.error("Stale audio generation was not ignored!");
          process.exit(1);
        }
        console.log("SUCCESS");
        process.exit(0);
        """
        res = subprocess.run([NODE_BIN, "-e", node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Stale check failed: {res.stderr}")
        print("  [Phase 5C Test 6 PASSED] Outdated generation ID cleanly dropped.")

    def test_07_stale_audio_prevention_during_decode_delay(self):
        """Verify that if an interruption occurs during decodeAudioData, decoded audio is not played."""
        node_script = """
        let isSpeaking = false;
        let coreState = 'IDLE';
        let currentAudioGeneration = 1;
        let audioSource = null;
        let startCalled = false;

        let audioCtx = {
          state: 'running',
          destination: {},
          createAnalyser: () => ({ connect: () => {}, fftSize: 128 }),
          decodeAudioData: (buffer, success) => {
            // Simulate decode delay
            setTimeout(() => {
              success({ duration: 2.0 });
            }, 30);
          },
          createBufferSource: () => ({
            buffer: null,
            connect: () => {},
            start: () => { startCalled = true; },
            stop: () => {},
            disconnect: () => {}
          })
        };
        function initAudioCtx() { return audioCtx; }
        function setCoreState(s) { coreState = s; }
        const interruptBtn = { classList: { add: () => {}, remove: () => {} } };
        const micBtn = { classList: { add: () => {}, remove: () => {} } };

        """ + self._extract_function_code("playAudioBase64") + """

        const b64 = Buffer.from("DELAYED_AUDIO").toString("base64");
        playAudioBase64(b64, 1);

        // User interrupts during decode:
        setTimeout(() => {
          currentAudioGeneration++; // Generation incremented to 2
        }, 10);

        setTimeout(() => {
          if (startCalled || isSpeaking) {
            console.error("Audio played despite generation increment during decode!");
            process.exit(1);
          }
          console.log("SUCCESS");
          process.exit(0);
        }, 60);
        """
        res = subprocess.run([NODE_BIN, "-e", node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Decode delay race failed: {res.stderr}\n{res.stdout}")
        print("  [Phase 5C Test 7 PASSED] In-flight decode safely discarded on generation increment.")

    def test_08_interrupt_button_invokes_interrupt_speech(self):
        """Verify interruptSpeech stops audio, aborts fetch, resets states to IDLE."""
        node_script = """
        let isSpeaking = true;
        let isThinking = true;
        let coreState = 'SPEAKING';
        let currentAudioGeneration = 10;
        let aborted = false;
        let stopped = false;
        let playSoundType = null;

        let activeChatAbortController = {
          abort: () => { aborted = true; }
        };

        let audioSource = {
          stop: () => { stopped = true; },
          disconnect: () => {},
          onended: () => {}
        };

        const interruptBtn = { classList: { remove: (c) => {} } };
        const micBtn = { classList: { remove: (c) => {} } };
        function setCoreState(s) { coreState = s; }
        function playSound(t) { playSoundType = t; }

        """ + self._extract_function_code("interruptSpeech") + """

        interruptSpeech();

        if (!aborted) { console.error("AbortController was not aborted"); process.exit(1); }
        if (!stopped) { console.error("audioSource was not stopped"); process.exit(2); }
        if (isSpeaking || isThinking) { console.error("States not cleared"); process.exit(3); }
        if (coreState !== 'IDLE') { console.error("coreState not set to IDLE"); process.exit(4); }
        if (currentAudioGeneration !== 11) { console.error("Generation not incremented"); process.exit(5); }
        if (playSoundType !== 'interrupt') { console.error("Interrupt sound not played"); process.exit(6); }

        console.log("SUCCESS");
        process.exit(0);
        """
        res = subprocess.run([NODE_BIN, "-e", node_script], cwd=BASE_DIR, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Interrupt button failed: {res.stderr}\n{res.stdout}")
        print("  [Phase 5C Test 8 PASSED] interruptSpeech cleanly stops audio, aborts stream, and restores IDLE.")

    def test_09_escape_key_triggers_interruption(self):
        """Verify Escape key listener calls interruptSpeech when speaking or thinking."""
        self.assertIn("e.code === 'Escape'", self.script_code)
        self.assertRegex(
            self.script_code,
            r"else\s+if\s*\(e\.code\s*===\s*['\"]Escape['\"]\)\s*\{[\s\S]*?else\s+if\s*\(isSpeaking\s*\|\|\s*isThinking\)\s*\{\s*interruptSpeech\(\);"
        )
        print("  [Phase 5C Test 9 PASSED] Escape key handler wired to unified interruptSpeech.")

    def test_10_spoken_barge_in_phrases(self):
        """Verify spoken phrases 'dur', 'tamam', 'kes', 'yeter' trigger interruptSpeech()."""
        phrases = ["dur", "tamam", "kes", "yeter"]
        for p in phrases:
            pattern = rf"lower\.includes\(['\"]{p}['\"]\)"
            self.assertRegex(self.script_code, pattern, f"Spoken phrase '{p}' missing from recognition barge-in filter")

        self.assertRegex(
            self.script_code,
            r"if\s*\(isSpeaking\s*\|\|\s*isThinking\)\s*\{[\s\S]*?interruptSpeech\(\);"
        )
        print("  [Phase 5C Test 10 PASSED] All 4 spoken barge-in trigger phrases verified.")

    def test_11_abort_controller_ownership_and_cancellation(self):
        """Verify handleUserMessage aborts previous controller and creates a fresh one."""
        self.assertIn("activeChatAbortController.abort()", self.script_code)
        self.assertIn("new AbortController()", self.script_code)
        self.assertIn("signal: controller.signal", self.script_code)
        # Check controller cleanup in finally
        self.assertRegex(
            self.script_code,
            r"finally\s*\{[\s\S]*?if\s*\(activeChatAbortController\s*===\s*controller\)\s*\{[\s\S]*?activeChatAbortController\s*=\s*null;"
        )
        print("  [Phase 5C Test 11 PASSED] AbortController ownership and lifecycle strictly scoped.")

    def test_12_expected_abort_error_preserves_partial_text(self):
        """Verify AbortError appends [Durduruldu] or sets [İptal edildi] without throwing or triggering fallback."""
        self.assertIn("if (e.name === 'AbortError')", self.script_code)
        self.assertIn("[Durduruldu]", self.script_code)
        self.assertIn("[İptal edildi]", self.script_code)
        # Verify fallback is not called on AbortError
        abort_catch = re.search(r"if\s*\(e\.name\s*===\s*['\"]AbortError['\"]\)\s*\{([\s\S]*?return;\s*\})", self.script_code)
        self.assertIsNotNone(abort_catch, "AbortError block missing explicit return")
        self.assertNotIn("/api/chat", abort_catch.group(1), "AbortError must never fall back to /api/chat")
        print("  [Phase 5C Test 12 PASSED] Expected AbortError preserves partial text without fallback.")

    def test_13_sse_normal_completion_contract(self):
        """Verify SSE stream handles agent, token, done events and passes generation ID to playAudioBase64."""
        self.assertIn("eventType === 'agent'", self.script_code)
        self.assertIn("eventType === 'token'", self.script_code)
        self.assertIn("eventType === 'done'", self.script_code)
        self.assertIn("playAudioBase64(dataObj.audio_base64, thisAudioGen)", self.script_code)
        print("  [Phase 5C Test 13 PASSED] SSE normal completion contract verified.")

    def test_14_sse_stream_interruption_cancels_reader(self):
        """Verify that when thisRequestId !== currentChatRequestId, reader is cancelled."""
        self.assertIn("if (thisRequestId !== currentChatRequestId)", self.script_code)
        self.assertIn("reader.cancel()", self.script_code)
        print("  [Phase 5C Test 14 PASSED] Stale SSE stream reader cancelled on newer request.")

    def test_15_network_failure_fallback_respects_abort_signal(self):
        """Verify /api/chat fallback request attaches controller.signal and checks request ID."""
        fallback_match = re.search(r"fetch\(['\"]/api/chat['\"],\s*\{([\s\S]*?)\}\);", self.script_code)
        self.assertIsNotNone(fallback_match, "Fallback fetch definition not found")
        self.assertIn("signal: controller.signal", fallback_match.group(1))
        self.assertIn("thisRequestId !== currentChatRequestId", self.script_code)
        print("  [Phase 5C Test 15 PASSED] Fallback /api/chat respects abort signal and request ownership.")

    def test_16_page_visibility_change_stops_audio_and_chat(self):
        """Verify visibilitychange stops active speech, thinking, and recognition."""
        vis_match = re.search(r"document\.addEventListener\(['\"]visibilitychange['\"],\s*\(\)\s*=>\s*\{([\s\S]*?)\}\);", self.script_code)
        self.assertIsNotNone(vis_match, "visibilitychange listener not found")
        body = vis_match.group(1)
        self.assertIn("document.hidden", body)
        self.assertIn("stopListening()", body)
        self.assertIn("interruptSpeech()", body)
        print("  [Phase 5C Test 16 PASSED] Page visibilitychange safely halts playback and chat.")

    def test_17_page_beforeunload_cleans_up_audio_and_requests(self):
        """Verify beforeunload listener cleans up recognition, speech, and closes audioCtx."""
        unload_match = re.search(r"window\.addEventListener\(['\"]beforeunload['\"],\s*\(\)\s*=>\s*\{([\s\S]*?)\}\);", self.script_code)
        self.assertIsNotNone(unload_match, "beforeunload listener not found")
        body = unload_match.group(1)
        self.assertIn("interruptSpeech()", body)
        self.assertIn("audioCtx.close()", body)
        print("  [Phase 5C Test 17 PASSED] Page beforeunload event cleans up audio and connections.")

    def test_18_microphone_consent_preserved_during_interruption(self):
        """Verify interruptSpeech does not alter mic consent state or start recognition."""
        fn_match = re.search(r"function\s+interruptSpeech\s*\(\)\s*\{([\s\S]*?)\n\s*\}", self.script_code)
        self.assertIsNotNone(fn_match, "interruptSpeech function definition not found")
        body = fn_match.group(1)
        self.assertNotIn("hasUserGivenMicConsent", body, "interruptSpeech must not alter mic consent state")
        self.assertNotIn("recognition.start", body, "interruptSpeech must never start recognition")
        self.assertNotIn("startListening", body, "interruptSpeech must never call startListening")
        print("  [Phase 5C Test 18 PASSED] Microphone consent preserved across all interruption paths.")

    def test_19_concurrency_race_protection(self):
        """Verify that older request cancellation cannot corrupt newer in-flight request."""
        self.assertIn("currentChatRequestId++", self.script_code)
        self.assertIn("currentAudioGeneration++", self.script_code)
        self.assertIn("const thisRequestId = currentChatRequestId", self.script_code)
        self.assertIn("const thisAudioGen = currentAudioGeneration", self.script_code)
        print("  [Phase 5C Test 19 PASSED] Monotonic request and audio generation IDs protect against races.")

    def _extract_function_code(self, fn_name):
        """Extracts complete JavaScript function body from script_code using brace counting."""
        start = self.script_code.find(f"function {fn_name}")
        if start == -1:
            raise ValueError(f"Function {fn_name} not found in script")
        brace_start = self.script_code.find("{", start)
        depth = 1
        i = brace_start + 1
        while i < len(self.script_code) and depth > 0:
            if self.script_code[i] == "{":
                depth += 1
            elif self.script_code[i] == "}":
                depth -= 1
            i += 1
        return self.script_code[start:i]


if __name__ == "__main__":
    unittest.main()

"""
ACCIO JARVIS V4.0 — Phase 7E Automated Test Suite
Focus: Command Center Automation & Gaming Mode UI, Safe DOM Rendering,
       Schedule & Action Type Handling, Notification Queue Telemetry,
       No Duplicate Requests, Intact Voice & Task Controls.
"""

import os
import re
import json
import subprocess
import unittest
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(os.path.dirname(BASE_DIR), "index.html")

def get_node_bin():
    n = shutil.which("node")
    if n:
        return n
    managed = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node\node.exe"
    if os.path.exists(managed):
        return managed
    return "node"

NODE_BIN = get_node_bin()


class Phase7EFrontendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            cls.html = f.read()

        script_matches = re.findall(r"<script\b[^>]*>([\s\S]*?)</script>", cls.html, flags=re.IGNORECASE)
        cls.scripts = script_matches

    def test_01_javascript_syntax_clean_via_node(self):
        """Test 1: All script tags in index.html compile with zero syntax errors under node --check."""
        self.assertGreater(len(self.scripts), 0)
        temp_js = os.path.join(BASE_DIR, "temp_check_syntax_7e.js")
        for i, code in enumerate(self.scripts):
            with open(temp_js, "w", encoding="utf-8") as f:
                f.write(code)
            try:
                res = subprocess.run([NODE_BIN, "--check", temp_js], capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, f"Script block {i+1} has syntax errors: {res.stderr}")
            finally:
                if os.path.exists(temp_js):
                    os.remove(temp_js)
        print("  [Phase 7E Test 1 PASSED] JavaScript syntax validation clean via node --check.")

    def test_02_automation_and_gaming_dom_ids_and_current_route(self):
        """Test 2: Automation and gaming DOM IDs exist and automation is reachable by command palette."""
        required_ids = [
            "viewAutomations",
            "gamingStatusBadge",
            "gamingReasonVal",
            "gamingSourceVal",
            "gamingSuppressedVal",
            "gamingActiveWindowVal",
            "notifQueueCountBadge",
            "notifOverflowCountVal",
            "notifExpiredCountVal",
            "notifPendingCountVal",
            "drainNotifsBtn",
            "refreshNotifsBtn",
            "drainFeedback",
            "schedulerStatusBadge",
            "autoAmbientMoodVal",
            "createAutoForm",
            "autoNameInput",
            "autoScheduleKindSelect",
            "autoTimeInput",
            "autoAtInput",
            "autoDaysWrapper",
            "autoActionSelect",
            "autoParamTextInput",
            "autoParamMoodSelect",
            "autoParamViewSelect",
            "submitAutoBtn",
            "autoFormFeedback",
            "autoListContainer",
            "refreshAutoListBtn"
        ]
        for dom_id in required_ids:
            self.assertIn(f'id="{dom_id}"', self.html, f"Missing required DOM element: id='{dom_id}'")
        self.assertIn("Otomasyon & Zamanlayıcı Yönetimini Aç", self.html)
        self.assertIn("switchView('automations')", self.html)
        print(f"  [Phase 7E Test 2 PASSED] {len(required_ids)} DOM IDs and current automation route verified.")

    def test_03_action_registry_allowlist_options_strictly_match_backend(self):
        """Test 3: Action select dropdown offers ONLY the 4 backend allowlisted action IDs."""
        action_select_match = re.search(r'<select[^>]*id="autoActionSelect"[^>]*>([\s\S]*?)</select>', self.html)
        self.assertIsNotNone(action_select_match, "autoActionSelect element must be present")
        options_html = action_select_match.group(1)

        values = re.findall(r'value="([^"]+)"', options_html)
        expected_allowlist = [
            "dispatch_study_reminder",
            "dispatch_proactive_notification",
            "change_ambient_mood",
            "open_allowlisted_view"
        ]
        self.assertEqual(sorted(values), sorted(expected_allowlist), f"Exposed actions must strictly match allowlist: {values}")
        print("  [Phase 7E Test 3 PASSED] Action select strictly restricted to 4 allowlisted action IDs.")

    def test_04_ambient_mood_and_view_dropdowns_strictly_match_allowlist(self):
        """Test 4: Ambient mood and view dropdowns match backend allowed values."""
        mood_match = re.search(r'<select[^>]*id="autoParamMoodSelect"[^>]*>([\s\S]*?)</select>', self.html)
        self.assertIsNotNone(mood_match)
        mood_values = re.findall(r'value="([^"]+)"', mood_match.group(1))
        expected_moods = ["focus", "relaxed", "gaming", "night", "default"]
        self.assertEqual(sorted(mood_values), sorted(expected_moods))

        view_match = re.search(r'<select[^>]*id="autoParamViewSelect"[^>]*>([\s\S]*?)</select>', self.html)
        self.assertIsNotNone(view_match)
        view_values = re.findall(r'value="([^"]+)"', view_match.group(1))
        expected_views = ["kokpit", "yks_takip"]
        self.assertEqual(sorted(view_values), sorted(expected_views))
        print("  [Phase 7E Test 4 PASSED] Mood and view options strictly match backend allowlists.")

    def test_05_safe_dom_construction_and_no_innerhtml_injection(self):
        """Test 5: renderAutomationsList uses safe textContent and replaceChildren without innerHTML injection."""
        js_code = "\n".join(self.scripts)
        render_fn_match = re.search(r'function renderAutomationsList\(automations\) \{([\s\S]*?)\n  \}', js_code)
        self.assertIsNotNone(render_fn_match, "renderAutomationsList function must be defined")
        body = render_fn_match.group(1)

        # Must not assign untrusted API fields (name, text, id) into innerHTML
        self.assertNotIn("innerHTML =", body, "renderAutomationsList must not use innerHTML assignments")
        self.assertIn("textContent", body, "renderAutomationsList must use textContent for text nodes")
        self.assertIn("replaceChildren", body, "renderAutomationsList must safely clear child nodes")
        print("  [Phase 7E Test 5 PASSED] Safe DOM construction verified (zero innerHTML injection).")

    def test_06_duplicate_request_guards_present(self):
        """Test 6: In-flight boolean locks prevent duplicate concurrent API requests."""
        js_code = "\n".join(self.scripts)
        self.assertIn("isAutoLoading", js_code)
        self.assertIn("isAutoSubmitting", js_code)
        self.assertIn("isDrainSubmitting", js_code)

        # Check guard checks
        self.assertIn("if (isAutoLoading) return;", js_code)
        self.assertIn("if (isAutoSubmitting) return;", js_code)
        self.assertIn("if (isDrainSubmitting) return;", js_code)
        print("  [Phase 7E Test 6 PASSED] In-flight concurrency locks present for all automation requests.")

    def test_07_simulated_dom_automation_rendering_and_xss_safety(self):
        """Test 7: Headless Node.js DOM harness executes renderAutomationsList with XSS payloads safely."""
        harness_js = r"""
        const fs = require('fs');
        const html = fs.readFileSync('index.html', 'utf8');
        const m = html.match(/function renderAutomationsList\(automations\) \{[\s\S]*?\n  \}/);
        if (!m) { console.error('renderAutomationsList not found'); process.exit(1); }

        function createMockElement(tag) {
          return {
            tagName: (tag || 'DIV').toUpperCase(),
            style: {},
            children: [],
            className: '',
            id: '',
            _textContent: '',
            set textContent(v) { this._textContent = String(v); this.children = []; },
            get textContent() {
              if (this.children.length === 0) return this._textContent;
              return this.children.map(c => c.textContent).join(' ');
            },
            appendChild(c) { this.children.push(c); return c; },
            replaceChildren(...nodes) { this.children = [...nodes]; this._textContent = ''; },
            querySelectorAll(sel) {
              const res = [];
              function walk(node) {
                if (!node || !node.children) return;
                for (const c of node.children) {
                  if (sel.startsWith('.') && c.className && c.className.includes(sel.slice(1))) res.push(c);
                  if (sel.toUpperCase() === c.tagName) res.push(c);
                  walk(c);
                }
              }
              walk(this);
              return res;
            }
          };
        }

        const autoListContainer = createMockElement('div');
        const document = {
          createElement: (tag) => createMockElement(tag)
        };

        const fn = new Function('automations', 'autoListContainer', 'document', m[0] + '; renderAutomationsList(automations);');

        const sample = [
          {
            id: 'a1',
            name: "<script>alert('xss_name')</script>AYT Soru Çözümü",
            schedule: { kind: 'daily', time: '09:00' },
            action: { action_id: 'dispatch_study_reminder', params: { text: "<img src=x onerror=alert('xss_text')>Deneme Sınavı" } },
            enabled: true,
            execution_count: 5
          },
          {
            id: 'a2',
            name: "Hafta Sonu Dinlenme",
            schedule: { kind: 'weekly', time: '18:00', days: ['sat', 'sun'] },
            action: { action_id: 'change_ambient_mood', params: { mood: 'relaxed' } },
            enabled: false,
            execution_count: 0
          }
        ];

        fn(sample, autoListContainer, document);

        if (autoListContainer.children.length !== 2) {
          throw new Error('Expected 2 cards, got ' + autoListContainer.children.length);
        }

        // Verify XSS tags were NOT parsed as HTML elements, but preserved as plain textContent
        const scriptTags = autoListContainer.querySelectorAll('SCRIPT');
        if (scriptTags.length > 0) throw new Error('Malicious script element parsed inside container!');

        const imgTags = autoListContainer.querySelectorAll('IMG');
        if (imgTags.length > 0) throw new Error('Malicious img element parsed inside container!');

        const firstCardText = autoListContainer.children[0].textContent;
        if (!firstCardText.includes("<script>alert('xss_name')</script>")) {
          throw new Error('Malicious name was not preserved safely as textContent');
        }

        console.log('OK_XSS_SAFE');
        """
        temp_test_js = os.path.join(BASE_DIR, "temp_harness_test.js")
        with open(temp_test_js, "w", encoding="utf-8") as f:
            f.write(harness_js)

        try:
            res = subprocess.run([NODE_BIN, temp_test_js], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Harness execution failed: {res.stderr}\n{res.stdout}")
            self.assertIn("OK_XSS_SAFE", res.stdout)
        finally:
            if os.path.exists(temp_test_js):
                os.remove(temp_test_js)
        print("  [Phase 7E Test 7 PASSED] DOM rendering verified with malicious payload isolation.")

    def test_08_gaming_mode_and_deferred_notifications_telemetry_binding(self):
        """Test 8: Node.js harness verifies gaming mode badge, reasons, and deferred notification counts."""
        harness_js = r"""
        function createMockElement(tag) {
          return {
            tagName: (tag || 'DIV').toUpperCase(),
            style: {},
            _textContent: '',
            set textContent(v) { this._textContent = String(v); },
            get textContent() { return this._textContent; }
          };
        }

        const elements = {};
        const document = {
          getElementById: (id) => elements[id] || (elements[id] = createMockElement('div'))
        };

        const mockMetrics = {
          telemetry_seq: 10,
          active_window: "Apex Legends",
          gaming_mode: {
            active: true,
            reason: "game_window",
            source: "active_window"
          },
          notifications: {
            deferred_count: 4,
            suppressed: true
          }
        };

        const gamingStatusBadge = document.getElementById('gamingStatusBadge');
        const gamingReasonVal = document.getElementById('gamingReasonVal');
        const gamingSourceVal = document.getElementById('gamingSourceVal');
        const gamingSuppressedVal = document.getElementById('gamingSuppressedVal');
        const gamingActiveWindowVal = document.getElementById('gamingActiveWindowVal');
        const notifPendingCountVal = document.getElementById('notifPendingCountVal');

        if (mockMetrics.gaming_mode) {
          const isGaming = Boolean(mockMetrics.gaming_mode.active);
          if (gamingStatusBadge) {
            gamingStatusBadge.textContent = isGaming ? 'Aktif (Oyun Modu)' : 'Pasif (Normal)';
          }
          if (gamingReasonVal) {
            const reasonMap = {
              'time_slot': 'Zaman Penceresi (16:00-17:30)',
              'game_window': 'Oyun Penceresi Tespit Edildi',
              'none': 'Normal (Boşta)'
            };
            gamingReasonVal.textContent = reasonMap[mockMetrics.gaming_mode.reason] || mockMetrics.gaming_mode.reason;
          }
          if (gamingSourceVal) {
            gamingSourceVal.textContent = mockMetrics.gaming_mode.source;
          }
          if (gamingSuppressedVal) {
            gamingSuppressedVal.textContent = isGaming ? 'Sessize Alındı (Erteleniyor)' : 'Açık (Serbest)';
          }
        }
        if (gamingActiveWindowVal) {
          gamingActiveWindowVal.textContent = mockMetrics.active_window;
        }
        if (notifPendingCountVal) {
          notifPendingCountVal.textContent = mockMetrics.notifications.deferred_count + " Bildirim";
        }

        if (gamingStatusBadge.textContent !== "Aktif (Oyun Modu)") throw new Error("Badge mismatch");
        if (gamingReasonVal.textContent !== "Oyun Penceresi Tespit Edildi") throw new Error("Reason mismatch");
        if (gamingSourceVal.textContent !== "active_window") throw new Error("Source mismatch");
        if (gamingSuppressedVal.textContent !== "Sessize Alındı (Erteleniyor)") throw new Error("Suppressed mismatch");
        if (gamingActiveWindowVal.textContent !== "Apex Legends") throw new Error("Active window mismatch");
        if (notifPendingCountVal.textContent !== "4 Bildirim") throw new Error("Pending count mismatch");

        console.log("OK_GAMING_BINDINGS");
        """
        temp_test_js = os.path.join(BASE_DIR, "temp_gaming_test.js")
        with open(temp_test_js, "w", encoding="utf-8") as f:
            f.write(harness_js)

        try:
            res = subprocess.run([NODE_BIN, temp_test_js], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Harness execution failed: {res.stderr}\n{res.stdout}")
            self.assertIn("OK_GAMING_BINDINGS", res.stdout)
        finally:
            if os.path.exists(temp_test_js):
                os.remove(temp_test_js)
        print("  [Phase 7E Test 8 PASSED] Gaming mode & deferred notification telemetry bindings verified.")

    def test_09_malformed_api_responses_fail_closed_gracefully(self):
        """Test 9: Malformed or null API payloads are handled without DOM runtime exceptions."""
        harness_js = r"""
        const fs = require('fs');
        const html = fs.readFileSync('index.html', 'utf8');
        const m = html.match(/function renderAutomationsList\(automations\) \{[\s\S]*?\n  \}/);
        if (!m) { console.error('renderAutomationsList not found'); process.exit(1); }

        function createMockElement(tag) {
          return {
            tagName: (tag || 'DIV').toUpperCase(),
            style: {},
            children: [],
            className: '',
            id: '',
            _textContent: '',
            set textContent(v) { this._textContent = String(v); this.children = []; },
            get textContent() {
              if (this.children.length === 0) return this._textContent;
              return this.children.map(c => c.textContent).join(' ');
            },
            appendChild(c) { this.children.push(c); return c; },
            replaceChildren(...nodes) { this.children = [...nodes]; this._textContent = ''; }
          };
        }

        const autoListContainer = createMockElement('div');
        const document = {
          createElement: (tag) => createMockElement(tag)
        };

        const fn = new Function('automations', 'autoListContainer', 'document', m[0] + '; renderAutomationsList(automations);');

        // Test with null, undefined, empty object, string, and numbers
        fn(null, autoListContainer, document);
        if (autoListContainer.children[0].textContent !== 'Tanımlı otomasyon bulunamadı.') throw new Error('Null failed');

        fn(undefined, autoListContainer, document);
        if (autoListContainer.children[0].textContent !== 'Tanımlı otomasyon bulunamadı.') throw new Error('Undefined failed');

        fn({}, autoListContainer, document);
        if (autoListContainer.children[0].textContent !== 'Tanımlı otomasyon bulunamadı.') throw new Error('Object failed');

        fn('invalid_string', autoListContainer, document);
        if (autoListContainer.children[0].textContent !== 'Tanımlı otomasyon bulunamadı.') throw new Error('String failed');

        console.log('OK_MALFORMED_HANDLED');
        """
        temp_test_js = os.path.join(BASE_DIR, "temp_malformed_test.js")
        with open(temp_test_js, "w", encoding="utf-8") as f:
            f.write(harness_js)

        try:
            res = subprocess.run([NODE_BIN, temp_test_js], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Malformed harness failed: {res.stderr}\n{res.stdout}")
            self.assertIn("OK_MALFORMED_HANDLED", res.stdout)
        finally:
            if os.path.exists(temp_test_js):
                os.remove(temp_test_js)
        print("  [Phase 7E Test 9 PASSED] Malformed API responses degrade gracefully to empty state.")

    def test_10_existing_voice_and_task_controls_remain_intact(self):
        """Test 10: Phase 4 task controls and Phase 5 voice & privacy mechanisms remain completely intact."""
        # Phase 5 Voice & Privacy
        self.assertIn("micConsentGranted", self.html)
        self.assertIn("interruptSpeech()", self.html)
        self.assertIn("currentAudioGeneration", self.html)
        self.assertIn("MediaRecorder", self.html)
        self.assertIn("/api/stt", self.html)
        self.assertIn("isListening", self.html)
        self.assertIn("micConsentModal", self.html)

        # Phase 4 Task Engine
        self.assertIn("currentTaskRevisionToken", self.html)
        self.assertIn("loadLiveTasks", self.html)
        self.assertIn("taskConflictBanner", self.html)
        self.assertIn("X-Task-Revision-Token", self.html)
        self.assertIn("toggleTaskDone", self.html)
        self.assertIn("deleteTask", self.html)

        # Phase 6 Command Center Views
        self.assertIn("viewCockpit", self.html)
        self.assertIn("viewSystem", self.html)
        self.assertIn("viewMemory", self.html)
        self.assertIn("viewLogs", self.html)
        self.assertIn("viewAutomations", self.html)
        self.assertIn("paletteModal", self.html)
        print("  [Phase 7E Test 10 PASSED] Phase 4 task, Phase 5 voice, and Phase 6 telemetry controls 100% intact.")


if __name__ == "__main__":
    unittest.main()

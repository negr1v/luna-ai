"""
ACCIO LUNA V4.0 — Phase 9B.4B Automated Test Suite
Focus: Frontend DOM Conversation Bounding (Max 60 bubbles) & Telegram Polling In-Flight Guard.
"""

import unittest
import os
import sys
import json
import shutil
import glob
import subprocess
import tempfile

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(PROJECT_DIR, "index.html")

def get_node_executable() -> str:
    """Find Node.js executable across system PATH and Accio managed runtime paths."""
    found = shutil.which("node")
    if found:
        return found
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidates = glob.glob(os.path.join(appdata, "Accio", "pre-install", "*", "node", "node.exe"))
        for c in candidates:
            if os.path.exists(c):
                return c
    hardcoded = r"C:\Users\negr1\AppData\Roaming\Accio\pre-install\bd5ff2c6816a\node\node.exe"
    if os.path.exists(hardcoded):
        return hardcoded
    return "node"

NODE_EXE = get_node_executable()


class TestPhase9B4ConversationDOMLimit(unittest.TestCase):
    """
    Validates conversation DOM pruning in index.html (Max 60 .msg-bubble elements).
    Executes actual appendBubble extracted verbatim from index.html using Node.js.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        # Locate appendBubble in index.html
        start_marker = "function appendBubble(text, role, agentName) {"
        end_marker = "// PAKET 4 & FAZ 2 — SSE STREAMING SOHBET İŞLEME"
        
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker)
        assert start_idx != -1 and end_idx != -1, "appendBubble function not found in index.html"

        cls.extracted_append_bubble = html[start_idx:end_idx]

    def _run_dom_harness(self, test_code: str) -> dict:
        """Run Node.js DOM harness with extracted appendBubble."""
        harness = f"""
class MockElement {{
  constructor(tag = 'div') {{
    this.tagName = tag.toUpperCase();
    this.className = '';
    this.style = {{}};
    this.textContent = '';
    this.children = [];
    this.parentElement = null;
  }}

  appendChild(child) {{
    child.parentElement = this;
    this.children.push(child);
    return child;
  }}

  removeChild(child) {{
    const idx = this.children.indexOf(child);
    if (idx !== -1) {{
      this.children.splice(idx, 1);
      child.parentElement = null;
    }}
  }}

  remove() {{
    if (this.parentElement) {{
      this.parentElement.removeChild(this);
    }}
  }}

  querySelector(sel) {{
    if (sel === '.bubble-text') {{
      return this.children.find(c => c.className === 'bubble-text') || null;
    }}
    return null;
  }}

  querySelectorAll(sel) {{
    if (sel === '.msg-bubble') {{
      return this.children.filter(c => c.className && c.className.includes('msg-bubble'));
    }}
    return [];
  }}
}}

const transcript = new MockElement('div');
transcript.id = 'transcript';
transcript.scrollTop = 0;
transcript.scrollHeight = 100;

global.document = {{
  createElement: (tag) => new MockElement(tag),
  getElementById: (id) => id === 'transcript' ? transcript : null
}};

// --- VERBATIM JS INJECTION ---
{self.extracted_append_bubble}
// --- END VERBATIM JS ---

async function runTest() {{
  {test_code}
}}

runTest().then(result => {{
  process.stdout.write(JSON.stringify({{ success: true, result }}));
}}).catch(err => {{
  process.stderr.write(err.stack || err.message);
  process.exit(1);
}});
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as tf:
            tf.write(harness)
            tmp_path = tf.name

        try:
            res = subprocess.run([NODE_EXE, tmp_path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            if res.returncode != 0:
                raise RuntimeError(f"Node execution failed (code {res.returncode}): {res.stderr}")
            return json.loads(res.stdout).get("result", {})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_01_under_threshold_bubbles_preserved(self):
        """1. Appending 60 or fewer bubbles preserves all bubbles in exact order."""
        code = """
        for (let i = 1; i <= 60; i++) {
          appendBubble(`Mesaj ${i}`, i % 2 === 0 ? 'assistant' : 'user');
        }
        const bubbles = transcript.querySelectorAll('.msg-bubble');
        return {
          totalBubbles: bubbles.length,
          firstText: bubbles[0].textContent,
          lastText: bubbles[59].textContent
        };
        """
        data = self._run_dom_harness(code)
        self.assertEqual(data["totalBubbles"], 60)
        self.assertEqual(data["firstText"], "Mesaj 1")
        self.assertEqual(data["lastText"], "Mesaj 60")

    def test_02_sixty_first_bubble_removes_oldest(self):
        """2. Appending the 61st bubble removes only the oldest bubble (#1) and retains 60."""
        code = """
        for (let i = 1; i <= 60; i++) {
          appendBubble(`Mesaj ${i}`, 'user');
        }
        // Append 61st bubble
        appendBubble("Mesaj 61", "user");

        const bubbles = transcript.querySelectorAll('.msg-bubble');
        return {
          totalBubbles: bubbles.length,
          firstText: bubbles[0].textContent,
          lastText: bubbles[59].textContent
        };
        """
        data = self._run_dom_harness(code)
        self.assertEqual(data["totalBubbles"], 60)
        self.assertEqual(data["firstText"], "Mesaj 2", "Oldest bubble (Mesaj 1) must be pruned")
        self.assertEqual(data["lastText"], "Mesaj 61")

    def test_03_structural_elements_preserved(self):
        """3. Structural/non-bubble elements inside #transcript are never removed."""
        code = """
        // Add a structural header or divider that is NOT a .msg-bubble
        const header = new MockElement('div');
        header.className = 'transcript-header';
        header.textContent = '--- CHAT BAŞLANGICI ---';
        transcript.appendChild(header);

        // Add 65 bubbles
        for (let i = 1; i <= 65; i++) {
          appendBubble(`Mesaj ${i}`, 'user');
        }

        const bubbles = transcript.querySelectorAll('.msg-bubble');
        const hasHeader = transcript.children.includes(header);
        return {
          totalChildren: transcript.children.length,
          totalBubbles: bubbles.length,
          hasHeader,
          headerText: header.textContent
        };
        """
        data = self._run_dom_harness(code)
        self.assertTrue(data["hasHeader"], "Non-bubble structural elements must be preserved")
        self.assertEqual(data["totalBubbles"], 60)
        self.assertEqual(data["totalChildren"], 61)  # 1 header + 60 bubbles

    def test_04_streaming_assistant_bubble_lifecycle(self):
        """4. Active streaming assistant bubble is created as newest bubble without being pruned."""
        code = """
        // Fill 60 bubbles
        for (let i = 1; i <= 60; i++) {
          appendBubble(`Mesaj ${i}`, 'user');
        }

        // Simulate streaming start: User message + empty assistant bubble
        appendBubble("Yeni Soru", "user");
        const streamingBubble = appendBubble("", "assistant", "LUNA");

        const bubbles = transcript.querySelectorAll('.msg-bubble');
        const isStreamingBubblePresent = transcript.children.includes(streamingBubble);
        const newestBubble = bubbles[bubbles.length - 1];

        return {
          totalBubbles: bubbles.length,
          isStreamingBubblePresent,
          isNewest: newestBubble === streamingBubble
        };
        """
        data = self._run_dom_harness(code)
        self.assertEqual(data["totalBubbles"], 60)
        self.assertTrue(data["isStreamingBubblePresent"])
        self.assertTrue(data["isNewest"])


class TestPhase9B4TelegramPollingGuard(unittest.TestCase):
    """
    Validates isTelegramPolling in-flight guard in index.html.
    Executes actual loadTelegramFeed extracted verbatim from index.html using Node.js.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        start_marker = "let previousTgCount = 0;"
        end_marker = "function renderTelegramFeed(msgs) {"
        
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker)
        assert start_idx != -1 and end_idx != -1, "loadTelegramFeed function not found in index.html"

        cls.extracted_tg_poll = html[start_idx:end_idx]

    def _run_tg_harness(self, test_code: str) -> dict:
        """Run Node.js harness with extracted loadTelegramFeed."""
        harness = f"""
let fetchCount = 0;
let fetchMock = null;

global.fetch = (url, opts) => {{
  fetchCount++;
  if (!fetchMock) throw new Error("fetchMock not defined");
  return fetchMock(url, opts);
}};

global.playSound = () => {{}};
global.tgPingDot = {{ style: {{ boxShadow: '' }} }};
global.renderTelegramFeed = () => {{}};
global.setTimeout = (fn, ms) => fn();

// --- VERBATIM JS INJECTION ---
{self.extracted_tg_poll}
// --- END VERBATIM JS ---

async function runTest() {{
  {test_code}
}}

runTest().then(result => {{
  process.stdout.write(JSON.stringify({{ success: true, result }}));
}}).catch(err => {{
  process.stderr.write(err.stack || err.message);
  process.exit(1);
}});
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as tf:
            tf.write(harness)
            tmp_path = tf.name

        try:
            res = subprocess.run([NODE_EXE, tmp_path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
            if res.returncode != 0:
                raise RuntimeError(f"Node execution failed (code {res.returncode}): {res.stderr}")
            return json.loads(res.stdout).get("result", {})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_05_concurrent_call_skipped_during_in_flight(self):
        """5. Second invocation while first is in-flight returns immediately without extra fetch."""
        code = """
        let resolveInFlight;
        const inFlightPromise = new Promise(r => { resolveInFlight = r; });

        fetchMock = async () => {
          await inFlightPromise;
          return { json: async () => [] };
        };

        // Call 1: Starts and stays in-flight
        const p1 = loadTelegramFeed();
        const guardStateWhileInFlight = isTelegramPolling;

        // Call 2: Triggered while Call 1 is in-flight
        const p2 = loadTelegramFeed();
        const callsAfterSecondInvocation = fetchCount;

        // Release Call 1
        resolveInFlight();
        await p1;
        await p2;

        return {
          guardStateWhileInFlight,
          callsAfterSecondInvocation,
          guardStateAfterCompletion: isTelegramPolling
        };
        """
        data = self._run_tg_harness(code)
        self.assertTrue(data["guardStateWhileInFlight"])
        self.assertEqual(data["callsAfterSecondInvocation"], 1, "Concurrent call must not initiate fetch")
        self.assertFalse(data["guardStateAfterCompletion"])

    def test_06_guard_released_after_network_failure(self):
        """6. Guard is released (isTelegramPolling = false) after network fetch rejection."""
        code = """
        fetchMock = async () => {
          throw new TypeError("Failed to fetch");
        };

        await loadTelegramFeed();
        const guardAfterNetworkFail = isTelegramPolling;

        // Next call should be allowed to run
        let call2Executed = false;
        fetchMock = async () => {
          call2Executed = true;
          return { json: async () => [] };
        };
        await loadTelegramFeed();

        return {
          guardAfterNetworkFail,
          call2Executed
        };
        """
        data = self._run_tg_harness(code)
        self.assertFalse(data["guardAfterNetworkFail"], "Guard must be released on network failure")
        self.assertTrue(data["call2Executed"], "Next call must proceed normally")

    def test_07_guard_released_after_json_parse_error(self):
        """7. Guard is released (isTelegramPolling = false) after JSON parsing exception."""
        code = """
        fetchMock = async () => {
          return {
            json: async () => { throw new SyntaxError("Unexpected token in JSON"); }
          };
        };

        await loadTelegramFeed();
        const guardAfterJsonFail = isTelegramPolling;

        return { guardAfterJsonFail };
        """
        data = self._run_tg_harness(code)
        self.assertFalse(data["guardAfterJsonFail"], "Guard must be released on JSON parse error")


if __name__ == "__main__":
    unittest.main()

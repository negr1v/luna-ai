"""
ACCIO JARVIS V4.0 — Phase 9B.4C.1 Long-Run Stability Test Suite
Focus: Deterministic long-run stability validation for conversation DOM bounding (5,000 insertions),
       Telegram in-flight polling guard (1,000 cycles), multi-failure resilience & timer discipline.
"""

import unittest
import os
import sys
import json
import shutil
import glob
import subprocess
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


class TestPhase9B4CLongRunDOM(unittest.TestCase):
    """
    Deterministic long-run simulation of conversation DOM bounding over 5,000 sequential insertions.
    Tests verbatim appendBubble extracted from index.html.
    """

    @classmethod
    def setUpClass(cls):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

        start_marker = "function appendBubble(text, role, agentName) {"
        end_marker = "  // OpenJarvis System Pulse Dynamic State Controller"
        
        start_idx = html.find(start_marker)
        end_idx = html.find(end_marker)
        assert start_idx != -1 and end_idx != -1, "appendBubble function not found in index.html"

        cls.extracted_append_bubble = html[start_idx:end_idx]

    def _run_dom_harness(self, test_code: str) -> dict:
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
global.window = global;
global.activeConversationId = 'test-conversation';

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
            res = subprocess.run(
                [NODE_EXE, tmp_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15
            )
            if res.returncode != 0:
                raise RuntimeError(f"Node execution failed (code {res.returncode}): {res.stderr}")
            return json.loads(res.stdout).get("result", {})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_01_repeated_5000_bubble_insertions_bounded(self):
        """1. [5,000 Insertions] Bubble count never exceeds 60; newest bubble retained; oldest pruned FIFO."""
        code = """
        // Inject 2 non-bubble structural elements into transcript
        const headerTop = new MockElement('div');
        headerTop.className = 'transcript-header';
        headerTop.textContent = 'SYSTEM_HEADER';
        transcript.appendChild(headerTop);

        const divider = new MockElement('div');
        divider.className = 'transcript-divider';
        divider.textContent = 'DIVIDER';
        transcript.appendChild(divider);

        let maxBubbleCountObserved = 0;
        let countViolations = 0;

        for (let i = 1; i <= 5000; i++) {
          appendBubble(`MSG_${i}`, i % 2 === 0 ? 'assistant' : 'user', i % 2 === 0 ? 'JARVIS' : null);
          const currentBubbles = transcript.querySelectorAll('.msg-bubble');
          if (currentBubbles.length > maxBubbleCountObserved) {
            maxBubbleCountObserved = currentBubbles.length;
          }
          if (currentBubbles.length > 60) {
            countViolations++;
          }
        }

        const finalBubbles = transcript.querySelectorAll('.msg-bubble');
        const structuralIntact = transcript.children.includes(headerTop) && transcript.children.includes(divider);

        // Extract first and last bubble text
        const firstBubble = finalBubbles[0];
        const lastBubble = finalBubbles[finalBubbles.length - 1];

        const firstText = (firstBubble.querySelector('.bubble-text') || firstBubble).textContent;
        const lastText = (lastBubble.querySelector('.bubble-text') || lastBubble).textContent;

        return {
          maxBubbleCountObserved,
          countViolations,
          finalBubbleCount: finalBubbles.length,
          totalChildren: transcript.children.length,
          structuralIntact,
          firstText,
          lastText
        };
        """
        data = self._run_dom_harness(code)
        self.assertEqual(data["maxBubbleCountObserved"], 60, "Bubble count must peak at exactly 60")
        self.assertEqual(data["countViolations"], 0, "Bubble count must never exceed 60 at any insertion")
        self.assertEqual(data["finalBubbleCount"], 60, "Final bubble count must be exactly 60")
        self.assertEqual(data["totalChildren"], 62, "2 structural elements + 60 bubbles = 62 elements")
        self.assertTrue(data["structuralIntact"], "Structural non-bubble elements must remain intact")
        self.assertEqual(data["firstText"], "MSG_4941", "Oldest remaining bubble must be MSG_4941 (5000 - 60 + 1)")
        self.assertEqual(data["lastText"], "MSG_5000", "Newest bubble must be MSG_5000")


class TestPhase9B4CLongRunTelegramPolling(unittest.TestCase):
    """
    Deterministic long-run simulation of Telegram polling in-flight guard over 1,000 cycles.
    Tests verbatim loadTelegramFeed extracted from index.html.
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
            res = subprocess.run(
                [NODE_EXE, tmp_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15
            )
            if res.returncode != 0:
                raise RuntimeError(f"Node execution failed (code {res.returncode}): {res.stderr}")
            return json.loads(res.stdout).get("result", {})
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_02_repeated_1000_polling_cycles_no_overlap(self):
        """2. [1,000 Polling Cycles] Guard prevents overlap; skipped concurrent calls do not create extra fetch."""
        code = """
        let totalCompletedCycles = 0;
        let skippedConcurrentCalls = 0;

        for (let cycle = 1; cycle <= 1000; cycle++) {
          let resolveFetch;
          const fetchPromise = new Promise(r => { resolveFetch = r; });

          fetchMock = async () => {
            await fetchPromise;
            return { json: async () => [{ id: `msg_${cycle}`, text: 'fırsat' }] };
          };

          // Primary poll starts in-flight
          const primaryPoll = loadTelegramFeed();

          // Concurrent poll attempted while primary is in-flight
          const beforeFetchCount = fetchCount;
          const concurrentPoll = loadTelegramFeed();
          const afterFetchCount = fetchCount;

          if (beforeFetchCount === afterFetchCount) {
            skippedConcurrentCalls++;
          }

          // Complete primary fetch
          resolveFetch();
          await primaryPoll;
          await concurrentPoll;

          if (!isTelegramPolling) {
            totalCompletedCycles++;
          }
        }

        return {
          totalCompletedCycles,
          skippedConcurrentCalls,
          totalFetchesInitiated: fetchCount,
          finalGuardState: isTelegramPolling
        };
        """
        data = self._run_tg_harness(code)
        self.assertEqual(data["totalCompletedCycles"], 1000, "All 1,000 cycles must complete cleanly")
        self.assertEqual(data["skippedConcurrentCalls"], 1000, "Every overlapping attempt must be skipped")
        self.assertEqual(data["totalFetchesInitiated"], 1000, "Exactly 1,000 fetches must be made, zero extra")
        self.assertFalse(data["finalGuardState"], "Guard must be released after completion")

    def test_03_repeated_failure_and_recovery_resilience(self):
        """3. [Multi-Failure Sequences] Guard never deadlocks under network drops, JSON syntax errors, and recovers."""
        code = """
        let successCount = 0;
        let networkDropCount = 0;
        let jsonErrorCount = 0;
        let recoveryCount = 0;

        for (let i = 1; i <= 300; i++) {
          // 1. Network drop (TypeError: Failed to fetch)
          fetchMock = async () => { throw new TypeError("Failed to fetch"); };
          await loadTelegramFeed();
          if (!isTelegramPolling) networkDropCount++;

          // 2. Recovery immediately after network drop
          fetchMock = async () => ({ json: async () => [{ id: `rec_${i}` }] });
          await loadTelegramFeed();
          if (!isTelegramPolling) recoveryCount++;

          // 3. JSON parsing error (SyntaxError)
          fetchMock = async () => ({ json: async () => { throw new SyntaxError("Unexpected token <"); } });
          await loadTelegramFeed();
          if (!isTelegramPolling) jsonErrorCount++;

          // 4. Recovery immediately after JSON error
          fetchMock = async () => ({ json: async () => [{ id: `rec_json_${i}` }] });
          await loadTelegramFeed();
          if (!isTelegramPolling) successCount++;
        }

        return {
          networkDropCount,
          jsonErrorCount,
          recoveryCount,
          successCount,
          finalGuardState: isTelegramPolling
        };
        """
        data = self._run_tg_harness(code)
        self.assertEqual(data["networkDropCount"], 300, "Guard must release on all 300 network drops")
        self.assertEqual(data["recoveryCount"], 300, "System must recover on all 300 post-network polls")
        self.assertEqual(data["jsonErrorCount"], 300, "Guard must release on all 300 JSON errors")
        self.assertEqual(data["successCount"], 300, "System must recover on all 300 post-JSON polls")
        self.assertFalse(data["finalGuardState"], "Guard must never remain locked")


class TestPhase9B4CTimerDiscipline(unittest.TestCase):
    """
    Static and architectural inspection of timers and intervals in index.html.
    Verifies no new or stray intervals were introduced.
    """

    def setUp(self):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_04_timer_count_and_intervals_verified(self):
        """4. Verify only existing expected setInterval instances exist, with no duplicate production timers."""
        intervals = [line.strip() for line in self.html.splitlines() if "setInterval(" in line]
        self.assertEqual(len(intervals), 5, f"Expected exactly 5 permanent intervals, found {len(intervals)}")

        # Verify telegram feed interval around line 4664 preserves document.hidden check
        tg_interval_block = self.html[self.html.find("loadTelegramFeed();", 4600):self.html.find("</script>", 4600)]
        self.assertIn("!document.hidden", tg_interval_block)
        self.assertIn("loadTelegramFeed()", tg_interval_block)


if __name__ == "__main__":
    unittest.main()

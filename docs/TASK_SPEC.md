Select and apply the skills that match this task. Keep the patch focused, eliminate artificial blockers, and ensure production-grade UX.

# UNBLOCKING PRODUCTION PIPELINE: DIRECT ELEVENLABS AUDIO, UNRESTRICTED CHAT & MIC FIX

Mode: PRODUCTION REFACTOR / UNBLOCKING
Project: C:\Users\negr1\Projeler\LUNA-AI
Primary files: luna_server.py, index.html
Report: Append to TASK_REPORT.md, preserving previous reports.

## 1. Eliminate TTS Approval Friction & Force True ElevenLabs Execution
- Problem: `generate_tts` in `luna_server.py` requires `validate_and_consume_paid_tts_authorization` tokens and silently downgrades to Microsoft Edge TTS (`tr-TR-EmelNeural`). As a result, all female voices sound identical (Microsoft voice) and browser popups block playback.
- Solution:
  * Remove `validate_and_consume_paid_tts_authorization` requirement from `generate_tts`. If `engine == "elevenlabs"` and `cfg.get("elevenlabs_api_key")` is present, call `_generate_elevenlabs_tts` DIRECTLY using `eleven_multilingual_v2` and the selected `voice_id` (Rachel, Emily, Elli, Charlotte).
  * Only fall back to Edge-TTS if ElevenLabs API returns a hard network/HTTP error or key is missing.
  * In `index.html`: Completely remove any `confirm()`, `alert()`, or approval dialog popups when clicking "Dinle" (Preview) or playing incoming speech. Previews and responses must synthesize and play instantly with zero user confirmation modals.

## 2. Eliminate Chat Blocking ("Durduruldu: Model ücretlidir ekrandan onaylayın")
- Problem: Sending standard chat messages with certain models (e.g., Llama 3.3 70B via Groq/OpenRouter) triggers an artificial HITL stop asking for approval cards that do not appear.
- Solution:
  * In `luna_server.py` (`handle_chat` / `handle_chat_stream`), remove the blocking paid-service authorization check that halts ordinary user conversation. User-selected chat models must generate completions immediately without stopping or demanding UI approval cards.

## 3. Fix Voice Input / Microphone (STT)
- In `index.html`: Inspect `#promptMicBtn` and `initSpeechRecognition()`. Ensure Web Speech API (webkitSpeechRecognition/SpeechRecognition) starts with Turkish (`tr-TR`), updates `#textInput` with recognized transcript in real time, and handles start/stop states smoothly without hanging or being suppressed by telemetry/approval state.

## 4. Verification & Testing
- In `luna_server.py`: Verify with a dry test that `generate_tts` routes to `_generate_elevenlabs_tts` when configured, without requiring an approval token.
- In `index.html`: Verify that "Dinle" triggers `/api/tts_direct` directly without browser confirmation dialogs.
- Append exact changed files and test commands to `TASK_REPORT.md`, then stop.

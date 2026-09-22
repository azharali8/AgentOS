# Streaming voice verification

Implemented September 12–13, 2026. This phase changes the voice path, not the Supervisor architecture.

## Architecture and protocol

Browser microphone → AudioWorklet → 16 kHz mono PCM16, 100 ms binary frames → authenticated AgentOS WebSocket `/api/v1/voice/stream` → AssemblyAI v3 → final-turn gate → existing VoiceService / VoiceAgent / CommandGateway → Supervisor. Results return over the socket; task progress uses existing task/event APIs; browser SpeechSynthesis provides feedback.

Verified against the current official [WebSocket reference](https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket), [message sequence](https://www.assemblyai.com/docs/streaming/message-sequence), and [error reference](https://www.assemblyai.com/docs/streaming/common-session-errors-and-closures): endpoint `wss://streaming.assemblyai.com/v3/ws`, raw API key in the server-side Authorization header, `speech_model=universal-3-5-pro`, `sample_rate=16000`, `encoding=pcm_s16le`; Begin, SpeechStarted, Turn, Error and Termination handling. Shutdown sends Terminate and waits briefly for acknowledgement. No AssemblyAI conversational/LLM gateway replaces AgentOS.

The browser sends a Start frame with its AgentOS session credential, not an API-key URL. Origin checks, authentication, role checks, handshake rate limits, frame/rate/queue/session limits and permission rechecks guard the relay. Provider error details are sanitized. REST transcription endpoints remain available; they are not an automatic replay fallback.

## Voice behavior

- Interim text is display-only. Only validated `end_of_turn: true` events can dispatch, once per provider session/turn order; formatting revisions cannot repeat execution.
- Continuous capture remains active during TTS. SpeechStarted cancels playback immediately; older queued responses are suppressed after an interruption. No manual Send or Finish Turn control.
- Reconnect is capped at two attempts. Audio and commands are not replayed; conversation identity stays stable across reconnects to the same backend process. In-memory conversation state does not survive server restart.
- Visible provider/auth/quota, microphone, malformed-event, silence and connectivity errors. A disconnected response may already have created a task: inspect task activity before repeating an instruction.
- A real browser attempt exposed speaker echo causing unintended commands. Capture was stopped and the isolated tasks cancelled through the normal API. Added a 20-second exact spoken-fragment echo guard with tests. This is not acoustic echo cancellation; headphones/muting remain useful, and a deliberate repetition of the same response fragment inside that window may also be suppressed.
- Supervisor stage labels, readable interim/final transcripts, approval status, speech mute, immediate session stop, progress recovery warnings, and a viewport-bounded overlay rendered outside header/sidebar stacking contexts.

## Verification

- Backend full regression: **531 passed, 1 skipped**, four existing collection/cache warnings (`tmp/stream-final-backend.log`).
- Voice/security selection before echo addition: **73 passed**; latest streaming suite including echo handling: **16 passed**.
- Frontend voice tests: **12 passed**; PCM checks cover 16/44.1/48 kHz inputs, mono mixing, byte order, frame sizing, clipping, interruption and reconnect bounds.
- New backend tests double only the external AssemblyAI connection. Routing uses the real VoiceService, gateway, persistence and Supervisor, including an actual failure for an invalid model configuration. They do not fabricate successful engineering execution. The existing full regression contains its established doubles.
- Frontend lint and production build passed; lint retains four pre-existing hook warnings. The mobile overlay was checked at 390 x 844 and moved above the sidebar; immediate start/stop was verified. Broader sidebar/mobile layout changes were deferred.

## Real acceptance result

**Verified with real AssemblyAI and synthetic spoken audio:** the provider emitted Begin, SpeechStarted, interim Turns, a final Turn and Termination. The exact URL-shortener request passed through the real relay and VoiceAgent, created the project, and launched Supervisor task `cc48172c-e329-44c1-b513-578c2bf7bef0` using `gpt-oss:120b-cloud`. Approved generated code ran real tests and entered debugging/recovery. The next repair proposed globally patching SQLAlchemy; it was rejected through the approval API and the task was cancelled. No generated implementation was manually repaired.

The streamed follow-up “Run the tests again and tell me the result” launched task `87f585aa-1004-4d57-be35-e86f56e01c7b` with `project_created: false` on the existing project. A service restart occurred between requests; the isolated backend was restored with that project as its workspace. This verifies existing-workspace routing, not persistence of conversational memory across restarts. The follow-up ran real tests and finished FAILED with **1 passed, 5 failed**; it did not report a successful engineering result.

Evidence: `tmp/stream-provider-live.log`, `tmp/stream-acceptance-first.log`, `tmp/stream-acceptance-followup.log`, and `tmp/stream-acceptance/`. These are local verification artifacts, not committed demo data. Provider credentials were neither hardcoded nor printed. Default local model configuration was not changed for the cloud trial.

**Not complete:** physical-microphone end-to-end completion, reliable acoustic barge-in after the echo fix, and user-confirmed audible TTS were not established. The hackathon workflow is not claimed complete. The main remaining blocker is reliable live microphone/TTS interaction; model repair quality also prevented completion of this generated app. Broader frontend redesign and infrastructure work were deferred.


## Files changed in this phase

- `backend/app/voice/streaming.py` (new relay, event gate and echo guard); `backend/app/voice/router.py` (WebSocket registration); `requirements.txt` (explicit websockets dependency).
- `frontend/public/voice-pcm.mjs`, `frontend/public/voice-capture.js` (audio worklet and conversion); `frontend/lib/voice-stream.ts` (playback/reconnect/stage handling); `frontend/lib/api.ts` (authenticated stream connection); `frontend/components/voice/VoiceControl.tsx` (continuous voice UI).
- `backend/tests/integration/test_streaming_voice.py`, `frontend/tests/voice-stream.test.cjs`, and this report.

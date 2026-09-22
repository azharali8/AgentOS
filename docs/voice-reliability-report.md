# Voice reliability and credit protection — September 13, 2026

This follow-up preserves the streaming implementation described in [the earlier report](streaming-voice-report.md). It does not repeat the full voice-to-project demo.

## Changes

- `backend/app/voice/streaming.py`: dispatch uses freshly authenticated identity and role; rejects identity changes and revoked execution permission. Silent sessions stop after 60 seconds and all sessions after five minutes by default. Both limits terminate the provider without automatic reconnect; submitted tasks continue independently.
- `backend/app/config/settings.py`, `.env.example`: bounded, positive `VOICE_STREAM_IDLE_SECONDS` and `VOICE_STREAM_MAX_SECONDS` settings.
- `frontend/lib/voice-stream.ts`, `frontend/components/voice/VoiceControl.tsx`: reset playback turn identity and transcript on provider Begin. Duplicate final revisions cannot clear a newer speech interruption or revive an old response. Existing microphone, transcript, Supervisor progress, approval and responsive panel controls remain in place; no auth redesign.
- `backend/app/voice/agent/command_router.py`: unavailable workspace inspection returns an explicit failed response instead of claiming success.
- `backend/tests/integration/test_streaming_voice.py`, `frontend/tests/voice-stream.test.cjs`: extend real conversation continuation across reconnect, auth revocation/role downgrade, idle/session shutdown, workspace failure, playback reset and duplicate-revision coverage.
- Local `.env`: repaired only WORKSPACE_ROOT, which pointed to a missing pytest temporary project, to the existing `C:/Users/evo/AgentOS/workspace`. Model and credential settings were preserved.
- This report; temporary smoke scripts/logs remain under `tmp/`.

## Architecture and behavior

Microphone → AudioWorklet → 16 kHz mono PCM16 → authenticated AgentOS WebSocket → AssemblyAI → confirmed final turn → VoiceService / VoiceAgent → CommandGateway → Supervisor for engineering commands. Workspace queries use the gateway's real inspection service. Interim text never executes; final IDs prevent duplicate execution. Existing security, approvals and auditing remain in the execution path.

Current official [WebSocket API](https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket) and [message sequence](https://www.assemblyai.com/docs/streaming/message-sequence) were checked before edits: v3 endpoint, server Authorization key, universal-3-5-pro, PCM16/16 kHz, Begin, SpeechStarted, Turn/end_of_turn and Terminate/Termination.

## Verification

**Verified with mocked AssemblyAI boundary:** targeted voice/security **81 passed**; frontend voice **14 passed**. New routing tests use the actual VoiceAgent, gateway, database and Supervisor. Engineering tests use an invalid model configuration to verify genuine failure without paid model calls; they do not fabricate successful engineering execution. Existing regression tests retain their established doubles.

Full backend regression: **537 passed, 1 skipped**, four collection/cache warnings. Frontend lint and production build passed, with four existing hook warnings. All required checks completed before the single real provider test. Logs: `tmp/voice-reliability-{targeted,backend,frontend-tests,lint,build}.log`.

**Verified with real AssemblyAI:** exactly **one** session in this phase, approximately **8 seconds**, carrying **4.49 seconds** of synthetic spoken audio. The provider emitted interim turns, final “Agent OS, tell me the current workspace status.”, one Processing event, a real authenticated gateway response, and Termination. No project or engineering task was created. Audio was generated locally; the server used its configured key.

**Live smoke outcome: failed workspace response.** The gateway correctly reported that the configured workspace was unavailable. This was not a provider-specific failure, so no second paid test was run. After repairing the stale local workspace setting, an authenticated local text replay through the same VoiceService/gateway returned “Project workspace has 19 files. Detected docker.” This local success is not a second real streaming verification.

Evidence: `tmp/voice-reliability-smoke.log`, `tmp/voice-reliability-smoke/result.json`, and `tmp/voice-reliability-smoke/offline-result.json`. The temporary localhost smoke server was stopped.

**Not yet verified:** successful live response after the workspace repair, physical microphone quality, audible browser TTS and acoustic barge-in after these fixes. Playback/interruption logic is covered by provider-double and frontend tests; the existing exact-fragment echo guard is not acoustic echo cancellation. Conversation state still does not survive backend restart. No production/hackathon readiness claim is made.

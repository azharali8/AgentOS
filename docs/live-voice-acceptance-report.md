# Live voice acceptance (in progress)

## Current pipeline trace

- DashboardView Live entry → VoiceControl; microphone permission/getUserMedia → AudioContext → voice-capture.js AudioWorklet → voice-pcm.mjs resampling/mono PCM16 framing.
- AgentOSClient.openVoiceStream → authenticated Start frame → backend voice.router /stream → streaming.stream_voice → server-side Authorization header → AssemblyAI v3 Universal Streaming.
- streaming.relay forwards binary audio, displays partial Turn events, reserves provider-session/turn-order finals once in FinalTurns, then VoiceService.process_transcript → VoiceAgent → AgentOSCommandGateway → MultiAgentService → normal Supervisor graph.
- Results return through the same WebSocket. VoiceControl polls real task/events and BrowserSpeech uses browser speechSynthesis. VoicePlayback handles turn identity/barge-in. Stop releases media/worklet/context and sends Stop; relay cancels workers, sends Terminate and closes upstream. Existing reconnect is bounded to two attempts.
- AssemblyAI contract checked against https://www.assemblyai.com/blog/raw-websocket-voice-agent-with-assemblyai-universal-3-pro-streaming : v3, universal-3-5-pro, backend Authorization, 16 kHz mono PCM16, binary 50–1000 ms frames, end_of_turn finals, Terminate.

## First identified boundaries

Voice task creation omits per-user model metadata used by typed requests; voice polling speaks raw task result_summary/error rather than a concise evidence-derived summary. Fix these integration boundaries without modifying the cloud router.

Real AssemblyAI sessions used in this phase: 0. Real acceptance has not started.

## Implemented and mock-tested boundaries

- Live-created tasks capture the authenticated user's existing Auto/local preference before Supervisor starts.
- Live project commands require a connected, available project; Live approval/rejection directs the user to the existing review buttons and retains role checks.
- Final transcripts and responses appear in the engineering conversation. Task voice summaries use recorded terminal status and test reports, not raw logs or invented success.
- Existing provider-session/turn-order deduplication and bounded reconnect remain. Capture cleanup also detaches worklet callbacks/ports and media track callbacks; stopping Live stops task polling.
- Mock multi-turn coverage checks partials do not execute, duplicate Result delivery executes once, a later identical phrase remains legitimate, TTS completion, one WebSocket, and track cleanup.

## Regression gate (September 29, 2026)

- Targeted voice/router: 91 passed, 1 warning, 65.40 seconds.
- Full backend: 658 passed, 1 skipped, 4 warnings, 306.80 seconds.
- Frontend: 58 passed, 0 failed.
- Lint: exit 0; four existing hook dependency warnings.
- Production build: exit 0.

## Real acceptance preparation

Connected acceptance project: `C:/Users/evo/AppData/Local/Temp/AgentOS-auto-cloud-20260928`.
The local acceptance launcher caps streaming at 90 seconds (45 seconds idle) and wraps the real provider connection with a one-attempt budget ledger. It does not replace microphone audio or provider responses. Automatic reconnect cannot open a second paid session during this acceptance. No real session has started; all regression gates passed and human readiness remains required.

Real multi-turn microphone, audible TTS, and post-session cleanup remain NOT VERIFIED. Code freeze is not declared.

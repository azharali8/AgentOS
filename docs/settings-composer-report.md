# Settings and unified composer verification

## Implemented

- Account details and existing session logout; Light (default), Dark and System themes with local persistence and system-change handling; persisted Live Voice read-aloud preference.
- Authenticated installed-model discovery using Ollama tags and model capabilities. Cloud and embedding models cannot be selected. Individual metadata failures mark only that model unavailable. Selection persists in the workspace database and updates the existing Ollama configuration/provider factory and ModelRouter.
- One composer for multiline text, bounded UTF-8 text/source attachments, model selection, one-shot microphone and continuous Live Voice. Typed requests enter the existing task/Supervisor execution path. Voice uses the existing VoiceAgent/CommandGateway path.
- Attachments: up to four files, 32 KB each and 64 KB total; validated names/types/content on client and server. No arbitrary file reads or server-side upload execution. PDFs and binary documents are not supported.
- Partial speech is display-only. Final turns are deduplicated, and one-shot mode accepts at most one command per session. Existing TTS, barge-in, reconnect limits, security checks and approvals remain.
- Removed Test Speaker, the separate voice panel and duplicate Workspace prompt/action controls. Fixed mobile header clipping.

## Verification

- Frontend: `node --test tests/*.test.cjs` — 36 passed.
- Backend: full suite — 590 passed, 1 skipped; 3 existing collection warnings. After the subsequent isolated model-metadata error-handling fix, all 15 focused workspace-settings tests passed.
- Focused settings and streaming voice tests also passed (37 tests before the additional metadata regression test).
- Frontend lint, TypeScript validation and final production build passed. Four existing React hook dependency warnings remain.
- Browser at localhost:3001: authenticated account information; Light/Dark/System controls; dark preference survives reload; actual installed models; Settings-to-Workspace selection synchronization; model preference survives backend restart; desktop and 390-pixel mobile composer rendering. Mobile document width and scroll width both 390 pixels after header fix.
- Actual local models discovered: llama3.2:latest, llama3.2:3b, qwen2.5-coder:3b, nomic-embed-text:latest and qwen3-vl:4b. The first three passed capability probes. The embedding model is disabled; qwen3-vl metadata could not be verified and is disabled. No models downloaded.
- Final browser verification: restored qwen2.5-coder:3b from the composer and observed it in Settings. Settings Sign out returned to Login with the server-confirmed signed-out message. Preview left signed out.
- Voice/audio/provider behavior was tested with doubles, not a real microphone-to-AssemblyAI session. No claim of fresh live audio acceptance or model-generated engineering completion is made.
- Real AssemblyAI API calls: **0**. The isolated browser-preview backend uses an empty AssemblyAI key and a separate local database.

## Local preview

The verification build can use `AGENTOS_NEXT_DIST_DIR=.next-verification` for both `npm run build` and `npm run start -- --port 3001`, preventing collisions with a running development server's `.next` directory. Normal development retains the default `.next` directory. Backend restart is required to load the new endpoints and model preference restoration.

## Limits

Live audio acceptance remains reserved for a separately authorized credit-consuming test. Model preference is workspace-wide; theme and speech preferences are local to the browser. A failed model capability probe requires Refresh before that model can be selected. Tablet emulation did not reliably retain the requested viewport, so tablet-specific visual acceptance is not claimed.

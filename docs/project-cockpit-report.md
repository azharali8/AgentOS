# Project cockpit implementation and acceptance report

Date: 2026-10-09 (Asia/Karachi). Scope: keep the existing AgentOS engine and upgrade project organization and engineering evidence presentation. No commit, push, deployment, or AssemblyAI session was performed.

## Baseline

The existing FastAPI API calls MultiAgentService, the LangGraph workflow, Supervisor, and specialized agents. Tasks, approvals, events, executions, and immutable artifacts already persist through SQLAlchemy. Workspace selection changes a process-global WORKSPACE_ROOT using validated routes and an idle-task guard. Next.js previously polled global tasks and presented global history. The existing WebSocket replays database events; it is retained.

Baseline: backend **658 passed, 1 skipped, 3 warnings in 215.75s**; frontend **58 passed**; focused persistence/workspace **7 passed in 3.97s**. Lint passed with four existing dependency warnings. An early build succeeded while the small license/Live changes were being introduced, so it is not represented as a pristine baseline build. Sandbox API tests stalled; completed backend runs used authorized localhost-capable execution.

## Root causes and changes

- Global task loading did not represent durable project membership. Three additive tables now link a project to conversations and the existing tasks.
- Equal-timestamp event ordering lacked a deterministic tie-break. Database ordering now uses timestamp and event ID; the hook sorts and deduplicates real events and rejects malformed or wrong-task messages.
- A previous subscription could expose old-task events for one render. Task filtering now happens before returning the hook value, with memoized identity. Browser acceptance caught and fixed an intermediate implementation that returned a new array every render and repeatedly triggered approval loading.
- Late approval/file/history responses could outlive project selection. Disposal/selection-generation guards prevent these results from repopulating the new project's UI.
- Historical turns restored prompts but lacked a way to retrieve execution evidence. Recorded activity now loads on demand in pages of 100 events. Projects and conversations have load-more controls; no other project's events load on initial navigation.
- Test failures use the backend's `message` field, which was previously omitted. Classification, source excerpt, likely cause, suggested fix, and raw output now display the recorded backend fields.
- Test artifacts were associated by a ten-second time window. New TEST_COMPLETED events carry the actual saved artifact ID and subtask ID. Older records match only when a single complete report is identical; ambiguous records are not guessed into another run.
- Filename-only PATCH_CREATED payloads produced empty diff rows before the patch artifact arrived. Only real structured patch hunks render as diffs.
- Replayed approval decisions now update the approval row instead of adding repeated resolved rows.
- Completed work uses a recorded-outcome header and concise latest-test/review/file summary, with the detailed backend report expandable. Paused activity does not animate as running.

## Architecture and database

`Project -> Conversation -> ConversationTask -> existing Task -> existing Events / Approvals / Artifacts`.

A project records owner, display name, canonical workspace path, and creation time. Conversations record project membership and title. The task link uses the existing task ID as its primary key. Task metadata also records project/conversation/owner for the API contract. Existing task requests and final responses provide persisted conversation turns; engine graph thread IDs are unchanged.

Migration `f2a3b4c5d6e7` follows `e1f2a3b4c5d6`. It creates `projects`, `conversations`, and `conversation_tasks`, indexes, an owner/workspace uniqueness constraint, and foreign keys. It does not rewrite legacy tasks or guess their workspace. Disconnect clears the selected-project preference; it does not delete history or source directories. There is no project-delete operation.

Use the existing Alembic procedure for an already versioned database, taking a backup first. The migration was exercised against a legacy-task fixture with foreign keys enabled. The user's normal database was not migrated or stamped during acceptance. Existing explicitly initialized, unversioned databases need their actual Alembic baseline reconciled before applying a migration; do not blindly stamp them. Acceptance used a separate SQLite database.

## Backend/API and security

New project routes list, connect, activate, list conversations, and list conversation tasks. Existing workspace validation and idle-only switching are reused. A process-local transition lock serializes task admission and workspace changes. v1 task creation validates project/conversation/workspace membership before admission. v1 task, event, artifact, approval, and WebSocket access checks project ownership. Tests confirm another owner, including an ADMIN identity, cannot read or resolve the project approval through these v1 routes.

Existing approval hashing/HMAC paths, roles, tool/path validation, immutable artifacts, audit evidence, and agent execution are retained. Auto routing code and verification expiry were not changed. Runtime verification had expired: real chat and structured-code probes refreshed only Gemma 4 cloud and Qwen Coder 3B records, retaining the old file as an acceptance backup. No stale model was marked healthy without a real probe.

This remains a local single-workspace engine, not a newly secured multi-tenant deployment. Older non-v1 API routes retain their pre-existing access behavior; the new owner checks are not a claim that every legacy API is tenant-isolated. See limitations before exposing this server.

## Frontend and Live

Projects replaces global Chat History. Create/connect/switch restores project-scoped conversations and task evidence. Sending requires a selected project. Existing attachments, repository browsing, model controls, one-shot dictation code, and Settings remain. Live is a disabled control labeled temporarily unavailable and the provider component is not mounted. AssemblyAI, VoiceService/VoiceAgent, capture, TTS, voice routes, and Live tests remain unchanged. No AssemblyAI credits were consumed. Microphone recording itself was not exercised in this task.

## Exact files changed

| File | Purpose |
|---|---|
| LICENSE | Official Apache License 2.0 text |
| README.md | License paragraph only |
| backend/app/db/models.py | Add project/conversation/task membership tables |
| backend/app/db/migrations/versions/f2a3b4c5d6e7_project_conversations.py | Additive Alembic migration |
| backend/app/services/project_service.py | Durable registration, selection, ownership, history |
| backend/app/services/workspace_transition.py | Serialize workspace changes and task admission |
| backend/app/api/routes/projects.py | Project and conversation API |
| backend/app/api/routes/v1.py | Project-aware admission, responses, ownership, workspace integration |
| backend/app/db/repositories/event_repository.py | Stable timestamp/ID ordering |
| backend/app/services/event_service.py | Project/conversation event envelope |
| backend/app/agents/supervisor.py | Retain saved test-report artifact ID |
| backend/app/workflows/multi_agent_nodes.py | Emit test artifact/subtask references |
| backend/tests/unit/test_projects.py | Isolation, restoration, migration, event ordering, API/approval ownership |
| backend/tests/unit/test_release_workspace.py | Isolated authenticated workspace fixtures |
| frontend/app/page.tsx | Stop global task-history polling |
| frontend/components/ProjectsSidebar.tsx | Project/conversation navigation and pagination controls |
| frontend/components/DashboardView.tsx | Project lifecycle, lazy history, stale-response guards, disabled Live |
| frontend/components/EngineeringStream.tsx | Structured failure evidence and concise recorded result |
| frontend/hooks/useTaskEventStream.ts | Stable scoped event identity, validation, ordering, cleanup |
| frontend/lib/api.ts | Project API and event/task pagination |
| frontend/lib/engineering-stream.ts | Evidence mapping, exact artifact association, replay handling |
| frontend/tests/projects.test.cjs | Sidebar isolation, states, disabled Live |
| frontend/tests/task-event-stream.test.cjs | Ordering, deduplication, stable identity, stale subscription delivery |
| frontend/tests/engineering-stream.test.cjs | Failure fields, exact/legacy artifact matching, approval replay |
| docs/project-cockpit-report.md | This report |

## Final verification

- Full backend: `python -m pytest backend/tests/ -q` — **666 passed, 1 skipped, 3 warnings in 329.08s**. Existing collection warnings name TestingAgent/TestExecutionReport classes.
- Additional focused project API run after extending approval-denial assertions: **8 passed in 17.52s**.
- Full frontend: `node --test tests/*.test.cjs` — **65 passed, 0 failed**, 4780.8859 ms.
- TypeScript checking passed; final production build also performed type checking.
- `npm run lint` — exit 0; four existing hook-dependency warnings in page.tsx, AgentCenterView, ApprovalCenterView, WorkspaceView. No new Dashboard warnings remain.
- Production build — exit 0, all four static pages generated; home route 30.9 kB and first-load JS 136 kB. Verification build used a separate `.next-cockpit-build` directory.
- `git diff --check` passed. Build-added tsconfig include paths were restored to their original values.

Local raw logs and DB-derived evidence are retained under `tmp/project-cockpit/` (ignored): backend-final.log, frontend-final.log, lint-final.log, build-final.log, browser-evidence.json, acceptance.db. These are local evidence, not newly committed public fixtures.

## Real browser acceptance

Used real FastAPI, Ollama, Next.js on localhost:3001, real authentication/approvals, and disposable external repositories. APP_ENV=test on the acceptance backend prevents root .env workspace persistence; LLM_PROVIDER remained ollama. No mock model, manual successful status, or manual repair was used.

1. Connected **Project A** through the UI. Task `8f32d531-a648-46c4-b084-30238242f092` ran its real existing test: **1 passed, exit 0, COMPLETED**. Auto initially paused because verification was expired; real verification and the normal Retry Cloud control resumed it.
2. Created **Project-B-UI** through the UI. It initially contained no Project A history. Switching back restored A. Refresh preserved its prompt, completion, events, and test artifact.
3. Task `60491b49-2baa-45c0-8e6b-c283594911d7` inspected A, proposed multiply() plus its test, displayed the actual two-file diff, waited for UI approval, applied it, executed pytest (**2 passed, 0 failed, exit 0**), passed review, and reached COMPLETED. Files on disk were inspected. Refresh while waiting for approval retained the same pending patch; it did not submit the task again.
4. Initialized a deliberately failing add() fixture in the empty disposable B repository before execution. Attempts `dcca2f61-7ad5-471a-97e1-322545698260` and `339756f0-ded0-46b6-8b28-24c4c05c44f6` stopped honestly with runner exit **3221225786**, zero captured output, and FAILED. They remain in history. No application diagnosis was claimed for those attempts.
5. After restarting only the isolated backend in a managed terminal, task `c0f44f07-f939-4280-939b-6fed68af4e5e` captured **1 failed test, exit 1**, displayed assertion/source/classification and the debugger's qualified evidence summary, proposed changing `return a - b` to `return a + b`, waited for UI approval, applied the approved patch, retested **1 passed, 0 failed, exit 0**, passed review, and reached COMPLETED. Initial and retest artifacts remain distinct. The source changed through AgentOS only.
6. Refreshed after completion and opened an older failed turn's lazy recorded activity. Correct project history, error, artifacts, latest outcome, and approval decision remained. DB snapshots before/after refresh had identical tasks and event counts: no duplicate execution.
7. Selected **Qwen Coder 3B** in the real model menu, verified the selected state, and restored **AgentOS Auto**. This verifies selection, not a second local-model engineering E2E run.
8. Live stayed disabled throughout. No provider session was started. Light and dark screenshots were inspected; settled dark composer background was rgb(23,29,39). Restored the original light theme.

## Limitations

- Not certified for public deployment or multi-user tenancy. The shared workspace root and process-local lock remain; use one backend worker for this workflow. Legacy APIs retain their existing authorization model and require a separate deployment security review.
- The event replay protocol still uses timestamp-ordered pagination. Deterministic ties, client deduplication, stale-task cleanup, and refresh were tested; arbitrary backdated inserts or delayed concurrent commits are not covered by a monotonic event sequence.
- Backend test-parser suggestions may identify the assertion's test file as the likely implementation location. The UI faithfully renders those backend suggestions; they are not independent proof. The separate debugger artifact qualifies uncertain causes, and the actual repair passed its unchanged assertion.
- The two detached-runner interruption causes were not conclusively identified. A managed backend session completed the same fixture correctly. Failed evidence was preserved.
- Very large histories, multi-worker deployments, mobile layouts, and a production database rollout were not browser-validated. New project/conversation lists have pagination; selected-conversation task summaries still refresh on the existing five-second cadence.
- Legacy unassigned tasks remain available through existing APIs; they are not guessed into the new sidebar. Read-only change-explanation messages are not a new durable chat-message store.
- Exact artifact IDs apply to newly generated reports. Ambiguous legacy artifacts remain separate rather than being guessed into a test run.

## Requested verdicts

| Requirement | Verdict |
|---|---|
| Apache License 2.0 added | YES |
| Projects replace global Chat History | YES |
| Project-specific history works | YES |
| Cross-project isolation verified | YES for the cockpit/project APIs; legacy API tenancy NOT VERIFIED |
| Real execution stream works | YES |
| Duplicate/out-of-order stream issue fixed | YES for tested replay/order/switch cases; delayed-commit edge case NOT VERIFIED |
| Real file activity displayed | YES |
| Real commands displayed | YES |
| Real test results displayed | YES |
| Structured diagnosis displayed | YES |
| Inline approval works | YES |
| Real diff works | YES |
| Refresh persistence verified | YES |
| Live temporarily disabled | YES |
| Existing Live implementation preserved | YES; live provider behavior not re-exercised |
| AgentOS Auto preserved | YES |
| Manual local models preserved | YES for real selection and verification probes; engineering E2E NOT VERIFIED in this phase |
| Security mechanisms preserved | YES for existing gates and tested v1 checks; no deployment certification |
| Full regression passing | YES |
| Production build passing | YES |
| Ready for deployment | NO — local acceptance passed; deployment/security limitations above remain |

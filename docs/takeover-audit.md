# Takeover audit — 2026-09-10

## Baseline before this turn's edits

The checkout arrived with 29 modified tracked files and existing live-voice integration tests/workspace components. Those changes are preserved and are part of the baseline, not newly authored work in this turn.

- System Python 3.13: `python -m pytest backend/tests/ -q --tb=short`: **491 passed, 1 skipped, 0 failed, 0 collection errors**, 109.18 s. Four warnings; pytest cache ACL warning and a background Ollama 404 were observed.
- Repository `.venv` has no pytest installed.
- `npm run build`: passed (Next 15.1.7 compilation/type validation/static generation).
- `npm run lint`: did not run checks; prompts for initial ESLint configuration.
- Logs: `tmp/takeover-baseline-{backend,build,lint}.log` (local ignored files).

## Actual architecture

FastAPI `backend.app.main:app` mounts legacy routers and `/api/v1`. Auth dependencies supply user roles; tool security, workspace path validation, sensitive-file checks, bounded subprocess execution, and SHA-256 patch approvals are separate boundaries. TaskService persists task lifecycle records; API v1 and VoiceService dispatch the same persisted task ID through MultiAgentService into the Supervisor LangGraph. Legacy agent/coding/adaptive graphs and worker/queue runtimes remain present.

Supervisor uses TaskClassifier, ContextEngine (bounded repository file context), TaskDecomposer (LLM DAG with heuristic fallback), ParallelExecutor, and ResultAggregator. WorkspaceService provides path confinement; ProjectCreatorService creates a project and changes the process-wide workspace. Artifacts, events, approvals, task records, worker leases and queue records use SQLAlchemy. LangGraph uses SQLite checkpoints. Events are persisted, optionally published to Redis, and replayed/polled through the authenticated v1 WebSocket. Frontend is Next App Router + React local state + AgentOSClient + useTaskEventStream, with five-second task polling.

Registered agents: Supervisor; Research (repository analysis, code readers); Coding (patch proposals); Debugger (tests/diagnosis); Reviewer (verdicts); Documentation (summary generation); Security (advisory sensitive-file inspection); Testing (bounded test runner); Data Engineer (dataset profiling); DevOps (infrastructure inspection); Cybersecurity (advisory analysis; direct invocation is admin-gated). Supervisor invokes workers by AgentType, passing SubTask and receiving AgentResult. Registry declares allowlists/budgets; actual enforcement varies by worker. Plan, context, patch, test, diagnosis, security and final-summary artifacts are persisted; subtask events feed execution UI. Additional planner/executor/orchestrator, reflection, investigator, failure-analyzer, judge and adaptive-supervisor classes serve older workflows, not additional user-managed workers. There is no distinct registered Repository Agent: Research supplies that role.

## Findings before modifications

- Voice already records audio with MediaRecorder, ends a turn after 1.4 seconds of silence, submits the combined execute endpoint automatically, and waits for AssemblyAI REST `completed`. It does not submit partial transcripts or require Send. TTS uses browser speech synthesis. Clarification/confirmation reuse a user/session-keyed, five-minute process-local conversation. No streaming STT is implemented.
- Agents navigation/manual selection already removed from the primary shell; backend catalog remains. Execution consumes real events. Settings is entirely local prototype state; Save only shows a temporary success label. Header search has no search implementation. Sidebar Artifacts actually opens approvals.
- Models declare one canonical Base, with no model import-time create_all. Explicit init_db runs in FastAPI lifespan, worker startup and pytest session setup. pytest_configure assigns a unique DB URL before collection. Settings normalizes relative SQLite URLs; init_db creates parent directories. Existing integration test checks clean imports and repeated initialization in a subprocess.
- CI/security workflows run on main/master push/PR; security also supports manual dispatch. No path/job filters suppress tests. Both install requirements and invoke pytest from repository root. A local run can verify their commands, not hosted trigger history. CI lacks frontend checks. Migrations live under backend/app/db/migrations; Dockerfile incorrectly references an absent top-level alembic directory.
- Critical execution gap: CodingAgent uses hardcoded calculator/authentication hunks; generic project instructions are not implemented by a model. Multi-agent graph runs all dependent tests/reviews before approval/application. Apply failures can still lead to completion. Debugger diagnosis contains a hardcoded root cause. Existing green tests alone do not establish demo readiness.
- Process-global workspace and process-local conversation mean multi-user/project concurrency is not isolated. PostgreSQL SQLAlchemy support does not make the SQLite-only specialized graph checkpointers PostgreSQL-compatible.

## Scoped implementation plan

Keep existing voice/event/agent/database architecture. Fix model-driven patch generation and ordering of approval/application versus dependent work; retain all security gates. Add behavioral graph/voice regressions, improve confidence/clarification behavior and honest execution display. Remove confirmed placeholder Settings/search controls. Configure frontend lint and run the exact security workflow test commands. Report live microphone/provider and hosted CI separately from local automated evidence.

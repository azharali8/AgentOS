# AgentOS

AgentOS is a secure, autonomous AI software-engineering platform that orchestrates specialized agents to inspect repositories, plan tasks, generate and apply code changes, run tests, recover from failures, and operate under human approval and security boundaries.

---

## Key Capabilities

- **Supervisor-Based Multi-Agent Orchestration**: Centralized task decomposition, dependency sequencing, dynamic handoffs, and lifecycle management.
- **LangGraph Workflow Execution**: Stateful execution graphs with deterministic state transitions and checkpointing.
- **Repository Intelligence**: AST indexing, symbol extraction, dependency graph traversal, semantic search, and file structure mapping.
- **Bounded Context Engine**: Agent-specific context pruning, relevance scoring, token budgeting, and explicit justification tracing (`why_selected`).
- **Task Classification & Adaptive Planning**: Automatic classification of software engineering intents (Feature, Bugfix, Refactor, Security, DevOps, Data) with dynamic replanning.
- **Specialized Engineering Agents**: Dedicated agents for Coding, Debugging, Testing, Data Engineering, DevOps, Cybersecurity, and Architecture Review.
- **Real Workspace Inspection & Mutation**: Sandboxed filesystem modifications, deterministic patch application, and workspace safety confinement.
- **Cryptographically Verified Patches**: SHA-256 patch hashing, pre-application diff inspection, and atomic application.
- **Human-in-the-Loop Approval Gates**: Policy-driven interrupt gates for high-risk operations (destructive commands, protected file modifications).
- **Durable Task Runtime**: Non-linear state machine supporting first-class pause/resume, two-phase cancellation (`RUNNING` &rarr; `CANCELLING` &rarr; `CANCELLED`), and process restart recovery (`RECOVERY_REQUIRED`).
- **Failure Classification & Automatic Recovery**: Categorization of Tool, Agent, Timeout, and Security failures with automatic retry and replan loops.
- **Immutable Execution Artifacts**: SHA-256 write-time content hashing and read-time cryptographic integrity checks (`ArtifactIntegrityError`).
- **Structured Agent Protocol**: Strongly typed agent message envelopes (`TaskAssignmentMessage`, `DiagnosisReportMessage`, `PatchProposalMessage`, `ReviewVerdictMessage`).
- **Hierarchical Execution Tracing**: Detailed execution trees capturing tool invocations, durations, tokens, and outputs.
- **Model Routing & Provider Health**: Task-specific model routing profiles (Coding, Reasoning, Classification) with latency measurement, fallback chains, and zero silent-mocking in production.
- **Authentication & RBAC**: Role-Based Access Control (`ADMIN`, `DEVELOPER`, `USER`, `VIEWER`), session TTL (3600s), sliding window refresh, and logout token revocation.
- **Rate Limiting & Brute-Force Protection**: Multi-domain sliding-window rate limiting (`auth`, `task_create`, `api`, `ws`) and 5-attempt / 15-minute account lockout.
- **Workspace Sandbox & Boundary Defense**: Strict defenses against path traversal (`..`), URL encoding, null bytes, UNC paths, Windows drive escapes, and symlink escapes.
- **Voice-Driven Autonomous Engineering**: Hands-free voice interface powered by AssemblyAI Speech-to-Text with bidirectional audio synthesis feedback and live workspace execution.
- **WebSocket Event Streaming & Replay**: Real-time append-only event streaming with handshake authentication and reconnection event replay from `last_event_id`.
- **Observability & Health Probes**: `/health` liveness and `/ready` readiness probes checking database integrity, workspace availability, and model router health.
- **SQLite Persistence & Integrity**: SQLite storage with `@with_db_retry` exponential backoff for busy/lock handling and `PRAGMA integrity_check` validation.
- **Disaster Recovery CLI**: CLI tool (`create`, `verify`, `restore`, `list`) with sidecar checksums and functional post-restore table query verification.
- **Docker & Compose Deployment**: Multi-stage Docker packaging with non-root runtime (`agentos:agentos`) and persistent named volumes.

---

## Architecture

The Supervisor agent and LangGraph workflow engine serve as the central orchestration authority:

```text
User / API / Frontend
       |
       v
Authentication & RBAC Gate (Session TTL, Logout Blacklist, Rate Limiting)
       |
       v
API v1 Router (`/api/v1/tasks`)
       |
       v
Task Classifier (Feature, Bugfix, Refactor, Security, DevOps, Data)
       |
       v
Supervisor Agent (Orchestration & Decomposition Authority)
       |
       +---> Repository Intelligence & Bounded Context Engine
       |
       v
Specialized Agent Execution (Coding, Debugger, Testing, DevOps, Data, Security)
       |
       v
Security Policy & Approval Gate (Human-in-the-Loop for high-risk operations)
       |
       v
Tool Execution (Filesystem, Git, Terminal, Code Parser)
       |
       v
Workspace Modification & SHA-256 Patch Verification
       |
       v
Automated Test Runner & Verification
       |
       v
Reviewer Agent (Code Quality & Security Verification)
       |
       v
[ Failure? ] ---> Failure Classifier ---> Recovery & Adaptive Replanning Loop
       | (Success)
       v
Immutable Artifacts + Event Bus + Hierarchical Execution Trace
       |
       v
Task Completion (`COMPLETED`)
```

---

## Security

AgentOS enforces security controls at each boundary:

- **Authentication & Sessions**: API key and session-based authentication with 3600s sliding-window TTL, instant logout revocation, and constant-time password comparison.
- **Role-Based Access Control (RBAC)**: Strict role boundaries (`ADMIN`, `DEVELOPER`, `USER`, `VIEWER`) guarding administrative endpoints and dangerous operations.
- **Brute-Force Protection**: 5 consecutive failed login attempts trigger an automatic 15-minute account lockout.
- **Multi-Domain Rate Limiting**: Independent rate limit buckets for Authentication (5/min), Task Creation (10/min), Standard API (100/min), and WebSockets (5/min).
- **Workspace Confinement**: All file access is strictly bound to `WORKSPACE_ROOT`. Symlink escapes, path traversal (`..`), URL-encoded paths, null bytes, UNC network paths, and Windows drive escapes are rejected.
- **Sensitive File Protection**: Immediate access denial for `.env*`, private keys (`id_rsa`, `*.pem`, `*.key`), credentials, and configuration files.
- **Command Execution Controls**: Shell constructs (`|`, `&&`, `;`, backticks, subshells) and dangerous shell wrappers (`cmd /c`, `powershell -c`, `bash -c`) are prohibited. Executables are restricted to an allowlist.
- **Cryptographic Patch & Artifact Integrity**: Write-time SHA-256 hashing and mandatory read-time verification. Tampered artifacts or patches raise `ArtifactIntegrityError`.
- **Human Approval Gate**: Mutations to protected directories or destructive commands require explicit human review before execution.
- **Audit Logging & Secret Redaction**: Append-only audit logs for security actions with automated credential redaction in logs and traces.
- **Non-Root Container**: Production Docker containers execute under a dedicated `agentos` non-root user.

---

## Project Structure

```text
AgentOS/
├── backend/
│   ├── app/
│   │   ├── agents/            # Supervisor, Coding, Debugger, Reviewer, Domain Experts
│   │   ├── api/               # FastAPI route modules and v1 API router
│   │   ├── auth/              # Authentication service, RBAC, session management
│   │   ├── code/              # AST parser, symbol extractor, patch engine, test runner
│   │   ├── config/            # Settings, development & production profiles
│   │   ├── db/                # SQLAlchemy database engine, models, session manager
│   │   ├── evaluation/        # Security, reliability, load, and phase benchmark suites
│   │   ├── llm/               # Model factory, providers (Ollama, Anthropic, OpenAI)
│   │   ├── models/            # Pydantic schemas (Task, Agent, Tool, Approval, Workflow)
│   │   ├── observability/     # Metrics collector, correlation middleware, redaction
│   │   ├── security/          # Rate limiter, sensitive file policy, agent permissions
│   │   ├── services/          # TaskRuntime, ModelRouter, ContextEngine, BackupService, etc.
│   │   ├── tools/             # Tool definitions (Filesystem, Terminal, Git, CodeTools)
│   │   ├── workflows/         # LangGraph StateGraph workflow nodes and execution logic
│   │   └── main.py            # FastAPI application entrypoint with health & ready probes
│   ├── scripts/               # E2E scenario runners (Phase 12, Phase 13, Phase 14)
│   └── tests/                 # 420+ Unit, integration, and security test suites
├── frontend/                  # Next.js 15 Control Center UI
│   ├── app/                   # App router pages (Dashboard, Tasks, Agents, Evaluation)
│   ├── components/            # UI components (TaskMonitor, EventStream, ApprovalModal)
│   ├── lib/                   # API client and WebSocket streaming adapters
│   └── package.json           # Frontend dependencies and build scripts
├── alembic/                   # Database migrations
├── sdk/                       # AgentOS Python SDK
├── Dockerfile                 # Multi-stage production container definition
├── docker-compose.yml         # Container orchestration with named persistent volumes
├── .dockerignore              # Docker build context exclusion rules
├── .gitignore                 # Version control ignore definitions
├── requirements.txt           # Python production dependencies
└── pyproject.toml             # Project metadata
```

---

## Installation & Setup

### Prerequisites

- **Python**: 3.11+
- **Node.js**: 20+ (with npm)
- **Git**

### 1. Clone the Repository

```bash
git clone https://github.com/azharali8/AgentOS.git
cd AgentOS
```

### 2. Backend Setup

Create and activate a virtual environment:

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Install backend dependencies:

```bash
pip install -r requirements.txt
```

Initialize the database:

```bash
alembic upgrade head
```

### 3. Frontend Setup

```bash
cd frontend
npm.cmd install
cd ..
```

---

## Running AgentOS

### Start the Backend Server

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Start the Control Center Frontend

```bash
cd frontend
npm.cmd run dev
```

Open `http://localhost:3000` to access the Control Center.

### Health & Operational Endpoints

- **Liveness Probe**: `GET /health` (Returns process uptime and basic status)
- **Readiness Probe**: `GET /ready` (Verifies database integrity, workspace root, and model router health; returns HTTP 503 if degraded)
- **Root Status**: `GET /` (Service version and status)

### API v1 Key Endpoints

- **Authentication**: `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`
- **Tasks**: `POST /api/v1/tasks`, `GET /api/v1/tasks/{task_id}`, `POST /api/v1/tasks/{task_id}/cancel`, `POST /api/v1/tasks/{task_id}/pause`, `POST /api/v1/tasks/{task_id}/resume`
- **Streaming**: `WS /api/v1/events/stream/{task_id}` (Real-time event stream with `last_event_id` replay)
- **Approvals**: `GET /api/v1/approvals`, `POST /api/v1/approvals/{approval_id}/resolve`
- **Workspace**: `GET /api/v1/workspace/tree`, `GET /api/v1/workspace/file`
- **Artifacts**: `GET /api/v1/artifacts/{artifact_id}`, `GET /api/v1/artifacts/task/{task_id}`
- **System & Runtime**: `GET /api/v1/system/status`, `GET /api/v1/system/runtime`, `GET /api/v1/system/concurrency`, `GET /api/v1/system/models`

---

## Docker Deployment

AgentOS includes a multi-stage Docker build with non-root security and persistent volumes:

### Build and Start Containers

```bash
docker compose up --build -d
```

### View Service Logs

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

### Stop Containers

```bash
docker compose down
```

### Persistent Data Volumes

The Docker Compose configuration mounts dedicated volumes to preserve state across restarts:
- `agentos-data` &rarr; `/app/data` (SQLite database and backups)
- `agentos-workspace` &rarr; `/app/workspace` (Code repository sandbox)
- `agentos-artifacts` &rarr; `/app/artifacts` (Immutable generated artifacts)

---

## Backup & Disaster Recovery CLI

AgentOS includes an integrated SQLite backup and recovery utility with checksum verification:

```bash
# Create a timestamped, checksummed database backup
python -m backend.app.services.backup_service create

# List available database backups
python -m backend.app.services.backup_service list

# Verify integrity and checksum of a backup
python -m backend.app.services.backup_service verify --path data/backups/agentos_backup_<timestamp>.db

# Restore from a backup (includes pre-restore snapshot, verification, and table checks)
python -m backend.app.services.backup_service restore --path data/backups/agentos_backup_<timestamp>.db
```

---

## Testing & Verification

Run the verification test suites and benchmarks locally:

```powershell
# 1. Full Backend Test Suite (420+ unit and integration tests)
python -m pytest backend/tests/ -q --tb=short -W ignore

# 2. Phase 13 Autonomous Platform Benchmark (20 cases)
python -m backend.app.evaluation.phase13_benchmark

# 3. Phase 14 Security Benchmark (25 deterministic cases)
python backend/app/evaluation/phase14_security_benchmark.py

# 4. Phase 14 Reliability Benchmark (20 deterministic cases)
python backend/app/evaluation/phase14_reliability_benchmark.py

# 5. Phase 14 Load & Performance Test (8 performance targets)
python backend/app/evaluation/phase14_load_test.py

# 6. Phase 14 E2E Crash & Recovery Simulation
python backend/scripts/run_e2e_phase14.py

# 7. Frontend Production Build
cd frontend; npm.cmd run build; cd ..
```

### Local Verification Results

| Verification Suite | Target | Local Result | Status |
| :--- | :--- | :--- | :---: |
| **Backend Unit & Integration Regression** | 420+ Tests | 420 passed, 1 skipped | **PASSED** |
| **Phase 13 Platform Benchmark** | 20 Cases | 20 / 20 (100%) | **PASSED** |
| **Phase 14 Security Benchmark** | 25 Cases | 25 / 25 (100%) | **PASSED** |
| **Phase 14 Reliability Benchmark** | 20 Cases | 20 / 20 (100%) | **PASSED** |
| **Phase 14 Load & Latency Test** | 8 Targets | 8 / 8 (100%) (p95 latency &le; 50ms, recovery &le; 3ms) | **PASSED** |
| **Phase 14 E2E Crash & Recovery** | 20 Steps | 20 / 20 (100%) | **PASSED** |
| **Frontend Production Build** | Static Build | 4 / 4 pages compiled cleanly | **PASSED** |

*(Note: These represent local test suite results executed against the repository codebase).*

---

## Create New Projects From Scratch

AgentOS supports two distinct project onboarding modes:

### Mode 1: Connect Existing Project

Point AgentOS at an existing software directory on your machine. AgentOS will index your files, extract AST symbols, assemble repository intelligence, and enable all specialized agents to work on your codebase immediately.

### Mode 2: Create New Project From Scratch

Give AgentOS a project name, parent directory, and natural-language instruction. AgentOS will:

1. **Create a safe project directory** at `<location>/<name>`.
2. **Initialize base files** — a `README.md` and `.gitignore`.
3. **Initialize a Git repository** (if available on the machine).
4. **Switch the active `WORKSPACE_ROOT`** to the newly created project directory.
5. **Submit the instruction to the Supervisor** as a standard engineering task.
6. **Execute the full engineering workflow** using existing specialized agents.

**Canonical Workflow:**

```text
User Prompt ("Create a FastAPI app with JWT and tests")
        |
        v
POST /api/v1/workspace/create-project
        |
ProjectCreatorService
  → validate project name and location
  → prevent path traversal & AgentOS self-targeting
  → detect existing directory conflicts
  → create project directory
  → write README.md + .gitignore
  → initialize Git
  → switch WORKSPACE_ROOT
        |
        v
TaskService.create_task (instruction passed as normal engineering task)
        |
        v
SupervisorAgent
  → understand requirements
  → decompose into engineering plan
  → delegate to specialized agents:
        CodingAgent    → scaffold modules, APIs, configuration
        TestingAgent   → write and run test suites
        DebuggerAgent  → diagnose and fix test failures
        ReviewerAgent  → verify code quality and security
  → human approval where required
        |
        v
Completed project, indexed and active as persistent workspace
```

**Follow-up tasks on the same project:**

Once the project is created, all subsequent prompts operate naturally against the same workspace:

- `"Add email authentication."`
- `"Write integration tests for the auth module."`
- `"Run the tests and fix failures."`
- `"Perform a security review."`

**Safety guarantees:**

- Project directories can only be created **outside** the AgentOS installation tree.
- Path traversal (`..`), null bytes, and UNC paths are rejected.
- If the target directory already exists and is non-empty, creation is **rejected** (HTTP 409 Conflict).
- If the engineering task fails, the **project directory is preserved**. Failure is tracked in the existing task state machine and visible through the AgentOS task activity view.

**API:**

```http
POST /api/v1/workspace/create-project
Content-Type: application/json

{
  "name": "TaskFlow",
  "location": "D:/Projects",
  "instruction": "Create a FastAPI task management API with JWT authentication and PostgreSQL",
  "auto_start_task": true
}
```

Response:

```json
{
  "status": "ok",
  "project_name": "TaskFlow",
  "path": "D:/Projects/TaskFlow",
  "git_initialized": true,
  "task_id": "task-abc12345-..."
}
```

---

## Voice Agent & Audio Interface

AgentOS features a voice-driven autonomous software engineering interface powered by **AssemblyAI**:

```text
Microphone Audio Capture (Browser MediaRecorder)
        |
        v
POST /api/v1/voice/transcribe or /api/v1/voice/execute
        |
AssemblyAI Speech-to-Text Provider (REST API)
  → Secure Upload Chunking
  → Asynchronous Audio Transcription
  → Polling & Status Verification
        |
        v
VoiceService (Intent Routing & Task Creation)
        |
        +---> Project Creation Intent? → ProjectCreatorService (scaffold & switch workspace)
        |
        +---> Standard Engineering Intent? → TaskService & Supervisor Agent
        |
        v
Multi-Agent Engineering Pipeline (Coding → Testing → Debugging → Review)
        |
        v
Real File Mutation & Test Verification
        |
        v
Audio Synthesis Feedback (Browser SpeechSynthesis / TTS Provider)
```

### Voice API Endpoints

- `GET /api/v1/voice/status` — Returns active provider (`assemblyai` / `mock`), configured TTS provider, and credit/quota readiness.
- `POST /api/v1/voice/transcribe` — Uploads raw audio (`.webm`, `.wav`, `.mp3`, `.ogg`, `.m4a`) and returns high-accuracy transcript with confidence score.
- `POST /api/v1/voice/execute` — End-to-end voice invocation: transcribes audio and immediately launches an autonomous engineering task on the active workspace.
- `POST /api/v1/voice/synthesize` — Synthesizes task completion summaries or agent feedback into audio responses.

### Voice Configuration (`.env`)

```env
ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here
VOICE_PROVIDER=assemblyai
VOICE_TTS_PROVIDER=browser
VOICE_MAX_AUDIO_SIZE_BYTES=26214400
VOICE_TIMEOUT_SECONDS=120
```

---

## Current Status

AgentOS has completed **Phases 0 through 15**. The system supports dual project onboarding (connect existing + create from scratch), durable task execution, bounded context management, model routing, multi-domain rate limiting, non-linear state machines, and disaster recovery.

---

## Roadmap

Planned future enhancements:
- Distributed worker queues (Celery / Redis / Temporal)
- Multi-database backend support (PostgreSQL / MySQL)
- Expanded cloud deployment templates (Kubernetes Helm charts, AWS ECS)
- OpenTelemetry metrics and distributed tracing exporters
- Additional LLM provider integrations (Google Gemini, Mistral, AWS Bedrock)
- CI/CD pipeline automation bots and GitHub Actions integration

---

## License

Licensing information is not yet specified.

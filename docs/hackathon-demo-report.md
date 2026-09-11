# Hackathon demo verification — 2026-09-11

## IMPLEMENTED

- Installed-model health reporting, bounded Ollama calls, explicit network/output-limit errors, schema validation and bounded regeneration of malformed output. Local default: `qwen2.5-coder:3b`.
- Supervisor test/review ordering, strict failure handling, original-request/runtime/source context, and one bounded read-and-regenerate step for previously unread existing files. Approval and patch validation remain enforced.
- Project test subprocesses exclude AgentOS configuration, including its database URL and provider credentials. Speech routing handles actual transcription spacing (`Agent OS`, `fast API`). Small model-health UI correction; no redesign.

## TESTED

- Latest targeted reliability/workflow checks: **22 passed** (`tmp/next-context-tests.log`).
- Full backend: **515 passed, 1 skipped**, four collection/cache warnings (`tmp/next-final-backend2.log`). Existing tests retained.
- Frontend production build passed (`tmp/next-final-build.log`); lint passed with four existing hook warnings (`tmp/next-lint.log`). `git diff --check` passed.

## REAL E2E RESULT

- Real AssemblyAI transcription of a synthetic spoken WAV initiated project creation and Supervisor execution. The recognized request was: “Agent OS, create a fast API URL shortener with authentication and tests.”
- **`gpt-oss:120b-cloud`** completed task `cb8ca02e-c192-4643-aceb-ba1c6aaf7490` through real approval, patch, failed tests, debugging, renewed approval, successful retest and review. The local 3B attempt failed safely; it did not complete this demo.
- Independent checks caught two defects missed by the first review: a hardcoded short-URL host and stripped destination path slashes. Follow-up instructions went through AgentOS; no generated implementation was manually edited. After correction, **all seven independent API checks passed** (`tmp/next-api-acceptance2.log`). This was a guided run, not evidence of reliable unattended generation.
- Final corrective task `e345f710-60ab-483f-b7a6-62cc3be32b42` completed after two debug/retest cycles: **6 generated tests passed**, followed by model review SUCCESS (`tmp/next-cloud-fix4-approve3.log`, final `state.json`). Corrections addressed invalid test passwords and URL expectations; all six tests and meaningful behavioral assertions remain. Two unrelated or ineffective repair proposals were rejected through the approval gateway during earlier corrective tasks.
- Generated project and complete model/task evidence: `tmp/next-live-77597ceb97b549eeaa5a197172f4f6c9/UrlShortenerApp` and its parent directory.

## NOT VERIFIED

- Successful physical-microphone utterance and audible browser TTS. The signed-in voice UI was exercised, but the verified speech input was a synthetic WAV sent through the real transcription service.
- Repeated unattended completion and production readiness of the generated application.

## NEXT BLOCKER

Model repair/review accuracy: independent acceptance and human patch review remain necessary.

## Reproducing the approved cloud profile

The default local configuration was preserved during cloud trials. The temporary cloud service was stopped after verification. To recreate it, run `$env:OLLAMA_HOST='127.0.0.1:11435'; ollama serve` in a separate PowerShell session with network access and the existing authenticated Ollama account. In the AgentOS process session use these overrides:

```powershell
$env:OLLAMA_BASE_URL='http://127.0.0.1:11435'
$env:OLLAMA_MODEL='gpt-oss:120b-cloud'
$env:OLLAMA_NUM_PREDICT='12288'
$env:OLLAMA_NUM_CTX='8192'
$env:OLLAMA_REASONING_EFFORT='medium'
$env:LLM_TIMEOUT_SECONDS='180'
```

The temporary `tmp/next_live.py` harness invokes real AgentOS services and records outputs; it does not supply generated application code. Cloud responses are validated client-side because [Ollama cloud does not support structured outputs](https://docs.ollama.com/capabilities/structured-outputs). The listed Qwen cloud model returned HTTP 402; no credits or subscription were purchased.

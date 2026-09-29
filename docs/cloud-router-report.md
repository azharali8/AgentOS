# Cloud-first Auto router acceptance

Local verification: September 28-29, 2026. This report supersedes the cloud-routing portion of the earlier release freeze report; it does not erase earlier failed Llama runs or certify deployment/voice.

## Model verification

Every listed cloud model was attempted through AgentOS's real Ollama generation adapter. At most two small requests per model: a short chat response, then a structured two-file calculator repair with a runnable pytest test. Successful structured results were parsed and Python-validated, then their generated test was executed. Latency is total probe elapsed time, not an inference benchmark. No large workflow was run for each model.

| Model | Status | Structured output | Coding / debugging probe | Latency |
|---|---|---|---|---|
| qwen3.5:397b-cloud | UNAVAILABLE: HTTP 410, retired | Not reached | Not reached | 10.78 s |
| nemotron-3-super:cloud | HEALTHY | Pass | Pass; 1 test passed | 32.71 s |
| deepseek-v4-flash:cloud | UNAVAILABLE: HTTP 410, retired | Not reached | Not reached | 9.40 s |
| glm-5.2:cloud | UNAVAILABLE: HTTP 402, account access restriction | Not reached | Not reached | 9.51 s |
| kimi-k3:cloud | UNAVAILABLE: HTTP 402, account access restriction | Not reached | Not reached | 8.56 s |
| kimi-k2.6:cloud | UNAVAILABLE: HTTP 402, account access restriction | Not reached | Not reached | 7.59 s |
| minimax-m2.7:cloud | UNAVAILABLE: HTTP 402, account access restriction | Not reached | Not reached | 9.04 s |
| gpt-oss:120b-cloud | HEALTHY | Pass | Pass; 1 test passed | 24.55 s |
| gemma4:31b-cloud | HEALTHY | Pass | Pass; 1 test passed | 26.73 s |

Healthy pool / initial order: **GPT OSS → Gemma4 → Nemotron**. All three passed the small capability check; elapsed latency breaks that tie. Six unavailable models are excluded, not repeatedly retried. A successful small probe is not a general reliability score or a guarantee of continued availability.

Local Qwen Coder 3B and Llama 3.2 3B passed chat/schema compatibility but failed their generated coding tests (missing fixture and parameterization mismatch respectively). They remain explicit local choices with no quality guarantee. Qwen3 VL returned HTTP 400 because this adapter's generate endpoint is unsupported; it is hidden. Nomic is embedding-only and excluded. Duplicate Llama tags share one selector entry.

Probe evidence is retained locally under `tmp/cloud-router/verification.json`, `local-verification.json`, and their generated probe directories. Account-specific results are intentionally ignored by Git. The maintained `scripts/verify_ollama_models.py` also adds independent calculator assertions for future verifications; those extra assertions are not retrospectively claimed for the original probe run.

## Architecture and quota

`AGENTOS_AUTO` is the default setting/template and default per-user browser preference. Tasks capture their model selection at creation; changing a preference does not rewrite another task. Explicit local tasks instantiate only that local adapter. Auto instances route only through verified healthy cloud records. Backend routing events record selected model, provider failure, failover, and exhaustion, while the normal conversation displays AgentOS Auto.

Verification is endpoint-bound and expires after seven days. Run the explicit verification command to refresh it. No background generation probes run. Runtime health uses a process-local lock/cooldown; it is not a distributed health database. Permanent quota/access blocks stay blocked for that process; reverify and restart after restoring provider access. Existing `.env` values may override the CLI setting; the browser's user preference defaults to Auto independently.

**Exact quota exposed by the current documented generation response/adapter: NO.** Remaining quota stays unknown/null. Generation token counters describe consumed work, not account balance. See [Ollama generation response](https://docs.ollama.com/api/generate) and [cloud account usage guidance](https://docs.ollama.com/cloud). No undocumented account scraping is used.

Explicit quota-exhaustion messages/codes on HTTP 402/429 yield QUOTA_EXHAUSTED. A bare access-denied 402 is UNAVAILABLE, not fabricated quota exhaustion. Other 429 responses use bounded Retry-After/default cooldown. HTTP access/missing/retired failures and transport/server failures are separately handled. See [Ollama API errors](https://github.com/ollama/ollama/blob/main/docs/api/errors.mdx). No fabricated balances or reset estimates appear.

Each eligible model is attempted at most once per generation request at the router level (the existing adapter retains its bounded connection retry). Schema, patch validation, and test failures retain existing bounded recovery semantics and cannot masquerade as quota failover. Pool exhaustion interrupts the graph at a saved node boundary with CLOUD_POOL_EXHAUSTED. Explicit local selection or retry resumes that checkpoint. Already applied patches are retained; new patches retain their own approval. A partially run node may repeat read/test work on resume, but prior approved patch application is not replayed. There is no automatic local fallback.

## Real browser Auto acceptance

- Command: **Create a simple FastAPI health endpoint and add a test for it.**
- Task: `86e1363e-a7d0-423f-813f-e54ddbbdcd47`.
- Fresh project: `C:/Users/evo/AppData/Local/Temp/AgentOS-auto-cloud-20260928`.
- Initial fixture: a FastAPI app in main.py; no endpoint or test.
- Internal provider: GPT OSS encountered UNAVAILABLE; real failover selected Gemma4.
- Generated files: `main.py`, `test_main.py`.
- Approval: inspected browser diff including status-code and JSON assertions, then clicked **Approve & Apply**.
- Runtime tests: **1 passed, 0 failed**, exit 0; captured pytest stdout reports 0.93 s (runner elapsed about 7 s).
- Review: approved; final state **COMPLETED**, 3/3 subtasks.
- No manual generated-file repair or success marking.

Durable local evidence: `tmp/cloud-router/acceptance.db` and `acceptance-evidence.json`; full task events retain patch/test/review evidence. The observed UNAVAILABLE reason is not claimed to be a quota failure.

## Manual local acceptance

Selected **Qwen Coder 3B** in the browser and confirmed the selected label before submitting: “Explain what the health endpoint in main.py does. Do not change files.” Task `6f4cebd0-406a-447f-9d63-5bcd45d7dd24` completed with `qwen2.5-coder:3b` and no cloud-routing events or file changes. Restored **AgentOS Auto**, confirmed in the browser.

An earlier immediate submission raced the asynchronous selection and used Auto. That exposed a UI bug: sending is now disabled/guarded while selection is pending. Failed selection returns an explicit failure, so Retry Cloud cannot silently resume using an old local choice. The preceding raced task is retained as evidence, not counted as local acceptance.

## Controlled failover and regression

Focused router tests: **19 passed**. External-provider doubles cover 402 quota, 429, missing model, server/transport timeout, exhaustion bounds, cooldown, invalid-output handling, task isolation, per-user selection, verification expiry, and health checks. Real internal graph tests exercise provider failover through plan/code/approval/apply/pytest/review; pool exhaustion before planning; and exhaustion during review after application. Explicit local resumption preserves actual test evidence and applies the approved patch exactly once. Existing repair tests continue to require new approval for new patches.

Frontend: **56 passed**, 0 failed. Lint: **exit 0**. Production build: **exit 0**, with four existing hook dependency warnings. Final backend rerun: **654 passed, 1 skipped, 4 warnings in 222.36 s**, exit 0. An intermediate full run had **654 passed, 1 failed, 1 skipped**: an existing mocked voice-workflow test's nested pytest exceeded its unchanged 15-second timeout while concurrent checks were running. No Voice code or timeout was changed; the final sequential rerun passed. Logs: `data/cloud-router-backend-final.log`, `data/cloud-router-frontend.log`, `data/cloud-router-lint.log`, and `data/cloud-router-build.log`. The focused router plus existing takeover workflow run passed **30 tests** after the separate capacity-checkpoint fix.

Post-suite cleanup found an older project-creation test replacing all of `os.environ`, hiding pytest's persistence guard and writing a temporary workspace into root `.env`. Its mocks now preserve environment markers using `patch.dict`; all **27 project-creation tests passed** afterward and the restored `.env` workspace stayed unchanged. This was a test-only follow-up after the full 654-pass run; no runtime project-lifecycle behavior was changed.

AssemblyAI calls: **0**. No voice code was changed in this router phase; existing prior-phase voice edits in the working tree remain separate. Full baseline tests include isolated speech-provider doubles, not real transcription.

## Verdicts and limits

- ALL CLOUD MODELS VERIFIED: **YES**, meaning all nine attempted; only three qualified healthy.
- AUTO CLOUD ROUTER WORKING: **YES**.
- CLOUD FAILOVER WORKING: **YES**, real unavailable-provider transition and controlled error cases.
- LOCAL MODELS ONLY VISIBLE ON FRONTEND: **YES**, alongside AgentOS Auto; no cloud-name options.
- MANUAL LOCAL OVERRIDE WORKING: **YES**.
- CLOUD-POOL-EXHAUSTION FALLBACK WORKING: **YES** in controlled real-graph tests, with explicit local selection; browser exhaustion notice is implemented, not a separately forced live provider-outage acceptance.
- CORE HACKATHON DEMO READY: **YES for the demonstrated small text/approval/test/review workflow**. Cloud access can change. This is not general production readiness.

A new real-cloud diagnosis/repair/reapproval/retest acceptance was not performed here. Earlier Llama repair failures remain valid limitations. Docker/production and physical voice readiness remain unverified/unresolved as documented in the earlier release report.

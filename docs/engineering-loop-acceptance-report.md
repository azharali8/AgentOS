# Engineering loop verification — September 22, 2026

## Scope and verdict

REAL AUTONOMOUS ENGINEERING LOOP WORKING END-TO-END: **NO**.

The real `llama3.2:latest` rerun did not complete the requested creation-to-repair-to-review loop. Regression success must not be interpreted as live-model success. No generated project files were manually repaired and no task was manually marked successful.

## Changes

- Strict debugger results publish captured test/source observations. Model root-cause narratives, API-history claims, confidence and invented file targets are not promoted to facts. Repair advice is explicitly unverified; underlying cause is not claimed as independently established.
- Diagnosis symptoms must occur in captured output, preventing generic parser defaults such as “Test assertion failed” from becoming factual claims about setup errors.
- Python proposals receive syntax and conservative test-preservation checks before approval. Whitespace-only proposals, removed assertions/test functions/fixtures, and removal of application imports present in context are rejected.
- Coding context includes directly imported workspace Python modules within existing file/context budgets. Installed-library traceback frames remain evidence, not mutation targets.
- Structured regeneration remains limited to two attempts. Retry feedback now includes the bounded invalid response and specific validation errors. The final failure retains its validation reason.
- Coding instructions are shorter while retaining security, real-application testing and approval requirements. Original failure artifacts and recovery limits remain intact.

## Real acceptance evidence

Harness: `data/run_engineering_loop_acceptance.py`. Isolated database/workspaces: `tmp/engineering-loop-acceptance/`. Log: `data/engineering-loop-real.log`. This uses the real model, graph, services, approval manager, patch applier and pytest subprocesses. Approvals are inspected and resolved through the service harness, not browser clicks. It tests a generated FastAPI project; it is not a new browser or HTTP-control-plane acceptance claim.

1. **Create a simple API endpoint in main.py and add a test for it.** Task `7a6fcae6-254f-4a98-b12f-159ea875a356`: **FAILED**. The endpoint patch was reviewed, approved and applied. The test proposal failed validation twice (proposal validation, then schema value validation); no test patch was applied. Saved state/events: `result-1.json`.
2. **Run the tests, find the bugs, and explain why they are failing.** Task `c60caf5c-d57a-4638-9640-186ee5db0ae4`: **COMPLETED as a diagnostic request**, with actual tests still failing: exit 1, one setup error, `AttributeError: 'FastAPI' object has no attribute 'test_client'` at `tests/test_main.py:5`. The observed traceback was retained. The model's unverified advice incorrectly proposed importing `TestClient` from `httpx`; it is not a verified repair. Saved state/events: `result-2.json`.
3. **Fix the issues.** Task `841293ba-d5f3-4596-86c7-bed942af9a61`: **CANCELLED during repair generation when the user requested finalization**. Real tests and diagnosis ran; no repair approval, successful retest or final review was reached. The isolated runner was stopped, cancellation used `TaskRuntime.cancel_task`, and the checkpoint/events were saved in `result-3.json`. This interruption is neither an exhausted model attempt nor a successful repair.

The live process started before the final compact-prompt, retry-feedback, imported-source and symptom-filter changes were loaded. Those final changes are covered by regression tests, but have not had a fresh complete live acceptance run. The earlier failures are preserved rather than replaced with a success claim.

## Verification

Focused command: `python -m pytest backend/tests/unit/test_engineering_blockers.py backend/tests/unit/test_repair_evidence.py backend/tests/unit/test_model_reliability.py backend/tests/unit/test_phase12_real_workflows.py backend/tests/integration/test_takeover_execution.py -q` — **76 passed, 3 warnings in 104.75s**. Log: `data/engineering-loop-focused-final.log`.

The first full run found one obsolete positive-confidence assertion (629 passed, 1 failed, 1 skipped). The test now requires evidence and explicitly unverified advice.

Final full command: `python -m pytest backend/tests -q` — **630 passed, 1 skipped, 4 warnings in 298.52s**. Log: `data/engineering-loop-full-final.log`. Warnings: three pytest class-collection warnings and one cache-directory permission warning. Regression tests use isolated settings/databases and controlled model fixtures; live acceptance above uses real Ollama.

No AssemblyAI credits were used. Voice/Live/frontend implementation and root `.env` were not modified in this phase. Production deployment, physical voice and frontend checks were outside scope.

## Limitations

The local 3B model still produces invalid proposals and incorrect repair advice. Captured observations are reliable evidence, not proof of an underlying cause. Conservative AST checks do not prove correctness and may reject legitimate test refactors. Real tests and review remain necessary. No final end-to-end PASS is established by this run.

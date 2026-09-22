# Engineering workflow blocker fixes

## Coding target root cause
The original failure is local to one GeneratedFiles proposal. CodingAgent creates a fresh `seen` set on each formulation, so applied patches, earlier subtasks, and replans do not share duplicate-target state. GeneratedFile already guarantees string content and the earlier loop rejects sensitive targets; the combined exception therefore identifies duplicate resolved paths within that proposal. Raw invalid responses were not persisted, so their exact path strings cannot be reconstructed.

Duplicate normalized paths are now rejected inside structured schema validation, allowing the existing bounded complete-response repair. Exhausted malformed output is MODEL_OUTPUT_ERROR. Resolved-path checks remain in CodingAgent to reject aliases that resolve to the same file, sensitive targets, traversal, escapes, stale originals, and unsafe proposals. No partial proposal is applied. Sequential subtasks reread current contents and bind new patches to current hashes. The coding prompt now respects completed dependency work instead of telling every subtask to reimplement the entire request.

## Diagnosis termination root cause
TaskDecomposer's prefix shortcut treated any instruction starting with Run the tests as test-only, discarding the explicit request to find and explain bugs. The execution node also treated every failed test result as fatal unless a coding patch had already been applied.

Planning now distinguishes test-only, diagnosis, and fix intent. Valid failed tests remain FAILED test results, but can be expected evidence for a successful test-reporting or diagnosis operation. Fix workflows run tests, diagnose captured evidence, propose changes, require approval, retest, and review. Infrastructure errors remain fatal. Recovery remains bounded; required failed verification cannot become a successful task through an unrelated passing test.

## Evidence and safety
Diagnosis consumes the original run's command, exit code, stdout/stderr, parsed issues, and traceback rather than silently rerunning. Failure history remains in state and immutable artifacts through repair attempts. Coding receives diagnosed implementation files as context, subject to unchanged security checks. Library frames in tracebacks remain evidence but are not promoted to workspace mutation targets. Existing StructuredTestReport is preserved and now includes the executed command. Final summaries include observed test outcomes and generated diagnosis/recommendation.

MODEL_OUTPUT_ERROR identifies exhausted invalid structured output; TARGET_VALIDATION_ERROR identifies rejected targets; TEST_FAILURE identifies a valid execution with failing tests; WORKFLOW_ERROR identifies execution/infrastructure failures. A failed test batch is distinguished from a crashed parallel workflow.

## Verification
- Initial execution/model suite: 36 passed.
- Relevant workflow/security/regression suite: 67 passed.
- Full backend suite on final code: 622 passed, 1 skipped; four collection/cache warnings.
- Final targeted workflow tests: 32 passed.
- Additional traceback-target handoff regression and graph test: 21 passed.
- Final normalized-path/model/execution checks: 57 passed.
- Frontend unchanged in this phase; frontend tests/build not rerun.
- AssemblyAI calls: 0.

## Real acceptance
Real selected local model: llama3.2:latest (Llama 3.2 3B). Real Supervisor, decomposer, coding, validator, approval manager, applier, test service, and reviewer are used through MultiAgentService with an isolated SQLite database. No mocks and no manual edits to generated files. Evidence is in tmp/engineering-blocker-acceptance/result-*.json and data/blockers-real-acceptance.log.

### Acceptance 1: create API
- Task: ffed44b7-2d8d-4164-a455-dd03175f0812.
- Real first patch modified main.py; the dependent patch created tests/test_main.py. Both were inspected, approved, and applied. The former duplicate-target blocker did not recur.
- The generated test had a missing closing parenthesis. Real pytest collection failed, and diagnosis ran.
- Recovery then rejected a library traceback path promoted to a coding target. Final state: FAILED. The subsequent workspace-source filtering fix passed focused regression tests and the full suite; this API acceptance was not rerun after that fix.
- Review was not reached. This is not a successful end-to-end API acceptance.

### Acceptance 2: find and explain bugs
- Task: 1639932b-08ca-4e5d-8b67-d233403586e4.
- Used an isolated copy of the genuine failing project generated in the previous phase; no manual repair.
- Real pytest: exit 1, 0 passed, 1 failed. Original evidence retained: tests/test_main.py:5, AttributeError: FastAPI object has no attribute test_client.
- Diagnosis executed using that original run and returned a cause and suggested TestClient change. Final task state: COMPLETED as a diagnostic operation, while the test result remained failed.
- Quality limitation: the local model added unsupported API/version-history claims. Therefore the fully grounded diagnosis requirement is not counted as a complete pass.

### Acceptance 3: fix issues
- Task: 04d48a01-7d39-446a-b98b-04df86e16d07.
- Fresh tests and diagnosis ran in the same failing project. A real fix patch was inspected, approved, and applied. Retest failed with fixture 'client' not found.
- The first recovery patch was approved and applied; another real retest still failed. Both original and subsequent failures remain in events, artifacts, and state.
- The second recovery proposal only changed the trailing newline. It did not repair the fixture and was rejected through the real approval manager and graph resumption.
- Final state: CANCELLED following that rejection. Review was not reached. No task or test was manually marked successful.

Approvals used the real ApprovalManager, hash-bound graph resumption, and PatchApplier through a service-level acceptance harness; these were not browser-click acceptance tests.

## Remaining blockers and final verdict
The backend regressions are fixed and the final full suite passes. The real local model still generates incorrect repairs and unsupported diagnostic claims. Successful API acceptance after the traceback-target fix remains unverified. The repair workflow did not reach passing tests and review.

REAL AUTONOMOUS ENGINEERING LOOP WORKING END-TO-END: NO.

Local services were restored and verified: frontend http://localhost:3001 and backend health on port 8000 both returned HTTP 200. Frontend and Voice/Live were not changed; real AssemblyAI calls remain 0.

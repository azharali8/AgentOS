# Session implementation report acceptance

## Design

`GET /api/v1/tasks/{task_id}/implementation-report` projects a terminal task's
durable task, event, approval, execution, and immutable artifact records into a
versioned report. It does not invoke an LLM, start an execution, mutate a task,
or create a duplicate summary row. The report is rebuilt for the selected task
after reopening it, so historical task reports remain independent.

Only `PATCH_APPLIED` events with `applied: true` contribute changed files. Line
counts and diff links appear only when that event names a matching persisted
patch artifact; legacy events intentionally show no counts. Each `TEST_REPORT`
is retained as a separate test run. A test is passed only when its recorded
success flag, zero exit code, and failure count agree. Commands are drawn from
recorded test reports; tool executions remain visible separately because the
execution table does not contain a reliable shell-command field.

Artifact controls fetch the existing authenticated artifact endpoint and render
the exact stored artifact content, preserving server-side task ownership and
artifact-integrity verification. The viewer omits reviewer reasoning fields.

## Browser acceptance

An isolated Project-B-UI task `72f6cec6-8bd1-4e0c-bd3d-9d5aa01f3b9f` requested
`subtract(a, b)` plus its test. The user-facing workflow produced patch
`165bfec0-885f-4c14-aa32-e58d2243e39b`, received recorded approval
`appr-72f`, ran test artifact `3e75191f-1349-4a74-ae43-97e475261166` with
`2 passed, 0 failed, exit 0`, and completed review artifact
`56f2db27-be02-4cfa-9d76-4ce749266f13`.

The report showed two applied files with exact patch statistics:

- `calculator.py` `+3 -0`
- `test_calculator.py` `+4 -1`

The browser acceptance also opened the persisted Context artifact, refreshed
the page, switched to Project A, and returned to Project-B-UI. The original
report restored under the same task ID without leaking into Project A. Existing
failed task `dcca2f61-7ad5-471a-97e1-322545698260` rendered as `FAILED` with its
recorded exit code `3221225786`, no applied files, and its remaining failure
evidence.

## Limitations

The report intentionally does not infer semantic file descriptions or commands
from an LLM or tool-name text. Older patch-applied events that predate a patch
reference remain visible, but their precise line counts and diff references are
unknown. The existing app retains its documented single-process workspace
constraint; this feature does not turn it into a public multi-tenant service.

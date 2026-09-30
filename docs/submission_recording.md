# Post-review submission recording

This command records evidence supplied after human review. It does not open a
browser, click Submit, inspect a page, or infer success from the application
workflow.

The same recording boundary is available from the local dashboard through
**Record result**. The dashboard adds a short-lived, one-use authorization and
stale-state check before delegating to this service; it does not add any
browser or submission capability.

## Confirmed submission

Use this only after you manually submitted the exact application and observed
independent success evidence:

```powershell
python -m scripts.record_submission `
    --job-id 123 `
    --submitted `
    --confirmed `
    --evidence "Portal displayed confirmation number 456"
```

The command requires nonblank evidence before it can record `APPLIED`. The
evidence is stored in the job notes for traceability. The applied date and
selected resume are preserved in SQLite, then the Excel tracker is regenerated
for the dashboard.

## Submission attempted but not confirmed

If the form was submitted but no independent success confirmation was visible:

```powershell
python -m scripts.record_submission `
    --job-id 123 `
    --submitted `
    --evidence "Submit was clicked, but no confirmation page appeared"
```

This records `SUBMISSION_UNCONFIRMED`. It never records `APPLIED` from ambiguous
evidence.

## No submission occurred

Running the command without `--submitted` records a `NOT_SUBMITTED` result and
does not advance the application lifecycle:

```powershell
python -m scripts.record_submission --job-id 123
```

## Lifecycle restrictions

Confirmation can begin only from `READY_TO_APPLY`, `FORM_STARTED`,
`NEEDS_REVIEW`, or `SUBMISSION_UNCONFIRMED`. Other states are blocked. The
service reloads the exact persisted job ID and verifies its identity before any
transition.

If Excel regeneration fails after a database transition, the command reports
the tracker error separately. The recorded SQLite result remains authoritative,
so a confirmed transition is never incorrectly reported as unrecorded.

## PyCharm configuration

Create a Python run configuration with:

- **Module name:** `scripts.record_submission`
- **Parameters:** the exact job ID and applicable evidence flags
- **Working directory:** the repository root
- **Python interpreter:** the project `.venv`

## Exit codes

- `0`: confirmed, unconfirmed, or explicitly not-submitted result processed
- `1`: blocked evidence/lifecycle or recording failure
- `2`: invalid arguments, local setup failure, or tracker refresh failure

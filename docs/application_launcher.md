# Controlled single-job launcher

The single-job launcher connects one exact persisted job to the existing
application workflow. It is deliberately separate from discovery and never
runs automatically after a discovery command.

## 1. List eligible job IDs

```powershell
python -m scripts.run_application --list-eligible
```

Only jobs with all three of these persisted values are listed:

- status `NEEDS_APPLICATION`
- company rule `AUTO`
- application method `AUTO`

Listing jobs does not inspect a page, start a browser session, change the
database, regenerate the tracker, or authorize submission.

## 2. Preview an exact job

```powershell
python -m scripts.run_application --job-id 123
```

Without `--allow-external`, the command returns the selected company, role,
location, URL, fit score, resume filename, and an `AUTHORIZATION_REQUIRED`
status. The workflow is not called and no browser session is created.

## 3. Authorize the controlled workflow

```powershell
python -m scripts.run_application --job-id 123 --allow-external
```

This flag explicitly authorizes browser inspection and field mutation for the
selected run. It does not authorize submission. The existing safety sequence
still applies:

```text
exact persisted identity
→ application readiness validation
→ separate read-only inspection browser
→ deterministic verified-answer plan
→ whole-form authorization
→ exact external-target authorization
→ separate execution browser
→ authorized field filling and resume upload
→ stop for human review
```

Successful field filling is stored as `FORM_STARTED`. The Excel tracker is then
regenerated so the dashboard reflects the new state. Human review and manual
submission remain required. Only the independent submission-confirmation
service may later record `APPLIED` from supplied evidence.

Greenhouse is currently the only production-composed ATS adapter. A persisted
LinkedIn URL or another unsupported ATS cannot fall back to Greenhouse; it is
moved to `NEEDS_REVIEW` by the inspection service.

## PyCharm configuration

Create a Python run configuration with:

- **Module name:** `scripts.run_application`
- **Parameters:** `--job-id 123`
- **Working directory:** the repository root
- **Python interpreter:** the project `.venv`

Run the preview first. Add `--allow-external` only after verifying the exact job
shown in the preview.

## Exit codes

- `0`: authorized fields were filled and the job is ready for human review
- `1`: preview only, missing/ineligible job, review requirement, block, or
  controlled workflow failure
- `2`: invalid command arguments or local configuration failure

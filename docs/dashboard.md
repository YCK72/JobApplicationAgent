# Application dashboard

The dashboard is a local view of the exported Excel application tracker. It
shows pipeline totals, status distribution, job links, and a searchable
application table. The Review queue metric and filter isolate actionable jobs,
and each queued row explains the required human action. Reasons distinguish
missing or invalid targets, Workday multi-step applications, manual-company
routing, filled forms awaiting review, unconfirmed submissions, and processing
errors. For unresolved LinkedIn records, the dashboard also provides a guarded
form for assigning an explicitly reviewed Greenhouse, Lever, Ashby, or Workday
application URL. The page checks the workbook every five seconds, so a newly
generated export appears without restarting the server.

Each persisted row also has a **Preview** action. Preview is read-only: it
loads the exact source URL, validated ATS application target, selected resume,
fit score, and current eligibility without starting a browser or running the
application workflow.

SQLite remains the authoritative application state, and the Excel workbook
remains the human-facing tracker. A successful target review updates the same
SQLite row, reruns the deterministic job pipeline, and regenerates Excel.

## Start from PowerShell

Activate the project virtual environment and run:

```powershell
python -m app.dashboard.server --open-browser
```

The default address is `http://127.0.0.1:8765`. Press `Ctrl+C` in the terminal
to stop the dashboard.

If the tracker is stored somewhere else, provide its path:

```powershell
python -m app.dashboard.server `
    --database "C:\path\to\jobs.db" `
    --workbook "C:\path\to\Job_Application_Tracker.xlsx" `
    --open-browser
```

## Start from PyCharm

Create a Python run configuration with:

- **Module name:** `app.dashboard.server`
- **Parameters:** `--open-browser`
- **Working directory:** the repository root
- **Python interpreter:** the project's `.venv`

Run that configuration whenever you want the dashboard available.

## Refresh behavior

The server reads the workbook only when its modified time or size changes. If
Excel briefly locks or replaces the file during an export, the page keeps the
last successful snapshot visible and shows a warning. It switches back to the
new workbook data after a later refresh succeeds.

## Review queue

Select **Needs action** in the Review filter to show only jobs that require
human attention. The Review column describes the boundary that stopped
automation. Source and Apply links remain separate so the original listing and
validated ATS target can be checked independently. Completed, rejected,
withdrawn, offered, and filtered-out jobs are excluded from this queue.

Use **Record decision** to save a `RESOLVED`, `DEFERRED`, or `DISMISSED`
decision with a required note. Decisions are appended to SQLite with the job,
review kind, and timestamp. `DEFERRED` keeps the item in the active queue;
`RESOLVED` and `DISMISSED` close that specific review kind. If the job later
develops a different review reason, it returns to the queue automatically.

Review decisions are dashboard audit data only. They do not change the job's
application status, authorize browser execution, submit an application, or
record `APPLIED`. The workbook refreshes after a decision so the dashboard can
reload its current job data, while SQLite retains the review history.

Select **History** on a job row to open its chronological audit panel. The
panel is read-only and can filter decisions by outcome and review kind. Its API
is `GET /api/jobs/{job_id}/review-history`; reading history never invokes the
application workflow or changes database state.

Every tracker refresh also exports the complete append-only audit log to the
`Review History` worksheet. The sheet includes decision ID, job ID, company,
title, review kind, outcome, note, and recorded timestamp, with Excel filters
enabled for offline review.

## Controlled application launch

An eligible preview displays an explicit external-browser authorization
checkbox. Checking it and selecting **Authorize and open application** sends a
separate JSON POST for that exact job. Previewing alone never starts the
workflow.

The preview authorization is held only in server memory, expires after two
minutes, and can be used once. It is bound to the job ID, source URL,
application URL, ATS provider, resume, routing, and application status. The
server reruns preflight immediately before launch. A changed job, an expired or
reused token, the wrong job ID, or a missing confirmation stops before the
launcher and browser.

The controlled run preserves the existing safety order: preparation,
inspection, deterministic form authorization, and exact external-target
authorization must all succeed before the execution browser is created. The
workflow fills only authorized fields and records `FORM_STARTED` only after a
successful run. The dashboard then retains that filled execution browser for
human review. It cannot click Submit, confirm submission, or record `APPLIED`;
those remain independent manual and post-review actions.

Only one active or pending review browser is allowed for a job. Its browser
lifecycle and Playwright operations stay on one dedicated owner thread. The
default review lease is fifteen minutes and can be changed with
`--review-session-minutes`. Select **Close review session** after finishing the
manual review. The same cleanup occurs automatically when the lease expires or
the dashboard server stops. Closing a review session does not change the
application status or claim that the application was submitted.

The endpoints are:

- `GET /api/jobs/{job_id}/application-preview` for browser-free preflight and
  a fresh authorization token when eligible.
- `POST /api/jobs/{job_id}/application-launch` for one explicitly confirmed
  controlled run.
- `POST /api/jobs/{job_id}/review-session/close` with exact close confirmation
  to release the retained browser without changing application status.

## Post-review outcome recording

After manually reviewing the filled form, complete any submission yourself and
close the retained browser session. Select **Record result** for the exact job.
The panel defaults to **Not submitted** and offers three explicit outcomes:

- **Not submitted** leaves the application lifecycle unchanged.
- **Submitted — success not confirmed** records `SUBMISSION_UNCONFIRMED`.
- **Submitted — success independently confirmed** requires nonblank evidence
  before recording `APPLIED`.

Opening the panel is read-only and issues a five-minute, one-use authorization
bound to the job's saved URL, status, resume, notes, and applied date. The
server reloads the exact job immediately before recording. Changed, expired,
reused, wrong-job, or outcome-mismatched authorizations fail closed. An active
review browser also blocks recording so browser control and lifecycle evidence
remain separate operations.

The post-review endpoints are:

- `GET /api/jobs/{job_id}/submission-review` for a read-only saved-state review
  and fresh recording authorization.
- `POST /api/jobs/{job_id}/submission-recording` for one explicitly confirmed
  observed outcome.

This service has no browser, form-filling, click, or submission capability.
SQLite is updated first and the Excel tracker is regenerated afterward.

The editable server must bind to `127.0.0.1`, `::1`, or `localhost`. Target
assignment accepts JSON only and validates the pasted URL through the same
HTTPS-only application-target resolver used by the application workflow.
Greenhouse, Lever, Ashby, and Workday are the enabled ATS providers. The
dashboard never guesses a URL, follows a redirect, or submits an application.
It opens and fills an execution browser only after the explicit, fresh,
exact-job authorization described above.

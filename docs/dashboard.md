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

The editable server must bind to `127.0.0.1`, `::1`, or `localhost`. Target
assignment accepts JSON only and validates the pasted URL through the same
HTTPS-only application-target resolver used by the application workflow.
Greenhouse, Lever, Ashby, and Workday are the enabled ATS providers. The dashboard never
guesses a URL, follows a redirect, opens an execution browser, fills a form, or
submits an application.

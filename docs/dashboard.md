# Application dashboard

The dashboard is a local view of the exported Excel application tracker. It
shows pipeline totals, status distribution, job links, and a searchable
application table. For unresolved LinkedIn records, it also provides a guarded
form for assigning an explicitly reviewed Greenhouse application URL. The page
checks the workbook every five seconds, so a newly generated export appears
without restarting the server.

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

The editable server must bind to `127.0.0.1`, `::1`, or `localhost`. Target
assignment accepts JSON only and validates the pasted URL through the same
HTTPS-only application-target resolver used by the application workflow.
Greenhouse is the only enabled ATS. The dashboard never guesses a URL, follows
a redirect, opens an execution browser, fills a form, or submits an application.

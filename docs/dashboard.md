# Application dashboard

The dashboard is a local, read-only view of the exported Excel application
tracker. It shows pipeline totals, status distribution, job links, and a
searchable application table. The page checks the workbook every five seconds,
so a newly generated export appears without restarting the server.

SQLite remains the authoritative application state, and the Excel workbook
remains the human-facing tracker. The dashboard does not write to either one.

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

The server binds to the local machine by default. Browser links are limited to
HTTP and HTTPS URLs from the tracker, and all server routes are read-only.

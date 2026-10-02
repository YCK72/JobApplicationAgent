@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Setup is incomplete. Run scripts\setup.ps1 first.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" -m agent.cli serve
echo.
echo The application has stopped. Any error is shown above.
pause

param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.venv/Scripts/python.exe' -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
New-Item -ItemType Directory -Force -Path 'data','secrets' | Out-Null
if (-not (Test-Path -LiteralPath 'data/profile.json')) {
    Copy-Item -LiteralPath 'profile.example.json' -Destination 'data/profile.json'
}
Write-Output 'Setup complete. See docs/SETUP.md for Gmail and OpenAI connections.'

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
Set-Location -LiteralPath $projectRoot
& $pythonPath -m agent.cli serve

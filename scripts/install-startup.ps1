$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.ps1 first.' }
$accountName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$existing = Get-ScheduledTask -TaskName 'JobApplicationAgent' -ErrorAction SilentlyContinue
if ($existing) { throw 'A task named JobApplicationAgent already exists. Inspect it before changing startup settings.' }
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument '-m agent.cli serve' -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $accountName
$principal = New-ScheduledTaskPrincipal -UserId $accountName -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'JobApplicationAgent' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Local job applications and daily reports; controlled by dashboard autopilot switch.' | Out-Null
Write-Output 'Startup task installed. Autopilot remains controlled by the dashboard.'

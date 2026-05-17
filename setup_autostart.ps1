# Campus network auto-login startup task installer.
# Run this script from an elevated PowerShell session.

$ErrorActionPreference = "Stop"

$taskName = "AutoLogin_CampusNetwork"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $scriptDir "run_monitor.bat"
$monitorPath = Join-Path $scriptDir "monitor.py"
$taskLogPath = Join-Path $scriptDir "startup_task.log"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    Write-Host "[ERROR] Please run this script as Administrator." -ForegroundColor Red
    Write-Host "Open PowerShell as Administrator, then run:" -ForegroundColor Yellow
    Write-Host "  cd `"$scriptDir`""
    Write-Host "  .\setup_autostart.ps1"
    exit 1
}

if (-not (Test-Path $monitorPath)) {
    Write-Host "[ERROR] monitor.py was not found: $monitorPath" -ForegroundColor Red
    exit 1
}

$preferredPython = "C:\Program Files\Python310\python.exe"
if (Test-Path $preferredPython) {
    $pythonPath = $preferredPython
} else {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " Campus auto-login startup setup" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Script dir: $scriptDir"
Write-Host "Batch file: $batPath"
Write-Host "Python:     $pythonPath"
Write-Host "Task log:   $taskLogPath"
Write-Host ""

$batContent = @(
    "@echo off",
    "chcp 65001 >nul",
    "cd /d `"$scriptDir`"",
    "`"$pythonPath`" `"$monitorPath`" >> `"$taskLogPath`" 2>>&1"
)
Set-Content -Path $batPath -Value $batContent -Encoding ASCII
Write-Host "Updated run_monitor.bat with absolute paths." -ForegroundColor Green

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Existing task found. Removing it first..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batPath`"" `
    -WorkingDirectory $scriptDir

$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = "PT30S"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Write-Host "Registering scheduled task as SYSTEM..." -ForegroundColor Green

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User "SYSTEM" `
    -RunLevel Highest `
    -Description "Campus network auto-login monitor" `
    -Force | Out-Null

$taskInfo = Get-ScheduledTask -TaskName $taskName

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host " Setup completed." -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host "Task name:  $taskName"
Write-Host "State:      $($taskInfo.State)"
Write-Host "Trigger:    At startup, delayed 30 seconds"
Write-Host "Run as:     SYSTEM"
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  schtasks /Run /TN $taskName"
Write-Host "  schtasks /Query /TN $taskName /V /FO LIST"
Write-Host "  .\remove_autostart.ps1"
Write-Host ""
Write-Host "Logs:"
Write-Host "  $taskLogPath"
Write-Host "  $(Join-Path $scriptDir "monitor.log")"

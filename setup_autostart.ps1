# 校园网自动登录 - 开机自启配置脚本（SYSTEM 账户）
# 以管理员身份运行此脚本

$ErrorActionPreference = "Stop"

$taskName = "AutoLogin_CampusNetwork"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $scriptDir "run_monitor.bat"
$pythonPath = (Get-Command python -ErrorAction Stop).Source

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " 校园网自动登录 - 开机自启配置" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "脚本目录: $scriptDir"
Write-Host "批处理:   $batPath"
Write-Host "Python:   $pythonPath"
Write-Host ""

# 检查文件
if (-not (Test-Path $batPath)) {
    Write-Host "[错误] 找不到 run_monitor.bat" -ForegroundColor Red
    exit 1
}

# 更新批处理文件，使用完整 Python 路径（SYSTEM 环境下 PATH 不同）
$batContent = @"
@echo off
chcp 65001 >nul
cd /d "$scriptDir"
"$pythonPath" monitor.py
"@
Set-Content -Path $batPath -Value $batContent -Encoding ASCII
Write-Host "已更新 run_monitor.bat（使用完整 Python 路径）" -ForegroundColor Green

# 删除已有任务
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "发现已存在的计划任务，正在删除..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 创建操作
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batPath`"" `
    -WorkingDirectory $scriptDir

# 开机后延迟 30 秒执行
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = "PT30S"

# 设置
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# 注册计划任务（SYSTEM 账户，无需密码，开机即运行）
Write-Host "正在注册计划任务（SYSTEM 账户）..." -ForegroundColor Green
Write-Host ""

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User "SYSTEM" `
    -RunLevel Highest `
    -Description "校园网自动登录 - 监控断线自动重连（SYSTEM账户）" `
    -Force

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host " 配置完成！" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Write-Host "任务名称: $taskName"
Write-Host "触发条件: 开机后 30 秒自动执行"
Write-Host "运行身份: SYSTEM（无需密码，开机即运行）"
Write-Host ""
Write-Host "管理方式:" -ForegroundColor Yellow
Write-Host "  查看任务:  Win+R -> taskschd.msc -> 任务计划程序库"
Write-Host "  手动触发:  右键任务 -> 运行"
Write-Host "  停止监控:  右键任务 -> 结束"
Write-Host "  删除任务:  运行 remove_autostart.ps1"
Write-Host "  查看日志:  打开 monitor.log"
Write-Host ""
Write-Host "说明: SYSTEM 账户在开机时即启动，" -ForegroundColor Yellow
Write-Host "      无论是否登录、是否锁屏都会运行。" -ForegroundColor Yellow

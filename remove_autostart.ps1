# 移除校园网自动登录的开机自启任务
$taskName = "AutoLogin_CampusNetwork"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "已移除计划任务: $taskName" -ForegroundColor Green
} else {
    Write-Host "未找到计划任务: $taskName" -ForegroundColor Yellow
}

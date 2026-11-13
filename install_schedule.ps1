# 建立／更新 Windows 排程：週一至週五 21:00 跑題材地圖每日產線（興櫃總經戰情室約 20:30 更新完），23:00 補跑一次
# - 透過 run_daily_hidden.vbs 在隱藏主控台執行：不開終端機視窗，關掉 Windows Terminal 不會中斷產線
# - --skip-if-done：當天已成功發布就不再跑，所以 23:00 只在 21:00 失敗或被中斷時才真的補跑
# - 錯過時間（關機、睡眠）開機後補跑；插電與否都跑；單次最多 4 小時；同時只跑一個
# 以目前使用者身分、登入時執行（不存密碼）；重複執行會覆蓋同名排程
$ErrorActionPreference = "Stop"
$taskName = "ThemeAtlas Weekday 2100 Update"
$vbs = Join-Path $PSScriptRoot "run_daily_hidden.vbs"
if (-not (Test-Path -LiteralPath $vbs)) { throw "Launcher not found: $vbs" }
$action = New-ScheduledTaskAction -Execute "$env:WINDIR\System32\wscript.exe" -Argument ('"' + $vbs + '" --skip-if-done') -WorkingDirectory $PSScriptRoot
$days = "Monday","Tuesday","Wednesday","Thursday","Friday"
$triggers = @(
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "21:00"),
  (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At "23:00")
)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Hours 4) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null
$t = Get-ScheduledTask -TaskName $taskName
"$($t.TaskName): $($t.Actions[0].Execute) $($t.Actions[0].Arguments)"
$t.Triggers | ForEach-Object { "  trigger: " + ([datetime]$_.StartBoundary).ToString("HH:mm") + " " + ($_.DaysOfWeek) }
"  next run: " + (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime

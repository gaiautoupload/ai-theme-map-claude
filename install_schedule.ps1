# 建立 Windows 排程：週一至週五 21:00 跑題材地圖每日產線（興櫃總經戰情室約 20:30 更新完）
# 以目前使用者身分、登入時執行（不存密碼）；重複執行會覆蓋同名排程
$ErrorActionPreference = "Stop"
$taskName = "ThemeAtlas Weekday 2100 Update"
$batchPath = Join-Path $PSScriptRoot "run_daily.bat"
if (-not (Test-Path -LiteralPath $batchPath)) { throw "Batch file not found: $batchPath" }
& "$env:WINDIR\System32\schtasks.exe" /Create /TN $taskName /TR ('"' + $batchPath + '"') /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 21:00 /F
if ($LASTEXITCODE -ne 0) { throw "Failed to create scheduled task: $taskName" }
& "$env:WINDIR\System32\schtasks.exe" /Query /TN $taskName /FO LIST

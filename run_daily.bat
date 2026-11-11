@echo off
rem 題材地圖每日產線（排程用）：記錄寫到 data\logs\daily_latest.log，並累積到 daily_all.log
setlocal
set "PYTHONIOENCODING=utf-8"
pushd "%~dp0"
if not exist "data\logs" mkdir "data\logs"
set "PY=%USERPROFILE%\anaconda3\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -X utf8 -u run_daily.py %* > "data\logs\daily_latest.log" 2>&1
set "RC=%ERRORLEVEL%"
type "data\logs\daily_latest.log" >> "data\logs\daily_all.log"
popd
exit /b %RC%

@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PY_SCRIPT=%SCRIPT_DIR%cleanup_logs_reports.py"

REM Cleanup utility for itrading logs and report artifacts
REM Removes:
REM   1) All *.log files under itrading/logs (recursive)
REM   2) All files under itrading/reports/*/ subfolders (recursive)
REM   3) All *_bars_8888.txt files under itrading/reports (recursive)

if not exist "%PY_SCRIPT%" (
  echo [ERROR] Missing script: "%PY_SCRIPT%"
  exit /b 1
)

python "%PY_SCRIPT%" %*
if %errorlevel%==9009 (
  rem Fallback if python is not on PATH
  py -3 "%PY_SCRIPT%" %*
)

exit /b %errorlevel%


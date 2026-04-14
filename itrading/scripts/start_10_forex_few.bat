@echo off
setlocal

REM Launch all 10 supported FX instruments, one terminal per instrument.
set "RUNNER=C:\PyCharmProjects\Live_Trading_Bot\itrading\scripts\run_bot_forex.bat"

if not exist "%RUNNER%" (
    echo [ERROR] Missing runner script: %RUNNER%
    exit /b 1
)

if /I "%START_10_FOREX_DRY_RUN%"=="1" (
    echo [DRY RUN] Would launch: GBPUSD AUDUSD EURUSD USDCHF USDJPY EURJPY USDCAD NZDUSD GBPJPY EURGBP
    exit /b 0
)

where wt >nul 2>&1
if errorlevel 1 (
    echo [WARN] Windows Terminal ^(wt.exe^) not found. Falling back to separate cmd windows.
    start "GBPUSD" cmd /k "\"%RUNNER%\" GBPUSD"
    start "AUDUSD" cmd /k "\"%RUNNER%\" AUDUSD"
    start "EURUSD" cmd /k "\"%RUNNER%\" EURUSD"
    start "NZDUSD" cmd /k "\"%RUNNER%\" NZDUSD"
    exit /b 0
)

wt -w 0 ^
  new-tab --title "GBPUSD" cmd /k "\"%RUNNER%\" GBPUSD" ; ^
  new-tab --title "AUDUSD" cmd /k "\"%RUNNER%\" AUDUSD" ; ^
  new-tab --title "EURUSD" cmd /k "\"%RUNNER%\" EURUSD" ; ^
  new-tab --title "NZDUSD" cmd /k "\"%RUNNER%\" NZDUSD"
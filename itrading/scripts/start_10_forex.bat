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
    timeout /t 2 /nobreak
    start "AUDUSD" cmd /k "\"%RUNNER%\" AUDUSD"
    timeout /t 2 /nobreak
    start "EURUSD" cmd /k "\"%RUNNER%\" EURUSD"
    timeout /t 2 /nobreak
    start "USDCHF" cmd /k "\"%RUNNER%\" USDCHF"
    timeout /t 2 /nobreak
    start "USDJPY" cmd /k "\"%RUNNER%\" USDJPY"
    timeout /t 2 /nobreak
    start "EURJPY" cmd /k "\"%RUNNER%\" EURJPY"
    timeout /t 2 /nobreak
    start "USDCAD" cmd /k "\"%RUNNER%\" USDCAD"
    timeout /t 2 /nobreak
    start "NZDUSD" cmd /k "\"%RUNNER%\" NZDUSD"
    timeout /t 2 /nobreak
    start "GBPJPY" cmd /k "\"%RUNNER%\" GBPJPY"
    timeout /t 2 /nobreak
    start "EURGBP" cmd /k "\"%RUNNER%\" EURGBP"
    exit /b 0
)

wt -w 0 ^
  new-tab --title "GBPUSD" cmd /k "\"%RUNNER%\" GBPUSD" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "AUDUSD" cmd /k "\"%RUNNER%\" AUDUSD" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "EURUSD" cmd /k "\"%RUNNER%\" EURUSD" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "USDCHF" cmd /k "\"%RUNNER%\" USDCHF" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "USDJPY" cmd /k "\"%RUNNER%\" USDJPY" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "EURJPY" cmd /k "\"%RUNNER%\" EURJPY" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "USDCAD" cmd /k "\"%RUNNER%\" USDCAD" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "NZDUSD" cmd /k "\"%RUNNER%\" NZDUSD" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "GBPJPY" cmd /k "\"%RUNNER%\" GBPJPY" ; ^
  timeout /t 2 /nobreak ; ^
  new-tab --title "EURGBP" cmd /k "\"%RUNNER%\" EURGBP"

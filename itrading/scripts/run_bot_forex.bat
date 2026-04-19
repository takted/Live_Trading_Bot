@echo off
REM ==============================================================================
REM ITRADING BOT - LAUNCHER SCRIPT
REM ==============================================================================
REM This script runs the bot with error handling and automatic restart
REM ==============================================================================

echo.
echo ========================================================================
echo ITRADING BOT - LAUNCHER is run_bot_forex.bat
echo ========================================================================
echo.

REM Check if executable exists
if not exist "C:\PyCharmProjects\Live_Trading_Bot\itrading\scripts\run_forex_live.py" (
    echo [ERROR] Executable not found!
    echo Please check C:\PyCharmProjects\Live_Trading_Bot\itrading\scripts\run_forex_live.py first to create the executable.
    echo.
    pause
    exit /b 1
)

REM Create logs directory if it doesn't exist
REM if not exist "logs" mkdir logs

REM Set log file with timestamp
REM for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
REM for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a%%b)
REM set logfile=logs\bot_launcher_%mydate%_%mytime%.log

echo [%date% %time%] Starting Bot...    Press Ctrl+C to stop the bot
echo.
echo ========================================================================
echo.

set INSTRUMENT=%~1
if "%INSTRUMENT%"=="" set INSTRUMENT=AUDUSD
set INSTRUMENT=%INSTRUMENT:"=%

if /I "%INSTRUMENT%"=="AUDUSD" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_audusd.json
) else if /I "%INSTRUMENT%"=="EURUSD" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_eurusd.json
) else if /I "%INSTRUMENT%"=="EURGBP" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_eurgbp.json
) else if /I "%INSTRUMENT%"=="GBPUSD" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_gbpusd.json
) else if /I "%INSTRUMENT%"=="GBPJPY" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_gbpjpy.json
) else if /I "%INSTRUMENT%"=="EURJPY" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_eurjpy.json
) else if /I "%INSTRUMENT%"=="USDCHF" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_usdchf.json
) else if /I "%INSTRUMENT%"=="USDJPY" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_usdjpy.json
) else if /I "%INSTRUMENT%"=="USDCAD" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_usdcad.json
) else if /I "%INSTRUMENT%"=="NZDUSD" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_nzdusd.json
) else (
    echo [ERROR] Unsupported instrument: %INSTRUMENT%
    echo Supported instruments: AUDUSD, EURUSD, EURGBP, GBPUSD, GBPJPY, EURJPY, USDCHF, USDJPY, USDCAD, NZDUSD
    pause
    exit /b 1
)

set ITRADING_FOREX_INSTRUMENT=%INSTRUMENT%
set ITRADING_LOG_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\logs\itrading_%INSTRUMENT%.log
set ITRADING_TRADE_LOG_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\logs\itrading_%INSTRUMENT%_trades.log

if "%ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR%"=="" set ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR=false
if "%ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN%"=="" set ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN=false
if "%ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH%"=="" set ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH=false
if "%ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS%"=="" set ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS=48
if "%ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY%"=="" set ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY=false


set ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR=true
set ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN=false
set ITRADING_RESTART_DAY_EXIT_REPAIR_PRICE_MODE=ATR_MARKET
set ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH=false

echo [%date% %time%] Instrument: %INSTRUMENT%
echo [%date% %time%] Params: %ITRADING_PARAMS_FILE%
echo [%date% %time%] Log: %ITRADING_LOG_FILE%
echo [%date% %time%] Startup DAY Exit Repair: %ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR% ^(dry_run=%ITRADING_RESTART_DAY_EXIT_REPAIR_DRY_RUN% mode=%ITRADING_RESTART_DAY_EXIT_REPAIR_PRICE_MODE%^)
echo [%date% %time%] Startup DAY Exit Repair From Cash: %ITRADING_ENABLE_RESTART_DAY_EXIT_REPAIR_FROM_CASH%
echo [%date% %time%] Startup DAY Exit Repair Cash Filters: lookback_hours=%ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_EXPIRED_LOOKBACK_HOURS% require_expired_day=%ITRADING_RESTART_DAY_EXIT_REPAIR_FROM_CASH_REQUIRE_EXPIRED_DAY%

REM Run the bot and log output
:RESTART
echo.
echo ========================================================================
echo.

cd C:\PyCharmProjects\Live_Trading_Bot
C:\PyCharmProjects\Live_Trading_Bot\.venv\Scripts\python.exe C:\PyCharmProjects\Live_Trading_Bot\itrading\scripts\run_forex_live.py


REM Check exit code
if errorlevel 1 (
    echo [%date% %time%] Bot stopped with error code %errorlevel%
    echo.
    echo [WARNING] Bot stopped with error!
    echo Check log file: %logfile%
    echo.
    echo Do you want to restart the bot? (Y/N)
    choice /c YN /n
    if errorlevel 2 goto END
    if errorlevel 1 (
        echo.
        echo Restarting bot in 5 seconds...
        timeout /t 5 /nobreak
        goto RESTART
    )
) else (
    echo [%date% %time%] Bot stopped normally
    echo.
    echo Bot stopped normally.
)

:END
echo.
echo ========================================================================
echo Bot launcher closed
echo ========================================================================
echo.
pause

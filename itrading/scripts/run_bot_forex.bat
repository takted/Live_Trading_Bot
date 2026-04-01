@echo off
REM ==============================================================================
REM ITRADING BOT - LAUNCHER SCRIPT
REM ==============================================================================
REM This script runs the bot with error handling and automatic restart
REM ==============================================================================

echo.
echo ========================================================================
echo ITRADING BOT - LAUNCHER
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

echo Starting ITrading Bot...
REM echo Log file: %logfile%
echo Press Ctrl+C to stop the bot
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
) else if /I "%INSTRUMENT%"=="GBPUSD" (
    set ITRADING_PARAMS_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\config\parameters_live_gbpusd.json
) else (
    echo [ERROR] Unsupported instrument: %INSTRUMENT%
    echo Supported instruments: AUDUSD, EURUSD, GBPUSD
    pause
    exit /b 1
)

set ITRADING_FOREX_INSTRUMENT=%INSTRUMENT%
set ITRADING_LOG_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\logs\itrading_%INSTRUMENT%.log
set ITRADING_TRADE_LOG_FILE=C:\PyCharmProjects\Live_Trading_Bot\itrading\logs\itrading_%INSTRUMENT%_trades.log

echo Instrument: %INSTRUMENT%
echo Params: %ITRADING_PARAMS_FILE%
echo Log: %ITRADING_LOG_FILE%
echo.

REM Run the bot and log output
:RESTART
echo [%date% %time%] Starting bot...
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

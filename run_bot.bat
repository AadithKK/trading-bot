@echo off
REM Trading Bot Scheduler - Windows Task Scheduler Entry Point
REM This file should be run by Windows Task Scheduler daily

setlocal enabledelayedexpansion

REM Set working directory to script location
cd /d "%~dp0"

REM Verify we're in the right directory
if not exist "main.py" (
    echo ERROR: main.py not found in %cd%
    echo This batch file must be in the trading-bot-local directory
    pause
    exit /b 1
)

REM Verify Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.13 and add it to your system PATH
    pause
    exit /b 1
)

REM Create logs directory if it doesn't exist
if not exist "logs" mkdir logs

REM Run the bot
echo.
echo =========================================
echo Trading Bot Starting at %date% %time%
echo =========================================
echo.

python main.py --force

REM Capture exit code
set EXITCODE=%errorlevel%

REM Log completion
if %EXITCODE% equ 0 (
    echo. >> logs\scheduler.log
    echo [%date% %time%] Trading cycle COMPLETED SUCCESSFULLY >> logs\scheduler.log
) else (
    echo. >> logs\scheduler.log
    echo [%date% %time%] Trading cycle FAILED with exit code %EXITCODE% >> logs\scheduler.log
)

echo.
echo =========================================
echo Trading Bot Finished at %date% %time%
echo Exit Code: %EXITCODE%
echo =========================================
echo.

if not "%1"=="batch" (
    echo.
    echo Press any key to close this window...
    pause
)

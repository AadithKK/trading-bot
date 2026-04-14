@echo off
REM Trading Bot Scheduler - Windows Task Scheduler Entry Point
REM This file should be run by Windows Task Scheduler daily

setlocal enabledelayedexpansion

REM Set working directory to script location
cd /d "%~dp0"

REM Activate virtual environment (if using one)
REM call venv\Scripts\activate.bat

REM Run the bot
python main.py

REM Log completion
echo Trading cycle completed at %date% %time% >> logs\scheduler.log

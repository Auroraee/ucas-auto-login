@echo off
chcp 65001 >nul
cd /d "%~dp0"
python monitor.py >> startup_task.log 2>>&1

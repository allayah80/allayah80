@echo off
REM Runs the overnight workflow once. Used by Windows Task Scheduler.
cd /d "%~dp0.."
if not exist output\logs mkdir output\logs
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
%PY% -m studio overnight >> output\logs\overnight.log 2>&1

@echo off
cd /d "%~dp0.."
set PY=python
if exist .venv\Scripts\python.exe set PY=.venv\Scripts\python.exe
start "" http://127.0.0.1:8765
%PY% -m studio dashboard

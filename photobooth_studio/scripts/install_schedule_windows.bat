@echo off
REM Creates a Windows scheduled task that runs every night at 01:30.
REM Remove later with:  schtasks /Delete /TN "PhotoBoothStudioOvernight" /F
set DIR=%~dp0
schtasks /Create /TN "PhotoBoothStudioOvernight" /TR "\"%DIR%run_overnight.bat\"" /SC DAILY /ST 01:30 /F
echo Installed. Your PC must be on (not asleep) at 01:30. Logs: output\logs\overnight.log
pause

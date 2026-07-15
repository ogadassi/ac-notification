@echo off
:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ========================================================
    echo ERROR: You must run this script as Administrator!
    echo Right-click this file and select "Run as administrator".
    echo ========================================================
    pause
    exit /b
)

echo Unregistering Windows Task Scheduler job 'AC_Proximity_Server_Boot'...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName 'AC_Proximity_Server_Boot' -Confirm:$False"

if %errorLevel% eq 0 (
    echo SUCCESS: Task Scheduler job removed successfully.
) else (
    echo ERROR: Failed to remove Task Scheduler job or task did not exist.
)
pause

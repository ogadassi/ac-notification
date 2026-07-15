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

cd /d "%~dp0"
echo Registering Windows Task Scheduler job 'AC_Proximity_Server_Boot' to run at system startup...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$Action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c \"%~dp0start_boot_services.bat\"' -WorkingDirectory '%~dp0'; ^
     $Trigger = New-ScheduledTaskTrigger -AtStartup; ^
     $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; ^
     Register-ScheduledTask -TaskName 'AC_Proximity_Server_Boot' -Action $Action -Trigger $Trigger -Settings $Settings -User 'NT AUTHORITY\SYSTEM' -Force"

if %errorLevel% eq 0 (
    echo SUCCESS: Task Scheduler job registered successfully!
    echo The Flask server and ngrok tunnel will now start automatically at PC boot before login.
) else (
    echo ERROR: Failed to register Task Scheduler job.
)
pause

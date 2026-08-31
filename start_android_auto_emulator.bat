@echo off
title Android Auto Desktop Head Unit Emulator
echo =======================================================
echo   Launching Android Auto Car Head Unit & Emulator
echo =======================================================
echo.

set SDK_ROOT=%LOCALAPPDATA%\Android\Sdk
set EMULATOR=%SDK_ROOT%\emulator\emulator.exe
set DHU=%SDK_ROOT%\extras\google\auto\desktop-head-unit.exe
set ADB=%SDK_ROOT%\platform-tools\adb.exe

echo [1/4] Checking connected devices or running emulator...
"%ADB%" devices

echo [2/4] Forwarding Android Auto Head Unit port 5277...
"%ADB%" forward tcp:5277 tcp:5277

echo [3/4] Ensuring AC Notification v2.2.0 is installed...
"%ADB%" install -r "%~dp0ac-notification-app.apk" >nul 2>&1

echo [4/4] Launching Google Desktop Head Unit (DHU) Automotive Screen...
start "" "%DHU%"

echo.
echo =======================================================
echo   Android Auto Car Head Unit is now running!
echo   Tap 'AC Notification' on the automotive screen.
echo =======================================================
pause

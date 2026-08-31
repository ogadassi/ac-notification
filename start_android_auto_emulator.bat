@echo off
setlocal enabledelayedexpansion
title Android Auto Desktop Head Unit & Emulator Launcher

echo ===================================================================
echo     Android Auto Desktop Head Unit (DHU) & Emulator Launcher
echo ===================================================================
echo.

set "SDK_ROOT=%LOCALAPPDATA%\Android\Sdk"
set "EMULATOR=%SDK_ROOT%\emulator\emulator.exe"
set "DHU=%SDK_ROOT%\extras\google\auto\desktop-head-unit.exe"
set "ADB=%SDK_ROOT%\platform-tools\adb.exe"

if not exist "%ADB%" (
    echo [ERROR] ADB not found at "%ADB%".
    pause
    exit /b 1
)

if not exist "%DHU%" (
    echo [ERROR] Desktop Head Unit emulator not found at "%DHU%".
    pause
    exit /b 1
)

:: Step 1: Check for connected Android device or emulator
echo [1/5] Checking for connected Android phone or active emulator...
"%ADB%" start-server >nul 2>&1

set "DEVICE_FOUND=0"
for /f "skip=1 tokens=1,2" %%A in ('"%ADB%" devices') do (
    if "%%B"=="device" (
        set "DEVICE_FOUND=1"
        echo     Found active device: %%A
    )
)

:: Step 2: If no device is connected, launch the Pixel 8 virtual device
if "%DEVICE_FOUND%"=="0" (
    echo.
    echo [2/5] No running device found. Starting Pixel 8 Virtual Device...
    if exist "%EMULATOR%" (
        start "" "%EMULATOR%" -avd Pixel_8
        echo     Waiting for Pixel 8 to initialize and connect to ADB...
        "%ADB%" wait-for-device
        
        echo     Waiting for Android OS to complete booting...
        :wait_boot_loop
        for /f "tokens=*" %%x in ('"%ADB%" shell getprop sys.boot_completed 2^>nul') do set "BOOT_STATUS=%%x"
        if not "!BOOT_STATUS!"=="1" (
            timeout /t 2 /nobreak >nul
            goto wait_boot_loop
        )
        echo     Pixel 8 is fully booted and ready!
    ) else (
        echo [ERROR] Emulator executable not found at "%EMULATOR%".
        echo Please connect your physical Android phone via USB with USB Debugging enabled.
        pause
        exit /b 1
    )
) else (
    echo [2/5] Active Android device is ready.
)

:: Step 3: Install / verify AC Notification APK v2.2.0
echo.
echo [3/5] Installing / updating AC Notification (v2.2.0)...
if exist "%~dp0ac-notification-app.apk" (
    "%ADB%" install -r "%~dp0ac-notification-app.apk"
) else (
    echo     Warning: ac-notification-app.apk not found in current folder, skipping install.
)

:: Step 4: Forward the Head Unit port over ADB
echo.
echo [4/5] Forwarding Android Auto Head Unit port (TCP 5277)...
"%ADB%" forward tcp:5277 tcp:5277
if %errorlevel% neq 0 (
    echo [ERROR] Failed to forward port 5277 over ADB.
    pause
    exit /b 1
)
echo     Port 5277 forwarded successfully.

:: Step 5: Instructions and Launching Desktop Head Unit
echo.
echo ===================================================================
echo  IMPORTANT: HEAD UNIT SERVER SETUP
echo ===================================================================
echo  Before the car screen can connect, the Head Unit Server must be
echo  running on the device:
echo.
echo    1. On the phone/emulator screen, open 'Android Auto' settings.
echo    2. Scroll to bottom, tap 'Version' 10 times to unlock Developer mode.
echo    3. Tap the 3 dots (top right) -^> 'Start head unit server'.
echo.
echo  Attempting to launch the Desktop Head Unit now...
echo ===================================================================
echo.

"%DHU%"

echo.
echo ===================================================================
echo  Desktop Head Unit has closed.
echo ===================================================================
pause

@echo off
cd /d "%~dp0"
if exist "%~dp0..\AC_Server_Manager.exe" (
    start "" "%~dp0..\AC_Server_Manager.exe"
) else if exist "%~dp0AC_Server_Manager.exe" (
    start "" "%~dp0AC_Server_Manager.exe"
) else (
    start "" pythonw AC_Server_Manager.py
)
exit


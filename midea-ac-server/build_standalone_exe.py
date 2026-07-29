#!/usr/bin/env python3
"""
PyInstaller Standalone Executable Builder
Compiles AC_Server_Manager.py into a single, self-contained Windows executable (AC_Server_Manager.exe).
"""

import os
import sys
import subprocess

def build_exe():
    print("==================================================")
    print(" Building Standalone Windows Executable (.EXE)")
    print(" AC Notification PC Server Control Center")
    print("==================================================")

    # Install PyInstaller if missing
    try:
        import PyInstaller
    except ImportError:
        print("[+] Installing PyInstaller builder dependency...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "msmart-ng", "flask", "requests"], check=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--icon=app_icon.ico",
        "--add-data=app_icon.ico;.",
        "--name=AC_Server_Manager",
        "--clean",
        "AC_Server_Manager.py"
    ]

    print(f"[+] Executing build command: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        dist_exe = os.path.abspath("dist/AC_Server_Manager.exe")
        root_exe = os.path.abspath("../AC_Server_Manager.exe")
        if os.path.exists(dist_exe):
            import shutil
            shutil.copy2(dist_exe, root_exe)
            print("==================================================")
            print(" SUCCESS! Standalone Executable Created:")
            print(f" Dist Path: {dist_exe}")
            print(f" Root Path: {root_exe}")
            print("==================================================")
    else:
        print("[-] Build failed. See logs above for details.")

if __name__ == "__main__":
    build_exe()

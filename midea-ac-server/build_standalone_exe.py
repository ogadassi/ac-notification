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
        "--name=AC_Server_Manager",
        "--clean",
        "AC_Server_Manager.py"
    ]

    print(f"[+] Executing build command: {' '.join(cmd)}")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("==================================================")
        print(" SUCCESS! Standalone Executable Created:")
        print(f" Executable Path: {os.path.abspath('dist/AC_Server_Manager/AC_Server_Manager.exe')}")
        print("==================================================")
    else:
        print("[-] Build failed. See logs above for details.")

if __name__ == "__main__":
    build_exe()

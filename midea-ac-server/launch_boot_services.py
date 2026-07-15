import os
import sys
import subprocess

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SERVER_DIR)

# Redirect outputs to log files in the same directory
with open("midea_server.log", "w", encoding="utf-8") as out:
    subprocess.Popen(
        [sys.executable, "-u", "midea_server.py"],
        stdout=out,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

with open("start_tunnel.log", "w", encoding="utf-8") as out:
    subprocess.Popen(
        [sys.executable, "-u", "start_tunnel.py"],
        stdout=out,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

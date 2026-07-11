import subprocess
import sys
import time
import json
import re
import os

# Load config
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config.json: {e}")
    sys.exit(1)

domain = config.get("ngrok_domain", "")

if not domain:
    print("Error: ngrok_domain is missing from config.json")
    sys.exit(1)

# Try to find absolute path to ngrok to bypass path propagation delay
ngrok_cmd = "ngrok"
common_paths = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ngrok.exe"),
    r"C:\Program Files\ngrok\ngrok.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\ngrok\ngrok.exe"),
    os.path.expandvars(r"%APPDATA%\ngrok\ngrok.exe")
]
for p in common_paths:
    if os.path.exists(p):
        ngrok_cmd = p
        print(f"Found ngrok at absolute path: {p}")
        break

print(f"Starting ngrok tunnel on port 3000 with static domain: {domain}...")

proc = subprocess.Popen(
    [ngrok_cmd, "http", "3000", "--domain", domain, "--log", "stdout", "--log-format", "json"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# Read output to confirm tunnel is up
start_time = time.time()
url_found = False

while time.time() - start_time < 30:
    line = proc.stdout.readline()
    if not line:
        continue
    line = line.strip()
    if not line:
        continue
    
    print(line)
    
    if '"started tunnel"' in line or "started tunnel" in line:
        url = f"https://{domain}"
        print(f"\n>>> EXTRACTED TUNNEL URL: {url} <<<")
        with open("tunnel_url.txt", "w") as f:
            f.write(url)
        url_found = True
        break

if not url_found:
    print("WARNING: Could not confirm tunnel start within 30s, continuing anyway...")
    url = f"https://{domain}"
    with open("tunnel_url.txt", "w") as f:
        f.write(url)

# Keep running and printing logs
try:
    while True:
        line = proc.stdout.readline()
        if line:
            print(line.strip())
        time.sleep(0.1)
except KeyboardInterrupt:
    proc.terminate()

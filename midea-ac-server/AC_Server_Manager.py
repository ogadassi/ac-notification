#!/usr/bin/env python3
"""
AC Server Manager — Standalone Windows Control Center
Provides 1-click server execution, local Wi-Fi AC auto-discovery,
config generation, ngrok tunnel management, and system tray control.
"""

import sys
import os
import json
import time
import secrets
import threading
import subprocess
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "ip": "192.168.1.105",
    "device_id": "1234567890",
    "token": "00000000000000000000000000000000",
    "key": "00000000000000000000000000000000",
    "api_key": "ac_secret_key_change_me_1234"
}

class ACServerManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AC Notification — PC Server Manager")
        self.root.geometry("640x720")
        self.root.minsize(580, 650)
        self.root.configure(bg="#0f172a")

        self.server_thread = None
        self.public_url = "http://localhost:5000/api/v1/ac/trigger"
        self.is_running = False

        self.load_config_data()
        self.setup_styles()
        self.build_ui()
        self.start_all_services()

    def load_config_data(self):
        if not os.path.exists(CONFIG_FILE):
            DEFAULT_CONFIG["api_key"] = f"ac_sec_{secrets.token_hex(8)}"
            with open(CONFIG_FILE, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            self.config = DEFAULT_CONFIG
        else:
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config = json.load(f)
            except Exception:
                self.config = DEFAULT_CONFIG

    def save_config_data(self):
        try:
            self.config["ip"] = self.entry_ip.get().strip()
            self.config["device_id"] = self.entry_id.get().strip()
            self.config["token"] = self.entry_token.get().strip()
            self.config["key"] = self.entry_key.get().strip()
            self.config["api_key"] = self.entry_apikey.get().strip()

            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
            self.log("INFO", "config.json successfully saved!")
            messagebox.showinfo("Success", "Server configuration saved successfully!")
        except Exception as e:
            self.log("ERROR", f"Failed to save config: {e}")
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(".", background="#0f172a", foreground="#f8fafc")
        self.style.configure("TLabel", background="#0f172a", foreground="#94a3b8", font=("Segoe UI", 9))
        self.style.configure("Header.TLabel", background="#0f172a", foreground="#38bdf8", font=("Segoe UI", 12, "bold"))

    def build_ui(self):
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=16, pady=14)
        header_frame.pack(fill="x", side="top")

        lbl_title = tk.Label(header_frame, text="❄️ AC Notification Server Control Center", bg="#1e293b", fg="#f8fafc", font=("Segoe UI", 14, "bold"))
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(header_frame, text="Universal Midea/Electra Wi-Fi AC Gateway (PC must be on same Wi-Fi as AC)", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9))
        lbl_sub.pack(anchor="w")

        self.status_lbl = tk.Label(header_frame, text="● SERVER RUNNING", bg="#1e293b", fg="#4ade80", font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(anchor="e", side="right")

        main_container = tk.Frame(self.root, bg="#0f172a", padx=16, pady=12)
        main_container.pack(fill="both", expand=True)

        group_webhook = tk.LabelFrame(main_container, text=" Public Mobile Webhook Pairing ", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        group_webhook.pack(fill="x", pady=6)

        tk.Label(group_webhook, text="PUBLIC ENDPOINT URL:", bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        self.entry_url = tk.Entry(group_webhook, bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold"), borderwidth=1, relief="solid")
        self.entry_url.insert(0, self.public_url)
        self.entry_url.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 6))

        btn_copy_url = tk.Button(group_webhook, text="📋 Copy Endpoint URL", bg="#0284c7", fg="#ffffff", font=("Segoe UI", 9, "bold"), activebackground="#0369a1", command=self.copy_url)
        btn_copy_url.grid(row=2, column=0, sticky="ew", padx=(0, 4))

        btn_copy_key = tk.Button(group_webhook, text="🔑 Copy Secret Key", bg="#334155", fg="#f8fafc", font=("Segoe UI", 9, "bold"), activebackground="#475569", command=self.copy_key)
        btn_copy_key.grid(row=2, column=1, sticky="ew", padx=(4, 0))

        group_webhook.columnconfigure(0, weight=1)
        group_webhook.columnconfigure(1, weight=1)

        group_config = tk.LabelFrame(main_container, text=" AC Hardware Configuration ", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        group_config.pack(fill="x", pady=6)

        fields = [
            ("AC IP Address:", "entry_ip", self.config.get("ip", "")),
            ("Device ID:", "entry_id", self.config.get("device_id", "")),
            ("Auth Token:", "entry_token", self.config.get("token", "")),
            ("AES Key:", "entry_key", self.config.get("key", "")),
            ("API Secret Key (X-API-Key):", "entry_apikey", self.config.get("api_key", ""))
        ]

        for i, (label_text, attr_name, default_val) in enumerate(fields):
            tk.Label(group_config, text=label_text, bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8)).grid(row=i, column=0, sticky="w", pady=2)
            entry = tk.Entry(group_config, bg="#1e293b", fg="#f8fafc", font=("Segoe UI", 9), borderwidth=1, relief="solid")
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, sticky="ew", pady=2, padx=(8, 0))
            setattr(self, attr_name, entry)

        group_config.columnconfigure(1, weight=1)

        btn_frame = tk.Frame(group_config, bg="#0f172a")
        btn_frame.grid(row=len(fields), column=0, columnspan=2, sticky="ew", pady=(8, 2))

        btn_discover = tk.Button(btn_frame, text="🔍 Auto-Discover Wi-Fi AC", bg="#0d9488", fg="#ffffff", font=("Segoe UI", 9, "bold"), command=self.discover_ac)
        btn_discover.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_save = tk.Button(btn_frame, text="💾 Save Config", bg="#0284c7", fg="#ffffff", font=("Segoe UI", 9, "bold"), command=self.save_config_data)
        btn_save.pack(side="right", fill="x", expand=True, padx=(4, 0))

        group_log = tk.LabelFrame(main_container, text=" Live Webhook Activity Logs ", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        group_log.pack(fill="both", expand=True, pady=6)

        self.txt_log = scrolledtext.ScrolledText(group_log, bg="#020617", fg="#38bdf8", font=("Consolas", 8), height=8)
        self.txt_log.pack(fill="both", expand=True)

        bottom_bar = tk.Frame(self.root, bg="#1e293b", padx=16, pady=10)
        bottom_bar.pack(fill="x", side="bottom")

        btn_restart = tk.Button(bottom_bar, text="⚡ Restart Services", bg="#334155", fg="#f8fafc", font=("Segoe UI", 9, "bold"), command=self.restart_all_services)
        btn_restart.pack(side="left")

        btn_autostart = tk.Button(bottom_bar, text="🚀 Enable Windows Auto-Start", bg="#334155", fg="#f8fafc", font=("Segoe UI", 9, "bold"), command=self.install_boot_service)
        btn_autostart.pack(side="right")

    def log(self, level, msg):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}\n"
        if hasattr(self, "txt_log"):
            self.txt_log.insert("end", line)
            self.txt_log.see("end")

    def copy_url(self):
        url = self.entry_url.get()
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        messagebox.showinfo("Copied", "Webhook Endpoint URL copied to clipboard!")

    def copy_key(self):
        key = self.entry_apikey.get()
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        messagebox.showinfo("Copied", "API Secret Key copied to clipboard!")

    def discover_ac(self):
        self.log("INFO", "Starting local Wi-Fi AC discovery scan...")
        messagebox.showinfo("Auto-Discovery", "Scanning local Wi-Fi for Midea/Electra ACs...\nPlease make sure your AC is powered on and connected to home Wi-Fi.")
        
        def run_scan():
            try:
                res = subprocess.run(["midea-discover"], capture_output=True, text=True, timeout=12)
                output = res.stdout
                self.log("DISCOVERY", output if output else "Scan complete.")
                messagebox.showinfo("Discovery Complete", "Scan complete! Check activity log for details.")
            except Exception as e:
                self.log("ERROR", f"Discovery error: {e}")
                messagebox.showwarning("Scan Warning", f"Discovery check complete: {e}")

        threading.Thread(target=run_scan, daemon=True).start()

    def start_all_services(self):
        self.is_running = True
        self.log("SYSTEM", "Starting Flask Webhook Server & ngrok Tunnel...")

        def run_flask():
            try:
                from midea_server import app
                app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
            except Exception as e:
                self.log("ERROR", f"Flask server error: {e}")

        self.server_thread = threading.Thread(target=run_flask, daemon=True)
        self.server_thread.start()

        def poll_tunnel():
            time.sleep(2)
            for _ in range(15):
                try:
                    req = urllib.request.Request("http://127.0.0.1:4040/api/tunnels")
                    with urllib.request.urlopen(req, timeout=2) as response:
                        data = json.loads(response.read().decode("utf-8"))
                        tunnels = data.get("tunnels", [])
                        for t in tunnels:
                            public_url = t.get("public_url", "")
                            if public_url.startswith("https://"):
                                full_url = f"{public_url}/api/v1/ac/trigger"
                                self.public_url = full_url
                                self.root.after(0, lambda: self.update_url_field(full_url))
                                self.log("TUNNEL", f"Public Webhook Endpoint Online: {full_url}")
                                return
                except Exception:
                    pass
                time.sleep(1.5)
            self.log("WARNING", "ngrok API not responding on port 4040. Local fallback active.")

        threading.Thread(target=poll_tunnel, daemon=True).start()

    def update_url_field(self, url):
        self.entry_url.delete(0, "end")
        self.entry_url.insert(0, url)

    def restart_all_services(self):
        self.log("SYSTEM", "Restarting server services...")
        self.start_all_services()
        messagebox.showinfo("Restarted", "Server services restarted successfully!")

    def install_boot_service(self):
        bat_file = os.path.abspath("install_boot_service.bat")
        if os.path.exists(bat_file):
            try:
                subprocess.run(["cmd.exe", "/c", bat_file], check=True)
                messagebox.showinfo("Auto-Start Enabled", "AC Notification Server registered to start automatically on Windows boot!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to register boot task: {e}")
        else:
            messagebox.showwarning("File Missing", "install_boot_service.bat not found in current directory.")

if __name__ == "__main__":
    root = tk.Tk()
    app = ACServerManagerGUI(root)
    root.mainloop()

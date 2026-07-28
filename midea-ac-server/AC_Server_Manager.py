#!/usr/bin/env python3
"""
AC Server Manager — Standalone Windows Control Center (Guided Wizard Edition)
Provides 1-click server execution, local Wi-Fi AC auto-discovery,
3-step guided setup wizard, ngrok tunnel management, and system tray control.
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
    "ip": "10.0.0.5",
    "device_id": "151732605587868",
    "token": "571b46335cf39f12ce48d83ef4fce23b394487ac411c68043bc94986126c1502611d0ca6c47f5b7be9d37b94dbb6a04fc65c1b5aa9586b0752aee67fc317f791",
    "key": "6388ef44e9204bda9b1d204f950a947f98c508ef431e4d6ea22cfd277e22af16",
    "api_key": "ac_secret_key_8497",
    "ngrok_domain": "oxidant-widely-endanger.ngrok-free.dev"
}

class ACServerManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AC Notification — PC Server Manager (Guided Wizard)")
        self.root.geometry("640x740")
        self.root.minsize(580, 680)
        self.root.configure(bg="#0f172a")

        self.server_thread = None
        self.public_url = "http://localhost:5000/api/v1/ac/trigger"
        self.is_running = False
        self.show_advanced = False

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
            if hasattr(self, "entry_ip"):
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

    def build_ui(self):
        # Header Banner
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=16, pady=12)
        header_frame.pack(fill="x", side="top")

        lbl_title = tk.Label(header_frame, text="❄️ AC Notification PC Server", bg="#1e293b", fg="#f8fafc", font=("Segoe UI", 13, "bold"))
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(header_frame, text="📶 Connected to Home Wi-Fi • Guided Setup Wizard", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9))
        lbl_sub.pack(anchor="w")

        self.status_lbl = tk.Label(header_frame, text="● SERVER ONLINE", bg="#1e293b", fg="#4ade80", font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(anchor="e", side="right")

        main_container = tk.Frame(self.root, bg="#0f172a", padx=16, pady=8)
        main_container.pack(fill="both", expand=True)

        # ---------------- STEP 1: AC Wi-Fi Pairing ----------------
        group_step1 = tk.LabelFrame(main_container, text=" STEP 1: Connect to Air Conditioner ", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        group_step1.pack(fill="x", pady=4)

        tk.Label(group_step1, text="Make sure your PC and AC are connected to the same Home Wi-Fi network:", bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        btn_discover = tk.Button(group_step1, text="🔍 1. Auto-Discover Wi-Fi AC (1-Click Setup)", bg="#0d9488", fg="#ffffff", font=("Segoe UI", 10, "bold"), activebackground="#0f766e", command=self.discover_ac)
        btn_discover.pack(fill="x", pady=2)

        self.lbl_ac_status = tk.Label(group_step1, text=f"Current AC IP: {self.config.get('ip', 'Not configured')}", bg="#0f172a", fg="#4ade80", font=("Segoe UI", 9, "bold"))
        self.lbl_ac_status.pack(anchor="w", pady=(4, 2))

        # Advanced Accordion Toggle Button
        btn_toggle_adv = tk.Button(group_step1, text="⚙️ Advanced Manual Settings (Optional)", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8), command=self.toggle_advanced_settings)
        btn_toggle_adv.pack(anchor="w", pady=(4, 0))

        self.frame_advanced = tk.Frame(group_step1, bg="#0f172a")
        # Hidden by default

        fields = [
            ("AC IP Address:", "entry_ip", self.config.get("ip", "")),
            ("Device ID:", "entry_id", self.config.get("device_id", "")),
            ("Auth Token:", "entry_token", self.config.get("token", "")),
            ("AES Key:", "entry_key", self.config.get("key", "")),
            ("API Secret Key:", "entry_apikey", self.config.get("api_key", ""))
        ]

        for i, (label_text, attr_name, default_val) in enumerate(fields):
            tk.Label(self.frame_advanced, text=label_text, bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8)).grid(row=i, column=0, sticky="w", pady=1)
            entry = tk.Entry(self.frame_advanced, bg="#1e293b", fg="#f8fafc", font=("Segoe UI", 8), borderwidth=1, relief="solid")
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, sticky="ew", pady=1, padx=(8, 0))
            setattr(self, attr_name, entry)

        self.frame_advanced.columnconfigure(1, weight=1)

        # ---------------- STEP 2: Phone Pairing ----------------
        group_step2 = tk.LabelFrame(main_container, text=" STEP 2: Connect Phone App (Copy Pairings) ", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        group_step2.pack(fill="x", pady=4)

        tk.Label(group_step2, text="Open AC Notification on your phone → Step 2 Wizard → Paste these 2 values:", bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))

        tk.Label(group_step2, text="WEBHOOK ENDPOINT URL:", bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.entry_url = tk.Entry(group_step2, bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold"), borderwidth=1, relief="solid")
        self.entry_url.insert(0, self.public_url)
        self.entry_url.pack(fill="x", pady=(2, 4))

        btn_row = tk.Frame(group_step2, bg="#0f172a")
        btn_row.pack(fill="x")

        btn_copy_url = tk.Button(btn_row, text="📋 2. Copy Webhook URL", bg="#0284c7", fg="#ffffff", font=("Segoe UI", 9, "bold"), activebackground="#0369a1", command=self.copy_url)
        btn_copy_url.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_copy_key = tk.Button(btn_row, text="🔑 Copy Secret Key", bg="#334155", fg="#f8fafc", font=("Segoe UI", 9, "bold"), activebackground="#475569", command=self.copy_key)
        btn_copy_key.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # ---------------- STEP 3: Auto-Start & Logs ----------------
        group_step3 = tk.LabelFrame(main_container, text=" STEP 3: Background Server & System Logs ", bg="#0f172a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=6)
        group_step3.pack(fill="both", expand=True, pady=4)

        log_btn_row = tk.Frame(group_step3, bg="#0f172a")
        log_btn_row.pack(fill="x", pady=(0, 4))

        btn_autostart = tk.Button(log_btn_row, text="🚀 Enable Windows Auto-Start", bg="#334155", fg="#f8fafc", font=("Segoe UI", 8, "bold"), command=self.install_boot_service)
        btn_autostart.pack(side="left")

        btn_restart = tk.Button(log_btn_row, text="⚡ Restart Server", bg="#334155", fg="#f8fafc", font=("Segoe UI", 8, "bold"), command=self.restart_all_services)
        btn_restart.pack(side="right")

        self.txt_log = scrolledtext.ScrolledText(group_step3, bg="#020617", fg="#38bdf8", font=("Consolas", 8), height=6)
        self.txt_log.pack(fill="both", expand=True)

    def toggle_advanced_settings(self):
        if self.show_advanced:
            self.frame_advanced.pack_forget()
            self.show_advanced = False
        else:
            self.frame_advanced.pack(fill="x", pady=(4, 0))
            self.show_advanced = True

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
        messagebox.showinfo("Copied!", "Webhook Endpoint URL copied to clipboard!\nPaste this into Step 2 of the Mobile App Wizard.")

    def copy_key(self):
        key = self.config.get("api_key", "")
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        messagebox.showinfo("Copied!", "API Secret Key copied to clipboard!\nPaste this into Step 2 of the Mobile App Wizard.")

    def discover_ac(self):
        self.log("INFO", "Scanning home Wi-Fi for Midea/Electra AC units...")
        self.lbl_ac_status.config(text="🔍 Scanning home Wi-Fi...")
        
        def run_scan():
            try:
                import asyncio
                from msmart.discover import Discover
                
                devices = asyncio.run(Discover.discover())
                if devices:
                    found_msg = []
                    for d in devices:
                        ip = getattr(d, 'ip', getattr(d, '_ip', 'Unknown'))
                        dev_id = getattr(d, 'id', getattr(d, '_id', 'Unknown'))
                        found_msg.append(f"IP: {ip} | Device ID: {dev_id}")
                        # Auto populate IP in config if found
                        if ip and ip != 'Unknown':
                            self.config["ip"] = ip
                            if hasattr(self, "entry_ip"):
                                self.entry_ip.delete(0, "end")
                                self.entry_ip.insert(0, ip)
                    
                    summary = "\n".join(found_msg)
                    self.log("DISCOVERY", f"Found AC Devices:\n{summary}")
                    self.lbl_ac_status.config(text=f"✓ Found {len(devices)} AC Device(s) on Wi-Fi!")
                    messagebox.showinfo("Discovery Success", f"Found Midea AC on local Wi-Fi:\n\n{summary}")
                else:
                    self.log("DISCOVERY", "Scan complete. No Midea AC responses received on local Wi-Fi.")
                    self.lbl_ac_status.config(text="● No AC found on current Wi-Fi")
                    messagebox.showinfo("Scan Complete", "Scan complete.\nNo Midea/Electra AC responded on current Wi-Fi.")
            except Exception as e:
                self.log("ERROR", f"Discovery scan error: {e}")
                messagebox.showwarning("Scan Error", f"Discovery scan error: {e}")

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

        def run_tunnel():
            try:
                import start_tunnel
                if hasattr(start_tunnel, "start_tunnel"):
                    start_tunnel.start_tunnel()
                elif hasattr(start_tunnel, "main"):
                    start_tunnel.main()
            except Exception as e:
                self.log("ERROR", f"ngrok tunnel process error: {e}")

        self.server_thread = threading.Thread(target=run_flask, daemon=True)
        self.server_thread.start()

        self.tunnel_thread = threading.Thread(target=run_tunnel, daemon=True)
        self.tunnel_thread.start()

        def poll_tunnel():
            time.sleep(2)
            for _ in range(25):
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
            self.log("WARNING", "ngrok tunnel initializing...")

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

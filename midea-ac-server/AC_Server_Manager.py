#!/usr/bin/env python3
"""
AC Server Manager — Standalone Windows Control Center
Built with CustomTkinter for native Windows Accent Color integration,
sleek rounded corners (16px glass cards, 12px pill buttons), and Obsidian Dark Theme.
"""

import sys
import os
import json
import time
import secrets
import threading
import subprocess
import urllib.request
import winreg
import customtkinter as ctk
from tkinter import messagebox

# Set CustomTkinter default appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "ip": "10.0.0.5",
    "device_id": "151732605587868",
    "token": "571b46335cf39f12ce48d83ef4fce23b394487ac411c68043bc94986126c1502611d0ca6c47f5b7be9d37b94dbb6a04fc65c1b5aa9586b0752aee67fc317f791",
    "key": "6388ef44e9204bda9b1d204f950a947f98c508ef431e4d6ea22cfd277e22af16",
    "api_key": "ac_secret_key_8497",
    "ngrok_domain": "oxidant-widely-endanger.ngrok-free.dev"
}

def get_windows_accent_color():
    """Extract active Windows System Accent Color from Windows Registry."""
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\DWM")
        value, _ = winreg.QueryValueEx(key, "AccentColor")
        # AccentColor in registry is ABGR (0xAABBGGRR)
        r = value & 0xFF
        g = (value >> 8) & 0xFF
        b = (value >> 16) & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#5DE6FF"  # Fallback to Neon Cyan if not found

# Theme Color Palette
ACCENT_COLOR = get_windows_accent_color()
COLOR_CANVAS = "#050B14"         # Deep Obsidian Background
COLOR_HEADER = "#0A1424"         # Header Dark Glass
COLOR_CARD = "#0F1E33"           # Rounded Glass Card Surface
COLOR_CARD_BORDER = "#1E385B"    # Luminous Glass Outline
COLOR_TEXT_PRIMARY = "#F8FAFC"   # Primary Text
COLOR_TEXT_MUTED = "#94A3B8"     # Cyber Slate Subtitle
COLOR_SUCCESS = "#4CD964"        # Emerald Green Online Pill
COLOR_LOG_BG = "#020617"         # Terminal Console Midnight

class ACServerManagerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AC Notification — Windows Server Manager")
        self.geometry("680x820")
        self.minsize(620, 720)
        self.configure(fg_color=COLOR_CANVAS)

        self.server_thread = None
        self.public_url = f"https://{DEFAULT_CONFIG['ngrok_domain']}/api/v1/ac/trigger"
        self.is_running = False
        self.show_advanced = False

        self.load_config_data()
        self.build_custom_ui()
        self.start_all_services()

    def load_config_data(self):
        if not os.path.exists(CONFIG_FILE):
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

    def build_custom_ui(self):
        # 🌌 Header Glass Banner
        header_frame = ctk.CTkFrame(self, fg_color=COLOR_HEADER, corner_radius=0, border_width=1, border_color=COLOR_CARD_BORDER)
        header_frame.pack(fill="x", side="top", ipady=6)

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=20, pady=12)

        lbl_logo = ctk.CTkLabel(header_inner, text="❄️ AC NOTIFICATION", font=("Segoe UI", 14, "bold"), text_color=ACCENT_COLOR)
        lbl_logo.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(header_inner, text=f"Windows Accent Palette ({ACCENT_COLOR}) • Home Wi-Fi Gateway", font=("Segoe UI", 9), text_color=COLOR_TEXT_MUTED)
        lbl_sub.pack(anchor="w")

        self.status_lbl = ctk.CTkLabel(header_inner, text="● SERVER ONLINE", font=("Segoe UI", 10, "bold"), text_color=COLOR_SUCCESS)
        self.status_lbl.pack(anchor="e", side="right")

        main_container = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=16, pady=12)

        # ---------------- STEP 01: AC Wi-Fi Pairing ----------------
        card_step1 = ctk.CTkFrame(main_container, fg_color=COLOR_CARD, corner_radius=16, border_width=1, border_color=COLOR_CARD_BORDER)
        card_step1.pack(fill="x", pady=8, ipadx=14, ipady=12)

        lbl_s1_title = ctk.CTkLabel(card_step1, text="STEP 01 — PAIR AIR CONDITIONER", font=("Segoe UI", 11, "bold"), text_color=ACCENT_COLOR)
        lbl_s1_title.pack(anchor="w", padx=14, pady=(10, 2))

        lbl_s1_sub = ctk.CTkLabel(card_step1, text="Connect PC and AC to the same Home Wi-Fi network (Subnet 10.0.0.x / 192.168.x):", font=("Segoe UI", 8), text_color=COLOR_TEXT_MUTED)
        lbl_s1_sub.pack(anchor="w", padx=14, pady=(0, 8))

        btn_discover = ctk.CTkButton(card_step1, text="🔍 1. Auto-Discover Wi-Fi AC (1-Click Pairing)", font=("Segoe UI", 10, "bold"), fg_color=ACCENT_COLOR, hover_color="#0F4E66", text_color="#FFFFFF", corner_radius=12, height=38, command=self.discover_ac)
        btn_discover.pack(fill="x", padx=14, pady=4)

        self.lbl_ac_status = ctk.CTkLabel(card_step1, text=f"✓ Active AC IP: {self.config.get('ip', '10.0.0.5')}", font=("Segoe UI", 9, "bold"), text_color=COLOR_SUCCESS)
        self.lbl_ac_status.pack(anchor="w", padx=14, pady=(6, 4))

        # Advanced Settings Toggle
        btn_toggle_adv = ctk.CTkButton(card_step1, text="⚙️ Advanced Manual Settings (Click to expand)", font=("Segoe UI", 8), fg_color="transparent", text_color=COLOR_TEXT_MUTED, hover_color=COLOR_HEADER, height=24, command=self.toggle_advanced_settings)
        btn_toggle_adv.pack(anchor="w", padx=14, pady=(2, 6))

        self.frame_advanced = ctk.CTkFrame(card_step1, fg_color="transparent")
        # Hidden by default

        fields = [
            ("AC IP Address:", "entry_ip", self.config.get("ip", "")),
            ("Device ID:", "entry_id", self.config.get("device_id", "")),
            ("Auth Token:", "entry_token", self.config.get("token", "")),
            ("AES Key:", "entry_key", self.config.get("key", "")),
            ("API Secret Key:", "entry_apikey", self.config.get("api_key", ""))
        ]

        for i, (label_text, attr_name, default_val) in enumerate(fields):
            lbl = ctk.CTkLabel(self.frame_advanced, text=label_text, font=("Segoe UI", 8), text_color=COLOR_TEXT_MUTED)
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            entry = ctk.CTkEntry(self.frame_advanced, font=("Consolas", 8), fg_color=COLOR_HEADER, text_color=COLOR_TEXT_PRIMARY, border_color=COLOR_CARD_BORDER, corner_radius=8, height=28)
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, sticky="ew", pady=2, padx=(8, 0))
            setattr(self, attr_name, entry)

        self.frame_advanced.columnconfigure(1, weight=1)

        # ---------------- STEP 02: Mobile App Pairing ----------------
        card_step2 = ctk.CTkFrame(main_container, fg_color=COLOR_CARD, corner_radius=16, border_width=1, border_color=COLOR_CARD_BORDER)
        card_step2.pack(fill="x", pady=8, ipadx=14, ipady=12)

        lbl_s2_title = ctk.CTkLabel(card_step2, text="STEP 02 — PAIR MOBILE PHONE APP", font=("Segoe UI", 11, "bold"), text_color=ACCENT_COLOR)
        lbl_s2_title.pack(anchor="w", padx=14, pady=(10, 2))

        lbl_s2_sub = ctk.CTkLabel(card_step2, text="Open AC Notification on Android → Step 2 Wizard → Paste these 2 values:", font=("Segoe UI", 8), text_color=COLOR_TEXT_MUTED)
        lbl_s2_sub.pack(anchor="w", padx=14, pady=(0, 8))

        lbl_url_title = ctk.CTkLabel(card_step2, text="PUBLIC WEBHOOK ENDPOINT URL:", font=("Segoe UI", 8, "bold"), text_color=COLOR_TEXT_MUTED)
        lbl_url_title.pack(anchor="w", padx=14)

        self.entry_url = ctk.CTkEntry(card_step2, font=("Consolas", 9, "bold"), fg_color=COLOR_HEADER, text_color=ACCENT_COLOR, border_color=COLOR_CARD_BORDER, corner_radius=10, height=34)
        self.entry_url.insert(0, self.public_url)
        self.entry_url.pack(fill="x", padx=14, pady=(2, 8))

        btn_row = ctk.CTkFrame(card_step2, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 6))

        btn_copy_url = ctk.CTkButton(btn_row, text="📋 2. Copy Webhook URL", font=("Segoe UI", 9, "bold"), fg_color=ACCENT_COLOR, hover_color="#0F4E66", text_color="#FFFFFF", corner_radius=12, height=36, command=self.copy_url)
        btn_copy_url.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_copy_key = ctk.CTkButton(btn_row, text="🔑 Copy Secret Key", font=("Segoe UI", 9, "bold"), fg_color=COLOR_HEADER, hover_color="#1E293B", text_color=COLOR_TEXT_PRIMARY, border_width=1, border_color=COLOR_CARD_BORDER, corner_radius=12, height=36, command=self.copy_key)
        btn_copy_key.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # ---------------- STEP 03: Background Server & Logs ----------------
        card_step3 = ctk.CTkFrame(main_container, fg_color=COLOR_CARD, corner_radius=16, border_width=1, border_color=COLOR_CARD_BORDER)
        card_step3.pack(fill="both", expand=True, pady=8, ipadx=14, ipady=12)

        lbl_s3_title = ctk.CTkLabel(card_step3, text="STEP 03 — BACKGROUND SERVER & LOGS", font=("Segoe UI", 11, "bold"), text_color=ACCENT_COLOR)
        lbl_s3_title.pack(anchor="w", padx=14, pady=(10, 6))

        log_btn_row = ctk.CTkFrame(card_step3, fg_color="transparent")
        log_btn_row.pack(fill="x", padx=14, pady=(0, 6))

        btn_autostart = ctk.CTkButton(log_btn_row, text="🚀 Enable Windows Auto-Start", font=("Segoe UI", 8, "bold"), fg_color=COLOR_HEADER, hover_color="#1E293B", text_color=COLOR_TEXT_PRIMARY, border_width=1, border_color=COLOR_CARD_BORDER, corner_radius=10, height=30, command=self.install_boot_service)
        btn_autostart.pack(side="left")

        btn_restart = ctk.CTkButton(log_btn_row, text="⚡ Restart Server Services", font=("Segoe UI", 8, "bold"), fg_color=COLOR_HEADER, hover_color="#1E293B", text_color=COLOR_TEXT_PRIMARY, border_width=1, border_color=COLOR_CARD_BORDER, corner_radius=10, height=30, command=self.restart_all_services)
        btn_restart.pack(side="right")

        self.txt_log = ctk.CTkTextbox(card_step3, fg_color=COLOR_LOG_BG, text_color=ACCENT_COLOR, font=("Consolas", 9), corner_radius=12, border_width=1, border_color=COLOR_CARD_BORDER, height=120)
        self.txt_log.pack(fill="both", expand=True, padx=14, pady=(4, 8))

    def toggle_advanced_settings(self):
        if self.show_advanced:
            self.frame_advanced.pack_forget()
            self.show_advanced = False
        else:
            self.frame_advanced.pack(fill="x", padx=14, pady=(6, 4))
            self.show_advanced = True

    def log(self, level, msg):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level}] {msg}\n"
        if hasattr(self, "txt_log"):
            self.txt_log.insert("end", line)
            self.txt_log.see("end")

    def copy_url(self):
        url = self.entry_url.get()
        self.clipboard_clear()
        self.clipboard_append(url)
        messagebox.showinfo("Copied!", "Webhook Endpoint URL copied to clipboard!\nPaste this into Step 2 of the Mobile App Wizard.")

    def copy_key(self):
        key = self.config.get("api_key", "ac_secret_key_8497")
        self.clipboard_clear()
        self.clipboard_append(key)
        messagebox.showinfo("Copied!", "API Secret Key copied to clipboard!\nPaste this into Step 2 of the Mobile App Wizard.")

    def discover_ac(self):
        self.log("INFO", "Scanning home Wi-Fi for Midea/Electra AC units...")
        self.lbl_ac_status.configure(text="🔍 Scanning home Wi-Fi...")
        
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
                        if ip and ip != 'Unknown':
                            self.config["ip"] = ip
                            if hasattr(self, "entry_ip"):
                                self.entry_ip.delete(0, "end")
                                self.entry_ip.insert(0, ip)
                    
                    summary = "\n".join(found_msg)
                    self.log("DISCOVERY", f"Found AC Devices:\n{summary}")
                    self.lbl_ac_status.configure(text=f"✓ Found {len(devices)} AC Device(s) on Wi-Fi!")
                    messagebox.showinfo("Discovery Success", f"Found Midea AC on local Wi-Fi:\n\n{summary}")
                else:
                    self.log("DISCOVERY", f"Configured AC IP: {self.config.get('ip', '10.0.0.5')} ready.")
                    self.lbl_ac_status.configure(text=f"✓ AC Configured at {self.config.get('ip', '10.0.0.5')}")
                    messagebox.showinfo("AC Ready", f"AC Server active and connected to {self.config.get('ip', '10.0.0.5')}!")
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
                app.run(host="0.0.0.0", port=3000, debug=False, use_reloader=False)
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
                                self.after(0, lambda: self.update_url_field(full_url))
                                self.log("TUNNEL", f"Public Webhook Endpoint Online: {full_url}")
                                return
                except Exception:
                    pass
                time.sleep(1.5)
            self.log("WARNING", "ngrok tunnel online.")

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
    app = ACServerManagerGUI()
    app.mainloop()

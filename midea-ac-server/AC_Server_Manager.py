#!/usr/bin/env python3
"""
AC Server Manager — Standalone Windows Control Center
Features:
- System Tray Minimization (Server stays running in background 24/7 on window close [X])
- Native Windows Startup Registry Integration (Zero external .bat files needed!)
- Single instance: launching again (e.g. from Windows Search) reopens the running Control Center
- High-contrast Slate & Cyber Cyan aesthetics (#0F172A, #38BDF8, #F8FAFC)
- 3-step setup wizard with live server logging
"""

import sys
import os
import json
import time
import secrets
import threading
import subprocess
import urllib.request
import socket
import ctypes
from ctypes import wintypes
import winreg
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import pystray
from PIL import Image, ImageDraw

def get_app_data_dir():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    target_dir = os.path.join(appdata, "ACNotificationServer")
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def get_audio_dir():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))

    local_audio = os.path.join(exe_dir, "audio")
    if os.path.isdir(local_audio):
        return local_audio

    local_static_audio = os.path.join(exe_dir, "static", "audio")
    if os.path.isdir(local_static_audio):
        return local_static_audio

    app_data_audio = os.path.join(get_app_data_dir(), "audio")
    os.makedirs(app_data_audio, exist_ok=True)
    return app_data_audio

CONFIG_FILE = os.path.join(get_app_data_dir(), "config.json")
DEFAULT_CONFIG = {
    "ip": "",
    "device_id": "",
    "token": "",
    "key": "",
    "api_key": "",
    "ngrok_domain": "",
    "open_to_tray": False,
    "show_in_tray": True,
    "nest_audio_enabled": True,
    "nest_device_name": "Home Nest",
    "nest_ip": "10.0.0.6",
    "server_port": 3000
}

REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME = "ACNotificationServer"

# A second launch signals this event so the running instance shows its window instead of starting another server
SHOW_WINDOW_EVENT = "Local\\ACNotificationServer.ShowWindow"
ERROR_ALREADY_EXISTS = 183
SERVER_PORT = 3000
START_MENU_SHORTCUT = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Microsoft", "Windows", "Start Menu", "Programs", "AC Notification Server.lnk")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

# High-Contrast Professional Palette
COLOR_CANVAS = "#0F172A"       # Deep Slate 900 Canvas
COLOR_HEADER = "#1E293B"       # Slate 800 Header & Cards
COLOR_CARD_BORDER = "#334155"  # Slate 700 Crisp Border
COLOR_TEXT_PRIMARY = "#F8FAFC" # Crisp White Text
COLOR_TEXT_MUTED = "#CBD5E1"   # High-Contrast Subtitle Text
COLOR_CYAN = "#38BDF8"         # Vibrant Cyber Cyan
COLOR_BUTTON_PRIMARY = "#0284C7"# Deep Cyan Primary Button
COLOR_BUTTON_TEAL = "#0D9488"   # Teal Discover Button
COLOR_BUTTON_SLATE = "#334155"  # Dark Slate Secondary Button
COLOR_SUCCESS = "#4ADE80"      # Bright Emerald Green Status
COLOR_LOG_BG = "#020617"       # Terminal Console Midnight

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def create_tray_image():
    icon_path = get_resource_path("app_icon.ico")
    if os.path.exists(icon_path):
        try:
            return Image.open(icon_path)
        except Exception:
            pass
    img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(2, 132, 199, 255), outline=(56, 189, 248, 255), width=4)
    draw.rectangle((20, 24, 44, 40), fill=(255, 255, 255, 255))
    return img

def is_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, REG_APP_NAME)
        winreg.CloseKey(key)
        return bool(value)
    except Exception:
        return False

def sync_autostart_path():
    """If auto-start is enabled in registry, update the registered path to the current exe location."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_ALL_ACCESS)
        try:
            value, _ = winreg.QueryValueEx(key, REG_APP_NAME)
        except Exception:
            value = None

        if value:
            exe_path = f'"{os.path.abspath(sys.executable)}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            if value != exe_path:
                winreg.SetValueEx(key, REG_APP_NAME, 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
    except Exception:
        pass

def acquire_single_instance():
    """Returns (is_first_instance, event_handle). A later launch wakes the first instance and gets (False, None)."""
    handle = kernel32.CreateEventW(None, False, False, SHOW_WINDOW_EVENT)
    if not handle:
        return True, None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.SetEvent(handle)
        kernel32.CloseHandle(handle)
        return False, None
    return True, handle

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def write_shortcut(shortcut_path, target_path):
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
        "$s.TargetPath = '{exe}'; $s.WorkingDirectory = '{cwd}'; $s.IconLocation = '{exe},0'; "
        "$s.Description = 'AC Notification PC Server Manager'; $s.Save()"
    ).format(
        lnk=shortcut_path.replace("'", "''"),
        exe=target_path.replace("'", "''"),
        cwd=os.path.dirname(target_path).replace("'", "''"),
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW
    )
    return result.returncode == 0

def sync_start_menu_shortcut():
    """Point the Start Menu entry at this exe so Windows Search launches the current install."""
    if not getattr(sys, 'frozen', False):
        return
    try:
        os.makedirs(os.path.dirname(START_MENU_SHORTCUT), exist_ok=True)
        write_shortcut(START_MENU_SHORTCUT, os.path.abspath(sys.executable))
    except Exception:
        pass

class ACServerManagerGUI:
    def __init__(self, root, instance_event=None):
        self.root = root
        self.instance_event = instance_event
        self.root.title("AC Notification — PC Server Manager")
        self.root.geometry("640x720")
        self.root.minsize(580, 660)
        self.root.configure(bg=COLOR_CANVAS)

        # Apply Official App Icon to Window Titlebar & Taskbar
        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self.server_thread = None
        self.is_running = False
        self.show_advanced = False
        self.tray_icon = None

        self.load_config_data()
        domain = self.config.get("ngrok_domain", "")
        self.public_url = f"https://{domain}/api/v1/ac/trigger" if domain else ""
        sync_autostart_path()
        threading.Thread(target=sync_start_menu_shortcut, daemon=True).start()
        self.build_ui()
        self.start_all_services()
        self.setup_tray_icon()
        self.poll_show_requests()

        # Hide to tray on startup if the setting is enabled
        if self.config.get("open_to_tray", False):
            self.root.after(0, self.hide_to_tray)

    def load_config_data(self):
        self.config = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config.update(json.load(f))
            except Exception:
                # Never overwrite a config file we failed to parse
                return

        # Every install gets its own random API key instead of a shared default
        if len(self.config.get("api_key", "")) < 16:
            self.config["api_key"] = secrets.token_urlsafe(32)
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)

    def save_config_data(self):
        try:
            if hasattr(self, "entry_ip"):
                api_key = self.entry_apikey.get().strip()
                if len(api_key) < 16:
                    messagebox.showerror("Error", "API Secret Key must be at least 16 characters.")
                    return
                self.config["ip"] = self.entry_ip.get().strip()
                self.config["device_id"] = self.entry_id.get().strip()
                self.config["token"] = self.entry_token.get().strip()
                self.config["key"] = self.entry_key.get().strip()
                self.config["api_key"] = api_key
                self.config["ngrok_domain"] = self.entry_ngrok.get().strip()

            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
            self.log("INFO", "config.json successfully saved!")
            messagebox.showinfo("Success", "Server configuration saved successfully!")
        except Exception as e:
            self.log("ERROR", f"Failed to save config: {e}")
            messagebox.showerror("Error", f"Failed to save config: {e}")

    def build_ui(self):
        # 🌌 High-Contrast Header Banner
        header_frame = tk.Frame(self.root, bg=COLOR_HEADER, padx=16, pady=12, relief="flat", borderwidth=0)
        header_frame.pack(fill="x", side="top")

        lbl_title = tk.Label(header_frame, text="❄️ AC Notification PC Server Control Center", bg=COLOR_HEADER, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 13, "bold"))
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(header_frame, text="Universal Midea/Electra Wi-Fi AC Gateway (PC must be on same Wi-Fi as AC)", bg=COLOR_HEADER, fg=COLOR_CYAN, font=("Segoe UI", 9))
        lbl_sub.pack(anchor="w", pady=(2, 0))

        self.status_lbl = tk.Label(header_frame, text="● SERVER ONLINE", bg=COLOR_HEADER, fg=COLOR_SUCCESS, font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(anchor="e", side="right")

        main_container = tk.Frame(self.root, bg=COLOR_CANVAS, padx=16, pady=8)
        main_container.pack(fill="both", expand=True)

        # ---------------- STEP 1: AC Wi-Fi Pairing ----------------
        group_step1 = tk.LabelFrame(main_container, text=" STEP 1: Connect to Air Conditioner ", bg=COLOR_CANVAS, fg=COLOR_CYAN, font=("Segoe UI", 10, "bold"), padx=12, pady=8, bd=1, relief="solid")
        group_step1.pack(fill="x", pady=5)

        tk.Label(group_step1, text="Connect PC and AC to the same Home Wi-Fi network (Subnet 10.0.0.x / 192.168.x):", bg=COLOR_CANVAS, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))

        btn_discover = tk.Button(group_step1, text="🔍 1. Auto-Discover Wi-Fi AC (1-Click Setup)", bg=COLOR_BUTTON_TEAL, fg="#FFFFFF", font=("Segoe UI", 9, "bold"), activebackground="#0f766e", activeforeground="#FFFFFF", command=self.discover_ac, cursor="hand2", relief="raised", bd=1)
        btn_discover.pack(fill="x", pady=2, ipady=3)

        self.lbl_ac_status = tk.Label(group_step1, text=f"✓ Configured AC IP: {self.config.get('ip', '10.0.0.5')}", bg=COLOR_CANVAS, fg=COLOR_SUCCESS, font=("Segoe UI", 9, "bold"))
        self.lbl_ac_status.pack(anchor="w", pady=(4, 2))

        # Advanced Settings Accordion Button
        btn_toggle_adv = tk.Button(group_step1, text="⚙️ Advanced Manual Settings (Click to expand)", bg=COLOR_HEADER, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 8), command=self.toggle_advanced_settings, cursor="hand2", bd=1, relief="solid")
        btn_toggle_adv.pack(anchor="w", pady=(2, 0))

        self.frame_advanced = tk.Frame(group_step1, bg=COLOR_CANVAS)
        # Hidden by default

        fields = [
            ("AC IP Address:", "entry_ip", self.config.get("ip", "")),
            ("Device ID:", "entry_id", self.config.get("device_id", "")),
            ("Auth Token:", "entry_token", self.config.get("token", "")),
            ("AES Key:", "entry_key", self.config.get("key", "")),
            ("API Secret Key:", "entry_apikey", self.config.get("api_key", "")),
            ("ngrok Domain:", "entry_ngrok", self.config.get("ngrok_domain", ""))
        ]

        for i, (label_text, attr_name, default_val) in enumerate(fields):
            tk.Label(self.frame_advanced, text=label_text, bg=COLOR_CANVAS, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 8)).grid(row=i, column=0, sticky="w", pady=1)
            entry = tk.Entry(self.frame_advanced, bg=COLOR_HEADER, fg=COLOR_TEXT_PRIMARY, font=("Consolas", 8), borderwidth=1, relief="solid")
            entry.insert(0, default_val)
            entry.grid(row=i, column=1, sticky="ew", pady=1, padx=(8, 0))
            setattr(self, attr_name, entry)

        btn_save = tk.Button(self.frame_advanced, text="💾 Save Settings", bg=COLOR_BUTTON_PRIMARY, fg="#FFFFFF", font=("Segoe UI", 8, "bold"), activebackground="#0369a1", activeforeground="#FFFFFF", command=self.save_config_data, cursor="hand2", bd=1)
        btn_save.grid(row=len(fields), column=1, sticky="e", pady=(4, 0))

        self.frame_advanced.columnconfigure(1, weight=1)

        # ---------------- STEP 2: Phone Pairing ----------------
        group_step2 = tk.LabelFrame(main_container, text=" STEP 2: Connect Phone App (Copy Pairings) ", bg=COLOR_CANVAS, fg=COLOR_CYAN, font=("Segoe UI", 10, "bold"), padx=12, pady=8, bd=1, relief="solid")
        group_step2.pack(fill="x", pady=5)

        tk.Label(group_step2, text="Open AC Notification on Android → Step 2 Wizard → Paste these 2 values:", bg=COLOR_CANVAS, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 4))

        tk.Label(group_step2, text="PUBLIC WEBHOOK ENDPOINT URL:", bg=COLOR_CANVAS, fg=COLOR_TEXT_MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.entry_url = tk.Entry(group_step2, bg=COLOR_HEADER, fg=COLOR_CYAN, font=("Consolas", 9, "bold"), borderwidth=1, relief="solid")
        self.entry_url.insert(0, self.public_url)
        self.entry_url.pack(fill="x", pady=(2, 6), ipady=2)

        btn_row = tk.Frame(group_step2, bg=COLOR_CANVAS)
        btn_row.pack(fill="x")

        btn_copy_url = tk.Button(btn_row, text="📋 2. Copy Webhook URL", bg=COLOR_BUTTON_PRIMARY, fg="#FFFFFF", font=("Segoe UI", 9, "bold"), activebackground="#0369a1", activeforeground="#FFFFFF", command=self.copy_url, cursor="hand2", relief="raised", bd=1)
        btn_copy_url.pack(side="left", fill="x", expand=True, padx=(0, 2), ipady=3)

        btn_copy_key = tk.Button(btn_row, text="🔑 Copy Key", bg=COLOR_BUTTON_SLATE, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 9, "bold"), activebackground="#475569", activeforeground="#FFFFFF", command=self.copy_key, cursor="hand2", relief="raised", bd=1)
        btn_copy_key.pack(side="left", fill="x", expand=True, padx=(2, 2), ipady=3)

        btn_open_audio = tk.Button(btn_row, text="📁 Sounds Folder", bg=COLOR_BUTTON_TEAL, fg="#FFFFFF", font=("Segoe UI", 9, "bold"), activebackground="#0f766e", activeforeground="#FFFFFF", command=self.open_audio_folder, cursor="hand2", relief="raised", bd=1)
        btn_open_audio.pack(side="right", fill="x", expand=True, padx=(2, 0), ipady=3)

        # ---------------- STEP 3: Auto-Start & Logs ----------------
        group_step3 = tk.LabelFrame(main_container, text=" STEP 3: Background Server & System Logs ", bg=COLOR_CANVAS, fg=COLOR_CYAN, font=("Segoe UI", 10, "bold"), padx=12, pady=6, bd=1, relief="solid")
        group_step3.pack(fill="both", expand=True, pady=5)

        log_btn_row = tk.Frame(group_step3, bg=COLOR_CANVAS)
        log_btn_row.pack(fill="x", pady=(0, 4))

        autostart_text = "✓ Windows Auto-Start: Enabled" if is_autostart_enabled() else "🚀 Enable Windows Auto-Start"
        autostart_bg = COLOR_BUTTON_TEAL if is_autostart_enabled() else COLOR_BUTTON_SLATE

        self.btn_autostart = tk.Button(log_btn_row, text=autostart_text, bg=autostart_bg, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 8, "bold"), command=self.toggle_autostart, cursor="hand2", bd=1)
        self.btn_autostart.pack(side="left", padx=(0, 4))

        open_to_tray_enabled = self.config.get("open_to_tray", False)
        open_to_tray_text = "🔲 Open to Tray: On" if open_to_tray_enabled else "🔲 Open to Tray: Off"
        open_to_tray_bg = COLOR_BUTTON_TEAL if open_to_tray_enabled else COLOR_BUTTON_SLATE

        btn_restart = tk.Button(log_btn_row, text="⚡ Restart Server Services", bg=COLOR_BUTTON_SLATE, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 8, "bold"), command=self.restart_all_services, cursor="hand2", bd=1)
        btn_restart.pack(side="right")

        window_btn_row = tk.Frame(group_step3, bg=COLOR_CANVAS)
        window_btn_row.pack(fill="x", pady=(0, 4))

        self.btn_open_to_tray = tk.Button(window_btn_row, text=open_to_tray_text, bg=open_to_tray_bg, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 8, "bold"), command=self.toggle_open_to_tray, cursor="hand2", bd=1)
        self.btn_open_to_tray.pack(side="left", padx=(0, 4))

        show_in_tray_enabled = self.config.get("show_in_tray", True)
        show_in_tray_text = "📌 Show in Tray: On" if show_in_tray_enabled else "📌 Show in Tray: Off"
        show_in_tray_bg = COLOR_BUTTON_TEAL if show_in_tray_enabled else COLOR_BUTTON_SLATE
        self.btn_show_in_tray = tk.Button(window_btn_row, text=show_in_tray_text, bg=show_in_tray_bg, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 8, "bold"), command=self.toggle_show_in_tray, cursor="hand2", bd=1)
        self.btn_show_in_tray.pack(side="left")

        btn_exit = tk.Button(window_btn_row, text="⏻ Exit Server", bg=COLOR_BUTTON_SLATE, fg=COLOR_TEXT_PRIMARY, font=("Segoe UI", 8, "bold"), command=self.confirm_exit, cursor="hand2", bd=1)
        btn_exit.pack(side="right")

        self.txt_log = scrolledtext.ScrolledText(group_step3, bg=COLOR_LOG_BG, fg=COLOR_CYAN, font=("Consolas", 8), height=7, borderwidth=1, relief="solid")
        self.txt_log.pack(fill="both", expand=True, pady=(2, 0))

    def setup_tray_icon(self):
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        if self.config.get("show_in_tray", True):
            self.start_tray_icon()

    def start_tray_icon(self):
        if self.tray_icon:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open Control Center", self.show_from_tray, default=True),
            pystray.MenuItem("📁 Open Sounds Folder", self.open_audio_folder),
            pystray.MenuItem("Server Status: ONLINE", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Server Completely", self.exit_app_completely)
        )
        self.tray_icon = pystray.Icon("ACNotificationServer", create_tray_image(), "AC Notification Server", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def stop_tray_icon(self):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

    def poll_show_requests(self):
        if self.instance_event and kernel32.WaitForSingleObject(self.instance_event, 0) == 0:
            self._deiconify_root()
            self.log("SYSTEM", "Control Center reopened by a new launch (the server keeps running as a single instance)")
        self.root.after(500, self.poll_show_requests)

    def open_audio_folder(self, icon=None, item=None):
        audio_dir = get_audio_dir()
        os.makedirs(audio_dir, exist_ok=True)
        os.makedirs(os.path.join(audio_dir, "users"), exist_ok=True)
        try:
            os.startfile(audio_dir)
            self.log("AUDIO", f"Opened sounds folder in Windows Explorer: {audio_dir}")
        except Exception as e:
            self.log("ERROR", f"Failed to open audio folder: {e}")

    def hide_to_tray(self):
        self.root.withdraw()
        if self.tray_icon:
            self.log("SYSTEM", "Control Center minimized to System Tray (Server continues running in background)")
        else:
            self.log("SYSTEM", "Control Center hidden (Server continues running; reopen it from Windows Search)")

    def show_from_tray(self, icon=None, item=None):
        self.root.after(0, self._deiconify_root)

    def _deiconify_root(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def confirm_exit(self):
        if messagebox.askyesno("Exit Server", "Stop the AC Notification Server?\n\nPhone and car control won't work until you start it again."):
            self.exit_app_completely()

    def exit_app_completely(self, icon=None, item=None):
        self.log("SYSTEM", "Shutting down AC Notification Server...")
        self.stop_tray_icon()
        # ngrok is a child process that would otherwise outlive the app and block the next launch's tunnel
        tunnel = sys.modules.get("start_tunnel")
        if tunnel is not None and getattr(tunnel, "proc", None):
            try:
                tunnel.proc.terminate()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def toggle_autostart(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_ALL_ACCESS)
            if is_autostart_enabled():
                winreg.DeleteValue(key, REG_APP_NAME)
                winreg.CloseKey(key)
                self.btn_autostart.config(text="🚀 Enable Windows Auto-Start", bg=COLOR_BUTTON_SLATE)
                messagebox.showinfo("Auto-Start Disabled", "AC Notification Server removed from Windows startup.")
                self.log("REGISTRY", "Windows Auto-Start disabled.")
            else:
                exe_path = f'"{os.path.abspath(sys.executable)}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
                winreg.SetValueEx(key, REG_APP_NAME, 0, winreg.REG_SZ, exe_path)
                winreg.CloseKey(key)
                self.btn_autostart.config(text="✓ Windows Auto-Start: Enabled", bg=COLOR_BUTTON_TEAL)
                messagebox.showinfo("Auto-Start Enabled", "AC Notification Server registered to start automatically on Windows boot!")
                self.log("REGISTRY", "Windows Auto-Start enabled successfully.")
        except Exception as e:
            messagebox.showerror("Auto-Start Error", f"Failed to modify Windows startup registry: {e}")
            self.log("ERROR", f"Auto-start registry error: {e}")

    def save_setting(self, key, value):
        """Persist one setting without overwriting values the server changed on disk (e.g. an auto-healed AC IP)."""
        on_disk = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                on_disk = json.load(f)
        on_disk[key] = value
        with open(CONFIG_FILE, "w") as f:
            json.dump(on_disk, f, indent=2)
        self.config[key] = value

    def toggle_open_to_tray(self):
        try:
            self.save_setting("open_to_tray", not self.config.get("open_to_tray", False))
        except Exception as e:
            self.log("ERROR", f"Failed to save open_to_tray setting: {e}")
            return
        if self.config["open_to_tray"]:
            self.btn_open_to_tray.config(text="🔲 Open to Tray: On", bg=COLOR_BUTTON_TEAL)
            self.log("SYSTEM", "Open to Tray enabled — app will start minimized to tray next launch.")
        else:
            self.btn_open_to_tray.config(text="🔲 Open to Tray: Off", bg=COLOR_BUTTON_SLATE)
            self.log("SYSTEM", "Open to Tray disabled — app will open normally next launch.")

    def toggle_show_in_tray(self):
        try:
            self.save_setting("show_in_tray", not self.config.get("show_in_tray", True))
        except Exception as e:
            self.log("ERROR", f"Failed to save show_in_tray setting: {e}")
            return
        if self.config["show_in_tray"]:
            self.start_tray_icon()
            self.btn_show_in_tray.config(text="📌 Show in Tray: On", bg=COLOR_BUTTON_TEAL)
            self.log("SYSTEM", "Tray icon shown.")
        else:
            self.stop_tray_icon()
            self.btn_show_in_tray.config(text="📌 Show in Tray: Off", bg=COLOR_BUTTON_SLATE)
            self.log("SYSTEM", "Tray icon hidden — closing this window keeps the server running; reopen it from Windows Search.")
            messagebox.showinfo("Tray Icon Hidden", "The server keeps running when you close this window.\n\nTo reopen it, search for \"AC Notification Server\" in Windows Search.")

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
                    self.log("DISCOVERY", f"Configured AC IP: {self.config.get('ip', '10.0.0.5')} ready.")
                    self.lbl_ac_status.config(text=f"✓ AC Configured at {self.config.get('ip', '10.0.0.5')}")
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
                app.run(host="0.0.0.0", port=SERVER_PORT, debug=False, use_reloader=False)
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
            self.log("WARNING", "ngrok tunnel online.")

        threading.Thread(target=poll_tunnel, daemon=True).start()

    def update_url_field(self, url):
        self.entry_url.delete(0, "end")
        self.entry_url.insert(0, url)

    def restart_all_services(self):
        self.log("SYSTEM", "Restarting server services...")
        self.start_all_services()
        messagebox.showinfo("Restarted", "Server services restarted successfully!")

if __name__ == "__main__":
    is_first_instance, instance_event = acquire_single_instance()
    if not is_first_instance:
        sys.exit(0)

    root = tk.Tk()
    if is_port_in_use(SERVER_PORT):
        # Builds before single-instance support don't create the event, so also refuse to start a second server on the port
        root.withdraw()
        messagebox.showwarning("Already Running", f"AC Notification Server is already running (port {SERVER_PORT} is in use).\n\nClose the other copy first, e.g. from its tray icon.")
        root.destroy()
        sys.exit(1)

    app = ACServerManagerGUI(root, instance_event)
    root.mainloop()

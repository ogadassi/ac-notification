import os
import sys
import json
import time
import socket
import threading
import subprocess
import traceback
import tkinter as tk
from tkinter import messagebox, scrolledtext
from PIL import Image
import pystray

# Setup path constants
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SERVER_DIR)

PORT_CONTROL = 23456
ICON_PATH = os.path.join(SERVER_DIR, "..", "ac-notification-app", "app", "src", "main", "res", "drawable", "ic_launcher_custom.png")
CONFIG_PATH = os.path.join(SERVER_DIR, "ac_tray_config.json")

# --- Persistent config ---
def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except:
        return {}

def save_config(data):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except:
        pass

config = load_config()
start_minimized = config.get("start_minimized", False)

# Error logging helper
def log_app_event(msg):
    try:
        with open("ac_tray_app.log", "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass

# Catch all uncaught exceptions
def handle_exception(exctype, value, tb):
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    log_app_event(f"Uncaught Exception:\n{err_msg}")
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = handle_exception

# State variables
server_proc = None
tunnel_proc = None
logs_lock = threading.Lock()
log_messages = []
current_webhook_url = "Starting..."
root = None
log_area = None
url_entry = None
tray_icon = None
icon_visible = True

# Function to read process output
def read_stream(stream, prefix):
    global current_webhook_url
    try:
        for line in iter(stream.readline, ''):
            clean_line = line.strip()
            if not clean_line:
                continue
            
            log_line = f"[{prefix}] {clean_line}\n"
            with logs_lock:
                log_messages.append(log_line)
                if len(log_messages) > 1000:
                    log_messages.pop(0)
            
            # Extract tunnel URL if printed
            if "EXTRACTED TUNNEL URL:" in clean_line:
                parts = clean_line.split("EXTRACTED TUNNEL URL:")
                if len(parts) > 1:
                    current_webhook_url = parts[1].replace("<<<", "").strip() + "/api/v1/ac/trigger"
    except Exception as e:
        with logs_lock:
            log_messages.append(f"[System Error] Error reading stream: {e}\n")

# File path constants for logs
MIDEA_LOG_PATH = os.path.join(SERVER_DIR, "midea_server.log")
TUNNEL_LOG_PATH = os.path.join(SERVER_DIR, "start_tunnel.log")

def is_port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except socket.error:
            return True

def tail_file(filepath, prefix):
    global current_webhook_url
    # Ensure file exists
    if not os.path.exists(filepath):
        try:
            open(filepath, "a").close()
        except:
            pass

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            # Read last 100 lines for historical logs
            lines = f.readlines()
            for line in lines[-100:]:
                clean_line = line.strip()
                if clean_line:
                    log_line = f"[{prefix}] {clean_line}\n"
                    with logs_lock:
                        log_messages.append(log_line)
                if "EXTRACTED TUNNEL URL:" in line:
                    parts = line.split("EXTRACTED TUNNEL URL:")
                    if len(parts) > 1:
                        current_webhook_url = parts[1].replace("<<<", "").strip() + "/api/v1/ac/trigger"

            # Tailing loop
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                clean_line = line.strip()
                if not clean_line:
                    continue
                log_line = f"[{prefix}] {clean_line}\n"
                with logs_lock:
                    log_messages.append(log_line)
                    if len(log_messages) > 1000:
                        log_messages.pop(0)
                if "EXTRACTED TUNNEL URL:" in clean_line:
                    parts = clean_line.split("EXTRACTED TUNNEL URL:")
                    if len(parts) > 1:
                        current_webhook_url = parts[1].replace("<<<", "").strip() + "/api/v1/ac/trigger"
    except Exception as e:
        with logs_lock:
            log_messages.append(f"[System Error] Error tailing {prefix} log: {e}\n")

# Start subprocesses
def start_subprocesses():
    global server_proc, tunnel_proc, current_webhook_url
    stop_subprocesses()
    current_webhook_url = "Starting..."
    
    if is_port_busy(3000):
        with logs_lock:
            log_messages.append("[System] Port 3000 is occupied. Connecting to existing background services...\n")
        # Tail log files instead of spawning new processes
        threading.Thread(target=tail_file, args=(MIDEA_LOG_PATH, "Flask"), daemon=True).start()
        threading.Thread(target=tail_file, args=(TUNNEL_LOG_PATH, "Tunnel"), daemon=True).start()
        return

    with logs_lock:
        log_messages.append("[System] Starting background services...\n")
        
    try:
        server_proc = subprocess.Popen(
            [sys.executable, "-u", "midea_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        threading.Thread(target=read_stream, args=(server_proc.stdout, "Flask"), daemon=True).start()
        
        tunnel_proc = subprocess.Popen(
            [sys.executable, "-u", "start_tunnel.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        threading.Thread(target=read_stream, args=(tunnel_proc.stdout, "Tunnel"), daemon=True).start()
    except Exception as e:
        with logs_lock:
            log_messages.append(f"[System Error] Failed to start services: {e}\n")

# Stop subprocesses
def stop_subprocesses():
    global server_proc, tunnel_proc
    if server_proc:
        try:
            server_proc.terminate()
        except:
            pass
        server_proc = None
    if tunnel_proc:
        try:
            tunnel_proc.terminate()
        except:
            pass
        tunnel_proc = None

# Thread-safe window show/hide triggers
def trigger_show_window():
    if root:
        root.after(0, show_window)

def show_window():
    global root
    if root:
        root.deiconify()
        root.lift()
        root.focus_force()

def hide_window():
    global root
    if root:
        root.withdraw()

def trigger_hide_window():
    if root:
        root.after(0, hide_window)

# System Tray Management
def load_icon_image():
    try:
        img = Image.open(ICON_PATH).convert("RGBA")
        datas = img.getdata()
        newData = []
        for item in datas:
            # If pixel is very close to black, make it transparent
            if item[0] < 35 and item[1] < 35 and item[2] < 35:
                newData.append((0, 0, 0, 0))
            else:
                newData.append(item)
        img.putdata(newData)
        
        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.ANTIALIAS
        return img.resize((32, 32), resample_filter)
    except Exception as e:
        log_app_event(f"Error loading custom icon: {e}")
        fallback = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(fallback)
        draw.ellipse([4, 4, 28, 28], fill="#4cd964")
        return fallback

def toggle_start_minimized(icon, item):
    global start_minimized, config
    start_minimized = not start_minimized
    config["start_minimized"] = start_minimized
    save_config(config)
    log_app_event(f"start_minimized set to {start_minimized}")

def on_tray_select(icon, item):
    val = str(item)
    if val == "Open Log Viewer":
        trigger_show_window()
    elif val == "Go Stealth (Hide Tray)":
        go_stealth()
    elif val == "Exit":
        shutdown_application()

def setup_tray_icon():
    global tray_icon, icon_visible
    try:
        image = load_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Open Log Viewer", on_tray_select, default=True),
            pystray.MenuItem(
                "Start minimized to tray",
                toggle_start_minimized,
                checked=lambda item: start_minimized
            ),
            pystray.MenuItem("Go Stealth (Hide Tray)", on_tray_select),
            pystray.MenuItem("Exit", on_tray_select)
        )
        tray_icon = pystray.Icon("ac_proximity", image, "AC Proximity Control", menu)
        icon_visible = True
        
        # Run pystray main loop in background thread
        threading.Thread(target=tray_icon.run, daemon=True).start()
        log_app_event("Tray icon initialized and thread started successfully.")
    except Exception as e:
        log_app_event(f"Failed to initialize tray icon: {e}")

def go_stealth():
    global tray_icon, icon_visible
    trigger_hide_window()
    if tray_icon and icon_visible:
        tray_icon.visible = False
        icon_visible = False
        log_app_event("Stealth mode activated - tray icon hidden.")

def restore_tray():
    global tray_icon, icon_visible
    if tray_icon:
        tray_icon.visible = True
        icon_visible = True
        trigger_show_window()
        log_app_event("Stealth mode deactivated - tray icon restored.")

def shutdown_application():
    log_app_event("Application shutting down.")
    stop_subprocesses()
    if tray_icon:
        tray_icon.stop()
    if root:
        root.after(0, root.quit)
    os._exit(0)

# Socket listener to detect second instance launch (Open from EXE)
def listen_for_second_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', PORT_CONTROL))
        s.listen(5)
    except:
        # Already running - signal first instance and exit
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', PORT_CONTROL))
            client.sendall(b"show")
            client.close()
        except:
            pass
        os._exit(0)

    while True:
        try:
            conn, addr = s.accept()
            msg = conn.recv(1024)
            if msg == b"show":
                # Restore tray and window
                restore_tray()
            conn.close()
        except:
            break

# Primary App Setup
if __name__ == "__main__":
    log_app_event("Application started.")
    
    # Single instance check
    threading.Thread(target=listen_for_second_instance, daemon=True).start()

    # Start Flask and Tunnel
    start_subprocesses()
    
    # Start System Tray Icon
    setup_tray_icon()
    
    # Create Tkinter GUI (on the main thread!)
    root = tk.Tk()
    root.title("AC Proximity Server Console")
    root.geometry("750x500")
    
    # Borderless Window configuration
    root.overrideredirect(True)
    root.configure(bg="#0c110c", highlightbackground="#4cd964", highlightcolor="#4cd964", highlightthickness=1)
    
    # Modern style variables
    bg_color = "#0c110c"
    surface_color = "#162217"
    accent_emerald = "#4cd964"
    accent_cyan = "#00f0ff"
    text_color = "#e0eae0"
    
    # Drag-to-move windows logic
    def start_drag(event):
        root._drag_x = event.x
        root._drag_y = event.y

    def drag(event):
        deltax = event.x - root._drag_x
        deltay = event.y - root._drag_y
        x = root.winfo_x() + deltax
        y = root.winfo_y() + deltay
        root.geometry(f"+{x}+{y}")
        
    # Custom Title Bar
    title_bar = tk.Frame(root, bg="#060906", height=32)
    title_bar.pack(fill=tk.X, side=tk.TOP)
    title_bar.pack_propagate(False)
    
    title_bar.bind("<Button-1>", start_drag)
    title_bar.bind("<B1-Motion>", drag)
    
    title_label = tk.Label(title_bar, text="❄  AC PROXIMITY CONTROL SYSTEM", font=("Segoe UI", 9, "bold"), fg=accent_emerald, bg="#060906")
    title_label.pack(side=tk.LEFT, padx=12)
    title_label.bind("<Button-1>", start_drag)
    title_label.bind("<B1-Motion>", drag)
    
    btn_close_title = tk.Button(title_bar, text="✕", font=("Segoe UI", 10), bg="#060906", fg="#8aa08a", activebackground="#ff3b30", activeforeground="#ffffff", bd=0, width=5, height=1, cursor="hand2", command=hide_window)
    btn_close_title.pack(side=tk.RIGHT, fill=tk.Y)
    
    btn_min_title = tk.Button(title_bar, text="—", font=("Segoe UI", 9), bg="#060906", fg="#8aa08a", activebackground=surface_color, activeforeground="#ffffff", bd=0, width=5, height=1, cursor="hand2", command=hide_window)
    btn_min_title.pack(side=tk.RIGHT, fill=tk.Y)

    # Webhook URL Label
    url_frame = tk.Frame(root, bg=bg_color)
    url_frame.pack(fill=tk.X, padx=15, pady=10)
    
    lbl = tk.Label(url_frame, text="Webhook Entry Endpoint:", font=("Segoe UI", 10, "bold"), fg=text_color, bg=bg_color)
    lbl.pack(side=tk.LEFT)
    
    url_entry = tk.Entry(url_frame, font=("Consolas", 10), bd=1, relief="flat", bg="#121b13", fg=accent_cyan, insertbackground=accent_cyan, width=45)
    url_entry.pack(side=tk.LEFT, padx=10)
    
    def copy_url():
        root.clipboard_clear()
        root.clipboard_append(url_entry.get())
        messagebox.showinfo("Copied", "Webhook URL copied to clipboard!")
        
    btn_copy = tk.Button(url_frame, text="Copy URL", font=("Segoe UI", 9, "bold"), bg=surface_color, fg=accent_emerald, activebackground=accent_emerald, activeforeground=bg_color, bd=0, padx=8, cursor="hand2", command=copy_url)
    btn_copy.pack(side=tk.RIGHT, padx=5)

    # Scrolled Text for Logs
    log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Consolas", 9), bg="#020402", fg="#a0bca0", insertbackground=accent_emerald, bd=0, highlightthickness=1, highlightcolor=accent_emerald, highlightbackground=surface_color)
    log_area.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

    # Actions panel
    btn_frame = tk.Frame(root, bg=bg_color)
    btn_frame.pack(fill=tk.X, padx=15, pady=15)

    def restart_services():
        start_subprocesses()
        log_area.insert(tk.END, "[System] Services restarting...\n")

    def force_ac_on():
        def run():
            try:
                # Use absolute path to resolve config.json correctly in all thread contexts
                config_json_path = os.path.join(SERVER_DIR, "config.json")
                try:
                    with open(config_json_path, "r") as f:
                        cfg = json.load(f)
                        api_key = cfg.get("api_key", "")
                except Exception as le:
                    log_app_event(f"Error loading config.json in force_ac_on: {le}")
                    
                import urllib.request
                import json
                
                url = "http://localhost:3000/api/v1/ac/trigger"
                payload = json.dumps({
                    "action": "ac_on",
                    "timestamp": int(time.time() * 1000)
                }).encode("utf-8")
                
                req = urllib.request.Request(url, data=payload, method="POST")
                req.add_header("Content-Type", "application/json")
                if api_key:
                    req.add_header("X-API-Key", api_key)
                    
                with urllib.request.urlopen(req, timeout=5) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    if response.status == 200 and res_body.get("success"):
                        log_area.insert(tk.END, "[Console Control] AC Cool On successfully triggered!\n")
                        log_area.see(tk.END)
                    else:
                        messagebox.showerror("Error", res_body.get("error", "Trigger failed."))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to connect to local server: {e}")
                
        threading.Thread(target=run, daemon=True).start()

    btn_trigger = tk.Button(btn_frame, text="❄ Force AC Cool On", font=("Segoe UI", 10, "bold"), bg=accent_emerald, fg=bg_color, activebackground=accent_cyan, activeforeground=bg_color, bd=0, padx=12, pady=5, cursor="hand2", command=force_ac_on)
    btn_trigger.pack(side=tk.LEFT, padx=5)

    btn_restart = tk.Button(btn_frame, text="⟳ Restart Services", font=("Segoe UI", 9, "bold"), bg=surface_color, fg=text_color, activebackground=accent_emerald, activeforeground=bg_color, bd=0, padx=10, pady=5, cursor="hand2", command=restart_services)
    btn_restart.pack(side=tk.LEFT, padx=5)
    
    btn_stealth = tk.Button(btn_frame, text="Go Stealth", font=("Segoe UI", 9, "bold"), bg=surface_color, fg=text_color, activebackground=accent_emerald, activeforeground=bg_color, bd=0, padx=10, pady=5, cursor="hand2", command=go_stealth)
    btn_stealth.pack(side=tk.LEFT, padx=5)
    
    btn_shutdown = tk.Button(btn_frame, text="Exit App", font=("Segoe UI", 9, "bold"), bg=surface_color, fg="#ff3b30", activebackground="#ff3b30", activeforeground=bg_color, bd=0, padx=10, pady=5, cursor="hand2", command=shutdown_application)
    btn_shutdown.pack(side=tk.RIGHT, padx=5)

    # Auto refresh log loop
    def refresh_logs():
        # Update URL
        url_entry.delete(0, tk.END)
        url_entry.insert(0, current_webhook_url)
        
        # Update Logs
        with logs_lock:
            current_len = log_area.get("1.0", tk.END).strip().splitlines()
            if len(log_messages) > len(current_len):
                log_area.delete("1.0", tk.END)
                log_area.insert(tk.END, "".join(log_messages))
                log_area.see(tk.END)
                
        root.after(1000, refresh_logs)

    # Intercept default close behavior to hide to tray instead of exiting
    root.protocol("WM_DELETE_WINDOW", hide_window)

    # Apply startup mode preference
    if start_minimized:
        root.withdraw()  # Start hidden in tray

    refresh_logs()
    
    # Start Tkinter main loop (blocks main thread securely)
    root.mainloop()

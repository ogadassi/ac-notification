# AC Proximity Alert & Control System

<p align="center">
  <img src="resources/app_icon.png" width="128" height="128" alt="AC Proximity Icon"/>
</p>

A location-aware, smart-home automation system designed to optimize comfort and energy. The project consists of a native Compose Android application that monitors a geofence around your home. When you cross the boundary from outside to inside, it triggers a system notification prompt to activate the AC. Tapping "YES" triggers a secure background webhook relayed through ngrok to a local Python Flask server, which controls the AC over LAN.

---

## 🛠 Project Architecture

The system operates across three nodes: the Android client, the ngrok cloud gateway, and the local PC server.

```mermaid
flowchart TD
    subgraph Phone Client (Android)
        A[MainActivity Compose UI] -->|Set Radius & Home Coordinates| B[Play Services Geofencing]
        B -->|Boundary ENTER transition event| C[GeofenceBroadcastReceiver]
        C -->|User clicks YES| D[ACActionReceiver Webhook Trigger]
        E[Simulation Broadcasts] -->|Skip GPS Checks| C
    end

    subgraph Cloud Gateway
        D -->|Secure HTTPS POST| F[ngrok Static Domain]
    end

    subgraph PC Home Server (Windows)
        F -->|Secure Relay| G[Flask REST API Server]
        H[Tkinter Tray App] -->|Management & Logs| G
        G -->|LAN Command decryption| I[Midea AC Unit]
    end
```

---

## 📋 Project Board & Mission Status
*This section serves as a structured status list designed for CRM scraping and JIRA integration.*

### 🟢 Completed Missions (Done)

#### 1. UI/UX Modernization & Layout Redesign
- **Emerald Dark-Mode Aesthetic**: Custom dark theme canvas (`#0C110C`) with surfaces (`#162217`) and active accents (`#4CD964`).
- **Interactive OpenStreetMap Overlay**: Embedded Leaflet.js map inside Compose to draw a dynamic, responsive geofence boundary circle in real-time as the slider values change.
- **Smart Autocomplete Geocoder**: Integrated the OSM Nominatim API with 600ms query debouncing to allow quick search-and-select coordinate matching.
- **Search-Integrated Current Location**: Added a compact **📍** icon button directly inside the search text field, replacing the large separate button at the bottom.
- **Explicit Apply Location Button**: Created an `Apply Location` action button that remains disabled unless the user has chosen a new location differing from the currently registered home coordinates.
- **Unified Permissions Board**: Moved the Battery Optimization Exemption into the main checklist alongside Location, Background Location, and Notifications, using clear status emojis (✅/❌) and action buttons.

#### 2. Geofence Logic & Transient Recovery
- **True Boundary Crossings**: Set geofence initial trigger parameter to `0` instead of `INITIAL_TRIGGER_ENTER`. The app will not alert immediately if monitoring is toggled on while the user is already inside the radius.
- **24/7 Monitoring**: Removed all hour, day, and weekday restrictions.
- **Transient GPS Recovery**: Added automated retry-with-backoff scheduling in `GeofenceManager` to retry up to 3 times (20s, 40s, 60s) on transient `GEOFENCE_NOT_AVAILABLE` errors (code 1000).
- **Anti-Jitter Cooldown**: Implemented a 30-minute block on repeat notifications.

#### 3. PC Server & Tunneling Stability
- **Windows System Tray App**: Low-overhead `pythonw.exe` app with stealth (hidden) mode and wake-on-re-run capabilities.
- **Single Instance Enforcement**: TCP socket listener on port 23456 prevents duplicate server runs.
- **Headless Process Log Correction**: Corrected background stdout print errors (`OSError: [Errno 22]`) by redirecting execution output to log files.

#### 4. Simulation & Diagnostic Testing Suite
- **Simulate Geofence Entry**: Triggered via UI button or shell command:
  ```bash
  adb shell am broadcast -a com.example.acnotification.ACTION_SIMULATE_GEOFENCE_ENTRY -p com.example.acnotification
  ```
- **Simulate YES click**: Triggered via shell command:
  ```bash
  adb shell am broadcast -a com.example.acnotification.ACTION_AC_YES -p com.example.acnotification
  ```

---

### 🟡 Future Missions (Backlog)

#### 1. Dual-AC Support (Multi-Room Coordination)
- Extend Flask API config to support registering and toggling multiple Midea/Electra AC devices simultaneously (e.g. Living Room + Bedroom).
- Update Android UI to show checkbox selectors to pick which rooms to target.

#### 2. Geofence Exit Turn-off Alerts (Energy Saver)
- Add monitoring for `GEOFENCE_TRANSITION_EXIT` transitions.
- If the user leaves the home radius, send a push notification asking: *"Still away? Want to turn off the AC?"* with a one-tap webhook callback.

#### 3. Secure Webhook Key Rotation
- Implement a rotating token mechanism instead of using a static header key.
- Store encrypted secrets inside the Android KeyStore API.

#### 4. Webhook Failure Notification Retries
- If the phone lacks internet connectivity or the ngrok tunnel returns a `500`/`404` error upon transition entry, cache the action and auto-retry as soon as network connectivity is restored.

---

## 🚀 Getting Started

### 1. Setup PC Server
1. Install Python 3.11+.
2. Install and configure ngrok:
   ```powershell
   winget install ngrok.ngrok
   ngrok config add-authtoken <YOUR_AUTH_TOKEN>
   ```
3. Reserve a permanent free static domain on your [ngrok Dashboard](https://dashboard.ngrok.com/domains).
4. Create a `config.json` inside the `midea-ac-server` directory:
   ```json
   {
     "ip": "YOUR_AC_LOCAL_IP",
     "device_id": "YOUR_MIDEA_DEVICE_ID",
     "token": "YOUR_MIDEA_DECRYPT_TOKEN",
     "key": "YOUR_MIDEA_DECRYPT_KEY",
     "api_key": "ac_secret_key_8497",
     "ngrok_domain": "your-assigned-domain.ngrok-free.dev"
   }
   ```
5. Run `start_ac_server.bat` to launch the background tray client.

### 2. Setup Android Client
1. Install `ac-proximity-app.apk` on your device.
2. Grant all permissions at the top of the app (Location, Background Location, Notifications, Battery Exemption).
3. Search for your home location in the autocomplete input, select a suggestion, and tap **Apply Location**. You can also tap **📍** inside the search bar to populate your current location before applying.
4. Set your geofence radius (e.g. 200 meters).
5. Enter your Webhook URL (`https://your-assigned-domain.ngrok-free.dev/api/v1/ac/trigger`) and your API Key.
6. Toggle **Monitoring Active** to ON.

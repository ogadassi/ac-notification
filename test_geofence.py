#!/usr/bin/env python3
"""
AC Proximity Geofence Diagnostic & Simulation Suite
=====================================================
Automates ADB commands to:
  1. Audit permissions on the connected device
  2. Simulate a smooth walking route into the geofence
  3. Check Doze mode and battery optimization state
  4. Stream diagnostic logcat in real-time

Usage:
  python test_geofence.py [--device <serial>] [--lat <home_lat>] [--lng <home_lng>] [--radius <meters>]
"""

import subprocess
import time
import math
import argparse
import sys
import threading

APP_PACKAGE = "com.example.acnotification"
LOG_TAG = "GeofenceReceiver|GeofenceManager|ACActionReceiver|GeofencingApi"

# ─── ADB Helper ──────────────────────────────────────────────────────────────

def adb(*args, device=None, capture=True):
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    cmd += list(args)
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.stdout.strip(), result.returncode
    else:
        subprocess.run(cmd, timeout=30)

def adb_shell(command, device=None):
    return adb("shell", command, device=device)

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ─── Step 1: Detect Device ───────────────────────────────────────────────────

def detect_device(preferred=None):
    out, _ = adb("devices")
    lines = [l for l in out.splitlines() if "\t" in l and "offline" not in l]
    if not lines:
        print("❌ No ADB devices connected. Start an emulator or connect a phone.")
        sys.exit(1)
    if preferred:
        serials = [l.split("\t")[0] for l in lines]
        if preferred in serials:
            return preferred
        print(f"⚠️ Device {preferred} not found. Using first available.")
    device = lines[0].split("\t")[0]
    print(f"✅ Using device: {device}")
    return device

# ─── Step 2: Permission Audit ────────────────────────────────────────────────

def audit_permissions(device):
    print_section("PERMISSION AUDIT")
    permissions = [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_BACKGROUND_LOCATION",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.RECEIVE_BOOT_COMPLETED",
    ]
    for perm in permissions:
        out, _ = adb_shell(f"dumpsys package {APP_PACKAGE} | grep '{perm}'", device=device)
        granted = "granted=true" in out
        status = "✅ GRANTED" if granted else "❌ DENIED"
        short = perm.replace("android.permission.", "")
        print(f"  {status}  {short}")
        if not granted and "BACKGROUND_LOCATION" in perm:
            print(f"           ⚠️  CRITICAL: Background geofencing will NOT work on Android 10+ without this")
            print(f"           FIX: adb shell pm grant {APP_PACKAGE} {perm}")

    # Grant background location automatically
    print("\n  Attempting to auto-grant ACCESS_BACKGROUND_LOCATION...")
    adb_shell(f"pm grant {APP_PACKAGE} android.permission.ACCESS_BACKGROUND_LOCATION", device=device)
    adb_shell(f"pm grant {APP_PACKAGE} android.permission.ACCESS_FINE_LOCATION", device=device)
    adb_shell(f"pm grant {APP_PACKAGE} android.permission.POST_NOTIFICATIONS", device=device)
    print("  ✅ Grants applied")

# ─── Step 3: Battery Optimization ───────────────────────────────────────────

def audit_battery(device):
    print_section("BATTERY OPTIMIZATION AUDIT")

    out, _ = adb_shell(f"dumpsys deviceidle | grep {APP_PACKAGE}", device=device)
    print(f"  Doze whitelist: {'✅ PRESENT' if APP_PACKAGE in out else '❌ NOT IN WHITELIST'}")

    out2, _ = adb_shell(f"dumpsys battery", device=device)
    plugged = any(f"powered: true" in l or "AC powered: true" in l or "USB powered: true" in l
                  for l in out2.splitlines())
    print(f"  Charging:       {'✅ YES (Doze won't activate)' if plugged else '⚠️  NO (device may Doze)'}")

    print("\n  Adding app to Doze/battery whitelist...")
    adb_shell(f"dumpsys deviceidle whitelist +{APP_PACKAGE}", device=device)
    print("  ✅ App whitelisted from Doze mode")

    out3, _ = adb_shell(f"cmd appops get {APP_PACKAGE} RUN_IN_BACKGROUND", device=device)
    print(f"  Background execution: {out3.strip() or 'N/A'}")

# ─── Step 4: Check Geofence Registration ─────────────────────────────────────

def audit_geofence_registration(device):
    print_section("GEOFENCE REGISTRATION AUDIT")
    out, _ = adb_shell("dumpsys activity service com.google.android.gms/.location.GeofencerService", device=device)
    if APP_PACKAGE in out:
        print(f"  ✅ App geofences ARE registered in Play Services")
        lines = [l for l in out.splitlines() if APP_PACKAGE in l or "HOME_GEOFENCE" in l or "radius" in l.lower()]
        for l in lines[:10]:
            print(f"    {l.strip()}")
    else:
        print(f"  ❌ App geofences NOT found in Play Services GeofencerService")
        print(f"     → The app may not have called addGeofences() yet, or Play Services rejected it")
        print(f"     → Open the app and toggle the Monitoring switch ON")

# ─── Step 5: Enable Diagnostic Mode ─────────────────────────────────────────

def enable_diagnostic_mode(device):
    print_section("ENABLING DIAGNOSTIC MODE")
    # Use shared preferences to signal diagnostic mode (bypass time/day filters)
    adb_shell(f'am broadcast -a {APP_PACKAGE}.DIAGNOSTIC_ON', device=device)
    print("  ✅ Diagnostic mode broadcast sent (bypasses time window and cooldown filters)")

# ─── Step 6: Smooth Location Simulation ──────────────────────────────────────

def simulate_route(device, home_lat, home_lng, radius_m):
    print_section("GEOFENCE ENTRY SIMULATION")

    # Start 500m outside the geofence boundary
    start_distance_m = radius_m + 500
    # Bearing: approach from due south (bearing 0° = north, 180° = south)
    bearing_rad = math.radians(0)  # approaching from south going north

    earth_radius = 6371000  # metres
    start_lat = home_lat - (start_distance_m / earth_radius) * (180 / math.pi)
    start_lng = home_lng
    end_lat = home_lat + (radius_m * 0.3 / earth_radius) * (180 / math.pi)
    end_lng = home_lng

    num_steps = 60
    speed_mps = 1.4  # ~5 km/h walking speed
    total_distance = start_distance_m + radius_m * 0.3
    step_distance = total_distance / num_steps
    step_delay = step_distance / speed_mps

    print(f"  Route: ({start_lat:.5f}, {start_lng:.5f}) → ({end_lat:.5f}, {end_lng:.5f})")
    print(f"  Distance: ~{total_distance:.0f}m total, {num_steps} steps, ~{step_delay:.1f}s per step")
    print(f"  Simulated speed: {speed_mps * 3.6:.1f} km/h (walking)")
    print(f"  Geofence boundary at: {start_distance_m - radius_m:.0f}m from start")
    print(f"  Expected trigger at: step ~{int(start_distance_m / step_distance)} of {num_steps}")
    print()

    geofence_cross_step = int(start_distance_m / step_distance)

    for i in range(num_steps + 1):
        frac = i / num_steps
        lat = start_lat + (end_lat - start_lat) * frac
        lng = start_lng + (end_lng - start_lng) * frac

        dist_from_home = math.sqrt((lat - home_lat)**2 + (lng - home_lng)**2) * 111320
        inside = dist_from_home <= radius_m
        boundary_marker = " ←── CROSSING GEOFENCE BOUNDARY" if i == geofence_cross_step else ""
        inside_marker = " [INSIDE]" if inside else " [outside]"

        print(f"  Step {i:3d}/{num_steps}  ({lat:.6f}, {lng:.6f})  dist={dist_from_home:6.1f}m{inside_marker}{boundary_marker}")

        adb_shell(f"geo fix {lng} {lat}", device=device)
        time.sleep(step_delay)

    print("\n  ✅ Route simulation complete")

# ─── Step 7: Logcat Streaming ────────────────────────────────────────────────

def stream_logcat(device, stop_event):
    """Stream filtered logcat in background thread."""
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    cmd += ["logcat", "-v", "time", "-s",
            "GeofenceReceiver:V", "GeofenceManager:V", "ACActionReceiver:V",
            "GeofencingApi:V", "LocationManager:W"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    print("\n  📡 Logcat stream active — watching for geofence events...\n")
    while not stop_event.is_set():
        line = proc.stdout.readline()
        if line:
            print(f"  [LOG] {line.rstrip()}")
    proc.terminate()

# ─── Step 8: Doze Simulation ────────────────────────────────────────────────

def simulate_doze(device):
    print_section("DOZE MODE SIMULATION")
    print("  Forcing Doze mode (device idle)...")
    adb_shell("dumpsys deviceidle force-idle deep", device=device)
    time.sleep(2)
    out, _ = adb_shell("dumpsys deviceidle", device=device)
    state_line = next((l for l in out.splitlines() if "mState=" in l), "")
    print(f"  Doze state: {state_line.strip()}")
    print("  Waiting 5s in Doze mode to observe any geofence suppression...")
    time.sleep(5)
    print("  Exiting Doze mode...")
    adb_shell("dumpsys deviceidle unforce", device=device)
    print("  ✅ Doze simulation complete")

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AC Proximity Geofence Diagnostic Suite")
    parser.add_argument("--device", default=None, help="ADB device serial")
    parser.add_argument("--lat", type=float, default=32.0684, help="Home latitude")
    parser.add_argument("--lng", type=float, default=34.8248, help="Home longitude")
    parser.add_argument("--radius", type=float, default=230, help="Geofence radius in metres")
    parser.add_argument("--skip-route", action="store_true", help="Skip location route simulation")
    parser.add_argument("--skip-doze", action="store_true", help="Skip Doze mode simulation")
    args = parser.parse_args()

    print("\n🔬 AC Proximity Geofence Diagnostic Suite")
    print(f"   Package:   {APP_PACKAGE}")
    print(f"   Home:      ({args.lat}, {args.lng})")
    print(f"   Radius:    {args.radius}m")

    device = detect_device(args.device)

    # Clear old logs
    adb("logcat", "-c", device=device)
    print("✅ Logcat cleared")

    # Start logcat stream in background
    stop_event = threading.Event()
    log_thread = threading.Thread(target=stream_logcat, args=(device, stop_event), daemon=True)
    log_thread.start()
    time.sleep(1)

    try:
        audit_permissions(device)
        audit_battery(device)
        audit_geofence_registration(device)

        if not args.skip_doze:
            simulate_doze(device)

        if not args.skip_route:
            print_section("STARTING ROUTE SIMULATION IN 5 SECONDS...")
            print("  Open Logcat or the app now to watch for the trigger.")
            time.sleep(5)
            simulate_route(device, args.lat, args.lng, args.radius)

        print_section("DIAGNOSTIC COMPLETE")
        print("  Review the logcat output above for:")
        print("  - ✅ 'Geofence registered successfully'")
        print("  - ✅ 'Geofence ENTER detected'")
        print("  - ✅ 'All guards passed — firing notification!'")
        print("  - ❌ Any GEOFENCE_NOT_AVAILABLE or permission errors")
        print("\n  Press Ctrl+C to stop logcat stream.")
        log_thread.join()

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    finally:
        stop_event.set()

if __name__ == "__main__":
    main()

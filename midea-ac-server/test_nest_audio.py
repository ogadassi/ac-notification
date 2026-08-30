#!/usr/bin/env python3
"""
Standalone Test Suite for Google Nest Audio Feedback (Mission 2).
Usage:
  python test_nest_audio.py               # Plays a random sound from static/audio/ (1.wav..7.wav)
  python test_nest_audio.py --sound 2.wav # Plays a specific sound
"""

import os
import sys
import time
import socket
import http.server
import threading
import json
import argparse
import logging

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from nest_broadcaster import NestAudioBroadcaster

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("TestNestAudio")


def run_standalone_test(sound_override=None):
    print("=" * 65)
    print(" 🚀 Mission 2: Google Nest Audio Feedback Test")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load config.json: {e}")

    config.setdefault("nest_device_name", "Home Nest")
    config.setdefault("nest_ip", "10.0.0.6")

    # Find free test port
    test_port = 8899
    for p in [8899, 8898, 8897, 8896, 8895]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', p)) != 0:
                test_port = p
                break

    broadcaster = NestAudioBroadcaster(config=config, base_dir=base_dir)
    broadcaster.server_port = test_port

    # 1. Local Network Information
    lan_ip = broadcaster.get_local_lan_ip()
    print(f"\n[1/4] Local Network Detection:")
    print(f"      • Host LAN IP       : {lan_ip}")
    print(f"      • Test Serving Port : {test_port}")
    print(f"      • Base Media URL    : http://{lan_ip}:{test_port}/")

    # 2. Start temporary HTTP server
    print(f"\n[2/4] Starting Local Test Media Server...")
    class StaticHandler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            rel = path.lstrip('/')
            return os.path.join(base_dir, rel)

        def log_message(self, format, *args):
            logger.debug(f"MediaServer: {format % args}")

    httpd = http.server.HTTPServer(('0.0.0.0', test_port), StaticHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"      ✔ Test HTTP Server active on port {test_port}")

    # 3. Audio Pool & Sound Selection
    print(f"\n[3/4] Audio Pool & Sound Selection:")
    broadcaster.ensure_audio_assets()
    pool = broadcaster.get_audio_pool()
    sound_name, sound_path, ctype, duration, _ = broadcaster.pick_sound(sound_override=sound_override)
    sound_size = os.path.getsize(sound_path) if os.path.exists(sound_path) else 0
    print(f"      • Available Pool    : {len(pool)} sounds ({', '.join(pool)})")
    print(f"      ✔ Selected Track    : '{sound_name}' ({sound_size} bytes, {duration:.2f}s, {ctype})")

    # 4. Device Connection & Streaming
    print(f"\n[4/4] Connecting & Streaming to Google Nest:")
    print(f"      • Target Device     : '{broadcaster.device_name}' (IP: {broadcaster.nest_ip})")

    t0 = time.time()
    cast = broadcaster.get_chromecast()
    conn_time = time.time() - t0

    if not cast:
        print("      ❌ Failed to connect to Google Nest speaker.")
        httpd.shutdown()
        return False

    print(f"      ✔ Connected in {conn_time:.2f}s! ({cast.model_name})")
    print(f"      ▶ Streaming '{sound_name}' now...")

    success = broadcaster.broadcast_ac_trigger(
        action="ac_on",
        target_temp=22.0,
        mode="Cool",
        sound_override=sound_name
    )

    time.sleep(0.5)
    httpd.shutdown()

    print("\n" + "=" * 65)
    if success:
        print(" 🎉 Test PASSED! Audio played on Google Nest speaker.")
        print("=" * 65)
        return True
    else:
        print(" ❌ Test failed.")
        print("=" * 65)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Nest Audio Feedback")
    parser.add_argument("--sound", help="Specific sound file (e.g. 1.wav, 2.wav)", default=None)
    args = parser.parse_args()

    result = run_standalone_test(sound_override=args.sound)
    sys.exit(0 if result else 1)
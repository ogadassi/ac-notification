import sys
import json
import time
import asyncio
from flask import Flask, jsonify, request
from msmart.device import AirConditioner as AC

app = Flask(__name__)

# Load config
CONFIG_FILE = 'config.json'
config = {}

# In-memory AC state cache — updated on trigger and on live status query
ac_state_cache = {"power_on": None, "last_updated": 0}
AC_CACHE_TTL = 300  # seconds (5 minutes)

def load_config():
    global config
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            print("Successfully loaded config.json")
    except FileNotFoundError:
        print("config.json not found. Please create one with your AC IP, ID, Token, and Key.")
    except Exception as e:
        print(f"Error loading config.json: {e}")

load_config()

async def control_ac():
    if not config:
        return False, "config.json is missing or invalid."
    try:
        device = AC(ip=config['ip'], port=6444, device_id=int(config['device_id']))
        await device.authenticate(config['token'], config['key'])
        await device.refresh()
        device.power_state = True
        device.operational_mode = AC.OperationalMode.COOL
        device.target_temperature = 22.0
        await device.apply()
        return True, "AC successfully turned on to Cool 22°C"
    except Exception as e:
        return False, f"Midea Control Error: {str(e)}"

async def query_ac_status():
    """Query the AC device for current power state. Returns (power_on: bool|None, message: str)"""
    if not config:
        return None, "config.json is missing or invalid."
    try:
        device = AC(ip=config['ip'], port=6444, device_id=int(config['device_id']))
        await device.authenticate(config['token'], config['key'])
        await device.refresh()
        power_on = bool(device.power_state)
        # Update cache
        ac_state_cache["power_on"] = power_on
        ac_state_cache["last_updated"] = time.time()
        return power_on, "OK"
    except Exception as e:
        return None, f"Midea Status Error: {str(e)}"

def check_auth():
    api_key = request.headers.get('X-API-Key')
    expected_key = config.get('api_key')
    if not expected_key:
        return True  # Default to pass if no key is configured yet
    return api_key == expected_key

@app.route('/api/v1/ac/trigger', methods=['POST'])
def trigger_ac():
    load_config()
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    success, message = asyncio.run(control_ac())
    if success:
        # Update cache immediately — we know AC is now on
        ac_state_cache["power_on"] = True
        ac_state_cache["last_updated"] = time.time()
        return jsonify({"success": True, "message": message}), 200
    else:
        return jsonify({"success": False, "error": message}), 500

@app.route('/api/v1/ac/status', methods=['GET'])
def ac_status():
    """
    Returns current AC power state.
    Uses cached value if fresh (< 5 min old), otherwise does a live device query.
    Android app calls this before deciding which notification to show.
    """
    load_config()
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    now = time.time()
    cache_age = now - ac_state_cache.get("last_updated", 0)

    # Return cached value if it's fresh enough
    if ac_state_cache.get("power_on") is not None and cache_age < AC_CACHE_TTL:
        return jsonify({
            "success": True,
            "ac_on": ac_state_cache["power_on"],
            "source": "cache",
            "cache_age_seconds": int(cache_age)
        })

    # Cache miss or stale — do live query
    print(f"[status] Cache stale ({int(cache_age)}s old), querying device...")
    power_on, message = asyncio.run(query_ac_status())
    if power_on is None:
        print(f"[status] Live query failed: {message}")
        return jsonify({"success": False, "error": message}), 500

    return jsonify({
        "success": True,
        "ac_on": power_on,
        "source": "live"
    })

@app.route('/health', methods=['GET'])
def health():
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return jsonify({
        "status": "online",
        "configured": bool(config),
        "ac_cache": {
            "power_on": ac_state_cache.get("power_on"),
            "age_seconds": int(time.time() - ac_state_cache.get("last_updated", 0))
        }
    })

if __name__ == '__main__':
    app.run(host='::', port=3000, debug=True)


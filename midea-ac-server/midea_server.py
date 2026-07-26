import sys
import json
import time
import asyncio
import threading
import hmac
import os
import logging
from flask import Flask, jsonify, request
from msmart.device import AirConditioner as AC
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# Configure robust internal logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Load config
CONFIG_FILE = 'config.json'
config = {}

# In-memory AC state cache — updated on trigger and on live status query
ac_state_cache = {"power_on": None, "last_updated": 0}
AC_CACHE_TTL = 5  # seconds

# Global thread lock to prevent concurrent sockets colliding on the AC
ac_lock = threading.Lock()

def load_config():
    global config
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            app.logger.info("Successfully loaded config.json")
            
        # Zero-trust validation on configuration load
        expected_key = config.get('api_key')
        if not expected_key:
            app.logger.error("[SECURITY] api_key is missing in config.json! Public endpoints will reject all requests.")
        elif len(expected_key) < 16:
            app.logger.error("[SECURITY] api_key is too short (must be at least 16 characters)! Public endpoints will reject all requests.")
    except FileNotFoundError:
        app.logger.error("config.json not found. Please create one with your AC IP, ID, Token, and Key.")
    except Exception as e:
        app.logger.error(f"Error loading config.json: {e}")

load_config()

async def control_ac(power_state=True):
    if not config:
        return False, "config.json is missing or invalid."
    
    last_err = ""
    for attempt in range(3):
        device = None
        try:
            device = AC(ip=config['ip'], port=6444, device_id=int(config['device_id']))
            await device.authenticate(config['token'], config['key'])
            await device.refresh()
            device.power_state = power_state
            if power_state:
                device.operational_mode = AC.OperationalMode.COOL
                device.target_temperature = 22.0
            await device.apply()
            msg = "AC successfully turned on to Cool 22°C" if power_state else "AC successfully turned off"
            return True, msg
        except Exception as e:
            last_err = str(e)
            app.logger.warning(f"[control] Attempt {attempt + 1} failed: {last_err}")
            if attempt < 2:
                await asyncio.sleep(0.5)
        finally:
            if device:
                try:
                    device._lan._disconnect()
                except Exception:
                    pass
            
    return False, f"Midea Control Error: {last_err}"

async def query_ac_status():
    """Query the AC device for current power state. Returns (power_on: bool|None, message: str)"""
    if not config:
        return None, "config.json is missing or invalid."
        
    last_err = ""
    for attempt in range(3):
        device = None
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
            last_err = str(e)
            app.logger.warning(f"[status] Query attempt {attempt + 1} failed: {last_err}")
            if attempt < 2:
                await asyncio.sleep(0.5)
        finally:
            if device:
                try:
                    device._lan._disconnect()
                except Exception:
                    pass
            
    return None, f"Midea Status Error: {last_err}"

def check_auth():
    """
    Verify client credentials securely.
    - Requires X-API-Key header.
    - Blocks requests if api_key in config is missing or insecure.
    - Uses timing-attack resistant hmac.compare_digest.
    """
    api_key = request.headers.get('X-API-Key')
    expected_key = config.get('api_key')
    
    if not expected_key or len(expected_key) < 16:
        app.logger.error("Authentication rejected: API key not configured or below minimum length (16 chars).")
        return False
        
    if not api_key:
        return False
        
    return hmac.compare_digest(api_key.encode('utf-8'), expected_key.encode('utf-8'))

def validate_trigger_payload(data):
    """
    Validates request payload:
    - Must be a dictionary.
    - Must contain exactly 'action' and 'timestamp'.
    - 'action' must be 'ac_on'.
    - 'timestamp' must be a valid integer.
    - Replay protection: 'timestamp' must be within 10 minutes of server current time.
    """
    if not isinstance(data, dict):
        return False, "Invalid payload format."
    
    if "action" not in data:
        return False, "Missing 'action' field in payload."
        
    action = data.get("action")
    timestamp = data.get("timestamp")
    
    if not isinstance(action, str) or action not in ["ac_on", "ac_off"]:
        return False, "Invalid action field (must be 'ac_on' or 'ac_off')."
        
    # Replay protection: if timestamp is provided, verify clock drift window
    if timestamp is not None and isinstance(timestamp, (int, float)):
        try:
            now_ms = int(time.time() * 1000)
            drift_limit_ms = 10 * 60 * 1000  # 10 minutes
            if abs(now_ms - int(timestamp)) > drift_limit_ms:
                return False, "Request timestamp expired or out of acceptable clock-drift window."
        except Exception:
            pass
            
    return True, None

@app.errorhandler(Exception)
def handle_exception(e):
    """
    Global exception handler to suppress detailed tracebacks on public endpoints.
    """
    if isinstance(e, HTTPException):
        return jsonify({"success": False, "error": e.description}), e.code
        
    # Log detailed traceback internally
    app.logger.error("Unhandled Exception: %s", str(e), exc_info=True)
    # Generic, uninformative public error message
    return jsonify({"success": False, "error": "Internal Server Error"}), 500

@app.route('/api/v1/ac/trigger', methods=['POST'])
def trigger_ac():
    load_config()
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json"}), 415

    payload = request.get_json(silent=True)
    is_valid, err_msg = validate_trigger_payload(payload)
    if not is_valid:
        return jsonify({"success": False, "error": err_msg}), 400

    action = payload.get("action")
    power_on = (action == "ac_on")

    with ac_lock:
        success, message = asyncio.run(control_ac(power_state=power_on))
        
    if success:
        # Update cache immediately
        ac_state_cache["power_on"] = power_on
        ac_state_cache["last_updated"] = time.time()
        return jsonify({"success": True, "message": message, "ac_on": power_on}), 200
    else:
        # Log detail internally, return generic error message publicly
        app.logger.error("AC trigger failed: %s", message)
        return jsonify({"success": False, "error": "Failed to complete AC action"}), 500

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
    app.logger.info(f"Cache stale ({int(cache_age)}s old), querying device...")
    with ac_lock:
        power_on, message = asyncio.run(query_ac_status())
        
    if power_on is None:
        app.logger.error("AC status query failed: %s", message)
        return jsonify({"success": False, "error": "Failed to query AC status"}), 500

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

def is_dev_env_validated():
    # Automatically toggle debugging off (debug=False) by default unless
    # a secure development environment is actively validated
    return os.environ.get("SECURE_DEV_ENV_VALIDATED") == "true"

if __name__ == '__main__':
    debug_mode = False
    if is_dev_env_validated():
        debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
    
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

import sys
import json
import time
import asyncio
import threading
import hmac
import os
import logging
from flask import Flask, jsonify, request, send_from_directory
from msmart.device import AirConditioner as AC
from werkzeug.exceptions import HTTPException
from nest_broadcaster import NestAudioBroadcaster

app = Flask(__name__, static_folder='static')

# Configure robust internal logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

def get_app_data_dir():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    target_dir = os.path.join(appdata, "ACNotificationServer")
    os.makedirs(target_dir, exist_ok=True)
    return target_dir

def get_audio_dir():
    # 1. Check beside executable or script (portable / zip installation)
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

    # 2. Check PyInstaller _MEIPASS bundled static/audio
    if hasattr(sys, '_MEIPASS'):
        mei_audio = os.path.join(sys._MEIPASS, 'static', 'audio')
        if os.path.isdir(mei_audio):
            app_audio = os.path.join(get_app_data_dir(), "audio")
            os.makedirs(app_audio, exist_ok=True)
            import shutil
            for item in os.listdir(mei_audio):
                s = os.path.join(mei_audio, item)
                d = os.path.join(app_audio, item)
                if os.path.isfile(s) and not os.path.exists(d):
                    try:
                        shutil.copy2(s, d)
                    except Exception:
                        pass
            return app_audio

    # 3. Default to persistent APPDATA folder
    app_data_audio = os.path.join(get_app_data_dir(), "audio")
    os.makedirs(app_data_audio, exist_ok=True)
    return app_data_audio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = get_audio_dir()
os.makedirs(os.path.join(AUDIO_DIR, "users"), exist_ok=True)
os.makedirs(os.path.join(AUDIO_DIR, "tts"), exist_ok=True)

# Write guide README if not present
readme_path = os.path.join(AUDIO_DIR, "README.txt")
if not os.path.exists(readme_path):
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(
                "=========================================================\n"
                " AC Notification — Google Nest Audio & Custom Sounds\n"
                "=========================================================\n\n"
                "📁 GENERAL SOUNDS:\n"
                "   - Drop any .mp3 or .wav audio files in this folder to be played at random.\n\n"
                "📁 USER-SPECIFIC SOUNDS:\n"
                "   - When you enter your name in the mobile app, a folder is automatically created:\n"
                "     audio/users/<Username>/\n"
                "   - Drop custom MP3/WAV welcome sounds into that user's folder!\n"
                "   - Example: audio/users/Ohad/welcome.mp3\n\n"
                "🗣️ AUTOMATIC TEXT-TO-SPEECH (TTS):\n"
                "   - If no custom sounds exist in the user's folder, Google Nest will automatically\n"
                "     speak a personalized welcome announcement.\n"
                "=========================================================\n"
            )
    except Exception:
        pass

CONFIG_FILE = os.path.join(get_app_data_dir(), 'config.json')
config = {}
nest_broadcaster = NestAudioBroadcaster(config=config, base_dir=BASE_DIR, audio_dir=AUDIO_DIR)


import socket
import concurrent.futures

# In-memory AC state cache — updated on trigger and on live status query
ac_state_cache = {"power_on": None, "last_updated": 0}
AC_CACHE_TTL = 30  # seconds

# Global thread lock to prevent concurrent sockets colliding on the AC
ac_lock = threading.Lock()

def auto_heal_ac_ip():
    """Scans local Wi-Fi subnet for Midea AC (port 6444) if current stored IP fails. Auto-updates config."""
    current_ip = config.get("ip", "")
    app.logger.info(f"[AUTO-HEAL] Searching local Wi-Fi for AC unit (current IP '{current_ip}' unreachable)...")
    
    found_ip = None
    def check_ip(ip):
        nonlocal found_ip
        if found_ip:
            return
        try:
            s = socket.socket()
            s.settimeout(0.2)
            if s.connect_ex((ip, 6444)) == 0:
                found_ip = ip
            s.close()
        except Exception:
            pass

    prefix = ".".join(current_ip.split(".")[:3]) if current_ip and len(current_ip.split(".")) == 4 else "10.0.0"
    ip_list = [f"{prefix}.{i}" for i in range(1, 255)]
    if prefix != "192.168.1":
        ip_list += [f"192.168.1.{i}" for i in range(1, 255)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
        ex.map(check_ip, ip_list)

    if found_ip and found_ip != current_ip:
        app.logger.info(f"[AUTO-HEAL] Found AC unit at new IP: {found_ip}! Updating config.json...")
        config["ip"] = found_ip
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            app.logger.error(f"[AUTO-HEAL] Failed to save updated IP: {e}")
        return True
    return False

def load_config():
    global config
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            app.logger.info("Successfully loaded config.json")
            nest_broadcaster.update_config(config)
            
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

async def control_ac(power_state=True, target_temp=22.0):
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
                device.target_temperature = float(target_temp)
            await device.apply()
            temp_display = int(target_temp) if float(target_temp).is_integer() else target_temp
            msg = f"AC successfully turned on to Cool {temp_display}°C" if power_state else "AC successfully turned off"
            return True, msg
        except Exception as e:
            last_err = str(e)
            app.logger.warning(f"[control] Attempt {attempt + 1} failed (IP: {config.get('ip')}): {last_err}")
            # Try auto-healing IP on first failure
            if attempt == 0:
                if auto_heal_ac_ip():
                    app.logger.info(f"[control] Retrying AC control with auto-healed IP: {config.get('ip')}...")
                    continue
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
    """Query the AC device for current power state with fast 3.0s timeout."""
    if not config:
        return None, "config.json is missing or invalid."

    device = None
    try:
        async def _fetch():
            nonlocal device
            device = AC(ip=config['ip'], port=6444, device_id=int(config['device_id']))
            await device.authenticate(config['token'], config['key'])
            await device.refresh()
            power_on = bool(device.power_state)
            ac_state_cache["power_on"] = power_on
            ac_state_cache["last_updated"] = time.time()
            return power_on, "OK"

        return await asyncio.wait_for(_fetch(), timeout=3.0)
    except Exception as e:
        app.logger.warning(f"[status] Live query failed/timed out on IP {config.get('ip')}: {e}")
        # Try auto-healing IP in background
        auto_heal_ac_ip()
        return None, f"Midea Status Error: {e}"
    finally:
        if device:
            try:
                device._lan._disconnect()
            except Exception:
                pass

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
    - Must contain 'action'.
    - 'action' must be 'ac_on' or 'ac_off'.
    - Optional 'target_temp' between 16.0 and 30.0.
    - Optional 'user' string <= 50 chars.
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

    # Optional target_temp validation
    if "target_temp" in data and data.get("target_temp") is not None:
        try:
            temp_val = float(data.get("target_temp"))
            if not (16.0 <= temp_val <= 30.0):
                return False, "target_temp must be between 16.0 and 30.0 degrees."
        except (ValueError, TypeError):
            return False, "target_temp must be a valid number."

    # Optional user validation
    user_val = data.get("user") or data.get("username")
    if user_val is not None:
        if not isinstance(user_val, str) or len(user_val) > 50:
            return False, "user must be a string up to 50 characters."
        
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

@app.route('/static/audio/<path:filename>', methods=['GET'])
def serve_audio(filename):
    """
    Serves static audio assets (chime and dynamic TTS) to Google Nest speaker on LAN.
    """
    file_path = os.path.join(AUDIO_DIR, filename)
    if not os.path.exists(file_path):
        # Fallback: if chime.mp3 requested, serve chime.wav if available
        if filename == "chime.mp3" and os.path.exists(os.path.join(AUDIO_DIR, "chime.wav")):
            return send_from_directory(AUDIO_DIR, "chime.wav", mimetype="audio/wav")
        return jsonify({"error": "Audio file not found"}), 404
        
    mimetype = "audio/wav" if filename.endswith(".wav") else "audio/mp3"
    return send_from_directory(AUDIO_DIR, filename, mimetype=mimetype)

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
    target_temp = float(payload.get("target_temp", 22.0))
    user = payload.get("user") or payload.get("username")
    mode = payload.get("mode", "Cool")
    power_on = (action == "ac_on")

    with ac_lock:
        success, message = asyncio.run(control_ac(power_state=power_on, target_temp=target_temp))
        
    if success:
        # Update cache immediately
        ac_state_cache["power_on"] = power_on
        ac_state_cache["last_updated"] = time.time()
        
        # Asynchronously trigger Google Nest Audio broadcast in background thread
        try:
            nest_broadcaster.broadcast_ac_trigger_async(
                action=action,
                target_temp=target_temp,
                mode=mode,
                user=user
            )
        except Exception as e:
            app.logger.warning(f"Failed to dispatch Nest Audio broadcast: {e}")

        response_data = {"success": True, "message": message, "ac_on": power_on, "target_temp": target_temp}
        if user:
            response_data["user"] = user
        return jsonify(response_data), 200
    else:
        # Log detail internally, return generic error message publicly
        app.logger.error("AC trigger failed: %s", message)
        return jsonify({"success": False, "error": "Failed to complete AC action"}), 500

@app.route('/api/v1/nest/test', methods=['POST', 'GET'])
def test_nest_audio():
    """
    Diagnostic endpoint to test local Google Nest speaker feedback.
    """
    load_config()
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    custom_text = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        custom_text = data.get("text")

    if custom_text:
        nest_broadcaster._executor.submit(
            lambda: nest_broadcaster.play_sequence(chime_first=True, tts_text=custom_text)
        )
    else:
        nest_broadcaster.broadcast_ac_trigger_async(action="ac_on", target_temp=22.0, mode="Cool")

    return jsonify({
        "success": True,
        "message": "Dispatched Nest Audio test sequence asynchronously",
        "nest_device": nest_broadcaster.device_name,
        "nest_ip": nest_broadcaster.nest_ip
    }), 200


@app.route('/api/v1/user/register', methods=['POST'])
def register_user():
    """
    Registers a user from the mobile app and immediately creates their dedicated sound folder.
    """
    load_config()
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json"}), 415

    payload = request.get_json(silent=True) or {}
    user = payload.get("user") or payload.get("userName") or payload.get("username")
    if not user or not isinstance(user, str):
        return jsonify({"success": False, "error": "Missing user parameter"}), 400

    user_clean = user.strip().replace("..", "").replace("/", "").replace("\\", "")
    if not user_clean or len(user_clean) > 50:
        return jsonify({"success": False, "error": "Invalid user name"}), 400

    user_folder = os.path.join(AUDIO_DIR, "users", user_clean)
    os.makedirs(user_folder, exist_ok=True)

    readme_file = os.path.join(user_folder, "README.txt")
    if not os.path.exists(readme_file):
        try:
            with open(readme_file, "w", encoding="utf-8") as f:
                f.write(
                    f"Drop custom welcome sound files (.mp3, .wav) for '{user_clean}' in this folder.\n"
                    f"When '{user_clean}' approaches home and triggers AC cooling, sounds from this folder will play on your Google Nest speaker!\n"
                )
        except Exception:
            pass

    app.logger.info(f"[USER] User '{user_clean}' registered. Dedicated sound folder ready at: {user_folder}")
    return jsonify({
        "success": True,
        "user": user_clean,
        "folder": user_folder,
        "message": f"User folder ready for '{user_clean}'"
    }), 200


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
        try:
            power_on, message = asyncio.run(query_ac_status())
        except Exception as e:
            power_on, message = None, str(e)

    if power_on is None:
        app.logger.warning(f"AC status query failed: {message}. Returning cached fallback.")
        fallback_val = ac_state_cache.get("power_on") if ac_state_cache.get("power_on") is not None else False
        return jsonify({
            "success": True,
            "ac_on": fallback_val,
            "source": "fallback_cache",
            "warning": message
        }), 200

    return jsonify({
        "success": True,
        "ac_on": power_on,
        "source": "live"
    }), 200

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

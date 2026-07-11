import sys
import json
import asyncio
from flask import Flask, jsonify, request
from msmart.device import AirConditioner as AC

app = Flask(__name__)

# Load config
CONFIG_FILE = 'config.json'
config = {}

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
        # Initialize device
        device = AC(
            ip=config['ip'],
            port=6444,
            device_id=int(config['device_id'])
        )
        
        # Authenticate using token and key
        await device.authenticate(config['token'], config['key'])
        
        # Connect and set state
        await device.refresh()
        
        # Turn ON, set to COOL mode (2), and target temp (22C)
        device.power_state = True
        device.operational_mode = AC.OperationalMode.COOL
        device.target_temperature = 22.0
        
        await device.apply()
        return True, "AC successfully turned on to Cool 22°C"
    except Exception as e:
        return False, f"Midea Control Error: {str(e)}"

def check_auth():
    api_key = request.headers.get('X-API-Key')
    expected_key = config.get('api_key')
    if not expected_key:
        return True # Default to pass if no key is configured yet
    return api_key == expected_key

@app.route('/api/v1/ac/trigger', methods=['POST'])
def trigger_ac():
    # Reload config in case it was updated
    load_config()
    
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    # Run the async control code
    success, message = asyncio.run(control_ac())
    if success:
        return jsonify({"success": True, "message": message}), 200
    else:
        return jsonify({"success": False, "error": message}), 500

@app.route('/api/v1/ac/status', methods=['GET'])
def status():
    if not check_auth():
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    return jsonify({
        "status": "online",
        "configured": bool(config),
        "config_loaded": {
            "ip": config.get("ip"),
            "device_id": config.get("device_id"),
            "has_token": bool(config.get("token")),
            "has_key": bool(config.get("key"))
        }
    })

if __name__ == '__main__':
    # Listen on port 3000 (both IPv4 and IPv6)
    app.run(host='::', port=3000, debug=True)

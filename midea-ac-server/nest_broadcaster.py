import os
import sys
import time
import math
import wave
import struct
import socket
import logging
import threading
import uuid
import random
from concurrent.futures import ThreadPoolExecutor

import pychromecast
from gtts import gTTS

logger = logging.getLogger("NestAudioBroadcaster")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s [NestAudio] %(levelname)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def get_audio_file_duration(file_path: str) -> float:
    """Accurately calculates audio file duration for both float32 and int16 WAV files."""
    if not os.path.exists(file_path):
        return 3.0
    if file_path.endswith('.wav'):
        try:
            from scipy.io import wavfile
            rate, data = wavfile.read(file_path)
            return max(0.5, len(data) / float(rate))
        except Exception:
            try:
                with wave.open(file_path, 'rb') as wf:
                    return max(0.5, wf.getnframes() / float(wf.getframerate()))
            except Exception:
                pass
    return 3.5


def sanitize_wav_files(audio_dir: str):
    """
    Checks all WAV files in audio_dir to ensure:
    1. They are encoded as standard 16-bit PCM integer WAV for Google Cast hardware.
    2. Quiet voice recordings are automatically normalized and boosted to studio volume (~30,000 peak).
    """
    try:
        from scipy.io import wavfile
        import numpy as np
        for f in os.listdir(audio_dir):
            if f.endswith('.wav'):
                p = os.path.join(audio_dir, f)
                try:
                    rate, data = wavfile.read(p)
                    needs_rewrite = False
                    data_float = data.astype(np.float64)

                    max_val = np.max(np.abs(data_float))
                    if data.dtype in (np.float32, np.float64):
                        needs_rewrite = True
                        if max_val > 0:
                            normalized = data_float / max_val
                            data_out = (normalized * 30000.0).astype(np.int16)
                        else:
                            data_out = data_float.astype(np.int16)
                    elif max_val < 20000.0 and max_val > 0:
                        needs_rewrite = True
                        gain = 30000.0 / max_val
                        data_out = np.clip(data_float * gain, -32768, 32767).astype(np.int16)
                        logger.info(f"Auto-boosted quiet recording {f} by {gain:.1f}x to studio volume")
                    else:
                        data_out = data

                    if needs_rewrite:
                        wavfile.write(p, rate, data_out)
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"WAV sanitization exception: {e}")


class NestAudioBroadcaster:
    """
    Handles local Google Nest speaker discovery, connection caching,
    random sound pool playback, static media streaming, and asynchronous execution.
    """

    def __init__(self, config=None, base_dir=None):
        self.config = config or {}
        if base_dir is None:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.base_dir = base_dir

        self.static_dir = os.path.join(self.base_dir, "static")
        self.audio_dir = os.path.join(self.static_dir, "audio")
        self.tts_dir = os.path.join(self.audio_dir, "tts")
        os.makedirs(self.tts_dir, exist_ok=True)

        self.ensure_audio_assets()

        # Configuration
        self.device_name = self.config.get("nest_device_name", "Home Nest")
        self.nest_ip = self.config.get("nest_ip", "10.0.0.6")
        self.enabled = self.config.get("nest_audio_enabled", True)
        self.server_port = int(self.config.get("server_port", 3000))
        self.server_lan_ip = self.config.get("server_lan_ip", "")

        # Cached connection
        self._cast = None
        self._cast_lock = threading.Lock()

        # Background worker
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="NestAudioWorker")
        self._cleanup_stale_tts_files()

    def update_config(self, config: dict):
        """Update runtime configuration parameters."""
        if not isinstance(config, dict):
            return
        self.config = config
        self.device_name = config.get("nest_device_name", self.device_name)
        self.nest_ip = config.get("nest_ip", self.nest_ip)
        self.enabled = config.get("nest_audio_enabled", self.enabled)
        self.server_port = int(config.get("server_port", self.server_port))
        self.server_lan_ip = config.get("server_lan_ip", self.server_lan_ip)

    def get_local_lan_ip(self) -> str:
        """Determines the local IPv4 address reachable on the home network."""
        if self.server_lan_ip:
            return self.server_lan_ip

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"

    def ensure_audio_assets(self):
        """Ensures quiet/float32 WAV recordings in static/audio are converted to loud 16-bit PCM."""
        sanitize_wav_files(self.audio_dir)

    def get_audio_pool(self) -> list[str]:
        """
        Discovers available audio recordings in static/audio/.
        Returns list of filenames (e.g. ['1.wav', '2.wav', ..., '7.wav']).
        """
        if not os.path.exists(self.audio_dir):
            return []
        return [
            f for f in sorted(os.listdir(self.audio_dir))
            if f.endswith((".wav", ".mp3", ".ogg", ".flac"))
        ]

    def pick_sound(self, sound_override: str = None, user: str = None) -> tuple[str, str, str, float, bool]:
        """
        Picks a sound track:
        1. Explicit sound_override if requested.
        2. User-specific audio recording/folder if 'user' is specified (e.g. static/audio/users/<user>/ or static/audio/<user>.wav).
        3. Random sound from the general audio pool.
        Returns: (filename, full_file_path, content_type, duration_sec, is_custom_recording)
        """
        chosen_relative = None

        # 1. Check sound override
        if sound_override and os.path.exists(os.path.join(self.audio_dir, sound_override)):
            chosen_relative = sound_override

        # 2. Check user-specific audio folder or file
        if not chosen_relative and user:
            user_clean = user.strip().replace("..", "")
            user_candidates = [
                os.path.join("users", user_clean),
                user_clean
            ]
            for candidate in user_candidates:
                candidate_dir = os.path.join(self.audio_dir, candidate)
                if os.path.isdir(candidate_dir):
                    user_pool = [
                        f for f in sorted(os.listdir(candidate_dir))
                        if f.endswith((".wav", ".mp3", ".ogg", ".flac"))
                    ]
                    if user_pool:
                        chosen_relative = os.path.join(candidate, random.choice(user_pool)).replace("\\", "/")
                        logger.info(f"Picked user-specific sound from folder '{candidate}': {chosen_relative}")
                        break

                # Check if direct file like <user>.wav exists
                for ext in (".wav", ".mp3", ".ogg", ".flac"):
                    candidate_file = os.path.join(self.audio_dir, f"{candidate}{ext}")
                    if os.path.isfile(candidate_file):
                        chosen_relative = f"{candidate}{ext}".replace("\\", "/")
                        logger.info(f"Picked user-specific sound file: {chosen_relative}")
                        break
                if chosen_relative:
                    break

        # 3. Fallback to general pool
        if not chosen_relative:
            pool = self.get_audio_pool()
            if pool:
                chosen_relative = random.choice(pool)
            else:
                logger.warning("No audio files found in static/audio/")
                return "", "", "audio/wav", 0.0, False

        full_path = os.path.join(self.audio_dir, chosen_relative)
        content_type = "audio/wav" if chosen_relative.endswith(".wav") else "audio/mp3"
        duration = get_audio_file_duration(full_path)

        return chosen_relative, full_path, content_type, duration, True

    def _cleanup_stale_tts_files(self):
        try:
            for fname in os.listdir(self.tts_dir):
                if fname.endswith(".mp3") or fname.endswith(".wav"):
                    try:
                        os.remove(os.path.join(self.tts_dir, fname))
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"TTS sweep exception: {e}")

    def get_chromecast(self, force_refresh: bool = False):
        """
        Retrieves active cached Chromecast instance or connects to Google Nest speaker.
        """
        with self._cast_lock:
            if not force_refresh and self._cast is not None:
                try:
                    if self._cast.socket_client and self._cast.socket_client.is_connected:
                        return self._cast
                except Exception:
                    pass

            logger.info(f"Connecting to Google Nest speaker '{self.device_name}' (IP: {self.nest_ip})...")
            found_cast = None

            # Quick port 8009 reachability check
            ip_reachable = False
            if self.nest_ip:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.6)
                        if s.connect_ex((self.nest_ip, 8009)) == 0:
                            ip_reachable = True
                except Exception:
                    ip_reachable = False

            # Direct IP probe
            if ip_reachable:
                try:
                    casts, browser = pychromecast.get_listed_chromecasts(
                        friendly_names=[self.device_name] if self.device_name else None,
                        known_hosts=[self.nest_ip],
                        discovery_timeout=1.5
                    )
                    if hasattr(browser, "stop_discovery"):
                        browser.stop_discovery()
                    else:
                        pychromecast.discovery.stop_discovery(browser)
                    if casts:
                        found_cast = casts[0]
                except Exception as e:
                    logger.debug(f"Direct IP probe failed: {e}")

            # Friendly name discovery fallback
            if not found_cast and self.device_name:
                try:
                    logger.info(f"Scanning local subnet for Cast device '{self.device_name}'...")
                    casts, browser = pychromecast.get_listed_chromecasts(
                        friendly_names=[self.device_name],
                        discovery_timeout=3.0
                    )
                    if hasattr(browser, "stop_discovery"):
                        browser.stop_discovery()
                    else:
                        pychromecast.discovery.stop_discovery(browser)
                    if casts:
                        found_cast = casts[0]
                except Exception as e:
                    logger.debug(f"Friendly name discovery failed: {e}")

            if found_cast:
                try:
                    found_cast.wait(timeout=5.0)
                    self._cast = found_cast
                    self.nest_ip = found_cast.cast_info.host
                    logger.info(f"Connected successfully to {found_cast.name} ({found_cast.model_name}) at {self.nest_ip}")
                    return self._cast
                except Exception as e:
                    logger.warning(f"Failed to wait on Chromecast connection: {e}")

            logger.warning(f"Could not reach Google Nest speaker '{self.device_name}'")
            self._cast = None
            return None

    def _play_track_and_wait(self, mc, media_url: str, content_type: str, duration_estimate: float = 3.0):
        """
        Plays a single media item on the Chromecast and reliably waits
        for playback to complete.
        """
        logger.info(f"Playing media: {media_url} ({content_type}) [est. duration: {duration_estimate:.2f}s]")
        mc.play_media(media_url, content_type)
        mc.block_until_active(timeout=4.0)

        t_start = time.time()
        time.sleep(0.4)

        while (time.time() - t_start) < (duration_estimate + 0.4):
            mc.update_status()
            if (time.time() - t_start) >= (duration_estimate * 0.75):
                if mc.status.player_state == 'IDLE' and mc.status.idle_reason in ('FINISHED', 'CANCELLED', 'INTERRUPTED'):
                    break
            time.sleep(0.2)

    def play_sound_clip(self, sound_filename: str, content_type: str, duration: float) -> bool:
        """Plays a sound recording directly on the Google Nest speaker."""
        if not self.enabled:
            logger.info("Nest Audio feedback is disabled in config.")
            return False

        cast = self.get_chromecast()
        if not cast:
            logger.warning("Nest Audio playback skipped: speaker unreachable.")
            return False

        try:
            lan_ip = self.get_local_lan_ip()
            base_url = f"http://{lan_ip}:{self.server_port}"
            mc = cast.media_controller

            audio_url = f"{base_url}/static/audio/{sound_filename}"
            self._play_track_and_wait(mc, audio_url, content_type, duration_estimate=duration)
            logger.info(f"Sound clip '{sound_filename}' finished playing successfully.")
            return True
        except Exception as e:
            logger.error(f"Error playing sound clip '{sound_filename}': {e}", exc_info=True)
            return False

    def broadcast_ac_trigger(self, action: str = "ac_on", target_temp: float = 22.0, mode: str = "Cool", sound_override: str = None, user: str = None) -> bool:
        """
        Dispatches audio playback on AC trigger.
        Picks a user-specific sound or random sound from the audio pool and plays it directly.
        """
        sound_name, full_path, content_type, duration, _ = self.pick_sound(sound_override=sound_override, user=user)
        user_tag = f" (User: {user})" if user else ""
        logger.info(f"▶ AC Trigger{user_tag}: Playing recording '{sound_name}' ({duration:.2f}s, target: {target_temp}°C)")
        return self.play_sound_clip(sound_name, content_type, duration)

    def broadcast_ac_trigger_async(self, action: str = "ac_on", target_temp: float = 22.0, mode: str = "Cool", sound_override: str = None, user: str = None):
        """
        Asynchronous non-blocking trigger:
        Dispatches broadcast_ac_trigger into a background worker thread and returns immediately.
        """
        def _worker():
            try:
                self.broadcast_ac_trigger(action=action, target_temp=target_temp, mode=mode, sound_override=sound_override, user=user)
            except Exception as e:
                logger.error(f"Background Nest Audio worker exception: {e}")

        self._executor.submit(_worker)
        logger.info(f"Dispatched asynchronous Nest Audio broadcast for action='{action}', user='{user}'")

    def test_broadcast(self, sound_override: str = None) -> bool:
        """Standalone diagnostic test."""
        logger.info("=== Starting Nest Audio Standalone Diagnostic Test ===")
        lan_ip = self.get_local_lan_ip()
        pool = self.get_audio_pool()
        sound_name, full_path, content_type, duration, _ = self.pick_sound(sound_override=sound_override)

        logger.info(f"Server Local LAN IP  : {lan_ip}:{self.server_port}")
        logger.info(f"Target Nest Device   : '{self.device_name}' (IP: {self.nest_ip})")
        logger.info(f"Audio Pool Size      : {len(pool)} sounds ({pool})")
        logger.info(f"Selected Sound Track : '{sound_name}' ({duration:.2f}s, {content_type})")

        success = self.play_sound_clip(sound_name, content_type, duration)
        if success:
            logger.info("=== Nest Audio Diagnostic Test PASSED! ===")
        else:
            logger.error("=== Nest Audio Diagnostic Test FAILED! ===")
        return success


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    broadcaster = NestAudioBroadcaster()
    broadcaster.test_broadcast()
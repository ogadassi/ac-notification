#!/usr/bin/env python3
"""
Automated Unit Tests for NestAudioBroadcaster sound selection and chime logic.
"""

import array
import struct
import math
import os
import shutil
import tempfile
import unittest
import wave

import audio_loudness
from nest_broadcaster import (NestAudioBroadcaster, generate_default_chime_wav,
                              get_audio_file_duration, sanitize_wav_files)


class TestNestAudioBroadcaster(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory structure for audio files
        self.test_dir = tempfile.mkdtemp()
        self.audio_dir = os.path.join(self.test_dir, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)

        # Create dummy sound files
        for name in ["1.wav", "2.wav", "3.wav"]:
            generate_default_chime_wav(os.path.join(self.audio_dir, name))

        # Create a user specific folder with a sound
        user_folder = os.path.join(self.audio_dir, "users", "Ohad")
        os.makedirs(user_folder, exist_ok=True)
        generate_default_chime_wav(os.path.join(user_folder, "welcome.wav"))

        self.broadcaster = NestAudioBroadcaster(config={}, audio_dir=self.audio_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_chime_generation(self):
        chime_path = os.path.join(self.audio_dir, "test_chime.wav")
        generate_default_chime_wav(chime_path)
        self.assertTrue(os.path.exists(chime_path))
        with wave.open(chime_path, 'rb') as wf:
            # Stereo at the sound pool's rate, so the Cast device handles the chime
            # exactly like every other sound (a mono track is duplicated across both
            # output channels and plays ~3 dB hot against stereo files).
            self.assertEqual(wf.getnchannels(), 2)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
            self.assertEqual(wf.getframerate(), 48000)
            duration = wf.getnframes() / float(wf.getframerate())
            self.assertGreater(duration, 0.8)
            self.assertLess(duration, 2.0)

    def test_generated_chime_matches_pool_loudness(self):
        chime_path = os.path.join(self.audio_dir, "level_chime.wav")
        generate_default_chime_wav(chime_path)
        measured = audio_loudness.measure(chime_path)
        self.assertAlmostEqual(measured["lufs"], audio_loudness.TARGET_LUFS,
                               delta=audio_loudness.TOLERANCE_LU)
        self.assertLessEqual(measured["true_peak_db"],
                             audio_loudness.TRUE_PEAK_CEILING_DB + 0.05)

    def test_float32_wav_is_read_and_levelled(self):
        """
        32-bit float WAVs must be levelled like any other file.

        The stdlib wave module refuses them, and a recorder that writes float WAVs
        typically leaves them far below full scale -- exactly the files that most
        need levelling. Skipping them silently is what let one person's recordings
        sit ~15 dB below everyone else's.
        """
        path = os.path.join(self.audio_dir, "float_source.wav")
        rate, seconds, peak = 48000, 2.0, 0.02
        frames = int(rate * seconds)
        samples = array.array('f', [0.0]) * (frames * 2)
        for i in range(frames):
            value = peak * math.sin(2 * math.pi * 440.0 * i / rate)
            samples[2 * i] = value
            samples[2 * i + 1] = value
        payload = samples.tobytes()
        with open(path, 'wb') as handle:
            handle.write(b'RIFF' + (36 + len(payload)).to_bytes(4, 'little') + b'WAVE')
            handle.write(b'fmt ' + (16).to_bytes(4, 'little'))
            handle.write(struct.pack('<HHIIHH', 3, 2, rate, rate * 2 * 4, 8, 32))
            handle.write(b'data' + len(payload).to_bytes(4, 'little') + payload)

        source = audio_loudness.measure(path)
        self.assertIsNotNone(source, "float WAV could not be read")
        self.assertTrue(source["is_float"])
        self.assertLess(source["lufs"], audio_loudness.TARGET_LUFS - 5.0,
                        "test fixture should start well below target")

        audio_loudness.normalize_file(path)

        result = audio_loudness.measure(path)
        self.assertTrue(result["is_pcm16"], "should be rewritten as 16-bit PCM for Cast")
        self.assertAlmostEqual(result["lufs"], audio_loudness.TARGET_LUFS,
                               delta=audio_loudness.TOLERANCE_LU)

    def test_sanitize_matches_volume_across_pool_and_user_folders(self):
        """A hot file and a faint one must end up at the same perceived volume."""
        def tone(path, peak_db, channels=2, seconds=2.0, rate=48000):
            amplitude = 10.0 ** (peak_db / 20.0)
            frames = int(rate * seconds)
            flat = array.array('h', [0]) * (frames * channels)
            for i in range(frames):
                value = int(amplitude * 32767 * math.sin(2 * math.pi * 440.0 * i / rate))
                for c in range(channels):
                    flat[i * channels + c] = value
            with wave.open(path, 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                wf.writeframes(flat.tobytes())

        tone(os.path.join(self.audio_dir, "hot.wav"), -1.0)
        user_folder = os.path.join(self.audio_dir, "users", "Ohad")
        tone(os.path.join(user_folder, "faint.wav"), -35.0)
        tone(os.path.join(user_folder, "faint_mono.wav"), -30.0, channels=1)

        sanitize_wav_files(self.audio_dir)

        levels = []
        for root, _, files in os.walk(self.audio_dir):
            for name in files:
                if name.endswith(".wav"):
                    levels.append(audio_loudness.measure(os.path.join(root, name))["lufs"])
        self.assertGreaterEqual(len(levels), 5)
        self.assertLess(max(levels) - min(levels), 1.0,
                        "sounds still differ by an audible amount")

    def test_audio_pool_excludes_chime(self):
        # Ensure chime.wav is created
        self.broadcaster.ensure_audio_assets()
        pool = self.broadcaster.get_audio_pool()
        self.assertIn("1.wav", pool)
        self.assertIn("2.wav", pool)
        self.assertIn("3.wav", pool)
        self.assertNotIn("chime.wav", pool)
        self.assertNotIn("chime.mp3", pool)
        self.assertNotIn("off.wav", pool)

    def test_ac_off_plays_generic_chime_not_user_sound(self):
        self.broadcaster.ensure_audio_assets()
        # Even with user specified as "Ohad", ac_off must return chime.wav, not Ohad's sound
        sound_name, full_path, ctype, duration, is_custom = self.broadcaster.pick_sound(
            action="ac_off",
            user="Ohad"
        )
        self.assertEqual(sound_name, "chime.wav")
        self.assertTrue(os.path.exists(full_path))
        self.assertFalse(is_custom)

    def test_ac_on_plays_user_sound_when_present(self):
        self.broadcaster.ensure_audio_assets()
        sound_name, full_path, ctype, duration, is_custom = self.broadcaster.pick_sound(
            action="ac_on",
            user="Ohad"
        )
        self.assertIn("users/Ohad", sound_name.replace("\\", "/"))
        self.assertTrue(os.path.exists(full_path))
        self.assertTrue(is_custom)

    def test_ac_on_falls_back_to_general_pool_for_unknown_user(self):
        self.broadcaster.ensure_audio_assets()
        sound_name, full_path, ctype, duration, is_custom = self.broadcaster.pick_sound(
            action="ac_on",
            user="NonExistentUser"
        )
        self.assertIn(sound_name, ["1.wav", "2.wav", "3.wav"])
        self.assertTrue(os.path.exists(full_path))

    def test_sound_override(self):
        self.broadcaster.ensure_audio_assets()
        sound_name, full_path, ctype, duration, is_custom = self.broadcaster.pick_sound(
            sound_override="2.wav",
            action="ac_off",
            user="Ohad"
        )
        self.assertEqual(sound_name, "2.wav")


if __name__ == "__main__":
    unittest.main()

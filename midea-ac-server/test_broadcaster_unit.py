#!/usr/bin/env python3
"""
Automated Unit Tests for NestAudioBroadcaster sound selection and chime logic.
"""

import os
import shutil
import tempfile
import unittest
import wave

from nest_broadcaster import NestAudioBroadcaster, generate_default_chime_wav, get_audio_file_duration


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
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit
            self.assertEqual(wf.getframerate(), 44100)
            duration = wf.getnframes() / float(wf.getframerate())
            self.assertGreater(duration, 0.8)
            self.assertLess(duration, 2.0)

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

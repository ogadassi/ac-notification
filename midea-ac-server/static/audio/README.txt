=========================================================
 AC Notification — Google Nest Audio & Custom Sounds
=========================================================

📁 GENERAL SOUNDS (AC ON):
   - Drop any .mp3 or .wav audio files in this folder to be played at random.

📁 USER-SPECIFIC SOUNDS (AC ON):
   - When you enter your name in the mobile app, a folder is automatically created:
     audio/users/<Username>/
   - Drop custom MP3/WAV welcome sounds into that user's folder!
   - Example: audio/users/Ohad/welcome.mp3

📁 AC OFF CHIME:
   - When the AC is turned off, a generic notification chime (chime.wav)
     is played on your Google Nest speaker.
   - You can customize this sound by placing your own chime.wav or chime.mp3 in this folder.

🔊 AUTOMATIC VOLUME MATCHING:
   - WAV files here are levelled to the same perceived loudness on server start,
     so no sound is startling and none is too faint to hear. A quiet recording is
     brought up, a hot one is brought down, and mono files are laid out as stereo
     so they do not play louder than the rest.
   - This applies to per-user folders too. Drop a file in and restart the server.
   - Measurement is the broadcast loudness standard (ITU-R BS.1770), not peak level,
     so files are matched by how loud they actually sound rather than by their
     tallest sample. Gain only — nothing is compressed or clipped.
   - MP3/OGG/FLAC files are played as-is and are NOT levelled. For a consistent
     volume, convert custom sounds to WAV.
   - Results are cached in .loudness.json so each file is only measured once.

🗣️ AUTOMATIC TEXT-TO-SPEECH (TTS):
   - If no custom sounds exist in the user's folder, Google Nest will automatically
     speak a personalized welcome announcement.
=========================================================

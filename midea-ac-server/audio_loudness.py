"""
ITU-R BS.1770-4 / EBU R128 loudness measurement and gain normalization.

Used to keep every sound the Nest speaker plays -- the shipped pool, the off-chime
and anything a user drops into static/audio/ -- at the same perceived volume.

Peak normalization (what this replaces) matches the tallest sample, not the loudness
the ear reports, so two files peaking at the same value can still differ by several
dB of perceived level. This measures K-weighted gated loudness instead.

numpy/scipy are used when present but are not required; the pure-stdlib path gives
the same results, only slower, and results are cached so each file is measured once.
"""

import os
import sys
import math
import wave
import array
import json
import struct
import logging

logger = logging.getLogger("NestAudioBroadcaster")

# Sounds are matched on a blend of gated integrated loudness and the 90th percentile
# of momentary loudness (see perceived_lufs). Chosen to sit at the existing sound
# pool's own median level, so the absolute volume of the system is unchanged --
# only the spread between sounds is removed.
TARGET_LUFS = -15.8

# Weight of the integrated term in that blend; the rest is the percentile term.
_INTEGRATED_WEIGHT = 0.5

# Percentile of momentary loudness used as the "how loud while it is sounding" term.
_MOMENTARY_PERCENTILE = 90.0

# Ceiling for inter-sample (true) peaks, leaving headroom for the DAC and for any
# resampling the Cast device does on the way to the speaker.
TRUE_PEAK_CEILING_DB = -1.0

# Files already this close to the target are left alone rather than rewritten.
TOLERANCE_LU = 0.5

# Most peak reduction allowed to pull a file up to the target when plain gain would
# breach the ceiling. A recording whose level is held down by one stray transient
# (a mouth click, a knock on the desk) would otherwise stay audibly quiet. Kept
# small so it only ever shaves the transient rather than squashing the sound.
MAX_LIMIT_DB = 3.0

# Assumed inter-sample overshoot above the sample peak when true-peak measurement
# is unavailable (no numpy). Conservative for typical program material.
_ISP_ALLOWANCE_DB = 0.6

_CACHE_NAME = ".loudness.json"

try:
    import numpy as _np
except Exception:
    _np = None

try:
    from scipy.signal import lfilter as _lfilter_fast
except Exception:
    _lfilter_fast = None


# --------------------------------------------------------------------------
# WAV I/O
# --------------------------------------------------------------------------

_WAVE_FORMAT_PCM = 0x0001
_WAVE_FORMAT_IEEE_FLOAT = 0x0003
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE


def _parse_riff(raw):
    """
    Minimal RIFF/WAVE reader, returning (audio_format, channels, rate, bits, data).

    The stdlib wave module raises on anything that is not integer PCM, so it cannot
    open the 32-bit float WAVs some recorders produce. Those files are exactly the
    ones most likely to need levelling, so they have to be readable here.
    """
    if len(raw) < 12 or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE':
        raise ValueError('not a RIFF/WAVE file')
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(raw):
        chunk_id = raw[pos:pos + 4]
        size = struct.unpack('<I', raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if chunk_id == b'fmt ':
            fmt = body
        elif chunk_id == b'data':
            data = body
        pos += 8 + size + (size & 1)
        if fmt is not None and data is not None:
            break
    if fmt is None or data is None or len(fmt) < 16:
        raise ValueError('missing or short fmt/data chunk')

    audio_format, nchannels, rate, _, _, bits = struct.unpack('<HHIIHH', fmt[:16])
    if audio_format == _WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 26:
        audio_format = struct.unpack('<H', fmt[24:26])[0]
    if nchannels < 1:
        raise ValueError('no channels')
    return audio_format, nchannels, rate, bits, data


def _unpack(raw, type_code, item_bytes):
    values = array.array(type_code)
    usable = len(raw) - (len(raw) % item_bytes)
    if values.itemsize == item_bytes:
        values.frombytes(raw[:usable])
        if sys.byteorder != 'little':
            values.byteswap()
        return values
    fmt = {'h': 'h', 'i': 'i', 'f': 'f', 'd': 'd'}[type_code]
    return array.array(type_code,
                       struct.unpack('<%d%s' % (usable // item_bytes, fmt), raw[:usable]))


def _decode_frames(raw, audio_format, nchannels, bits):
    """Interleaved sample bytes -> list of per-channel float lists, full scale = 1.0."""
    if audio_format == _WAVE_FORMAT_IEEE_FLOAT:
        if bits == 32:
            flat, scale = _unpack(raw, 'f', 4), 1.0
        elif bits == 64:
            flat, scale = _unpack(raw, 'd', 8), 1.0
        else:
            raise ValueError('unsupported float width: %d bits' % bits)
    elif audio_format == _WAVE_FORMAT_PCM:
        if bits == 16:
            flat, scale = _unpack(raw, 'h', 2), 32768.0
        elif bits == 8:
            flat, scale = array.array('i', (b - 128 for b in raw)), 128.0
        elif bits == 24:
            count = len(raw) // 3
            flat = array.array('i', [0]) * count
            for i in range(count):
                value = raw[3 * i] | (raw[3 * i + 1] << 8) | (raw[3 * i + 2] << 16)
                flat[i] = value - 0x1000000 if value & 0x800000 else value
            scale = 8388608.0
        elif bits == 32:
            flat, scale = _unpack(raw, 'i', 4), 2147483648.0
        else:
            raise ValueError('unsupported PCM width: %d bits' % bits)
    else:
        raise ValueError('unsupported WAVE format tag: 0x%04X' % audio_format)

    return [[flat[i] / scale for i in range(c, len(flat), nchannels)]
            for c in range(nchannels)]


def read_wav(path):
    """
    Returns (channels, sample_rate, meta); channels are float lists at full scale 1.0.
    meta carries the source encoding so callers can tell a file that needs rewriting
    into plain 16-bit PCM from one that is already in the right shape.
    """
    with open(path, 'rb') as handle:
        raw = handle.read()
    audio_format, nchannels, rate, bits, data = _parse_riff(raw)
    meta = {
        'format': audio_format,
        'bits': bits,
        'sampwidth': bits // 8,
        'is_float': audio_format == _WAVE_FORMAT_IEEE_FLOAT,
        'is_pcm16': audio_format == _WAVE_FORMAT_PCM and bits == 16,
    }
    return _decode_frames(data, audio_format, nchannels, bits), rate, meta


def write_wav_pcm16(path, channels, sample_rate):
    """Writes float channels back as interleaved 16-bit PCM, clamped to full scale."""
    nch = len(channels)
    count = len(channels[0])
    flat = array.array('h', [0]) * (count * nch)
    for c in range(nch):
        source = channels[c]
        for i in range(count):
            value = int(round(source[i] * 32767.0))
            if value < -32768:
                value = -32768
            elif value > 32767:
                value = 32767
            flat[i * nch + c] = value
    with wave.open(path, 'wb') as handle:
        handle.setnchannels(nch)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(flat.tobytes())


# --------------------------------------------------------------------------
# K-weighting (BS.1770 stage 1 high shelf, stage 2 high pass)
# --------------------------------------------------------------------------

def _k_coeffs(rate):
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh ** 0.4996667741545416
    den = 1.0 + k / q + k * k
    shelf_b = [(vh + vb * k / q + k * k) / den,
               2.0 * (k * k - vh) / den,
               (vh - vb * k / q + k * k) / den]
    shelf_a = [1.0, 2.0 * (k * k - 1.0) / den, (1.0 - k / q + k * k) / den]

    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    den = 1.0 + k / q + k * k
    hp_b = [1.0, -2.0, 1.0]
    hp_a = [1.0, 2.0 * (k * k - 1.0) / den, (1.0 - k / q + k * k) / den]
    return (shelf_b, shelf_a), (hp_b, hp_a)


def _biquad(b, a, x):
    if _lfilter_fast is not None and _np is not None:
        return _lfilter_fast(b, a, _np.asarray(x, dtype=_np.float64))
    b0, b1, b2 = b
    a1, a2 = a[1], a[2]
    x1 = x2 = y1 = y2 = 0.0
    out = [0.0] * len(x)
    for i in range(len(x)):
        sample = x[i]
        value = b0 * sample + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, sample
        y2, y1 = y1, value
        out[i] = value
    return out


def _k_weight(channels, rate):
    (shelf_b, shelf_a), (hp_b, hp_a) = _k_coeffs(rate)
    return [_biquad(hp_b, hp_a, _biquad(shelf_b, shelf_a, ch)) for ch in channels]


def _channel_weights(nch):
    if nch == 5:
        return [1.0, 1.0, 1.0, 1.41, 1.41]        # L R C Ls Rs
    if nch == 6:
        return [1.0, 1.0, 1.0, 0.0, 1.41, 1.41]   # LFE excluded
    return [1.0] * nch


def _mean_square(seg, block):
    if not len(seg):
        return 0.0
    if _np is not None:
        return float(_np.sum(_np.square(seg))) / block
    return sum(v * v for v in seg) / block


def _block_loudness(weighted, rate, weights, block_s=0.400, overlap=0.75):
    """Loudness of each overlapping gating block, in LKFS."""
    block = int(round(block_s * rate))
    step = max(1, int(round(block * (1.0 - overlap))))
    count = len(weighted[0])
    span = max(block, count)

    out = []
    for start in range(0, span - block + 1, step):
        total = 0.0
        for channel, weight in zip(weighted, weights):
            if weight == 0.0:
                continue
            total += weight * _mean_square(channel[start:start + block], block)
        out.append(-0.691 + 10.0 * math.log10(total) if total > 0 else float('-inf'))
    return out


def _mean_loudness(blocks):
    """Average block powers, then convert back to loudness."""
    acc = 0.0
    for level in blocks:
        acc += 10.0 ** ((level + 0.691) / 10.0)
    return -0.691 + 10.0 * math.log10(acc / len(blocks))


def _blocks_above_absolute_gate(channels, rate):
    weights = _channel_weights(len(channels))
    blocks = _block_loudness(_k_weight(channels, rate), rate, weights)
    return [level for level in blocks if level > -70.0]


def integrated_lufs(channels, rate, blocks=None):
    """EBU R128 gated integrated loudness."""
    if blocks is None:
        blocks = _blocks_above_absolute_gate(channels, rate)
    if not blocks:
        return float('-inf')
    relative_gate = _mean_loudness(blocks) - 10.0
    gated = [level for level in blocks if level > relative_gate]
    if not gated:
        return float('-inf')
    return _mean_loudness(gated)


def _percentile(values, pct):
    """Linear-interpolated percentile, defined here so numpy and stdlib paths agree."""
    ordered = sorted(values)
    if not ordered:
        return float('-inf')
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (pct / 100.0)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def perceived_lufs(channels, rate, blocks=None):
    """
    Single loudness figure used for matching sounds against each other.

    Gated integrated loudness alone under-rates a short, evenly-loud sound next to a
    longer one with quiet tails: matching the two on integrated loudness leaves the
    short one audibly softer while it is actually sounding. The 90th percentile of
    momentary (400 ms) loudness captures that "loud while sounding" level but ignores
    how sustained the sound is. Averaging the two keeps both within about 1 LU across
    a pool mixing brief chimes with longer announcements.
    """
    if blocks is None:
        blocks = _blocks_above_absolute_gate(channels, rate)
    if not blocks:
        return float('-inf')
    integrated = integrated_lufs(channels, rate, blocks)
    if integrated == float('-inf'):
        return float('-inf')
    percentile = _percentile(blocks, _MOMENTARY_PERCENTILE)
    return _INTEGRATED_WEIGHT * integrated + (1.0 - _INTEGRATED_WEIGHT) * percentile


# --------------------------------------------------------------------------
# Peaks
# --------------------------------------------------------------------------

def sample_peak_db(channels):
    peak = 0.0
    for channel in channels:
        for value in channel:
            magnitude = -value if value < 0 else value
            if magnitude > peak:
                peak = magnitude
    return 20.0 * math.log10(peak) if peak > 0 else float('-inf')


def true_peak_db(channels, rate):
    """4x oversampled peak. Falls back to sample peak plus a fixed allowance without numpy."""
    if _np is None:
        peak = sample_peak_db(channels)
        return peak + _ISP_ALLOWANCE_DB if peak != float('-inf') else peak
    peak = 0.0
    for channel in channels:
        x = _np.asarray(channel, dtype=_np.float64)
        if x.size == 0:
            continue
        spectrum = _np.fft.rfft(x)
        padded = _np.zeros(4 * x.size // 2 + 1, dtype=complex)
        padded[:spectrum.size] = spectrum
        upsampled = _np.fft.irfft(padded, n=4 * x.size) * 4
        peak = max(peak, float(_np.max(_np.abs(upsampled))))
    return 20.0 * math.log10(peak) if peak > 0 else float('-inf')


# --------------------------------------------------------------------------
# Measurement and normalization
# --------------------------------------------------------------------------

def measure(path):
    """Returns a dict with loudness, peaks and format, or None if unreadable."""
    try:
        channels, rate, meta = read_wav(path)
    except Exception as e:
        logger.debug('Loudness: cannot read %s (%s)', os.path.basename(path), e)
        return None
    if not channels or not channels[0]:
        return None
    blocks = _blocks_above_absolute_gate(channels, rate)
    return {
        'lufs': perceived_lufs(channels, rate, blocks),
        'integrated_lufs': integrated_lufs(channels, rate, blocks),
        'momentary_p90': _percentile(blocks, _MOMENTARY_PERCENTILE),
        'sample_peak_db': sample_peak_db(channels),
        'true_peak_db': true_peak_db(channels, rate),
        'rate': rate,
        'channels': len(channels),
        'sampwidth': meta['sampwidth'],
        'is_float': meta['is_float'],
        'is_pcm16': meta['is_pcm16'],
        'duration': len(channels[0]) / float(rate),
    }


def _sliding_min(values, window):
    """Running minimum over a forward window, used as limiter look-ahead."""
    from collections import deque
    out = [0.0] * len(values)
    keep = deque()
    for i in range(len(values) - 1, -1, -1):
        while keep and values[keep[-1]] >= values[i]:
            keep.pop()
        keep.append(i)
        if keep[0] - i >= window:
            keep.popleft()
        out[i] = values[keep[0]]
    return out


def peak_limit(channels, rate, ceiling_db=TRUE_PEAK_CEILING_DB,
               max_reduction_db=MAX_LIMIT_DB, attack_ms=3.0, release_ms=60.0):
    """
    Shaves peaks above the ceiling using a smoothed, look-ahead gain envelope.

    Applied only to reach the loudness target on a file whose peaks would otherwise
    hold it back. Gain reduction ramps over a few milliseconds instead of clipping
    the waveform, and is floored at max_reduction_db so a genuinely dense recording
    is left quieter rather than crushed.
    """
    ceiling = 10.0 ** (ceiling_db / 20.0)
    floor = 10.0 ** (-abs(max_reduction_db) / 20.0)
    count = len(channels[0])

    if _np is not None:
        stack = _np.vstack([_np.asarray(c, dtype=_np.float64) for c in channels])
        envelope = _np.max(_np.abs(stack), axis=0)
    else:
        envelope = [max(abs(c[i]) for c in channels) for i in range(count)]

    reduction = [1.0] * count
    over = False
    for i in range(count):
        level = float(envelope[i])
        if level > ceiling:
            reduction[i] = max(ceiling / level, floor)
            over = True
    if not over:
        return channels, 0.0

    look = max(1, int(attack_ms * rate / 1000.0))
    reduction = _sliding_min(reduction, look)

    # One-pole release so the gain returns smoothly after the transient passes.
    coeff = math.exp(-1.0 / max(1.0, release_ms * rate / 1000.0))
    smoothed = [1.0] * count
    state = 1.0
    for i in range(count):
        target_gain = reduction[i]
        state = target_gain if target_gain < state else coeff * state + (1.0 - coeff) * target_gain
        smoothed[i] = state

    if _np is not None:
        envelope_gain = _np.asarray(smoothed)
        limited = [_np.asarray(c, dtype=_np.float64) * envelope_gain for c in channels]
    else:
        limited = [[c[i] * smoothed[i] for i in range(count)] for c in channels]
    return limited, 20.0 * math.log10(min(smoothed))


def required_gain_db(info, target=TARGET_LUFS, ceiling=TRUE_PEAK_CEILING_DB):
    """Gain to reach the target, held back if needed so true peak stays under the ceiling."""
    if info is None or info['lufs'] == float('-inf'):
        return 0.0
    return min(target - info['lufs'], ceiling - info['true_peak_db'])


def normalize_file(path, target=TARGET_LUFS, ceiling=TRUE_PEAK_CEILING_DB,
                   tolerance=TOLERANCE_LU, force_pcm16=True, force_stereo=True,
                   max_limit_db=MAX_LIMIT_DB):
    """
    Brings one WAV to the loudness target with gain only -- no limiting, so nothing
    is reshaped or clipped. Returns the gain applied in dB, or None if left alone.

    A mono file is first laid out as dual-mono stereo. The Cast device duplicates a
    mono track across both output channels, which lands about 3 dB above the same
    signal stored as stereo, so measuring it as mono would leave it playing hot
    against the rest of the pool.
    """
    try:
        channels, rate, meta = read_wav(path)
    except Exception as e:
        logger.debug('Loudness: cannot read %s (%s)', os.path.basename(path), e)
        return None
    if not channels or not channels[0]:
        return None

    upmixed = force_stereo and len(channels) == 1
    if upmixed:
        channels = [channels[0], list(channels[0])]

    loudness = perceived_lufs(channels, rate)
    if loudness == float('-inf'):
        return None

    wanted = target - loudness
    headroom = ceiling - true_peak_db(channels, rate)
    gain = min(wanted, headroom)

    needs_format_fix = upmixed or (force_pcm16 and not meta['is_pcm16'])
    if abs(gain) <= tolerance and not needs_format_fix and wanted <= headroom:
        return None

    # Peaks alone would leave this file short of the target: take the rest by
    # shaving the offending transients instead of leaving the sound quiet.
    shortfall = wanted - headroom
    if shortfall > tolerance and max_limit_db > 0.0:
        gain = min(wanted, headroom + min(shortfall, max_limit_db))

    factor = 10.0 ** (gain / 20.0)
    if _np is not None:
        channels = [_np.asarray(ch, dtype=_np.float64) * factor for ch in channels]
    else:
        channels = [[v * factor for v in ch] for ch in channels]

    if gain > headroom:
        channels, _ = peak_limit(channels, rate, ceiling, max_limit_db)
        # Inter-sample peaks can still poke through; trim the remainder off.
        excess = true_peak_db(channels, rate) - ceiling
        if excess > 0.0:
            trim = 10.0 ** (-excess / 20.0)
            if _np is not None:
                channels = [ch * trim for ch in channels]
            else:
                channels = [[v * trim for v in ch] for ch in channels]

    write_wav_pcm16(path, channels, rate)
    return gain


# --------------------------------------------------------------------------
# Directory sweep, with an mtime/size cache so each file is measured once
# --------------------------------------------------------------------------

def _load_cache(root):
    try:
        with open(os.path.join(root, _CACHE_NAME), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(root, cache):
    try:
        with open(os.path.join(root, _CACHE_NAME), 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception as e:
        logger.debug('Loudness: cannot write cache (%s)', e)


def _stamp(path):
    stat = os.stat(path)
    return '%d:%d' % (stat.st_size, int(stat.st_mtime))


def normalize_tree(root, target=TARGET_LUFS, ceiling=TRUE_PEAK_CEILING_DB,
                   tolerance=TOLERANCE_LU, skip_dirs=('tts',),
                   max_limit_db=MAX_LIMIT_DB):
    """
    Normalizes every WAV under root, per-user folders included, to a common loudness.
    Files already matched are skipped, and each file is measured only once per change.
    """
    if not os.path.isdir(root):
        return
    cache = _load_cache(root)
    seen = set()
    changed = False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in sorted(filenames):
            if not name.lower().endswith('.wav'):
                continue
            path = os.path.join(dirpath, name)
            key = os.path.relpath(path, root).replace('\\', '/')
            seen.add(key)
            try:
                stamp = _stamp(path)
            except OSError:
                continue
            if cache.get(key) == stamp:
                continue
            gain = normalize_file(path, target, ceiling, tolerance,
                                  max_limit_db=max_limit_db)
            if gain is not None:
                logger.info('Loudness: %s adjusted by %+.1f dB to %.1f LUFS', key, gain, target)
            try:
                cache[key] = _stamp(path)
            except OSError:
                cache.pop(key, None)
            changed = True

    for stale in [k for k in cache if k not in seen]:
        del cache[stale]
        changed = True
    if changed:
        _save_cache(root, cache)

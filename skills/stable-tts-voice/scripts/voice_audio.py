# stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
# Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
"""Small audio helpers shared by the scripts: WAV in/out (standard library), pitch, level, trimming.

Only numpy is needed, so this runs inside any Qwen3-TTS runtime (mlx-audio brings numpy).
"""
from __future__ import annotations

import math
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 24000


def read_wav(path, rate: int = RATE) -> np.ndarray:
    """Mono float32 at `rate`. Anything that is not 16-bit PCM WAV at that rate goes through afconvert."""
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() == 2 and w.getframerate() == rate:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
                return data.reshape(-1, w.getnchannels()).mean(axis=1)
    except (wave.Error, EOFError):
        pass
    with tempfile.TemporaryDirectory() as tmp:
        converted = Path(tmp) / "converted.wav"
        subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{rate}", "-c", "1", str(path), str(converted)],
                       check=True, capture_output=True)
        return read_wav(converted, rate)


def write_wav(path, audio: np.ndarray, rate: int = RATE) -> None:
    pcm = (np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def frame_rms(audio: np.ndarray, rate: int = RATE, frame: float = 0.04, hop: float = 0.01) -> np.ndarray:
    n, h = int(frame * rate), int(hop * rate)
    if audio.size < n:
        return np.zeros(0, dtype=np.float32)
    starts = np.arange(0, audio.size - n + 1, h)
    frames = np.stack([audio[s:s + n] for s in starts])
    return np.sqrt((frames ** 2).mean(axis=1))


def trim(audio: np.ndarray, rate: int = RATE, floor_db: float = -45.0, pad: float = 0.08) -> np.ndarray:
    """Leading and trailing silence removed (frames quieter than floor_db below the loudest frame)."""
    rms = frame_rms(audio, rate)
    if rms.size == 0 or rms.max() <= 0:
        return audio
    loud = np.nonzero(rms > rms.max() * 10 ** (floor_db / 20))[0]
    hop, keep = int(0.01 * rate), int(pad * rate)
    start = max(0, loud[0] * hop - keep)
    end = min(audio.size, loud[-1] * hop + int(0.04 * rate) + keep)
    return audio[start:end]


def level_db(audio: np.ndarray) -> float:
    """Loudness of the speech itself: the median of the louder half of the frames, in dBFS."""
    rms = frame_rms(audio)
    if rms.size == 0:
        return -120.0
    loud = np.sort(rms)[rms.size // 2:]
    return round(20 * math.log10(max(float(np.median(loud)), 1e-6)), 1)


def pitch_track(audio: np.ndarray, rate: int = RATE, low: float = 60.0, high: float = 400.0) -> np.ndarray:
    """F0 in Hz for every voiced 40 ms frame (10 ms hop), by normalized autocorrelation.

    Good enough to compare clips of the same voice with each other; it is not a phonetics tool.
    Frames quieter than 20 dB below the loudest frame, or without a clear period, are skipped.
    The window's own autocorrelation is divided out (Boersma 1993), so short and long periods are
    judged alike; the shortest period whose peak is within 5 % of the strongest wins, which
    avoids octave-low errors."""
    n, h = int(0.04 * rate), int(0.01 * rate)
    if audio.size < n:
        return np.zeros(0)
    starts = np.arange(0, audio.size - n + 1, h)
    frames = np.stack([audio[s:s + n] for s in starts]).astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    keep = rms > max(1e-3, rms.max() * 0.1)
    frames = frames[keep]
    if not len(frames):
        return np.zeros(0)
    size = 1 << (2 * n - 1).bit_length()
    window = np.hanning(n)
    spec = np.fft.rfft(frames * window, size, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, size, axis=1)[:, :n]
    ac /= np.maximum(ac[:, :1], 1e-12)
    window_ac = np.fft.irfft(np.abs(np.fft.rfft(window, size)) ** 2, size)[:n]
    ac /= np.maximum(window_ac / window_ac[0], 1e-3)
    lo, hi = int(rate / high), min(int(rate / low), n // 2)
    band = ac[:, lo - 1:hi + 1]
    inner = band[:, 1:-1]
    strongest = inner.max(axis=1, keepdims=True)
    peaks = (inner >= band[:, :-2]) & (inner >= band[:, 2:]) & (inner >= 0.95 * strongest)
    lags = lo + np.argmax(peaks, axis=1)          # the shortest period that is (nearly) the strongest
    voiced = strongest[:, 0] > 0.5
    return rate / lags[voiced]


def f0_median(audio: np.ndarray, rate: int = RATE) -> float:
    track = pitch_track(audio, rate)
    return round(float(np.median(track)), 1) if track.size >= 10 else 0.0


def semitones(f: float, center: float) -> float:
    return 12.0 * math.log2(f / center) if f > 0 and center > 0 else 0.0


def cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float64).reshape(-1), np.asarray(b, dtype=np.float64).reshape(-1)
    return float(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12))

"""Shared DSP helpers for the Iron Reign audio generators.

Everything works on mono float64 arrays at SR = 22050 Hz and only needs numpy + scipy.
Contents: filters (Butterworth + RBJ biquads), envelopes, a synthetic reverb impulse response,
ITU-R BS.1770 loudness (LUFS), a look-ahead peak limiter and 16-bit WAV I/O.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.ndimage import minimum_filter1d, uniform_filter1d

SR = 22050
NYQ = SR / 2.0


# ----------------------------------------------------------------------------------------------- basics

def samples(seconds: float) -> int:
    return max(0, int(round(seconds * SR)))


def time_axis(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) / SR


def midi_hz(midi):
    return 440.0 * 2.0 ** ((np.asarray(midi, dtype=np.float64) - 69.0) / 12.0)


def to_db(value: float) -> float:
    return 20.0 * np.log10(max(float(value), 1e-12))


def from_db(decibels: float) -> float:
    return 10.0 ** (decibels / 20.0)


def peak(x: np.ndarray) -> float:
    return float(np.max(np.abs(x))) if len(x) else 0.0


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def pad_to(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros(n - len(x))])


def mix_at(dst: np.ndarray, src: np.ndarray, start: int, gain: float = 1.0) -> None:
    """Adds src into dst at sample index start (clipped to dst)."""
    if start < 0:
        src = src[-start:]
        start = 0
    end = min(len(dst), start + len(src))
    if end > start:
        dst[start:end] += gain * src[: end - start]


# ----------------------------------------------------------------------------------------------- filters

def _sos(kind: str, freq, order: int):
    return signal.butter(order, freq, btype=kind, fs=SR, output="sos")


def lowpass(x: np.ndarray, freq: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(_sos("lowpass", min(freq, NYQ * 0.95), order), x)


def highpass(x: np.ndarray, freq: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(_sos("highpass", freq, order), x)


def bandpass(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    return signal.sosfilt(_sos("bandpass", [lo, min(hi, NYQ * 0.95)], order), x)


def rbj(kind: str, f0: float, gain_db: float = 0.0, q: float = 0.707):
    """RBJ cookbook biquad coefficients (b, a) for peak / lowshelf / highshelf / bandpass / highpass."""
    amp = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * min(f0, NYQ * 0.95) / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2.0 * q)
    sa = 2.0 * np.sqrt(amp) * alpha
    if kind == "peak":
        b = [1 + alpha * amp, -2 * cw, 1 - alpha * amp]
        a = [1 + alpha / amp, -2 * cw, 1 - alpha / amp]
    elif kind == "lowshelf":
        b = [amp * ((amp + 1) - (amp - 1) * cw + sa), 2 * amp * ((amp - 1) - (amp + 1) * cw),
             amp * ((amp + 1) - (amp - 1) * cw - sa)]
        a = [(amp + 1) + (amp - 1) * cw + sa, -2 * ((amp - 1) + (amp + 1) * cw), (amp + 1) + (amp - 1) * cw - sa]
    elif kind == "highshelf":
        b = [amp * ((amp + 1) + (amp - 1) * cw + sa), -2 * amp * ((amp - 1) + (amp + 1) * cw),
             amp * ((amp + 1) + (amp - 1) * cw - sa)]
        a = [(amp + 1) - (amp - 1) * cw + sa, 2 * ((amp - 1) - (amp + 1) * cw), (amp + 1) - (amp - 1) * cw - sa]
    elif kind == "bandpass":
        b = [alpha, 0.0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "highpass":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    else:
        raise ValueError(kind)
    b = np.asarray(b, dtype=np.float64)
    a = np.asarray(a, dtype=np.float64)
    return b / a[0], a / a[0]


def eq(x: np.ndarray, bands) -> np.ndarray:
    """bands: iterable of (kind, freq, gain_db, q)."""
    for kind, f0, gain, q in bands:
        b, a = rbj(kind, f0, gain, q)
        x = signal.lfilter(b, a, x)
    return x


def resonate(x: np.ndarray, f0: float, q: float) -> np.ndarray:
    b, a = rbj("bandpass", f0, 0.0, q)
    return signal.lfilter(b, a, x)


def smooth(x: np.ndarray, seconds: float, passes: int = 2, mode: str = "nearest") -> np.ndarray:
    size = max(1, samples(seconds))
    for _ in range(passes):
        x = uniform_filter1d(x, size=size, mode=mode)
    return x


# ----------------------------------------------------------------------------------------------- envelopes

def exp_decay(n: int, tau: float) -> np.ndarray:
    return np.exp(-time_axis(n) / max(tau, 1e-4))


def ramp_in(x: np.ndarray, seconds: float) -> np.ndarray:
    m = min(len(x), samples(seconds))
    if m > 1:
        x = x.copy()
        x[:m] *= np.sin(0.5 * np.pi * np.linspace(0.0, 1.0, m)) ** 2
    return x


def fade_out(x: np.ndarray, seconds: float) -> np.ndarray:
    m = min(len(x), samples(seconds))
    if m > 1:
        x = x.copy()
        x[-m:] *= np.cos(0.5 * np.pi * np.linspace(0.0, 1.0, m)) ** 2
    return x


def noise(rng: np.random.Generator, n: int) -> np.ndarray:
    return rng.standard_normal(n)


def slow_noise(rng: np.random.Generator, n: int, rate_hz: float) -> np.ndarray:
    """Smooth random curve (unit variance-ish) varying at about rate_hz."""
    raw = rng.standard_normal(n + 64)
    out = lowpass(raw, max(rate_hz, 0.5), 2)[64:]
    s = np.std(out)
    return out / s if s > 0 else out


# ----------------------------------------------------------------------------------------------- reverb

def make_ir(t60: float = 1.6, predelay: float = 0.018, seed: int = 1, brightness: float = 1.0,
            early_taps: int = 8) -> np.ndarray:
    """Synthetic room impulse response: early reflections + band-split exponentially decaying noise.

    High frequencies decay faster than lows (air/wall absorption). Energy-normalised (sum of squares = 1),
    so a send of g yields a wet signal roughly g times the dry RMS.
    """
    rng = np.random.default_rng(seed)
    n = samples(t60 * 1.15 + predelay)
    t = time_axis(n)
    raw = rng.standard_normal(n)
    low = lowpass(raw, 700.0, 2)
    high = highpass(raw, 3200.0, 2)
    mid = raw - low - high

    def env(t60_band):
        return np.exp(-6.9078 * t / t60_band)

    late = low * env(t60 * 1.2) + mid * env(t60) + high * env(t60 * 0.45 * brightness)
    late *= 1.0 - np.exp(-t / 0.03)  # diffusion build-up
    pd = samples(predelay)
    ir = np.zeros(n)
    ir[pd:] = late[: n - pd]
    for _ in range(early_taps):
        d = pd + samples(rng.uniform(0.003, 0.045))
        if d < n:
            ir[d] += rng.uniform(2.5, 6.0) * rng.choice([-1.0, 1.0])
    ir = lowpass(ir, 9000.0, 2)
    return ir / np.sqrt(np.sum(ir * ir))


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    return signal.oaconvolve(x, ir)[: len(x)]


# ----------------------------------------------------------------------------------------------- loudness

def _k_weighting():
    # ITU-R BS.1770-4 pre-filter (high shelf) and RLB high-pass, re-derived for SR (same as pyloudnorm).
    shelf = _bs1770_biquad("highshelf", 1681.9744509555319, 3.99984385397, 0.7071752369554193)
    hipass = _bs1770_biquad("highpass", 38.13547087613982, 0.0, 0.5003270373253953)
    return shelf, hipass


def _bs1770_biquad(kind, fc, gain_db, q):
    amp = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / SR
    cw = np.cos(w0)
    alpha = np.sin(w0) / (2.0 * q)
    if kind == "highshelf":
        sa = 2.0 * np.sqrt(amp) * alpha
        b = [amp * ((amp + 1) + (amp - 1) * cw + sa), -2 * amp * ((amp - 1) + (amp + 1) * cw),
             amp * ((amp + 1) + (amp - 1) * cw - sa)]
        a = [(amp + 1) - (amp - 1) * cw + sa, 2 * ((amp - 1) - (amp + 1) * cw), (amp + 1) - (amp - 1) * cw - sa]
    else:
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    b = np.asarray(b)
    a = np.asarray(a)
    return b / a[0], a / a[0]


_KW = _k_weighting()


def loudness(x: np.ndarray) -> float:
    """Integrated loudness in LUFS (mono, BS.1770 gating). Returns -inf for silence."""
    y = signal.lfilter(*_KW[0], x)
    y = signal.lfilter(*_KW[1], y)
    block = samples(0.4)
    step = samples(0.1)
    if len(y) < block:
        y = np.concatenate([y, np.zeros(block - len(y))])
    cs = np.concatenate([[0.0], np.cumsum(y * y)])
    starts = np.arange(0, len(y) - block + 1, step)
    z = (cs[starts + block] - cs[starts]) / block
    lk = -0.691 + 10.0 * np.log10(np.maximum(z, 1e-20))
    keep = lk > -70.0
    if not np.any(keep):
        return float("-inf")
    rel = -0.691 + 10.0 * np.log10(np.mean(z[keep])) - 10.0
    keep2 = keep & (lk > rel)
    return float(-0.691 + 10.0 * np.log10(np.mean(z[keep2])))


# ----------------------------------------------------------------------------------------------- dynamics

def limit(x: np.ndarray, ceiling_db: float = -1.0, window: float = 0.012, wrap: bool = False) -> np.ndarray:
    """Look-ahead brick-wall limiter. Gain = box-smoothed running minimum of the required gain, so the
    output never exceeds the ceiling and the gain changes smoothly. wrap=True treats x as a seamless loop."""
    ceiling = from_db(ceiling_db)
    need = np.minimum(1.0, ceiling / np.maximum(np.abs(x), 1e-12))
    if need.min() >= 1.0:
        return x.copy()
    r = max(2, samples(window))
    mode = "wrap" if wrap else "nearest"
    gain = minimum_filter1d(need, size=2 * r + 1, mode=mode)
    gain = uniform_filter1d(gain, size=r, mode=mode)
    gain = uniform_filter1d(gain, size=r, mode=mode)
    y = x * np.minimum(gain, 1.0)
    return np.clip(y, -ceiling, ceiling)


def normalize_peak(x: np.ndarray, peak_db: float) -> np.ndarray:
    p = peak(x)
    return x * (from_db(peak_db) / p) if p > 0 else x


def normalize_loudness(x: np.ndarray, target_lufs: float, ceiling_db: float, wrap: bool) -> np.ndarray:
    """Gain to target loudness, then limit to the ceiling; iterate so limiting losses are made up."""
    y = x
    for _ in range(5):
        lk = loudness(y)
        if not np.isfinite(lk):
            return y
        y = limit(y * from_db(target_lufs - lk), ceiling_db, wrap=wrap)
        if abs(loudness(y) - target_lufs) < 0.15:
            break
    return y


# ----------------------------------------------------------------------------------------------- I/O

def to_pcm16(x: np.ndarray, seed: int) -> np.ndarray:
    """Float [-1, 1] -> int16 with deterministic TPDF dither."""
    rng = np.random.default_rng(seed)
    dither = rng.random(len(x)) - rng.random(len(x))
    q = np.round(x * 32767.0 + dither)
    return np.clip(q, -32768, 32767).astype("<i2")


def write_wav(path: Path, pcm: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.ascontiguousarray(pcm, dtype="<i2").tobytes())


def read_wav(path: Path):
    """Returns (float samples in [-1, 1], sample_rate, channels). Multi-channel input is averaged."""
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        rate = w.getframerate()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM, got {8 * width}-bit")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate, channels

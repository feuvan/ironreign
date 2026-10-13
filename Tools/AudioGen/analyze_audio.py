#!/usr/bin/env python3
"""Objective checks for the generated audio (we cannot listen in CI).

    python3 Tools/AudioGen/analyze_audio.py [--png OUT_DIR] [files...]

Prints duration, size, peak / RMS / integrated loudness (LUFS), DC offset, clipped samples and, for music
loops, the loop-seam continuity (jump and slope change across the wrap point compared with the largest
sample-to-sample steps inside the file). With --png it renders a waveform overview, a log-frequency
spectrogram and a zoom on the loop seam per file (needs Pillow).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audiolib_dsp import loudness, read_wav, to_db  # noqa: E402

AUDIO_DIR = Path(__file__).resolve().parents[2] / "Content" / "Data" / "Audio"
LOOPED = {"Music_Title", "Music_Strategy", "Music_Battle", "Music_Duel"}


def metrics(path: Path) -> dict:
    x, rate, channels = read_wav(path)
    loop = path.stem in LOOPED
    raw = np.round(x * 32768.0)
    m = dict(name=path.stem, rate=rate, channels=channels, seconds=len(x) / rate, bytes=path.stat().st_size,
             peak_db=to_db(np.max(np.abs(x))), rms_db=to_db(np.sqrt(np.mean(x * x))), lufs=loudness(x),
             dc=float(np.mean(x)), clipped=int(np.sum((raw >= 32767) | (raw <= -32768))), loop=loop)
    if loop:
        d1 = np.abs(np.diff(x))
        d2 = np.abs(np.diff(x, 2))
        jump = abs(x[0] - x[-1])
        slope = abs((x[1] - x[0]) - (x[-1] - x[-2]))
        m["seam_jump"] = jump / max(np.percentile(d1, 99.9), 1e-9)
        m["seam_slope"] = slope / max(np.percentile(d2, 99.9), 1e-9)
        w = int(0.05 * rate)
        m["seam_rms_db"] = to_db(np.sqrt(np.mean(x[-w:] ** 2))) - to_db(np.sqrt(np.mean(x[:w] ** 2)))
    return m


def print_table(rows) -> None:
    print(f"{'file':16s} {'sec':>6s} {'KiB':>7s} {'peak':>6s} {'rms':>6s} {'LUFS':>6s} {'dc':>8s} {'clip':>4s}  seam")
    total = 0
    for m in rows:
        total += m["bytes"]
        seam = ""
        if m["loop"]:
            seam = f"jump {m['seam_jump']:.2f}x  slope {m['seam_slope']:.2f}x  rms {m['seam_rms_db']:+.1f} dB"
        print(f"{m['name']:16s} {m['seconds']:6.2f} {m['bytes'] / 1024:7.0f} {m['peak_db']:6.1f} {m['rms_db']:6.1f} "
              f"{m['lufs']:6.1f} {m['dc']:8.1e} {m['clipped']:4d}  {seam}")
    print(f"total {total / 1024 / 1024:.2f} MiB ({total / 1e6:.2f} MB) in {len(rows)} files")


# ----------------------------------------------------------------------------------------------- images

_STOPS = np.array([[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21],
                   [250, 193, 39], [252, 255, 164]], dtype=np.float64)


def _colormap(v: np.ndarray) -> np.ndarray:
    v = np.clip(v, 0.0, 1.0) * (len(_STOPS) - 1)
    i = np.minimum(v.astype(int), len(_STOPS) - 2)
    f = (v - i)[..., None]
    return (_STOPS[i] * (1 - f) + _STOPS[i + 1] * f).astype(np.uint8)


def render_png(path: Path, out_png: Path) -> None:
    from PIL import Image, ImageDraw

    x, rate, _ = read_wav(path)
    loop = path.stem in LOOPED
    width = 1600 if len(x) > rate * 5 else 800
    wave_h, spec_h, seam_h, pad = 160, 320, 160 if loop else 0, 24
    height = pad + wave_h + pad + spec_h + (pad + seam_h if loop else 0) + 8
    img = Image.new("RGB", (width, height), (18, 18, 22))
    draw = ImageDraw.Draw(img)
    m = metrics(path)
    head = f"{path.name}  {m['seconds']:.2f}s  peak {m['peak_db']:.1f} dBFS  {m['lufs']:.1f} LUFS"
    draw.text((6, 5), head, fill=(230, 230, 230))

    # waveform overview (min/max per column) with -3 / -1 dBFS guides
    top = pad
    mid = top + wave_h // 2
    cols = np.array_split(x, width)
    for c, chunk in enumerate(cols):
        if len(chunk) == 0:
            continue
        lo, hi = float(chunk.min()), float(chunk.max())
        draw.line([(c, mid - hi * wave_h / 2), (c, mid - lo * wave_h / 2)], fill=(120, 200, 255))
    for level in (10 ** (-3 / 20), 10 ** (-1 / 20)):
        for sgn in (1, -1):
            y = mid - sgn * level * wave_h / 2
            draw.line([(0, y), (width, y)], fill=(90, 50, 50))
    draw.line([(0, mid), (width, mid)], fill=(70, 70, 70))

    # log-frequency spectrogram
    nper, hop = (1024, 256) if len(x) > rate * 5 else (512, 32)
    f, _, z = signal.stft(x, fs=rate, nperseg=nper, noverlap=nper - hop, boundary=None)
    mag = 20 * np.log10(np.abs(z) + 1e-9)
    count = mag.shape[1]
    frames = [np.arange(int(c * count / width), max(int((c + 1) * count / width), int(c * count / width) + 1))
              for c in range(width)]
    fmin, fmax = 40.0, rate / 2
    edges = np.geomspace(fmin, fmax, spec_h + 1)
    rows = []
    for r in range(spec_h):
        sel = np.where((f >= edges[r]) & (f < edges[r + 1]))[0]
        if len(sel) == 0:
            sel = np.array([np.argmin(np.abs(f - edges[r]))])
        rows.append(sel)
    spec = np.zeros((spec_h, width))
    for c, fr in enumerate(frames):
        if len(fr) == 0:
            continue
        col = mag[:, fr].max(axis=1)
        spec[:, c] = [col[sel].max() for sel in rows]
    ref = np.percentile(spec, 99.5)
    norm = (spec - (ref - 80.0)) / 80.0
    rgb = _colormap(norm[::-1])
    stop = top + wave_h + pad
    img.paste(Image.fromarray(rgb, "RGB"), (0, stop))
    for hz in (100, 1000, 10000):
        y = stop + spec_h - int(spec_h * np.log(hz / fmin) / np.log(fmax / fmin))
        draw.line([(0, y), (12, y)], fill=(255, 255, 255))
        draw.text((14, y - 6), f"{hz} Hz", fill=(255, 255, 255))
    if len(x) > rate * 5:
        for s in range(0, int(len(x) / rate) + 1, 10):
            xpix = int(s * rate / len(x) * width)
            draw.line([(xpix, stop + spec_h - 6), (xpix, stop + spec_h)], fill=(255, 255, 255))

    # loop seam: last 25 ms then first 25 ms
    if loop:
        w = int(0.025 * rate)
        seg = np.concatenate([x[-w:], x[:w]])
        s0 = stop + spec_h + pad
        smid = s0 + seam_h // 2
        scale = (seam_h / 2 - 4) / max(np.max(np.abs(seg)), 1e-6)
        pts = [(i * width / len(seg), smid - v * scale) for i, v in enumerate(seg)]
        draw.line(pts, fill=(140, 255, 160))
        draw.line([(width / 2, s0), (width / 2, s0 + seam_h)], fill=(255, 80, 80))
        draw.text((6, s0 - 16), "loop seam: last 25 ms | first 25 ms (auto-scaled)", fill=(200, 200, 200))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--png", type=Path, help="write <name>.png analysis images here")
    args = ap.parse_args(argv)
    files = args.files or sorted(AUDIO_DIR.glob("*.wav"))
    rows = [metrics(p) for p in files]
    print_table(rows)
    if args.png:
        for p in files:
            render_png(p, args.png / f"{p.stem}.png")
        print(f"images written to {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

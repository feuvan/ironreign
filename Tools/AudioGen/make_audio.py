#!/usr/bin/env python3
"""Generates every WAV in Content/Data/Audio (16-bit PCM mono, 22050 Hz). Deterministic: same output each run.

    python3 Tools/AudioGen/make_audio.py                 # everything
    python3 Tools/AudioGen/make_audio.py Music_Battle Sfx_Click   # selected files
    python3 Tools/AudioGen/make_audio.py --png /tmp/audio_png      # also render analysis images

Music loops are rendered circularly (tails folded onto the start) and normalised to about -16 LUFS with a
-1 dBFS limiter; sound effects get a small room, a fade-out and a -3 dBFS peak. Requires numpy + scipy
(Pillow only for --png).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_audio  # noqa: E402
from audio_music import TRACKS  # noqa: E402
from audio_sfx import SFX  # noqa: E402
from audiolib_dsp import (SR, convolve, fade_out, from_db, highpass, limit, loudness, make_ir,  # noqa: E402
                          normalize_peak, pad_to, ramp_in, samples, to_pcm16, write_wav)

OUT_DIR = Path(__file__).resolve().parents[2] / "Content" / "Data" / "Audio"
SFX_PEAK_DB = -3.0
SFX_MIN_LUFS = -20.0  # very peaky effects get up to SFX_MAX_BOOST dB of limiting to sit closer to the others
SFX_MAX_BOOST = 4.0
SFX_NO_BOOST = {"Sfx_Click"}


def _seed(name: str) -> int:
    return sum((i + 1) * ord(c) for i, c in enumerate(name)) % (1 << 31)


def render_sfx(name: str) -> np.ndarray:
    fn, length, send, fade = SFX[name]
    rng = np.random.default_rng(_seed(name))
    dry = fn(rng)
    n = samples(length)
    dry = pad_to(dry, n + samples(0.6))
    if send > 0.0:
        room = make_ir(0.7, 0.008, seed=7, brightness=0.9, early_taps=6)
        dry = dry + send * convolve(dry, room)
    y = highpass(dry, 35.0, 2)[:n]
    y = ramp_in(y, 0.0005)
    y = fade_out(y, fade)
    y = y - np.linspace(y[0], y[-1], len(y))  # exact zero at both ends (no click when the voice starts/stops)
    y = normalize_peak(y, SFX_PEAK_DB)
    boost = min(SFX_MAX_BOOST, max(0.0, SFX_MIN_LUFS - loudness(y)))
    if name not in SFX_NO_BOOST and boost > 0.05:
        y = limit(y * from_db(boost), SFX_PEAK_DB, window=0.004)
    return y


def build(names, out_dir: Path) -> list[Path]:
    written = []
    for name in names:
        t = time.time()
        if name in TRACKS:
            print(f"  {name} ...", flush=True)
            y = TRACKS[name][0]()
        else:
            y = render_sfx(name)
        path = out_dir / f"{name}.wav"
        write_wav(path, to_pcm16(y, seed=_seed(name)))
        written.append(path)
        print(f"  {name}: {len(y) / SR:.2f} s in {time.time() - t:.1f} s", flush=True)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="Music_* / Sfx_* names to build (default: all)")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--png", type=Path, help="also write analysis PNGs (waveform, spectrogram, loop seam) here")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)
    every = list(TRACKS) + list(SFX)
    if args.list:
        print("\n".join(every))
        return 0
    names = args.names or every
    unknown = [n for n in names if n not in every]
    if unknown:
        ap.error(f"unknown names: {', '.join(unknown)}")
    print(f"Writing {len(names)} files to {args.out}")
    written = build(names, args.out)
    rows = [analyze_audio.metrics(p) for p in written]
    analyze_audio.print_table(rows)
    if args.png:
        for p in written:
            analyze_audio.render_png(p, args.png / f"{p.stem}.png")
        print(f"analysis images in {args.png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

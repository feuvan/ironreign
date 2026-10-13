"""Synthesised traditional Chinese instruments and percussion for Iron Reign.

* Plucked strings (guzheng, pipa, guqin, ruan): modal synthesis - a sum of exponentially decaying, slightly
  inharmonic partials shaped by the pluck position, in two detuned string polarisations (prompt sound +
  aftersound), plus a filtered pluck-noise burst, with optional pitch-bend curves for the pressed-string
  ornaments (slides, falls, pressing vibrato) and a pipa tremolo (lunzhi) helper.
* Continuous lines (dizi flute, erhu fiddle, war horn): additive synthesis on a phrase-long pitch curve with
  portamento, delayed vibrato, grace notes and slides; dizi adds breath noise, onset chiff and a membrane
  (dimo) buzz, erhu is a band-limited sawtooth through body formant filters with bow noise.
* Percussion: membrane drums (pitch-swept sine + membrane modes + stick noise), gongs (inharmonic partial
  pairs with slow beating, bloom and pitch glide), cymbals, bells, wood blocks and clappers, metal clangs.
All functions are deterministic for a given numpy Generator.
"""
from __future__ import annotations

import numpy as np

from audiolib_dsp import (SR, bandpass, eq, exp_decay, fade_out, highpass, lowpass, midi_hz, mix_at, ramp_in,
                          resonate, samples, slow_noise, smooth, time_axis)

TAU = 2.0 * np.pi


def _phase(freq_curve: np.ndarray) -> np.ndarray:
    """Running phase (radians) of an instantaneous-frequency curve, starting at 0."""
    return TAU * (np.cumsum(freq_curve) - freq_curve[0]) / SR


def bend_curve(n: int, points) -> np.ndarray:
    """Piecewise-linear semitone curve from [(time_s, semitones), ...]; held constant outside."""
    pts = sorted(points)
    ts = np.array([p[0] for p in pts], dtype=np.float64)
    vs = np.array([p[1] for p in pts], dtype=np.float64)
    return np.interp(time_axis(n), ts, vs)


def vibrato_curve(n: int, rate: float, depth: float, onset: float, ramp: float) -> np.ndarray:
    t = time_axis(n)
    return depth * np.clip((t - onset) / max(ramp, 1e-3), 0.0, 1.0) * np.sin(TAU * rate * t)


# =============================================================================================== plucked

PLUCK = {
    # Steel-nylon zither: bright, long singing sustain, airy box.
    "guzheng": dict(pos=0.12, alpha=1.0, fbright=6500.0, tau=2.3, tau_ref=294.0, tau_exp=0.55, fdamp=2700.0,
                    inharm=6e-5, detune=1.4, noise=0.10, noise_band=(1800.0, 7000.0), noise_tau=0.004,
                    slide_noise=0.010, gain=1.0,
                    eq=[("peak", 230.0, 2.0, 1.0), ("peak", 2400.0, 3.0, 1.2), ("highshelf", 8000.0, -3.0, 0.7)]),
    # Pear-shaped lute: plectrum attack, nasal, short.
    "pipa": dict(pos=0.08, alpha=0.85, fbright=6500.0, tau=0.85, tau_ref=330.0, tau_exp=0.4, fdamp=1900.0,
                 inharm=1.5e-4, detune=1.0, noise=0.26, noise_band=(2200.0, 8000.0), noise_tau=0.003,
                 slide_noise=0.012, gain=1.0,
                 eq=[("lowshelf", 220.0, -4.0, 0.7), ("peak", 520.0, 3.0, 1.2), ("peak", 1500.0, 3.0, 1.5),
                     ("peak", 3200.0, 2.5, 1.5)]),
    # Seven-string zither plucked with the flesh: dark, deep, very long, audible finger slides.
    "guqin": dict(pos=0.21, alpha=1.35, fbright=1700.0, tau=3.2, tau_ref=147.0, tau_exp=0.3, fdamp=1100.0,
                  inharm=3e-5, detune=0.8, noise=0.05, noise_band=(400.0, 2500.0), noise_tau=0.008,
                  slide_noise=0.035, gain=1.3,
                  eq=[("peak", 160.0, 3.0, 0.9), ("highshelf", 3000.0, -6.0, 0.7)]),
    # Moon guitar used as the bass ostinato in the battle music.
    "ruan": dict(pos=0.15, alpha=1.1, fbright=3000.0, tau=1.0, tau_ref=131.0, tau_exp=0.4, fdamp=1500.0,
                 inharm=8e-5, detune=1.0, noise=0.12, noise_band=(800.0, 4000.0), noise_tau=0.004,
                 slide_noise=0.0, gain=1.0,
                 eq=[("peak", 180.0, 3.0, 1.0), ("peak", 900.0, 2.0, 1.2), ("highshelf", 5000.0, -6.0, 0.7)]),
}


def pluck(freq: float, dur: float, vel: float = 0.8, preset: str = "guzheng", bend=None, vib: float = 0.0,
          rng: np.random.Generator | None = None, tau_scale: float = 1.0, damp_at: float | None = None) -> np.ndarray:
    """One plucked note of length dur seconds (it rings for the whole length unless damp_at is given).

    bend: [(t, semitones), ...] pitch curve (pressed-string ornaments); vib: pressing vibrato depth in semitones.
    """
    p = PLUCK[preset]
    rng = rng if rng is not None else np.random.default_rng(0)
    n = max(samples(dur), 16)
    t = time_axis(n)
    semis = np.zeros(n)
    if bend:
        semis += bend_curve(n, bend)
    if vib > 0.0:
        semis += vibrato_curve(n, 4.8 + rng.uniform(-0.3, 0.3), vib, 0.22, 0.25)
    finst = freq * 2.0 ** (semis / 12.0)
    ph = _phase(finst)
    tau1 = float(np.clip(p["tau"] * (p["tau_ref"] / freq) ** p["tau_exp"], 0.12, 9.0)) * tau_scale
    bright = p["fbright"] * (0.55 + 0.6 * vel)
    fmax = 0.45 * SR / 2.0 ** (max(0.0, float(semis.max())) / 12.0)
    out = np.zeros(n)
    for pol_amp, tau_mul, cents in ((0.72, 0.65, 0.0), (0.28, 1.6, p["detune"])):
        shift = 2.0 ** (cents / 1200.0)
        for k in range(1, 80):
            ratio = k * np.sqrt(1.0 + p["inharm"] * k * k) * shift
            fk = freq * ratio
            if fk > fmax:
                break
            a = abs(np.sin(np.pi * k * p["pos"])) / k ** p["alpha"] * np.exp(-fk / bright)
            if a < 2e-4:
                continue
            tk = tau1 * tau_mul / (1.0 + (fk / p["fdamp"]) ** 2)
            out += pol_amp * a * np.exp(-t / tk) * np.sin(ratio * ph)
    nn = min(n, samples(max(0.03, p["noise_tau"] * 10)))
    burst = bandpass(rng.standard_normal(nn), *p["noise_band"]) * exp_decay(nn, p["noise_tau"])
    out[:nn] += p["noise"] * (0.5 + 0.5 * vel) * burst
    if bend and p["slide_noise"] > 0.0:
        speed = np.abs(np.gradient(semis)) * SR  # semitones per second
        speed = smooth(speed, 0.02)
        rub = bandpass(rng.standard_normal(n), 700.0, 2600.0) * np.clip(speed / 30.0, 0.0, 1.0)
        out += p["slide_noise"] * rub
    out = ramp_in(out, 0.0012)
    if damp_at is not None and damp_at < dur:
        m = samples(damp_at)
        out[m:] *= np.exp(-(t[m:] - t[m]) / 0.025)
    # strings are let ring: release over the last third of the buffer instead of cutting a ringing note
    out = fade_out(out, min(0.04, dur * 0.2) if damp_at is not None else min(0.9, dur * 0.35))
    out = eq(out, p["eq"])
    return out * vel * p["gain"]


def tremolo(freq: float, dur: float, vel: float, rng: np.random.Generator, preset: str = "pipa",
            rate: float = 12.8, ring: float = 0.7) -> np.ndarray:
    """Pipa lunzhi tremolo: rapid alternating-finger re-plucks of one string for dur seconds."""
    count = max(1, int(round(dur * rate)))
    out = np.zeros(samples(dur + ring + 0.1))
    for i in range(count):
        start = i / rate + (rng.normal(0.0, 0.002) if i else 0.0)
        last = i == count - 1
        v = vel * (1.0 if i % 2 == 0 else 0.82) * (0.92 + 0.08 * rng.random())
        swell = 0.8 + 0.2 * np.sin(np.pi * min(1.0, i / max(1, count - 1)))
        note = pluck(freq, ring if last else 0.3, v * swell, preset, rng=rng, tau_scale=1.0 if last else 0.3)
        mix_at(out, note, samples(max(0.0, start)))
    return out


def gliss(freqs, start_gap: float, vel: float, rng: np.random.Generator, preset: str = "guzheng",
          ring: float = 2.0, accel: float = 0.0) -> np.ndarray:
    """Guzheng glissando (hua zhi): one pluck per string, gap seconds apart (optionally accelerating)."""
    total = start_gap * len(freqs) + ring + 0.2
    out = np.zeros(samples(total))
    t = 0.0
    for i, f in enumerate(freqs):
        v = vel * (0.75 + 0.25 * i / max(1, len(freqs) - 1)) * (0.9 + 0.1 * rng.random())
        mix_at(out, pluck(f, ring, v, preset, rng=rng), samples(t))
        t += start_gap * (1.0 - accel * i / max(1, len(freqs)))
    return out


# =============================================================================================== lines

LINES = {
    "dizi": dict(harm=[1.0, 0.52, 0.36, 0.20, 0.15, 0.11, 0.08, 0.06, 0.045, 0.035, 0.028, 0.022, 0.018, 0.014],
                 glide=0.035, attack=0.05, release=0.08, vib_rate=5.3, vib_depth=0.13, vib_onset=0.22,
                 amp_vib=0.10, bright=0.9, breath=0.05, chiff=0.22, dip=0.6, buzz=0.35,
                 eq=[("highpass", 300.0, 0.0, 0.7), ("peak", 3400.0, 5.0, 1.2), ("highshelf", 7500.0, -6.0, 0.7)]),
    "erhu": dict(harm=None, nh=48, h1=0.65, glide=0.11, attack=0.085, release=0.13, vib_rate=5.9, vib_depth=0.30,
                 vib_onset=0.16, amp_vib=0.05, bright=0.55, breath=0.020, chiff=0.03, dip=0.45, buzz=0.0,
                 eq=[("lowshelf", 300.0, -8.0, 0.7), ("peak", 760.0, 6.0, 1.4), ("peak", 1650.0, 4.0, 2.0),
                     ("peak", 3100.0, 3.0, 2.0), ("highshelf", 5500.0, -9.0, 0.7)]),
    "horn": dict(harm=None, nh=40, h1=0.8, slope=0.65, glide=0.09, attack=0.14, release=0.22, vib_rate=4.5,
                 vib_depth=0.06, vib_onset=0.4, amp_vib=0.04, bright=1.8, breath=0.015, chiff=0.05, dip=0.7,
                 buzz=0.0,
                 eq=[("lowshelf", 120.0, -4.0, 0.7), ("peak", 520.0, 4.0, 1.0), ("peak", 1250.0, 3.0, 1.4),
                     ("highshelf", 4200.0, -7.0, 0.7)]),
}


def _harmonic_table(p) -> list[float]:
    if p["harm"] is not None:
        return list(p["harm"])
    slope = p.get("slope", 1.0)
    table = [1.0 / h ** slope for h in range(1, p["nh"] + 1)]
    table[0] *= p["h1"]
    return table


def line(events, kind: str, rng: np.random.Generator):
    """Renders a monophonic phrase. events: list of dicts with start, dur (s), midi, vel, orn, grace, lower.

    Ornaments in orn: '^' grace from the upper neighbour, '/' slide up from the lower neighbour, '\\' fall at
    the end, '~' wide vibrato, '>' accent. Returns (signal, start_time_of_signal)."""
    p = LINES[kind]
    events = sorted(events, key=lambda e: e["start"])
    pre = 0.12
    t0 = events[0]["start"] - pre
    t_end = max(e["start"] + e["dur"] for e in events) + p["release"] + 0.4
    n = samples(t_end - t0)
    target = np.full(n, np.nan)
    amp = np.zeros(n)
    vdepth = np.zeros(n)
    onsets = []
    rel = samples(p["release"])
    for i, e in enumerate(events):
        s = samples(e["start"] - t0)
        d = max(2, samples(e["dur"]))
        end = min(n, s + d)
        nxt = events[i + 1] if i + 1 < len(events) else None
        legato_next = nxt is not None and nxt["start"] - (e["start"] + e["dur"]) < 0.03
        prev = events[i - 1] if i > 0 else None
        legato_prev = prev is not None and e["start"] - (prev["start"] + prev["dur"]) < 0.03
        target[s:end] = e["midi"]
        orn = e.get("orn", "")
        if "/" in orn and e.get("lower") is not None:
            target[s:min(end, s + samples(0.07))] = e["lower"]
        if "^" in orn and e.get("grace") is not None:
            target[s:min(end, s + samples(0.075 if kind == "dizi" else 0.09))] = e["grace"]
        if "\\" in orn and e.get("lower") is not None and d > samples(0.4):
            target[max(s, end - samples(0.16)):end] = e["lower"]
        # amplitude envelope of this note
        env = np.full(d, float(e["vel"]))
        if e["dur"] > 0.9:  # long notes swell and relax
            env *= 0.9 + 0.18 * np.sin(np.pi * np.linspace(0.0, 1.0, d)) ** 1.5
        a = min(d, samples(p["attack"]))
        start_level = p["dip"] if legato_prev else 0.0
        env[:a] *= start_level + (1.0 - start_level) * np.sin(0.5 * np.pi * np.linspace(0.0, 1.0, a))
        if "\\" in orn and d > samples(0.4):
            f = samples(0.18)
            env[-f:] *= np.linspace(1.0, 0.25, f)
        if not legato_next:
            env = np.concatenate([env, env[-1] * np.cos(0.5 * np.pi * np.linspace(0.0, 1.0, rel)) ** 2])
        seg = amp[s:s + len(env)]
        amp[s:s + len(env)] = np.maximum(seg, env[:len(seg)])
        if not legato_prev:
            onsets.append((s, e["vel"]))
        # vibrato depth: delayed onset, only on notes long enough to bloom
        if e["dur"] > 0.32:
            depth = p["vib_depth"] * (1.6 if "~" in orn else 1.0)
            ramp = np.clip((time_axis(end - s) - p["vib_onset"]) / 0.3, 0.0, 1.0)
            vdepth[s:end] = np.maximum(vdepth[s:end], depth * ramp)
        # hold this pitch through the release before the next note (if any) takes over
        if not legato_next:
            target[end:min(n, end + rel + samples(p["glide"]))] = e["midi"]
    # rests take the next note's pitch so notes after a rest start in tune
    idx = np.where(~np.isnan(target))[0]
    target = np.interp(np.arange(n), idx, target[idx])
    nan_free = target.copy()  # (np.interp only filled the lead-in before the first note)
    for i in range(len(events) - 1):
        a_end = samples(events[i]["start"] + events[i]["dur"] - t0) + rel + samples(p["glide"])
        b_start = samples(events[i + 1]["start"] - t0)
        if b_start > a_end:
            nan_free[a_end:b_start] = events[i + 1]["midi"]
    semis = smooth(nan_free, p["glide"], passes=2)
    vdepth = smooth(vdepth, 0.05, passes=1)
    rate_wobble = 1.0 + 0.06 * slow_noise(rng, n, 0.7)
    vib_phase = TAU * np.cumsum(p["vib_rate"] * rate_wobble) / SR
    semis = semis + vdepth * np.sin(vib_phase) + 0.03 * slow_noise(rng, n, 3.0)
    f0 = midi_hz(semis)
    amp = smooth(amp, 0.006, passes=1)
    vnorm = vdepth / max(1e-6, p["vib_depth"])
    amp = amp * (1.0 + p["amp_vib"] * np.clip(vnorm, 0.0, 1.6) * np.sin(vib_phase + 0.6))
    amp = amp * (1.0 + 0.025 * slow_noise(rng, n, 9.0))
    amp = np.clip(amp, 0.0, None)
    ph = _phase(f0)
    out = np.zeros(n)
    for h, base in enumerate(_harmonic_table(p), start=1):
        taper = np.clip((0.46 * SR - f0 * h) / (0.03 * SR), 0.0, 1.0)
        if taper.max() <= 0.0:
            break
        weight = amp ** (1.0 + p["bright"] * 0.15 * (h - 1))
        out += base * taper * weight * np.sin(h * ph + rng.uniform(0.0, TAU))
    hiss = bandpass(rng.standard_normal(n), 1200.0, 7500.0)
    out += p["breath"] * hiss * amp
    if p["chiff"] > 0.0:
        cn = samples(0.045)
        for s, v in onsets:
            burst = bandpass(rng.standard_normal(cn), 1800.0, 6000.0) * exp_decay(cn, 0.012)
            mix_at(out, burst, s, p["chiff"] * v)
    if p["buzz"] > 0.0:
        hb = highpass(out, 2200.0, 2)
        out += p["buzz"] * np.tanh(4.0 * hb) / 4.0
    out = eq(out, p["eq"])
    out = ramp_in(out, 0.01)
    out = fade_out(out, 0.05)
    return out, t0


# =============================================================================================== drums

DRUMS = {
    # Big barrel drum (taiko-like): deep boom with a sharp stick attack.
    "taiko": dict(f_hi=150.0, f_lo=68.0, sweep=0.028, decay=0.40, dur=1.3, noise=0.45, band=(120.0, 1800.0),
                  ntau=0.022, modes=[(1.59, 0.30, 0.55), (2.14, 0.18, 0.40), (2.30, 0.12, 0.35), (2.65, 0.08, 0.3)]),
    # Very large court drum for the title and stings.
    "dagu": dict(f_hi=128.0, f_lo=63.0, sweep=0.04, decay=0.6, dur=2.0, noise=0.35, band=(90.0, 1500.0),
                 ntau=0.03, modes=[(1.59, 0.30, 0.5), (2.14, 0.18, 0.4), (2.65, 0.10, 0.3)]),
    # Small hall drum (tanggu): rolls, fills and backbeats.
    "tanggu": dict(f_hi=290.0, f_lo=200.0, sweep=0.018, decay=0.15, dur=0.6, noise=0.70, band=(300.0, 5000.0),
                   ntau=0.018, modes=[(1.59, 0.35, 0.6), (2.14, 0.22, 0.45), (2.65, 0.15, 0.35)]),
    # Muffled heartbeat thump for the duel.
    "heart": dict(f_hi=100.0, f_lo=56.0, sweep=0.03, decay=0.10, dur=0.45, noise=0.25, band=(70.0, 700.0),
                  ntau=0.02, modes=[(1.59, 0.35, 0.6), (2.30, 0.25, 0.4), (3.1, 0.12, 0.3)], lp=700.0),
}


def drum(kind: str, vel: float, rng: np.random.Generator) -> np.ndarray:
    p = DRUMS[kind]
    n = samples(p["dur"])
    t = time_axis(n)
    f_hi = p["f_hi"] * (0.88 + 0.12 * vel)
    f = p["f_lo"] + (f_hi - p["f_lo"]) * np.exp(-t / p["sweep"])
    ph = _phase(f)
    out = np.exp(-t / p["decay"]) * np.sin(ph)
    for ratio, a, dmul in p["modes"]:
        out += a * np.exp(-t / (p["decay"] * dmul)) * np.sin(ratio * ph + rng.uniform(0.0, TAU))
    nz = bandpass(rng.standard_normal(n), *p["band"]) * np.exp(-t / p["ntau"])
    out = out + p["noise"] * np.sqrt(max(vel, 0.05)) * nz * 2.0
    if "lp" in p:
        out = lowpass(out, p["lp"], 2)
    out = ramp_in(out, 0.0015)
    out = fade_out(out, 0.08)
    return out * vel


def woodblock(freq: float, vel: float, rng: np.random.Generator, decay: float = 0.03,
              ratios=(1.0, 2.71, 4.53), amps=(1.0, 0.45, 0.18), click: float = 0.35) -> np.ndarray:
    """Wooden bar/slit idiophone (muyu, rim click, clapper): a few fast-decaying modes + a contact click."""
    n = samples(decay * 9 + 0.03)
    t = time_axis(n)
    out = np.zeros(n)
    for r, a, dm in zip(ratios, amps, (1.0, 0.55, 0.35, 0.25)):
        f = freq * r * (1.0 + rng.uniform(-0.004, 0.004))
        if f < 0.45 * SR:
            out += a * np.exp(-t / (decay * dm)) * np.sin(TAU * f * t)
    cn = min(n, samples(0.004))
    out[:cn] += click * highpass(rng.standard_normal(cn), 1500.0, 2) * exp_decay(cn, 0.0008)
    out = ramp_in(out, 0.0004)
    return fade_out(out, 0.01) * vel


def clapper(vel: float, rng: np.random.Generator) -> np.ndarray:
    """Bangzi / paiban clapper: hard high wooden clack."""
    return woodblock(2350.0, vel, rng, decay=0.016, ratios=(1.0, 1.73, 2.61), amps=(1.0, 0.6, 0.35), click=0.9)


def rim(vel: float, rng: np.random.Generator) -> np.ndarray:
    """Drum-rim / drum-body 'ka' stroke."""
    return woodblock(1250.0, vel, rng, decay=0.018, ratios=(1.0, 2.31, 3.9), amps=(1.0, 0.5, 0.3), click=0.7)


# =============================================================================================== metals

GONG_RATIOS = [1.0, 1.43, 1.79, 2.25, 2.59, 2.96, 3.42, 3.88, 4.39, 4.97, 5.61, 6.33, 7.12, 8.01, 9.05,
               10.3, 11.6, 13.1, 14.8, 16.7]


def gong(f0: float, dur: float, vel: float, rng: np.random.Generator, glide: float = -0.8, glide_tau: float = 0.6,
         decay: float = 3.5, bloom: float = 1.0, bright: float = 1.0) -> np.ndarray:
    """Chinese gong: inharmonic partial pairs (slow beating), bloom of the upper partials, pitch glide
    (big opera gong falls, small gong rises), mallet thud and a shimmering noise band."""
    n = samples(dur)
    t = time_axis(n)
    semis = glide * (1.0 - np.exp(-t / glide_tau))
    ph = _phase(f0 * 2.0 ** (semis / 12.0))
    out = np.zeros(n)
    for r in GONG_RATIOS:
        f = f0 * r
        if f * 1.1 > 0.45 * SR:
            break
        a = rng.uniform(0.6, 1.0) / r ** 0.55 * np.exp(-f / (5500.0 * bright))
        d = decay / (1.0 + 0.16 * (r - 1.0)) * rng.uniform(0.8, 1.2)
        att = 0.004 + bloom * 0.035 * max(0.0, r - 2.0)
        env = (1.0 - np.exp(-t / att)) * np.exp(-t / d)
        beat = rng.uniform(0.25, 2.2) / f
        out += a * env * (np.sin(r * ph + rng.uniform(0, TAU)) + 0.6 * np.sin(r * (1.0 + beat) * ph + rng.uniform(0, TAU)))
    thud_n = min(n, samples(0.4))
    tt = time_axis(thud_n)
    out[:thud_n] += 0.25 * np.exp(-tt / 0.07) * np.sin(TAU * max(f0 * 0.5, 70.0) * tt)
    sn = min(n, samples(0.06))
    out[:sn] += 0.5 * lowpass(rng.standard_normal(sn), 1800.0) * exp_decay(sn, 0.015)
    shimmer = bandpass(rng.standard_normal(n), 2000.0, 6500.0) * (1.0 - np.exp(-t / 0.25)) * np.exp(-t / (decay * 0.4))
    out += 0.06 * bright * shimmer
    out = ramp_in(out, 0.001)
    out = fade_out(out, dur * 0.4)
    return out * vel


def cymbal(dur: float, vel: float, rng: np.random.Generator, decay: float = 1.1, low: float = 350.0) -> np.ndarray:
    """Bo / nao crash cymbals: dense inharmonic partials plus noise."""
    n = samples(dur)
    t = time_axis(n)
    out = np.zeros(n)
    for f in np.exp(rng.uniform(np.log(low), np.log(9800.0), 70)):
        a = rng.uniform(0.2, 1.0) * (f / 1000.0) ** -0.25
        d = decay * rng.uniform(0.35, 1.1) * (1000.0 / f) ** 0.25
        out += a * np.exp(-t / d) * np.sin(TAU * f * t + rng.uniform(0, TAU))
    out /= 6.0
    out += 0.6 * highpass(rng.standard_normal(n), 2500.0, 2) * np.exp(-t / (decay * 0.55))
    out += 0.7 * bandpass(rng.standard_normal(n), 400.0, 3000.0) * np.exp(-t / 0.05)
    out = ramp_in(out, 0.0008)
    return fade_out(out, dur * 0.4) * vel


BELL_PARTIALS = [(0.5, 0.30, 1.6), (1.0, 1.0, 1.0), (1.19, 0.50, 0.75), (1.51, 0.30, 0.6), (2.0, 0.42, 0.5),
                 (2.52, 0.20, 0.36), (2.68, 0.16, 0.32), (3.01, 0.12, 0.28), (4.07, 0.08, 0.2), (5.2, 0.05, 0.15)]


def bell(f0: float, dur: float, vel: float, rng: np.random.Generator, decay: float = 2.0) -> np.ndarray:
    """Bronze bell / chime (bianzhong-like minor-third bell spectrum) with slow beating partial pairs."""
    n = samples(dur)
    t = time_axis(n)
    out = np.zeros(n)
    for r, a, dm in BELL_PARTIALS:
        f = f0 * r
        if f * 1.01 > 0.45 * SR:
            continue
        beat = rng.uniform(0.4, 1.6)
        env = np.exp(-t / (decay * dm))
        out += a * env * (np.sin(TAU * f * t) + 0.5 * np.sin(TAU * (f + beat) * t + rng.uniform(0, TAU)))
    sn = min(n, samples(0.01))
    out[:sn] += 0.3 * highpass(rng.standard_normal(sn), 2000.0) * exp_decay(sn, 0.002)
    out = ramp_in(out, 0.0015)
    return fade_out(out, dur * 0.35) * vel


BAR_MODES = [1.0, 2.756, 5.404, 8.933, 13.344]


def clang(f0: float, dur: float, vel: float, rng: np.random.Generator, decay: float = 0.7, extra: int = 8,
          noise_amt: float = 0.6) -> np.ndarray:
    """Steel blade strike: free-bar modes + scattered plate partials, impact noise and a short scrape."""
    n = samples(dur)
    t = time_axis(n)
    out = np.zeros(n)
    for i, r in enumerate(BAR_MODES):
        f = f0 * r * (1.0 + rng.uniform(-0.01, 0.01))
        if f > 0.44 * SR:
            break
        d = decay / (1.0 + 0.5 * i)
        out += (1.0 / (1.0 + 0.6 * i)) * np.exp(-t / d) * (np.sin(TAU * f * t) + 0.4 * np.sin(TAU * (f + rng.uniform(1, 4)) * t))
    for f in np.exp(rng.uniform(np.log(1800.0), np.log(7500.0), extra)):
        out += rng.uniform(0.15, 0.45) * np.exp(-t / (decay * rng.uniform(0.2, 0.6))) * np.sin(TAU * f * t + rng.uniform(0, TAU))
    hn = min(n, samples(0.012))
    out[:hn] += noise_amt * 2.0 * highpass(rng.standard_normal(hn), 900.0) * exp_decay(hn, 0.003)
    sc = min(n, samples(0.09))
    out[:sc] += noise_amt * 0.5 * bandpass(rng.standard_normal(sc), 3000.0, 8000.0) * np.linspace(1.0, 0.0, sc)
    out = ramp_in(out, 0.0005)
    return fade_out(out, min(0.2, dur * 0.25)) * vel


# =============================================================================================== noises

def swept_noise(dur: float, f_start: float, f_end: float, rng: np.random.Generator, bands: int = 10,
                q: float = 3.0, shape: float = 1.0) -> np.ndarray:
    """Noise whose spectral centre glides from f_start to f_end (crossfaded resonant bands)."""
    n = samples(dur)
    t = time_axis(n) / max(dur, 1e-6)
    src = rng.standard_normal(n)
    out = np.zeros(n)
    centres = np.geomspace(f_start, f_end, bands)
    width = 1.3 / bands
    for i, fc in enumerate(centres):
        pos = (i / max(1, bands - 1)) ** shape
        env = np.exp(-0.5 * ((t - pos) / width) ** 2)
        out += resonate(src, min(fc, 0.45 * SR), q) * env
    return out


def crackle(dur: float, rate: float, rng: np.random.Generator, lo: float = 1800.0) -> np.ndarray:
    """Fire crackle: sparse random snaps with heavy-tailed amplitudes."""
    n = samples(dur)
    out = np.zeros(n)
    count = int(rate * dur)
    for _ in range(count):
        pos = int(rng.uniform(0, n))
        ln = samples(rng.uniform(0.001, 0.005))
        if ln < 4:
            continue
        snap = highpass(rng.standard_normal(ln), lo, 2) * exp_decay(ln, ln / SR / 3.0)
        mix_at(out, snap, pos, rng.pareto(2.5) * 0.4 + 0.1)
    return out


def shout(dur: float, f0: float, vel: float, rng: np.random.Generator, vowel=(750.0, 1150.0, 2500.0)) -> np.ndarray:
    """One warrior's shout ('Ha!'): glottal harmonic source with jitter through vowel formants."""
    n = samples(dur)
    t = time_axis(n)
    x = t / dur
    semis = 3.0 * np.sin(np.pi * np.clip(x * 1.2, 0, 1)) - 4.0 * x ** 2 + 0.25 * slow_noise(rng, n, 8.0)
    f = f0 * 2.0 ** (semis / 12.0)
    ph = _phase(f)
    src = np.zeros(n)
    for h in range(1, 40):
        if f0 * h * 1.3 > 0.45 * SR:
            break
        src += (1.0 / h ** 1.1) * np.sin(h * ph + rng.uniform(0, TAU))
    src += 0.3 * rng.standard_normal(n)
    out = np.zeros(n)
    for fc, qq, g in zip(vowel, (6.0, 8.0, 10.0), (1.0, 0.7, 0.35)):
        out += g * resonate(src, fc * rng.uniform(0.93, 1.07), qq)
    env = np.sin(np.pi * np.clip(x, 0, 1)) ** 0.6 * np.exp(-1.2 * x)
    env = ramp_in(env, 0.03)
    return out * env * vel

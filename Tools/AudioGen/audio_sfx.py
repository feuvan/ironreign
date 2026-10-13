"""Iron Reign sound effects (each < 2 s). Every function takes a seeded numpy Generator and returns float audio;
make_audio.py adds the room, trims, fades and peak-normalises them."""
from __future__ import annotations

import numpy as np

import audiolib_instruments as ins
from audiolib_dsp import (SR, bandpass, exp_decay, lowpass, midi_hz, mix_at, ramp_in, resonate, samples,
                          time_axis)


def _buf(seconds: float) -> np.ndarray:
    return np.zeros(samples(seconds))


def _hz(midi: float) -> float:
    return float(midi_hz(midi))


def click(rng):
    """UI tick: small high wood block."""
    out = _buf(0.12)
    mix_at(out, ins.woodblock(1900.0, 1.0, rng, decay=0.011, ratios=(1.0, 2.31, 3.92), amps=(1.0, 0.4, 0.15),
                              click=0.5), 0)
    return out


def confirm(rng):
    """Positive confirm: wood tap + two rising guzheng notes (zhi -> gong)."""
    out = _buf(0.75)
    mix_at(out, ins.woodblock(1450.0, 0.5, rng, decay=0.02), 0)
    mix_at(out, ins.pluck(_hz(69), 0.7, 0.75, "guzheng", rng=rng), 0)
    mix_at(out, ins.pluck(_hz(74), 0.65, 0.95, "guzheng", rng=rng), samples(0.075))
    return out


def cancel(rng):
    """Back / cancel: two falling, damped notes and a low knock."""
    out = _buf(0.45)
    mix_at(out, ins.pluck(_hz(74), 0.2, 0.6, "pipa", rng=rng, damp_at=0.1), 0)
    mix_at(out, ins.pluck(_hz(69), 0.35, 0.65, "pipa", rng=rng, damp_at=0.22), samples(0.085))
    mix_at(out, ins.woodblock(820.0, 0.45, rng, decay=0.025), 0)
    return out


def end_turn(rng):
    """End of the planning phase: medium gong."""
    out = _buf(1.95)
    mix_at(out, ins.gong(150.0, 1.95, 1.0, rng, glide=-0.5, decay=1.7, bloom=0.7), 0)
    return out


def march(rng):
    """Armies set out: accelerating hall-drum roll into a big accent."""
    out = _buf(1.8)
    t = 0.0
    gap = 0.11
    i = 0
    while t < 1.18:
        v = 0.3 + 0.6 * (t / 1.18) ** 1.3
        mix_at(out, ins.drum("tanggu", v * (0.9 if i % 2 else 1.0), rng), samples(t))
        t += gap
        gap = max(0.06, gap * 0.95)
        i += 1
    mix_at(out, ins.drum("taiko", 1.0, rng), samples(1.22))
    mix_at(out, ins.drum("tanggu", 0.9, rng), samples(1.22))
    return out


def attack(rng):
    """Melee: battle cry of a squad, clashing blades, a drum hit and trampling dust."""
    out = _buf(1.6)
    mix_at(out, 0.8 * ins.drum("taiko", 1.0, rng), 0)
    for _ in range(11):
        start = rng.uniform(0.0, 0.16)
        mix_at(out, ins.shout(rng.uniform(0.5, 0.8), rng.uniform(95.0, 190.0), rng.uniform(0.25, 0.45), rng),
               samples(start))
    for _ in range(6):
        start = rng.uniform(0.08, 0.75)
        mix_at(out, ins.clang(rng.uniform(480.0, 1100.0), 0.5, rng.uniform(0.25, 0.6), rng, decay=0.2, extra=4),
               samples(start))
    n = len(out)
    dust = bandpass(rng.standard_normal(n), 150.0, 1200.0) * np.exp(-time_axis(n) / 0.5)
    out += 0.15 * dust
    return out


def arrow(rng):
    """Arrow volley: bowstring thrums, a cloud of whooshes, scattered impacts."""
    out = _buf(1.6)
    for _ in range(5):
        mix_at(out, ins.pluck(rng.uniform(85.0, 140.0), 0.3, 0.6, "ruan", rng=rng, damp_at=0.12),
               samples(rng.uniform(0.0, 0.05)))
    for _ in range(16):
        dur = rng.uniform(0.45, 0.7)
        w = ins.swept_noise(dur, rng.uniform(3800.0, 5200.0), rng.uniform(700.0, 1100.0), rng, bands=8, q=4.0)
        w *= np.sin(np.pi * np.linspace(0.0, 1.0, len(w))) ** 2
        mix_at(out, w, samples(rng.uniform(0.04, 0.45)), rng.uniform(0.12, 0.25))
    for _ in range(9):
        mix_at(out, ins.woodblock(rng.uniform(260.0, 520.0), rng.uniform(0.25, 0.6), rng, decay=0.02, click=0.6),
               samples(rng.uniform(0.7, 1.25)))
    return out


def fire(rng):
    """Fire attack: ignition whoosh, roaring body and crackle."""
    n = samples(1.85)
    t = time_axis(n)
    out = np.zeros(n)
    swell = ins.swept_noise(1.0, 250.0, 3200.0, rng, bands=10, q=1.6, shape=0.8)
    swell *= np.sin(np.pi * np.clip(np.linspace(0.0, 1.0, len(swell)) * 1.1, 0, 1)) ** 1.5
    mix_at(out, swell, 0, 0.6)
    roar = lowpass(rng.standard_normal(n), 380.0, 2) * (1.0 - np.exp(-t / 0.15)) * np.exp(-t / 1.1)
    out += 2.2 * roar
    body = bandpass(rng.standard_normal(n), 500.0, 2500.0) * (1.0 - np.exp(-t / 0.25)) * np.exp(-t / 0.8)
    out += 0.35 * body
    cr = ins.crackle(1.85, 55.0, rng) * np.clip(t / 0.3, 0.0, 1.0) * np.exp(-t / 1.4)
    out += 0.7 * cr
    return out


def confuse(rng):
    """Confusion stratagem: wobbling, detuned cluster sliding down, a glassy bell and a rising breath."""
    n = samples(1.6)
    t = time_axis(n)
    out = np.zeros(n)
    for m in (69.0, 72.4, 75.0, 78.2):
        rate = rng.uniform(3.0, 7.0)
        semis = -5.0 * (t / 1.6) ** 1.5 + 0.6 * np.sin(2.0 * np.pi * rate * t + rng.uniform(0, 6.28))
        ph = 2.0 * np.pi * np.cumsum(_hz(m) * 2.0 ** (semis / 12.0)) / SR
        env = np.sin(np.pi * np.clip(t / 1.6, 0, 1)) ** 0.8
        out += 0.25 * env * (np.sin(ph) + 0.3 * np.sin(2.0 * ph + 0.5) + 0.15 * np.sin(3.0 * ph))
    mix_at(out, ins.bell(1320.0, 1.4, 0.35, rng, decay=0.9), 0)
    breath = bandpass(rng.standard_normal(n), 900.0, 4000.0) * np.clip(t / 0.5, 0, 1) * np.exp(-t / 0.7)
    out += 0.12 * breath
    return out


def rally(rng):
    """Rally: a war horn calls (two horns, rising inflection) over a drum stroke."""
    out = _buf(1.75)
    mix_at(out, ins.drum("dagu", 0.9, rng), 0)
    for midi, start, vel in ((50, 0.03, 1.0), (57, 0.12, 0.7)):
        events = [dict(start=start, dur=1.15 - start, midi=midi, vel=vel, orn="/", grace=None, lower=midi - 3)]
        sig, t0 = ins.line(events, "horn", rng)
        mix_at(out, sig, samples(max(0.0, t0)))
    return out


def gate_hit(rng):
    """Battering ram against a gate: deep thud, splintering wood, falling debris."""
    n = samples(1.3)
    t = time_axis(n)
    out = np.zeros(n)
    f = 72.0 + 60.0 * np.exp(-t / 0.035)
    out += 0.35 * np.exp(-t / 0.14) * np.sin(2.0 * np.pi * np.cumsum(f) / SR)
    src = rng.standard_normal(n) * np.exp(-t / 0.06)
    for fc, q, g in ((118.0, 5.0, 1.0), (186.0, 6.0, 0.9), (305.0, 6.0, 0.9), (520.0, 5.0, 0.8), (870.0, 4.0, 0.6),
                     (1400.0, 3.0, 0.4)):
        out += g * resonate(src, fc, q) * 6.0
    out += 1.6 * bandpass(rng.standard_normal(n), 300.0, 3500.0) * np.exp(-t / 0.03)
    debris = ins.crackle(1.3, 28.0, rng, lo=900.0) * np.clip((t - 0.06) / 0.05, 0, 1) * np.exp(-t / 0.4)
    out += 0.35 * debris
    return ramp_in(out, 0.001)


def sword(rng):
    """Duel strike: two blades meet."""
    out = _buf(1.3)
    mix_at(out, ins.clang(690.0, 1.3, 1.0, rng, decay=0.6), 0)
    mix_at(out, ins.clang(935.0, 1.2, 0.7, rng, decay=0.5), samples(0.004))
    return out


def guard(rng):
    """Duel guard: a blade stopped by a shield - dull metal, wood thunk."""
    out = _buf(0.6)
    mix_at(out, ins.clang(420.0, 0.5, 0.55, rng, decay=0.12, extra=3, noise_amt=0.8), 0)
    mix_at(out, ins.woodblock(210.0, 0.9, rng, decay=0.05, click=0.8), 0)
    mix_at(out, ins.drum("tanggu", 0.45, rng), 0)
    return out


def event(rng):
    """Event popup: two bronze chime bells (zhi then gong)."""
    out = _buf(1.9)
    mix_at(out, ins.bell(_hz(81), 1.9, 0.8, rng, decay=1.3), 0)
    mix_at(out, ins.bell(_hz(86), 1.7, 0.7, rng, decay=1.2), samples(0.2))
    return out


def coins(rng):
    """Gold: a handful of bronze cash coins clinking."""
    n = samples(0.85)
    out = np.zeros(n)
    times = np.sort(rng.uniform(0.0, 0.42, 10) ** 1.3)
    for tt in times:
        ln = samples(0.2)
        tl = time_axis(ln)
        c = np.zeros(ln)
        for f in rng.uniform(2600.0, 8200.0, 4):
            c += rng.uniform(0.3, 1.0) * np.exp(-tl / rng.uniform(0.02, 0.09)) * np.sin(2.0 * np.pi * f * tl)
        c[: samples(0.003)] += 0.4 * rng.standard_normal(samples(0.003))
        mix_at(out, ramp_in(c, 0.0005), samples(tt), rng.uniform(0.4, 1.0))
    out += 0.05 * bandpass(rng.standard_normal(n), 3000.0, 8000.0) * exp_decay(n, 0.2)
    return out


def victory(rng):
    """Battle won: rising small gong and a quick pentatonic run up to a bright dyad."""
    out = _buf(1.9)
    mix_at(out, ins.gong(330.0, 1.9, 0.6, rng, glide=2.5, glide_tau=0.08, decay=1.0, bloom=0.3), 0)
    for i, m in enumerate((62, 64, 66, 69, 71, 74)):
        mix_at(out, ins.pluck(_hz(m), 1.5, 0.7 + 0.05 * i, "guzheng", rng=rng), samples(0.06 + 0.065 * i))
    mix_at(out, ins.pluck(_hz(81), 1.3, 0.9, "guzheng", rng=rng), samples(0.5))
    mix_at(out, ins.drum("taiko", 0.8, rng), samples(0.5))
    return out


def defeat(rng):
    """Battle lost: low falling gong and a descending guqin line."""
    out = _buf(1.9)
    mix_at(out, ins.gong(88.0, 1.9, 0.8, rng, glide=-1.5, decay=1.5, bright=0.7), 0)
    for i, m in enumerate((57, 55, 52, 50, 47)):
        mix_at(out, ins.pluck(_hz(m), 1.4, 0.85, "guqin", rng=rng), samples(0.1 + 0.2 * i))
    return out


# name -> (function, length seconds, reverb send, fade-out seconds)
SFX = {
    "Sfx_Click": (click, 0.12, 0.0, 0.02),
    "Sfx_Confirm": (confirm, 0.75, 0.12, 0.15),
    "Sfx_Cancel": (cancel, 0.45, 0.08, 0.1),
    "Sfx_EndTurn": (end_turn, 1.95, 0.15, 0.35),
    "Sfx_March": (march, 1.8, 0.12, 0.3),
    "Sfx_Attack": (attack, 1.6, 0.15, 0.3),
    "Sfx_Arrow": (arrow, 1.6, 0.12, 0.25),
    "Sfx_Fire": (fire, 1.85, 0.1, 0.4),
    "Sfx_Confuse": (confuse, 1.6, 0.3, 0.3),
    "Sfx_Rally": (rally, 1.75, 0.2, 0.3),
    "Sfx_GateHit": (gate_hit, 1.3, 0.12, 0.3),
    "Sfx_Sword": (sword, 1.3, 0.15, 0.3),
    "Sfx_Guard": (guard, 0.6, 0.1, 0.15),
    "Sfx_Event": (event, 1.9, 0.25, 0.35),
    "Sfx_Coins": (coins, 0.85, 0.1, 0.2),
    "Sfx_Victory": (victory, 1.9, 0.2, 0.35),
    "Sfx_Defeat": (defeat, 1.9, 0.2, 0.4),
}

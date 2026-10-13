"""Score helpers: jianpu (numbered notation) parsing, pentatonic arpeggios, performers and the stem mixer.

Jianpu tokens (whitespace separated, '|' bar lines are ignored):
    <degree><octave marks>[:<beats>]<ornaments>
    degree 1-7 (0 = rest), "'" = octave up, "," = octave down, beats = duration (default: previous duration),
    "-" extends the previous note by one beat.
    Ornaments: '~' vibrato (pressing/wide), '^' grace note from the upper pentatonic neighbour, '/' slide up
    from the lower neighbour, '\\' fall to the lower neighbour, '*' tremolo, '>' accent, '!' damped
    (staccato), '+' bend up a semitone (tension).
Pentatonic degrees: 1 gong, 2 shang, 3 jue, 5 zhi, 6 yu.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

import audiolib_instruments as ins
from audiolib_dsp import (SR, convolve, fade_out, from_db, highpass, loudness, midi_hz, normalize_loudness, peak,
                          samples, to_db)

DEGREE_SEMIS = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}
PENT = [0, 2, 4, 7, 9]
DEGREE_PENT = {1: 0, 2: 1, 3: 2, 5: 3, 6: 4}
_TOKEN = re.compile(r"^([0-7])([',]*)(?::([0-9]*\.?[0-9]+))?([~^/\\*>!+]*)$")


@dataclass
class Note:
    start: float  # beats
    dur: float  # beats
    midi: int
    vel: float
    orn: str
    grace: int
    lower: int


def pent_neighbour(midi: int, key: int, direction: int) -> int:
    m = midi + direction
    while (m - key) % 12 not in PENT:
        m += direction
    return m


def pent_midi(index: int, key: int) -> int:
    """Pentatonic scale step index (0 = degree 1 of the key octave, 5 = 1', -1 = 6,) -> MIDI note."""
    octave, step = divmod(index, 5)
    return key + 12 * octave + PENT[step]


def degree_index(text: str) -> int:
    """'6,' -> -1, '1' -> 0, "2'" -> 6 (pentatonic step index)."""
    deg = int(text[0])
    return DEGREE_PENT[deg] + 5 * (text.count("'") - text.count(","))


def jianpu(text: str, key: int, start: float = 0.0, vel: float = 0.8) -> list[Note]:
    notes: list[Note] = []
    t = start
    dur = 1.0
    last: Note | None = None
    for tok in text.replace("|", " ").split():
        if tok == "-":
            if last is not None:
                last.dur += 1.0
            t += 1.0
            continue
        m = _TOKEN.match(tok)
        if not m:
            raise ValueError(f"bad jianpu token {tok!r}")
        deg = int(m.group(1))
        octaves = m.group(2).count("'") - m.group(2).count(",")
        if m.group(3):
            dur = float(m.group(3))
        orn = m.group(4)
        if deg == 0:
            last = None
            t += dur
            continue
        midi = key + 12 * octaves + DEGREE_SEMIS[deg]
        v = min(1.0, vel * (1.18 if ">" in orn else 1.0))
        last = Note(t, dur, midi, v, orn, pent_neighbour(midi, key, 1), pent_neighbour(midi, key, -1))
        notes.append(last)
        t += dur
    return notes


def bars(text: str) -> str:
    """Allows multi-line scores with comments (# ...)."""
    return " ".join(line.split("#")[0] for line in text.strip().splitlines())


def arpeggio(roots, key: int, pattern, beats_per_step: float, start_bar: int = 0, bar_beats: float = 4.0,
             vel: float = 0.6, accent=None, vel_curve=None, orn: str = "") -> list[Note]:
    """Pentatonic arpeggio: for each bar root (jianpu text like '6,'), plays pattern = pentatonic step offsets."""
    notes = []
    steps_per_bar = int(round(bar_beats / beats_per_step))
    for b, root in enumerate(roots):
        if root is None:
            continue
        base = degree_index(root)
        pat = pattern[b % len(pattern)] if isinstance(pattern[0], (list, tuple)) else pattern
        bar_vel = vel * (vel_curve[b] if vel_curve is not None else 1.0)
        for s in range(steps_per_bar):
            off = pat[s % len(pat)]
            if off is None:
                continue
            midi = pent_midi(base + off, key)
            v = bar_vel * (accent[s % len(accent)] if accent else (1.0 if s == 0 else 0.85))
            notes.append(Note((start_bar + b) * bar_beats + s * beats_per_step, beats_per_step, midi, v, orn,
                              pent_neighbour(midi, key, 1), pent_neighbour(midi, key, -1)))
    return notes


# =============================================================================================== mixer

class Mix:
    """Stem buffers on a timeline. Loops are rendered circularly: everything that rings past the loop end
    (notes, gong tails, reverb) is folded back onto the start, so the file loops without a seam."""

    def __init__(self, length: float, tempo: float, loop: bool = True, tail: float = 11.0, seed: int = 1):
        self.length = samples(length)
        self.tempo = tempo
        self.loop = loop
        self.total = self.length + samples(tail)
        self.stems: dict[str, np.ndarray] = {}
        self.rng = np.random.default_rng(seed)

    def beat(self, beats: float) -> float:
        return beats * 60.0 / self.tempo

    def bar(self, bar: float, beat: float = 0.0, bar_beats: float = 4.0) -> float:
        """Seconds at (0-based bar, 0-based beat)."""
        return self.beat(bar * bar_beats + beat)

    def add(self, stem: str, start: float, sig: np.ndarray, gain: float = 1.0) -> None:
        buf = self.stems.setdefault(stem, np.zeros(self.total))
        i = int(round(start * SR))
        if self.loop:
            i %= self.length
        if i < 0:
            sig = sig[-i:]
            i = 0
        end = min(self.total, i + len(sig))
        if end > i:
            buf[i:end] += gain * sig[: end - i]

    # ------------------------------------------------------------------ performers

    def plucks(self, stem: str, notes, preset: str, vel: float = 1.0, ring: float = 2.5, human: float = 0.006,
               trem_rate: float = 12.8, offset: float = 0.0) -> None:
        rng = self.rng
        for nt in notes:
            start = offset + self.beat(nt.start) + (rng.normal(0.0, human) if human > 0 else 0.0)
            d = self.beat(nt.dur)
            f = float(midi_hz(nt.midi))
            v = nt.vel * vel * (0.94 + 0.06 * rng.random())
            if "*" in nt.orn:
                self.add(stem, start, ins.tremolo(f, d, v, rng, preset, rate=trem_rate))
                continue
            bend = []
            if "/" in nt.orn:
                lo = nt.lower - nt.midi
                bend += [(0.0, lo), (0.07, lo), (0.22, 0.0)]
            if "+" in nt.orn:
                bend += [(0.0, 0.0), (min(0.25, d * 0.4), 0.0), (min(0.25, d * 0.4) + 0.12, 1.0)]
            if "\\" in nt.orn:
                at = max(0.3, d * 0.55)
                bend = (bend or [(0.0, 0.0)]) + [(at, 0.0), (at + 0.25, nt.lower - nt.midi)]
            vib = 0.28 if "~" in nt.orn else 0.0
            damped = "!" in nt.orn
            length = d if damped else max(d, ring)
            sig = ins.pluck(f, length, v, preset, bend=bend or None, vib=vib, rng=rng,
                            damp_at=d * 0.85 if damped else None)
            self.add(stem, start, sig)

    def line(self, stem: str, notes, kind: str, vel: float = 1.0, offset: float = 0.0) -> None:
        """Continuous instrument; notes separated by >= 2 beats of rest are rendered as separate phrases."""
        if not notes:
            return
        phrases = [[notes[0]]]
        for nt in notes[1:]:
            prev = phrases[-1][-1]
            if nt.start - (prev.start + prev.dur) >= 2.0:
                phrases.append([nt])
            else:
                phrases[-1].append(nt)
        for ph in phrases:
            events = [dict(start=offset + self.beat(nt.start), dur=self.beat(nt.dur), midi=nt.midi,
                           vel=nt.vel * vel, orn=nt.orn, grace=nt.grace, lower=nt.lower) for nt in ph]
            sig, t0 = ins.line(events, kind, self.rng)
            self.add(stem, t0, sig)

    def hits(self, stem: str, times_vels, maker, variants: int = 4, human: float = 0.004) -> None:
        """Percussion hits; maker(vel=1, rng) is pre-rendered in a few variants and scaled per hit."""
        rng = self.rng
        cache = [maker(1.0, np.random.default_rng(int(rng.integers(1 << 30)))) for _ in range(variants)]
        for t, v in times_vels:
            sig = cache[int(rng.integers(variants))]
            self.add(stem, t + (rng.normal(0.0, human) if human > 0 else 0.0), sig, v * (0.95 + 0.05 * rng.random()))

    def pattern(self, stem: str, bars_list, pattern: str, maker, vel: float = 1.0, steps: int = 16,
                bar_beats: float = 4.0, ghost: float = 0.35, soft: float = 0.65, variants: int = 4,
                crescendo: bool = False) -> None:
        """Step pattern per bar: 'X' accent, 'x' normal, 'o' soft, 'g' ghost, '.' rest."""
        events = []
        for b in bars_list:
            for s, ch in enumerate(pattern[:steps]):
                level = {"X": 1.0, "x": 0.78, "o": soft, "g": ghost}.get(ch)
                if level is None:
                    continue
                if crescendo:
                    level *= 0.45 + 0.55 * s / max(1, steps - 1)
                events.append((self.bar(b, s * bar_beats / steps, bar_beats), level * vel))
        self.hits(stem, events, maker, variants)

    # ------------------------------------------------------------------ render

    def render(self, levels: dict, sends: dict, ir: np.ndarray, target_lufs: float = -16.0,
               ceiling_db: float = -1.0, hpf: float = 40.0, report: bool = True) -> np.ndarray:
        """Balances stems by loudness (levels = relative LU per stem), adds reverb, folds loops, normalises."""
        dry = np.zeros(self.total)
        bus = np.zeros(self.total)
        stats = []
        for name, buf in self.stems.items():
            lk = loudness(buf)
            if not np.isfinite(lk):
                continue
            g = from_db(levels.get(name, -10.0) - lk)
            dry += g * buf
            bus += g * buf * sends.get(name, 0.2)
            stats.append((name, levels.get(name, -10.0), sends.get(name, 0.2)))
        wet = highpass(convolve(bus, ir), 140.0, 2)  # keep the low end of the reverb return clean
        mix = highpass(dry + wet, hpf, 2)
        if self.loop:
            y = mix[: self.length].copy()
            rest = mix[self.length:]
            while len(rest):
                chunk = rest[: self.length]
                y[: len(chunk)] += chunk
                rest = rest[self.length:]
            y -= np.mean(y)
        else:
            y = fade_out(mix[: self.length].copy(), 1.2)
        pre = y * from_db(target_lufs - loudness(y))
        y = normalize_loudness(y, target_lufs, ceiling_db, wrap=self.loop)
        if report:
            reduction = 20.0 * np.log10(np.maximum(np.abs(pre), 1e-9) / np.maximum(np.abs(y), 1e-9))
            loud = np.abs(pre) > from_db(ceiling_db - 6.0)
            print("      stems: " + ", ".join(f"{n} {lv:+.0f}LU/send {sd:.2f}" for n, lv, sd in stats))
            print(f"      limiter: pre-limit peak {to_db(peak(pre)):+.1f} dBFS, max reduction {reduction.max():.1f} dB, "
                  f"mean on loud samples {reduction[loud].mean() if loud.any() else 0.0:.2f} dB")
        return y

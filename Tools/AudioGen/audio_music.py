"""Iron Reign music: four seamless loops (title, strategy map, battle, duel) and two stings.

Every piece is written in jianpu over a pentatonic mode (gong/shang/jue/zhi/yu) with call-and-response
phrasing between the solo instruments. Bar numbers in comments are 1-based; Mix.bar() takes 0-based bars.
"""
from __future__ import annotations

import numpy as np

import audiolib_instruments as ins
from audiolib_dsp import make_ir, midi_hz
from audiolib_score import Mix, arpeggio, bars, jianpu, pent_midi

# Pentatonic step offsets from the bar root (see audiolib_score.arpeggio).
ROLL_UP = [0, 3, 5, 6, 7, 6, 5, 3]  # root, 5th, octave, 9th, 10th and back
FLOW = [0, 2, 3, 5, 6, 5, 3, 2]
SLOW = [0, 3, 5, 3]


def _guzheng_bass(mix: Mix, roots, key: int, vel: float, skip=(), stem: str = "guzheng_bass") -> None:
    notes = arpeggio([None if i in skip else r for i, r in enumerate(roots)], key - 12, [0], 4.0, vel=vel)
    mix.plucks(stem, notes, "guzheng", ring=3.5)


# =============================================================================================== title

def title() -> np.ndarray:
    """D gong mode, 64 BPM, 16 bars (60 s). Majestic: guqin call, dizi answer, guzheng, court drum, gong."""
    mix = Mix(60.0, 64.0, seed=101)
    d4, d5, d3 = 62, 74, 50
    guqin = jianpu(bars("""
        1:2/ 5,:1 6,:1 | 1:3~ 2:1 | 3:2 2:1 1:1 | 6,:2 5,:2~         # 1-4  call
        1,:4~ | 0:4 | 6,:4~ | 5,:4                                     # 5-8  low support under the dizi
        1,:4~ | 0:4 | 6,:4~ | 0:4                                      # 9-12
        5:2 6:1 1':1 | 2':1.5 1':0.5 6:1 5:1 | 3:1.5 5:0.5 2:1 3:1 | 1:4~   # 13-16 doubled by the dizi
    """), d3, vel=0.85)
    mix.plucks("guqin", guqin, "guqin", ring=4.5)

    dizi = jianpu(bars("""
        0:4 | 0:4 | 0:4 | 0:4
        5,:1.5 6,:0.5 1:2 | 2:1 3:1 2:1 1:0.5 6,:0.5 | 5,:3~ 6,:0.5 1:0.5 | 2:2 1:2~      # 5-8 answer
        3:1.5^ 5:0.5 6:1 5:1 | 0:4 | 6:1.5 1':0.5 2':1 1':0.5 6:0.5 | 0:4                   # 9-12 calls
        5:2 6:1 1':1 | 2':1.5^ 1':0.5 6:1 5:1 | 3:1.5 5:0.5 2:1 3:1 | 1:4~                   # 13-16
    """), d5, vel=0.85)
    mix.line("dizi", dizi, "dizi")

    # guzheng answers the dizi calls in bars 10 and 12
    mel = jianpu("3':0.5 2':0.5 1':0.5 6:0.5 5:2~", d4, start=36, vel=0.8)
    mel += jianpu("5':0.5 3':0.5 2':0.5 1':0.5 2':2~", d4, start=44, vel=0.8)
    mix.plucks("guzheng_mel", mel, "guzheng", ring=3.0)

    roots = ["1", "1", "6,", "5,", "1", "2", "5,", "1", "1", "5,", "6,", "2", "1", "2", "5,", "1"]
    slow = arpeggio(roots[:8], d4, SLOW, 1.0, vel=0.55, vel_curve=[1, 1, 1, 1, 0.7, 0.7, 0.7, 0.7])
    fast = arpeggio(roots[8:15], d4, ROLL_UP, 0.5, start_bar=8, vel=0.5,
                    vel_curve=[1.0, 0.8, 1.0, 0.8, 1.1, 1.1, 1.1])
    mix.plucks("guzheng", slow + fast, "guzheng", ring=2.6)
    _guzheng_bass(mix, roots, d4, 0.75, skip=(15,))
    # bar 16: two-octave glissando up into the gong of bar 1
    up = [float(midi_hz(pent_midi(i, d4))) for i in range(0, 11)]
    mix.add("guzheng", mix.bar(15, 2.0), ins.gliss(up, 0.075, 0.7, mix.rng, accel=0.4))
    mix.add("guzheng_bass", mix.bar(15, 0.0), ins.pluck(float(midi_hz(d3 - 12 + 7)), 3.0, 0.7, "guzheng", rng=mix.rng))

    drums = [(mix.bar(0), 1.0)]
    for b in range(1, 16):
        drums.append((mix.bar(b), 0.45 if 4 <= b < 8 else 0.62))
        if 8 <= b < 15:
            drums.append((mix.bar(b, 2.0), 0.33))
    drums += [(mix.bar(7, 3.0), 0.38), (mix.bar(7, 3.5), 0.5), (mix.bar(11, 3.5), 0.5)]
    mix.hits("drum", drums, lambda v, r: ins.drum("dagu", v, r))
    roll = [(mix.bar(15, 2.0 + i * 0.125), 0.25 + 0.7 * (i / 15.0) ** 1.5) for i in range(16)]
    mix.hits("roll", roll, lambda v, r: ins.drum("tanggu", v, r), variants=6)
    mix.add("gong", mix.bar(0), ins.gong(105.0, 9.0, 1.0, mix.rng, glide=-0.9, decay=4.0))
    mix.add("gong", mix.bar(8), ins.gong(118.0, 8.0, 0.6, mix.rng, glide=-0.7, decay=3.5))
    mix.add("cymbal", mix.bar(12), ins.cymbal(3.0, 0.5, mix.rng, decay=1.4))

    levels = {"dizi": -1, "guqin": -3, "guzheng_mel": -4, "guzheng": -6, "guzheng_bass": -10, "drum": -7,
              "roll": -9, "gong": -6, "cymbal": -15}
    sends = {"dizi": 0.38, "guqin": 0.3, "guzheng_mel": 0.35, "guzheng": 0.35, "guzheng_bass": 0.25, "drum": 0.2,
             "roll": 0.2, "gong": 0.25, "cymbal": 0.3}
    return mix.render(levels, sends, make_ir(2.4, 0.025, seed=11))


# =============================================================================================== strategy

def strategy() -> np.ndarray:
    """E yu mode (1 = G), 80 BPM, 24 bars (72 s). Calm map music: flowing guzheng, erhu lead, distant dizi."""
    mix = Mix(72.0, 80.0, seed=202)
    g4, g5, g2 = 67, 79, 43
    roots = ["6,", "1", "5,", "6,", "6,", "5,", "1", "6,", "6,", "1", "2", "6,",
             "6,", "1", "5,", "2", "6,", "1", "5,", "1", "6,", "1", "5,", "6,"]
    sparse = [0, None, 3, None, 5, None, 3, None]
    pats = []
    curve = []
    for b in range(24):
        if b in (6, 7, 10, 11):  # guzheng plays the answers itself: thin the arpeggio
            pats.append(sparse)
            curve.append(0.55)
        elif b == 23:
            pats.append([0, 3, 5, 6, None, None, None, None])
            curve.append(0.8)
        else:
            pats.append(ROLL_UP if b % 2 == 0 else FLOW)
            curve.append(1.0 if b < 4 else 0.72)
    arp = []
    for b in range(24):
        arp += arpeggio([roots[b]], g4, pats[b], 0.5, start_bar=b, vel=0.55, vel_curve=[curve[b]],
                        accent=[1.0, 0.8, 0.9, 0.8, 0.95, 0.8, 0.9, 0.8])
    mix.plucks("guzheng", arp, "guzheng", ring=2.4)
    _guzheng_bass(mix, roots, g4, 0.6)
    down = [float(midi_hz(pent_midi(i, g4))) for i in range(9, -2, -1)]
    mix.add("guzheng", mix.bar(23, 2.25), ins.gliss(down, 0.07, 0.5, mix.rng, accel=0.2))

    erhu = jianpu(bars("""
        0:4 | 0:4 | 0:4 | 0:4                                                         # 1-4 guzheng alone
        6,:1/ 1:0.5 2:0.5 3:2~ | 2:1 1:0.5 6,:0.5 5,:2~ | 0:4 | 0:4                    # 5-8 call (answer: guzheng)
        3:1.5 5:0.5 6:1 5:0.5 3:0.5 | 2:1 3:0.5 2:0.5 1:2~ | 0:4 | 0:4                 # 9-12
        6:2/ 1':1 2':1 | 3':3~ 2':0.5 3':0.5 | 5':1.5 3':0.5 2':1 1':1 | 2':4~          # 13-16 climb
        0:4 | 0:4 | 2:1 3:0.5 2:0.5 1:1 6,:1 | 5,:1.5 6,:0.5 1:2~                       # 17-20 answers the dizi
        6,:1 1:0.5 2:0.5 3:2~ | 5:1 3:0.5 2:0.5 3:2 | 2:1 1:0.5 2:0.5 3:1 2:0.5 1:0.5 | 6,:4~   # 21-24
    """), g4, vel=0.85)
    mix.line("erhu", erhu, "erhu")

    dizi = jianpu("3:1 5:1 6:2~ | 5:1 3:0.5^ 2:0.5 3:2~", g5, start=64, vel=0.7)
    mix.line("dizi", dizi, "dizi")

    mel = jianpu("6:0.5 1':0.5 2':0.5 3':0.5 2':1 6:1~ | 1':1 6:0.5 5:0.5 6:2~", g4, start=24, vel=0.75)
    mel += jianpu("2':0.5 3':0.5 5':1 3':0.5 2':0.5 1':1 | 6:1.5 5:0.5 6:2~", g4, start=40, vel=0.75)
    mix.plucks("guzheng_mel", mel, "guzheng", ring=2.8)

    guqin = []
    for b in (0, 8, 16, 20):
        guqin += jianpu("6,:4~", g2 + 12, start=b * 4, vel=0.7)
    guqin += jianpu("1:4/", g2 + 12, start=48, vel=0.6)
    mix.plucks("guqin", guqin, "guqin", ring=5.0)

    mix.hits("drum", [(mix.bar(b), 0.5) for b in (12, 14, 16, 18)], lambda v, r: ins.drum("dagu", v, r))
    mix.add("bell", mix.bar(0), ins.bell(float(midi_hz(76)), 5.0, 0.6, mix.rng, decay=2.6))
    mix.add("bell", mix.bar(12), ins.bell(float(midi_hz(79)), 5.0, 0.45, mix.rng, decay=2.4))

    levels = {"erhu": -1, "dizi": -4, "guzheng_mel": -4, "guzheng": -6, "guzheng_bass": -10, "guqin": -7,
              "drum": -13, "bell": -12}
    sends = {"erhu": 0.3, "dizi": 0.4, "guzheng_mel": 0.32, "guzheng": 0.3, "guzheng_bass": 0.25, "guqin": 0.3,
             "drum": 0.25, "bell": 0.45}
    return mix.render(levels, sends, make_ir(2.0, 0.022, seed=12))


# =============================================================================================== battle

TAIKO_MAIN = "X..x..x.X..x..x."
TAIKO_FILL = "X..x..x.X.x.x.xx"
TANGGU_MAIN = "....x.......x..."
TANGGU_FILL = "....x.......oxxX"
TANGGU_BIG = "....x...oxoxxxXX"
RIM_MAIN = "..g...g...g...gg"


def battle() -> np.ndarray:
    """A yu mode (1 = C), 128 BPM, 32 bars (60 s). War drums, gongs, pipa tremolo, dizi, ruan bass."""
    mix = Mix(60.0, 128.0, seed=303)
    c4, c5, c3 = 60, 72, 48
    roots = ["6,", "5,", "6,", "2", "1", "6,", "5,", "6,",
             "6,", "1", "5,", "3", "1", "2", "5,", "6,",
             "6,", "1", "6,", "5,", "1", "6,", "5,", "6,",
             "6,", "6,", "5,", "5,", "6,", "1", "2", "5,"]
    drive = [0, 0, 5, 0, 3, 0, 5, 3]
    bass_pats = [drive] * 24 + [[0, None, None, None, None, None, None, None]] * 4 + [drive] * 4
    bass = []
    for b in range(32):
        bass += arpeggio([roots[b]], c3, bass_pats[b], 0.5, start_bar=b, vel=0.8, orn="!",
                         accent=[1.0, 0.6, 0.85, 0.6, 0.9, 0.6, 0.85, 0.7])
    mix.plucks("bass", bass, "ruan", ring=0.5, human=0.003)

    pipa = jianpu(bars("""
        6:2* 1':1 6:1 | 5:1.5 3:0.5 5:2* | 6:1 1':1 2':1 3':1 | 2':4*            # 1-4   call
        3':2* 2':1 1':1 | 6:1.5 5:0.5 6:2* | 3:1 5:1 6:1 1':1 | 6:4*             # 5-8
        0:4 | 0:4 | 0:4 | 0:4 | 0:4 | 0:4 | 0:4 | 0:4                             # 9-16  dizi answers
        6:1 1':1 2':1 3':1 | 5':2* 3':1 5':1 | 6':2* 5':1 3':1 | 2':4*            # 17-20 together
        3':1.5 5':0.5 3':1 2':1 | 1':1 2':1 3':2* | 6:1 5:1 3:1 5:1 | 6:4*        # 21-24
        6:0.5> 6:0.5 0:0.5 1':0.5 6:1 0:1 | 0:4 | 5:0.5> 5:0.5 0:0.5 6:0.5 5:1 0:1 | 0:4   # 25-28 breakdown
        6:4* | 1':4* | 2':4* | 3':2* 5':2*                                         # 29-32 build
    """), c4, vel=0.85)
    mix.plucks("pipa", pipa, "pipa", ring=0.9, human=0.004)
    chops = []
    for b in range(8, 16):
        chops += arpeggio([roots[b]], c4, [None, 5, None, 5, None, 5, None, 5], 0.5, start_bar=b, vel=0.55, orn="!")
    mix.plucks("pipa_chops", chops, "pipa", ring=0.3, human=0.003)

    dizi = jianpu(bars("""
        0:32
        6:0.5 1':0.5 2':1 3':2~ | 5':1 3':0.5 2':0.5 3':2~ | 2':1 1':0.5 6:0.5 5:1 6:1 | 3':4~      # 9-12
        5':1.5^ 6':0.5 5':1 3':1 | 2':1 3':0.5 2':0.5 1':2~ | 6:1 1':1 2':1 3':0.5 2':0.5 | 6:4~    # 13-16
        6:1 1':1 2':1 3':1 | 5':2 3':1 5':1 | 6':2 5':1 3':1 | 2':4~                                # 17-20
        3':1.5 5':0.5 3':1 2':1 | 1':1 2':1 3':2 | 6:1 5:1 3:1 5:1 | 6:4~                           # 21-24
        0:4 | 3':0.5> 2':0.5 6:1 0:2 | 0:4 | 2':0.5> 1':0.5 5:1 0:2                                 # 25-28
        0:4 | 0:4 | 2':4~ | 3':2 5':2~                                                              # 29-32
    """), c5, vel=0.85)
    mix.line("dizi", dizi, "dizi")

    taiko = lambda v, r: ins.drum("taiko", v, r)  # noqa: E731
    tanggu = lambda v, r: ins.drum("tanggu", v, r)  # noqa: E731
    fills = {3, 11, 19}
    big_fills = {7, 15, 23}
    main = [b for b in range(24) if b not in fills | big_fills]
    mix.pattern("taiko", main + [28, 29, 30], TAIKO_MAIN, taiko)
    mix.pattern("taiko", sorted(fills | big_fills), TAIKO_FILL, taiko)
    mix.pattern("taiko", [24, 25, 26, 27], "X.......X.......", taiko)
    mix.pattern("taiko", [31], "X...X...X.X.XXXX", taiko)
    mix.pattern("tanggu", main, TANGGU_MAIN, tanggu)
    mix.pattern("tanggu", sorted(fills), TANGGU_FILL, tanggu)
    mix.pattern("tanggu", sorted(big_fills), TANGGU_BIG, tanggu)
    for i, b in enumerate((28, 29, 30)):
        mix.pattern("tanggu", [b], "x.x.x.x.x.x.x.x.", tanggu, vel=0.5 + 0.15 * i)
    mix.pattern("tanggu", [31], "xxxxxxxxxxxxxxxx", tanggu, crescendo=True)
    mix.pattern("rim", list(range(24)), RIM_MAIN, lambda v, r: ins.rim(v, r), vel=0.8)
    mix.pattern("rim", [24, 25, 26, 27], "..x...x...x...x.", lambda v, r: ins.rim(v, r), vel=0.9)

    for b, v in ((0, 1.0), (8, 0.75), (16, 1.0), (24, 0.65)):
        mix.add("gong", mix.bar(b), ins.gong(98.0, 7.0, v, mix.rng, glide=-1.0, decay=3.0))
    for b, v in ((0, 0.9), (8, 0.6), (16, 0.9), (24, 0.5)):
        mix.add("cymbal", mix.bar(b), ins.cymbal(2.5, v, mix.rng, decay=1.0))
    naos = [(mix.bar(b, beat), 0.7) for b in range(16, 24) for beat in (1.0, 3.0)]
    mix.hits("nao", naos, lambda v, r: ins.cymbal(0.35, v, r, decay=0.12, low=700.0), variants=3)

    levels = {"taiko": -2, "tanggu": -6, "rim": -13, "gong": -7, "cymbal": -11, "nao": -15, "bass": -6,
              "pipa": -2, "pipa_chops": -10, "dizi": -2}
    sends = {"taiko": 0.15, "tanggu": 0.15, "rim": 0.15, "gong": 0.25, "cymbal": 0.2, "nao": 0.15, "bass": 0.1,
             "pipa": 0.25, "pipa_chops": 0.2, "dizi": 0.3}
    return mix.render(levels, sends, make_ir(1.5, 0.015, seed=13))


# =============================================================================================== duel

def duel() -> np.ndarray:
    """D yu mode (1 = F), 80 BPM, 20 bars (60 s). Tense and sparse: heartbeat, guqin, pipa, clapper."""
    mix = Mix(60.0, 80.0, seed=404)
    f4, f3 = 65, 53
    beats = []
    for b in range(20):
        v = 0.6 if b < 8 else (0.7 + 0.03 * (b - 8) if b < 16 else 0.55)
        for beat in range(4):
            beats.append((mix.bar(b, beat), v))
            beats.append((mix.bar(b, beat) + 0.17, v * 0.62))
    mix.hits("heart", beats, lambda v, r: ins.drum("heart", v, r), human=0.002)

    guqin = jianpu(bars("""
        6,:4~ | 0:4 | 6,:2 5,:2\\ | 6,:4~           # 1-4
        0:4 | 3,:2 2,:2~ | 0:4 | 6,,:4~             # 5-8   answers the pipa
        6,:4 | 0:4 | 5,:4~ | 0:4                    # 9-12
        0:4 | 6,,:4~ | 0:4 | 5,,:2 6,,:2\\          # 13-16
        6,:4~ | 0:4 | 5,:2 3,:2 | 6,:4~             # 17-20
    """), f3, vel=0.85)
    mix.plucks("guqin", guqin, "guqin", ring=4.5)

    pipa = jianpu(bars("""
        0:16
        0:1 6,:0.5 1:0.5 2:2+ | 0:4 | 0:1 3:0.5 2:0.5 1:1 6,:1~ | 0:4               # 5-8   calls
        6,:2* 1:2* | 2:2* 3:2* | 5:4* | 6:2* 5:1! 3:1!                               # 9-12  rising tremolo
        6:0.5>! 0:1.5 6:0.5>! 0:1.5 | 0:4 | 1':0.5>! 6:0.5! 0:3 | 0:4                # 13-16 clashes
        0:2 6,:1 1:1 | 2:3+ 1:1 | 6,:4~ | 0:4                                         # 17-20
    """), f4, vel=0.8)
    mix.plucks("pipa", pipa, "pipa", ring=1.4, trem_rate=11.0)

    claps = [(mix.bar(9, 3.0), 0.7), (mix.bar(11, 3.0), 0.8), (mix.bar(12, 0.0), 1.0), (mix.bar(12, 2.0), 1.0),
             (mix.bar(14, 0.0), 0.9), (mix.bar(14, 0.5), 0.6), (mix.bar(15, 3.5), 0.7), (mix.bar(3, 3.5), 0.5)]
    mix.hits("clapper", claps, lambda v, r: ins.clapper(v, r))
    for b, v in ((8, 0.6), (16, 0.45), (12, 0.5)):
        mix.add("gong", mix.bar(b), ins.gong(370.0, 3.5, v, mix.rng, glide=2.5, glide_tau=0.08, decay=1.1, bloom=0.3))
    rolls = []
    for b in (11, 15):
        rolls += [(mix.bar(b, 2.0 + i * 0.125), 0.12 + 0.55 * (i / 15.0) ** 2) for i in range(16)]
    mix.hits("roll", rolls, lambda v, r: ins.drum("taiko", v, r), variants=5)

    levels = {"heart": -10, "guqin": -4, "pipa": -2, "clapper": -11, "gong": -10, "roll": -10}
    sends = {"heart": 0.05, "guqin": 0.35, "pipa": 0.32, "clapper": 0.35, "gong": 0.3, "roll": 0.2}
    return mix.render(levels, sends, make_ir(2.2, 0.03, seed=14))


# =============================================================================================== stings

def victory() -> np.ndarray:
    """12.5 s fanfare in D gong mode: drum roll, gong + court drum, dizi fanfare over guzheng, final chord."""
    mix = Mix(12.5, 100.0, loop=False, tail=4.0, seed=505)
    d4, d5, d3 = 62, 74, 50
    off = 1.2
    roll = [(i * off / 16.0, 0.25 + 0.65 * (i / 15.0) ** 1.4) for i in range(16)]
    mix.hits("roll", roll, lambda v, r: ins.drum("tanggu", v, r), variants=6)
    mix.add("gong", off, ins.gong(110.0, 8.0, 1.0, mix.rng, glide=-0.7, decay=4.5))
    mix.add("gong", off + mix.bar(2), ins.gong(131.0, 7.0, 0.75, mix.rng, glide=-0.6, decay=4.0))
    mix.add("cymbal", off, ins.cymbal(3.0, 0.8, mix.rng, decay=1.4))
    drum_hits = [(off + mix.bar(0, 0), 1.0), (off + mix.bar(0, 2), 0.6), (off + mix.bar(1, 0), 0.8),
                 (off + mix.bar(1, 2), 0.6), (off + mix.bar(1, 3), 0.6), (off + mix.bar(1, 3.5), 0.75),
                 (off + mix.bar(2, 0), 1.0)]
    mix.hits("drum", drum_hits, lambda v, r: ins.drum("dagu", v, r))

    dizi = jianpu("1:0.5 2:0.5 3:1 5:0.5 6:0.5 1':2~ | 6:0.5 1':0.5 2':1 3':1^ 2':0.5 3':0.5 | 5':4~", d5, vel=0.9)
    mix.line("dizi", dizi, "dizi", offset=off)
    arp = arpeggio(["1", "5,"], d4, ROLL_UP, 0.5, vel=0.55)
    mix.plucks("guzheng", arp, "guzheng", ring=2.4, offset=off)
    up = [float(midi_hz(pent_midi(i, d4 - 12))) for i in range(5, 18)]
    mix.add("guzheng", off + mix.bar(1, 3.0), ins.gliss(up, 0.045, 0.6, mix.rng, accel=0.3))
    chord = [d3 - 12, d3 - 5, d3, d4, d4 + 4, d4 + 7, d5]
    for i, m in enumerate(chord):
        mix.add("guzheng", off + mix.bar(2) + 0.02 * i, ins.pluck(float(midi_hz(m)), 4.0, 0.75, "guzheng", rng=mix.rng))
    guqin = jianpu("1,:4 | 5,:4 | 1,:4~", d3, vel=0.9)
    mix.plucks("guqin", guqin, "guqin", ring=4.0, offset=off)

    levels = {"dizi": -1, "guzheng": -5, "guqin": -6, "drum": -4, "gong": -6, "roll": -8, "cymbal": -12}
    sends = {"dizi": 0.35, "guzheng": 0.32, "guqin": 0.3, "drum": 0.2, "gong": 0.25, "roll": 0.2, "cymbal": 0.3}
    return mix.render(levels, sends, make_ir(2.2, 0.025, seed=15))


def defeat() -> np.ndarray:
    """10.5 s lament in A yu mode: falling erhu over low guqin, muffled drum and a distant gong."""
    mix = Mix(10.5, 58.0, loop=False, tail=4.0, seed=606)
    c5, c3 = 72, 48
    off = 0.25
    erhu = jianpu("3:1.5/ 2:0.5 1:1 6,:1 | 5,:1 3,:1\\ 6,:2~", c5, vel=0.85)
    mix.line("erhu", erhu, "erhu", offset=off)
    guqin = jianpu("6,:4~ | 3,:2 6,:2\\", c3, vel=0.9)
    mix.plucks("guqin", guqin, "guqin", ring=5.0, offset=off)
    mix.hits("drum", [(off, 0.75), (off + mix.bar(1, 2.0), 0.6)], lambda v, r: ins.drum("dagu", v, r))
    mix.add("gong", off + mix.bar(1, 2.0), ins.gong(92.0, 7.0, 0.5, mix.rng, glide=-1.3, decay=3.5, bright=0.7))

    levels = {"erhu": -1, "guqin": -4, "drum": -7, "gong": -9}
    sends = {"erhu": 0.35, "guqin": 0.3, "drum": 0.2, "gong": 0.3}
    return mix.render(levels, sends, make_ir(2.4, 0.03, seed=16))


TRACKS = {
    "Music_Title": (title, True),
    "Music_Strategy": (strategy, True),
    "Music_Battle": (battle, True),
    "Music_Duel": (duel, True),
    "Music_Victory": (victory, False),
    "Music_Defeat": (defeat, False),
}

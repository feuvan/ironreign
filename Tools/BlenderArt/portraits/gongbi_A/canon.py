"""The gongbi canon as a generator: archetype + index (+ officer data) -> a full portrait spec.

    canon.spec("m_warrior_07")                 # archetype m_warrior, variant 7
    canon.spec("m_warrior_07", officer=o)      # also uses the officer's age / gender

Every face is built from the *classical figure-painting canon* (see face.py): heroic warriors
get sword or silkworm brows and wide fierce eyes, scholars long phoenix eyes and calm brows,
ladies willow brows, almond eyes and small rouged lips, elders long white brows and beards.
Faces vary through the MakeHuman *feature* targets (jaw, cheekbones, nose, mouth, chin) and the
decal parameters - never through the ethnicity macros, which stay at MakeHuman's neutral default.
"""

import zlib

import numpy as np

import costume
import gear
import patterns as pat

ROBES = [  # outer, outer tint, band, band tint, inner, motif
    ("#2E4E86", "#16264A", "#A82A2E", "#4A1012", "lead_white", "gold"),        # azurite
    ("#2F7457", "#123A2A", "#B8893C", "#5A4018", "lead_white", "#C9A040"),     # malachite
    ("#8E2A22", "#4A1410", "#2A2520", "#100E0C", "#E8D8C0", "gold"),           # cinnabar
    ("#5A4A78", "#2A2040", "#C9A040", "#5A4018", "lead_white", "#B8A0D0"),     # purple
    ("#3C4A58", "#1C242C", "lead_white", "#8A8478", "lead_white", "#55687A"),  # slate
    ("#34485A", "#18222C", "#B8893C", "#5A4018", "#E8D8C0", "#6E8296"),        # indigo
    ("#7A5A36", "#3A2A16", "#2A2520", "#100E0C", "#E8D8C0", "#A08458"),        # ochre-brown
    ("#4E9576", "#1F4A38", "#8E2A22", "#4A1410", "lead_white", "#E6C978"),     # green
    ("#A9524A", "#5A2420", "#34485A", "#18222C", "lead_white", "gold"),        # rouge
]
ARMOUR = [  # plate, plate light, pauldron, pauldron light, lacing, trim, scarf
    ("#4D5E70", "#6E8194", "#8C3A2A", "#B5604A", "#9A3A28", "gold", "#B3301F"),  # azure iron
    ("#2E2B2A", "#5A5450", "#2E2B2A", "#5A5450", "#B3301F", "gold", "#B3301F"),  # black lacquer
    ("#8A6A3A", "#C09858", "#4D5E70", "#6E8194", "#2F7457", "#E6C978", "#2F7457"),  # bronze
    ("#7A2A22", "#A8483A", "#2E2B2A", "#5A5450", "#C9A040", "gold", "#2A2520"),  # red lacquer
    ("#4F5A50", "#76857A", "#7A5A36", "#A88454", "#8E2A22", "#C9A040", "#8E2A22"),  # green iron
]
SKIN_M = ["skin_warm", "skin_peach", "skin_bronze", "#E2BE9C", "#DDB894"]
SKIN_F = ["skin_ivory", "#F1DCC8", "skin_peach"]


class Rnd:
    def __init__(self, key):
        self.g = np.random.default_rng(zlib.crc32(key.encode()) & 0xFFFFFFFF)

    def u(self, a, b):
        return float(self.g.uniform(a, b))

    def pick(self, seq):
        return seq[int(self.g.integers(len(seq)))]

    def chance(self, p):
        return self.g.uniform() < p


def _face_mods(r, kind):
    """MakeHuman *feature* targets only (jaw, cheeks, nose, mouth, chin, brow ridge)."""
    m = {
        "chin/chin-width-decr|incr": r.u(-0.35, 0.35),
        "chin/chin-prominent-decr|incr": r.u(-0.2, 0.35),
        "chin/chin-height-decr|incr": r.u(-0.25, 0.25),
        "cheek/{s}-cheek-bones-decr|incr": r.u(-0.2, 0.4),
        "cheek/{s}-cheek-volume-decr|incr": r.u(-0.3, 0.3),
        "nose/nose-scale-horiz-decr|incr": r.u(-0.25, 0.2),
        "nose/nose-scale-vert-decr|incr": r.u(-0.2, 0.25),
        "nose/nose-hump-decr|incr": r.u(-0.2, 0.4),
        "nose/nose-point-width-decr|incr": r.u(-0.2, 0.2),
        "mouth/mouth-scale-horiz-decr|incr": r.u(-0.2, 0.2),
    }
    shape = r.pick({"warrior": ["head/head-square", "head/head-rectangular", "head/head-round"],
                    "scholar": ["head/head-oval", "head/head-rectangular", "head/head-oval"],
                    "elder": ["head/head-oval", "head/head-rectangular", "head/head-diamond"],
                    "monk": ["head/head-round", "head/head-oval"],
                    "rogue": ["head/head-square", "head/head-diamond", "head/head-triangular"],
                    "lady": ["head/head-oval", "head/head-round"]}[kind])
    m[shape] = r.u(0.3, 0.65)
    if kind in ("warrior", "rogue"):
        m["eyebrows/eyebrows-trans-backward|forward"] = r.u(0.1, 0.4)
        m["neck/neck-scale-horiz-decr|incr"] = r.u(0.2, 0.45)
    if kind == "lady":
        m.update({"chin/chin-bones-decr|incr": r.u(-0.4, -0.15),
                  "head/head-scale-vert-decr|incr": r.u(-0.3, -0.1),
                  "nose/nose-scale-horiz-decr|incr": r.u(-0.3, -0.1),
                  "cheek/{s}-cheek-volume-decr|incr": r.u(0.0, 0.3),
                  "neck/neck-scale-horiz-decr|incr": 0.25})
    return m


def _eyes(r, kind, yaw):
    g = 0.22 if yaw < 0 else -0.22
    if kind == "warrior":
        e = dict(W=r.u(3.15, 3.4), Hu=r.u(0.66, 0.78), Hl=r.u(0.3, 0.37), tilt=r.u(0.15, 0.32),
                 tail=r.u(0.1, 0.26), tail_rise=r.u(8, 16), lid_w=r.u(0.18, 0.21),
                 iris_r=r.u(0.44, 0.5), crease=r.u(0.15, 0.24))
    elif kind in ("scholar", "monk"):
        e = dict(W=r.u(3.2, 3.45), Hu=r.u(0.62, 0.7), Hl=r.u(0.28, 0.33), tilt=r.u(0.18, 0.3),
                 tail=r.u(0.18, 0.3), tail_rise=r.u(10, 16), lid_w=r.u(0.16, 0.19),
                 iris_r=r.u(0.47, 0.52), crease=r.u(0.14, 0.22))
    elif kind == "elder":
        e = dict(W=r.u(3.0, 3.2), Hu=r.u(0.6, 0.66), Hl=r.u(0.28, 0.32), tilt=r.u(-0.12, 0.02),
                 tail=r.u(0.0, 0.08), tail_rise=-5, lid_w=r.u(0.15, 0.17), iris_r=r.u(0.45, 0.49),
                 crease=r.u(0.22, 0.28))
    elif kind == "rogue":
        e = dict(W=r.u(3.1, 3.35), Hu=r.u(0.64, 0.74), Hl=r.u(0.3, 0.36), tilt=r.u(0.1, 0.3),
                 tail=r.u(0.1, 0.22), tail_rise=r.u(6, 14), lid_w=r.u(0.18, 0.21),
                 iris_r=r.u(0.42, 0.48), crease=r.u(0.15, 0.22))
    else:  # lady
        e = dict(W=r.u(3.2, 3.4), Hu=r.u(0.72, 0.8), Hl=r.u(0.33, 0.37), tilt=r.u(0.2, 0.3),
                 tail=r.u(0.2, 0.3), tail_rise=r.u(12, 18), lid_w=r.u(0.17, 0.19),
                 iris_r=r.u(0.5, 0.54), crease=r.u(0.15, 0.2), lower_w=0.065)
    e.update(peak_u=r.u(0.4, 0.46), peak_l=r.u(0.55, 0.62), gaze=(g, 0.0), dx=r.u(0.0, 0.05))
    return e


def _robe_layers(r, pal, kind, female=False):
    outer, otint, band, btint, inner, motif = pal
    zb = 0.11 if female else 0.12
    motif_fn = r.pick([
        lambda: pat.roundels(outer, motif, rep_u=r.u(18, 26), rep_v=r.u(15, 22), amount=0.6),
        lambda: pat.scattered_flowers(motif, rep_u=r.u(22, 30), rep_v=r.u(18, 26), amount=0.7),
        lambda: None])()
    if kind in ("rogue", "monk"):
        motif_fn = None
    out = dict(name="RobeOuter", color=outer, tint=otint, ease=0.016, ease_low=0.02,
               z_back=zb, v_left=(0.048, zb + 0.008), v_bottom=(-0.01, r.u(0.215, 0.245)),
               v_right=(-0.048, zb + 0.008), ext=(-0.13, 0.37), pattern=motif_fn,
               band=dict(w=r.u(0.026, 0.036), color=band, tint=btint,
                         pattern=pat.band(motif if motif != outer else "gold", motif, rep=60,
                                          amount=0.7, kind=r.pick(["dots", "diamond"]))))
    inn = dict(name="RobeInner", color=inner, tint="#9A9282", ease=0.008, z_back=zb - 0.004,
               v_left=(0.036, zb + 0.004), v_bottom=(-0.004, 0.19), v_right=(-0.036, zb + 0.004),
               ext=None, fold_lines=[], band=dict(w=0.014, color="#D8D0BE", tint="#8A8478"))
    return [inn, out]


def spec(key, officer=None, start_year=212):
    """Full spec for a portrait key like 'm_warrior_07' (or 'unknown')."""
    arch, idx = key.rsplit("_", 1) if key[-1].isdigit() else (key, "0")
    r = Rnd(key)
    female = arch.startswith("f_")
    kind = arch.split("_", 1)[1] if "_" in arch else "scholar"
    kind = {"warrior": "warrior", "scholar": "scholar", "elder": "elder", "monk": "monk",
            "rogue": "rogue"}.get(kind, "scholar")
    years = {"warrior": r.u(24, 52), "scholar": r.u(22, 50), "elder": r.u(62, 80),
             "monk": r.u(30, 65), "rogue": r.u(24, 48)}[kind]
    if officer is not None and officer.get("birth"):
        years = max(16, start_year - int(officer["birth"]))
        female = officer.get("gender", "m") == "f"
    yaw = r.pick([-1, 1]) * r.u(20, 29)
    fk = "lady" if female else kind
    body = dict(gender=0.0 if female else 1.0, years=years,
                muscle=r.u(0.55, 0.85) if kind in ("warrior", "rogue") and not female
                else r.u(0.35, 0.55),
                weight=r.u(0.4, 0.65), mods=_face_mods(r, fk))
    eye = _eyes(r, "lady" if female else kind, yaw)
    old = years >= 58
    grey = old or (years > 45 and r.chance(0.5))
    hair_col = "#E9E6DE" if years >= 66 else ("#8C8780" if old else "hair")
    brow_col = "#8E877C" if years >= 66 else ("#4A4642" if grey else "#2A2622")
    if female:
        brow = dict(kind="willow" if kind != "warrior" else "sword", color="#2E2925",
                    thick=r.u(1.15, 1.45), dz=r.u(-0.15, 0.0), hair=0.35, sharp=0.3,
                    rise=0.15 if kind == "warrior" else 0.0)
    elif kind == "elder":
        brow = dict(kind="elder", color=brow_col, streak="#F2EEE6" if years >= 66 else None,
                    thick=r.u(1.1, 1.3), rise=r.u(-0.25, -0.1), hair=0.7)
    elif kind in ("warrior", "rogue"):
        brow = dict(kind=r.pick(["sword", "silkworm", "sword"]), color=brow_col,
                    streak="#6E6964" if grey else None, thick=r.u(1.15, 1.4),
                    rise=r.u(0.15, 0.35), hair=0.55)
    else:
        brow = dict(kind=r.pick(["calm", "sword", "calm"]), color=brow_col,
                    thick=r.u(0.95, 1.15), rise=r.u(0.0, 0.15), hair=0.5)
    mouth = dict(W=r.u(2.9, 3.4) if female else r.u(3.8, 4.5),
                 Hu=r.u(0.4, 0.47) if female else r.u(0.32, 0.4),
                 Hl=r.u(0.5, 0.58) if female else r.u(0.38, 0.46),
                 corner=r.u(0.0, 0.08) if female or kind in ("scholar", "elder", "monk")
                 else r.u(-0.1, 0.0),
                 color="#C0383A" if female else r.pick(["#9E5A4C", "#A9605A", "#B06A5E"]),
                 line="#7A2226" if female else "#5A2A22", line_len=0.86 if female else 0.92)
    wr = {}
    if years > 40:
        wr = dict(forehead=1 + int(years > 50) + int(years > 62), crows=1 + int(years > 55),
                  nasolabial=0.8 + 0.4 * (years > 55))
        if years > 62:
            wr.update(crows=3, under_eye=1)
    skin = dict(base=r.pick(SKIN_F if female else SKIN_M), cheek=r.u(0.28, 0.36) if female
                else r.u(0.14, 0.24), ear=0.3)
    if female:
        skin.update(eyelid=r.u(0.15, 0.28), three_white=r.u(0.2, 0.32), nose=0.08,
                    shade_tint="#C98A78", edge=0.45, ao=0.6)
    if old:
        skin["base"] = "skin_old"
    face = dict(eye=eye, brow=brow, mouth=mouth, nose=dict(wing=0.82 if female else
                                                              r.u(0.95, 1.12),
                                                              bridge=0.6 if female else 1.0),
                wrinkles=wr, skin=skin)
    builders = []
    pal = r.pick(ROBES)
    # ---------------------------------------------------------------- costume
    if kind == "warrior" and not (female and r.chance(0.3)):
        ar = r.pick(ARMOUR)
        A = dict(plate=ar[0], plate_light=ar[1], p_plate=ar[2], p_plate_light=ar[3],
                 lacing=ar[4], trim=ar[5], rep_u=r.u(70, 85), rows=r.u(40, 48), ease=0.03,
                 z_neck=0.168, front_dip=0.03, disc_r=0.031, disc_x=0.06, disc_dz=0.232,
                 z_top=0.158, z_bot=0.3, span=52)
        under = _robe_layers(r, pal, kind, female)[1]
        under.update(fold_lines=[], ext=None, pattern=None)
        discs = r.chance(0.6)
        scarf = ar[6]

        def armour(C, A=A, under=under, discs=discs, scarf=scarf):
            costume.robe_layer(C, under, C.root)
            costume.cuirass(C, A, C.root)
            costume.pauldrons(C, A, C.root)
            if discs:
                costume.chest_discs(C, A, C.root)
            costume.scarf(C, dict(color=scarf, dz=0.152, r=0.013, ease=0.016, sag=0.02), C.root)
        builders.append(armour)
    else:
        layers = _robe_layers(r, pal, kind, female)
        if kind == "monk":
            layers[1].update(color=r.pick(["#C08A3E", "#A0643E", "#8C5A2A"]), tint="#4A2A10",
                             pattern=pat.kasaya(), band=dict(w=0.03, color="#7A4A20",
                                                             tint="#3A200C"))
        if kind == "rogue":
            layers[1].update(color=r.pick(["#3A3632", "#4A4038", "#34485A"]), tint="#141210")

        def robes(C, layers=layers):
            for L in layers:
                costume.robe_layer(C, L, C.root)
        builders.append(robes)
        if kind == "monk":
            builders.append(lambda C: costume.prayer_beads(C, dict(), C.root))
        if female and kind == "scholar" and r.chance(0.6):
            sh = r.pick(["#A9CFB5", "#E8C3B0", "#C9D6E8", "#E6D9A8"])
            builders.append(lambda C, sh=sh: costume.shawl(C, dict(color=sh, w=0.036, ease=0.02,
                                                                   twist=0.8), C.root))
    # ---------------------------------------------------------------- head
    if female:
        Lh = dict(color=hair_col if years < 66 else "#D8D4CC", comb=False,
                  crown=kind in ("scholar",) and r.chance(0.6), flower=r.chance(0.7),
                  flower_r=r.u(0.024, 0.032), bun_lift=0.012, bun_back=0.016,
                  flower_col=r.pick([("#E8A7A0", "#C2414A"), ("#F2E6D8", "#D9AE45"),
                                     ("#E6B8C8", "#9A2433")]))
        if kind == "warrior":
            Lh.update(crown=False, flower=False, pins=[(1, 0.6, 0.35)])
        if kind == "elder":
            Lh.update(crown=False, flower=False, pins=[(1, 0.6, 0.35)],
                      lobes=[(0.0, 0.004, 0.03, 0.03, 0.026, 0.022)])
        builders.append(lambda C, Lh=Lh: gear.lady_hair(C, Lh, C.root))
        builders.append(lambda C: gear.earrings(C, dict(), C.root))
        if kind == "warrior":
            builders.append(lambda C: gear.head_band(C, dict(color="cinnabar", w=7.0), C.root))
    else:
        hc = dict(color=hair_col, thick=0.004, top=0.006)
        if kind == "monk":
            pass  # shaven head
        elif kind == "warrior":
            hg = r.pick(["helmet", "helmet", "topknot", "band"])
            ar_col = r.pick(ARMOUR)
            if hg == "helmet":
                Hm = dict(color=ar_col[0], color_light=ar_col[1], band=ar_col[5],
                          guard=ar_col[0], guard_light=ar_col[1], lacing=ar_col[4],
                          stem=r.u(0.015, 0.025), tassel_len=r.u(0.05, 0.07),
                          tassel_col=r.pick(["cinnabar", "cinnabar", "ink_dense", "lead_white"]),
                          neck_guard=r.chance(0.8), ribs=int(r.u(8, 14)))
                builders.append(lambda C, Hm=Hm: gear.helmet(C, Hm, C.root))
            else:
                builders.append(lambda C, hc=hc: gear.hair_cap(C, hc, C.root))
                builders.append(lambda C: gear.topknot(C, dict(crown=dict(color="gold")), C.root))
                if hg == "band":
                    col = r.pick(["cinnabar", "ink_dense", "#2F7457"])
                    builders.append(lambda C, col=col: gear.head_band(C, dict(color=col),
                                                                      C.root))
        elif kind == "rogue":
            builders.append(lambda C, hc=hc: gear.hair_cap(C, hc, C.root))
            builders.append(lambda C: gear.topknot(C, dict(), C.root))
            col = r.pick(["#3A3632", "cinnabar", "#34485A"])
            builders.append(lambda C, col=col: gear.head_band(C, dict(color=col), C.root))
            builders.append(lambda C, hcol=hair_col: gear.loose_locks(C, dict(color=hcol),
                                                                       C.root))
        elif kind == "elder":
            builders.append(lambda C, hc=hc: gear.hair_cap(C, hc, C.root))
            if r.chance(0.5):
                builders.append(lambda C: gear.tall_hat(C, dict(), C.root))
            else:
                cc = r.pick(["gold", "#C9C2B0"])
                builders.append(lambda C, cc=cc: gear.topknot(C, dict(crown=dict(color=cc)),
                                                              C.root))
        else:  # scholar
            builders.append(lambda C, hc=hc: gear.hair_cap(C, hc, C.root))
            if r.chance(0.55):
                builders.append(lambda C: gear.futou(C, dict(), C.root))
            else:
                builders.append(lambda C: gear.topknot(C, dict(crown=dict(color="gold")),
                                                       C.root))
        # beards
        bcol = ([("#F4F1EA", 0.55), ("#9E978C", 0.45)] if years >= 66 else
                [("ink_dense", 0.5), ("#5A5550", 0.3), ("#A8A39B", 0.2)] if grey else
                [("ink_dense", 0.75), ("#4A4642", 0.25)])
        wash = "#D6D1C6" if years >= 66 else "#3A3632"
        style = {"warrior": r.pick(["full", "full", "goatee", "moustache", "none"]),
                 "scholar": r.pick(["long3", "goatee", "none", "goatee"]),
                 "elder": r.pick(["long3", "long3", "full"]),
                 "monk": "none",
                 "rogue": r.pick(["full", "goatee", "moustache", "none"])}[kind]
        if years < 24:
            style = "none"
        if style != "none":
            B = dict(style=style, length=r.u(0.07, 0.11) if style == "full" else r.u(0.08, 0.18),
                     n=110, n_side=100, n_m=90, locks=7, span=0.045, above=0.009, colors=bcol,
                     wash=wash, wash_r=0.0012, r=0.00018, m_len=r.u(0.035, 0.045),
                     m_droop=r.u(1.0, 1.4), shadow=0.35 if style == "full" else 0.0,
                     moustache=True)
            if style == "moustache":
                B.update(style="none_body")
            builders.append(lambda C, B=B: gear.beard(C, B, C.root))
    return dict(key=key, seed=zlib.crc32(key.encode()) & 0xFFFF, yaw=yaw, pitch=r.u(2.0, 6.0),
                head_frac=0.47 if female else 0.46, shoulder_dz=0.19 if female else 0.2,
                arm_drop=0.3 if female else 0.25, body=body, face=face, builders=builders)

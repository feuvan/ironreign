"""Cast generator of gongbi_C: one deterministic spec per portrait key.

    spec_for("m_warrior_07")   -> spec dict (see specs.py)

The key's archetype (``m_warrior``, ``m_scholar``, ``m_elder``, ``m_monk``, ``m_rogue``,
``f_warrior``, ``f_scholar``, ``f_elder``; ``unknown``) picks the canon vocabulary; the officer
who uses the key in ``Content/Data/Scenarios/BrokenMandate.json`` (if any) steers it: age from
the birth year (wrinkles, grey hair, beard length), faction (costume palette), martial / charm
(build, fierceness), epithet keywords (khan -> fur hat, monk / bell -> bald, ...).  Everything
else is drawn from the archetype's ranges with an RNG seeded by the key, so the same key always
renders the same face, and 103 keys give 103 distinct faces.

Hand-tuned heroes override their keys (:data:`HERO_KEYS`).
"""

import copy
import hashlib
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
SCENARIO = os.path.join(REPO, "Content", "Data", "Scenarios", "BrokenMandate.json")

COUNTS = dict(m_warrior=30, m_scholar=20, m_elder=12, m_monk=6, m_rogue=10, f_warrior=10,
              f_scholar=10, f_elder=4)

HERO_KEYS = {"m_warrior_01": "hero_warlord", "f_scholar_04": "hero_scholar",
             "m_elder_06": "hero_elder"}

#: faction costume palettes: robe colours, accent (collar / cloak), armour metal
FACTIONS = {
    "iron_banner": dict(robe=["cinnabar", "ink_wash", "cinnabar_d", "iron"],
                        accent=["cinnabar", "gold", "white"], metal=["steel", "iron"]),
    "wolf_riders": dict(robe=["ochre_d", "umber", "teal", "leather"],
                        accent=["cinnabar", "teal_l", "gold"], metal=["bronze", "steel"]),
    "azure_court": dict(robe=["azurite", "azurite_d", "white", "indigo"],
                        accent=["gold", "white", "azurite_l"], metal=["gold", "steel"]),
    "sea_league": dict(robe=["teal", "indigo", "malachite_d", "white"],
                       accent=["white", "teal_l", "gold"], metal=["steel", "bronze"]),
    "southern_lotus": dict(robe=["malachite", "plum", "cinnabar", "lotus"],
                           accent=["gold", "lotus_l", "malachite_l"], metal=["gold", "bronze"]),
    "black_mountain": dict(robe=["ink_wash", "umber", "ochre", "indigo_d"],
                           accent=["cinnabar", "ochre_l", "white"], metal=["iron", "steel"]),
    None: dict(robe=["azurite", "malachite", "ochre", "indigo", "plum", "teal"],
               accent=["white", "gold", "cinnabar"], metal=["steel", "bronze"]),
}

METAL = {"steel": ("steel", "steel_l"), "iron": ("iron", "steel"), "bronze": ("bronze", "gold_l"),
         "gold": ("#9A7A3A", "gold_l")}

_OFFICERS = None


def officers():
    global _OFFICERS
    if _OFFICERS is None:
        _OFFICERS = {}
        try:
            with open(SCENARIO) as f:
                d = json.load(f)
            for o in d.get("officers", []):
                _OFFICERS[o.get("portrait")] = dict(o, _year=d.get("startYear", 212))
        except OSError:
            pass
    return _OFFICERS


class R:
    """Seeded choices."""

    def __init__(self, key):
        h = int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)
        self.seed = h % 100000
        self.g = np.random.default_rng(h)

    def u(self, a, b):
        return float(self.g.uniform(a, b))

    def c(self, items, p=None):
        if p is not None:
            p = np.asarray(p, float)
            p = p / p.sum()
        return items[int(self.g.choice(len(items), p=p))]

    def b(self, p):
        return bool(self.g.random() < p)


def parse(key):
    if key == "unknown":
        return "unknown", 0
    arch, _, idx = key.rpartition("_")
    return arch, int(idx)


def spec_for(key):
    if key in HERO_KEYS:
        import specs
        sp = copy.deepcopy(specs.HEROES[HERO_KEYS[key]])
        sp["name"] = key
        return sp
    arch, idx = parse(key)
    r = R(key)
    off = officers().get(key, {})
    age = (off["_year"] - off["birth"]) if off.get("birth") else None
    fac = FACTIONS.get(off.get("faction"), FACTIONS[None])
    build = BUILDERS[arch]
    sp = build(r, age, off, fac)
    sp.setdefault("name", key)
    sp.setdefault("seed", r.seed)
    sp["officer"] = off.get("key")
    side = -1.0 if r.b(0.6) else 1.0           # most face image-left, some image-right
    vary(sp, r, arch)
    sp.setdefault("pose", {})
    sp["pose"].setdefault("body_yaw", side * r.u(24, 32))
    sp["pose"].setdefault("head_yaw", -side * r.u(3, 9))
    sp["pose"].setdefault("head_pitch", r.u(-2, 2))
    sp["pose"].setdefault("cam_pitch", -2.0)
    return sp


# =============================================================================================
# shared pieces
# =============================================================================================
def vary(sp, r, arch):
    """Per-officer feature variation inside the canon (spacing, sizes, angles) so that two
    officers with the same presets still look like two different people."""
    f = sp.get("face")
    if f is None or sp.get("silhouette"):
        return
    fem = arch.startswith("f_")
    f.setdefault("eye_x", r.u(0.136, 0.150))
    f.setdefault("eye_z", r.u(-0.012, 0.01))
    f.setdefault("brow_dz", r.u(-0.012, 0.01))
    em = f.setdefault("eye_mod", {})
    em.setdefault("w", r.u(0.128, 0.142) if not fem else r.u(0.136, 0.146))
    em.setdefault("tilt_add", 0.0)
    em["open_add"] = r.u(-0.02, 0.03)
    em["tilt_add"] = r.u(-0.02, 0.025)
    bm = f.setdefault("brow_mod", {})
    bm["thick_k"] = r.u(0.85, 1.2) if not fem else r.u(0.85, 1.1)
    bm["z1_add"] = r.u(-0.012, 0.015)
    nm = f.setdefault("nose_mod", {})
    nm.setdefault("tip_z", r.u(-0.2, -0.172))
    nm["ala_k"] = r.u(0.92, 1.12) if not fem else r.u(0.9, 1.0)
    mm = f.setdefault("mouth_mod", {})
    mm.setdefault("z", r.u(-0.295, -0.275))
    mm["w_k"] = r.u(0.92, 1.1)
    mm["lip_k"] = r.u(0.85, 1.2)



def age_face(r, age, sex="m"):
    w = {}
    if age is None:
        return w
    if age >= 38:
        w["naso"] = min(1.0, (age - 34) / 22)
        w["crow"] = 1 if age < 50 else 2
    if age >= 45:
        w["forehead"] = 1 if age < 55 else 2
        w["bags"] = min(1.0, (age - 40) / 25)
    if age >= 58:
        w["crow"] = 3
        w["mouth"] = 0.6
    if sex == "f":
        w = {k: (v * 0.6 if not isinstance(v, int) else max(0, v - 1)) for k, v in w.items()}
    return w


def hair_color(age, r, base="hair"):
    if age is None or age < 40:
        return base
    if age < 52:
        return r.c(["#3A3632", "#45403A", base])
    if age < 62:
        return r.c(["grey_hair", "#6E6A64"])
    return "white_hair"


def beard_color(age):
    if age is None or age < 40:
        return "black"
    if age < 52:
        return "grizzled"
    if age < 62:
        return "grey"
    return "white"


def collar(r, fac, robe, kind="plain"):
    acc = r.c(fac["accent"])
    layers = [dict(color="white", w=0.035)]
    if kind == "rich":
        layers.append(dict(color=r.c(["cinnabar", "lotus_l", "gold_l", "malachite_l"]), w=0.04))
        layers.append(dict(color=r.c(["cinnabar", "indigo", "ink_wash", "malachite_d"]), w=0.08,
                           pattern=dict(kind="brocade", motif=r.c(["lozenge", "dots"]),
                                        color="gold", period=0.05)))
    elif kind == "dark":
        layers.append(dict(color="#2A2622", w=r.u(0.08, 0.11)))
    else:
        layers.append(dict(color=acc if acc != robe else "white", w=r.u(0.045, 0.07)))
    return dict(neck_z=r.u(-0.68, -0.64), cross_z=r.u(-1.0, -0.93), x_neck=r.u(0.13, 0.17),
                layers=layers)


def m_head(r, broad=1.0):
    return dict(cheek_w=r.u(0.318, 0.34) * (0.98 + 0.02 * broad),
                jaw_w=r.u(0.25, 0.29) * (0.97 + 0.03 * broad), chin_w=r.u(0.105, 0.135),
                jaw_sq=r.u(2.1, 2.7), temple_w=r.u(0.31, 0.325), skull_w=r.u(0.328, 0.342),
                flat=r.u(2.35, 2.6), chin_d=r.u(0.365, 0.39), cheek_full=r.u(-0.01, 0.012))


def f_head(r):
    return dict(cheek_w=r.u(0.303, 0.318), jaw_w=r.u(0.226, 0.245), chin_w=r.u(0.10, 0.12),
                jaw_sq=r.u(1.8, 2.0), temple_w=r.u(0.303, 0.314), skull_w=r.u(0.316, 0.326),
                cheek_full=r.u(0.01, 0.026), flat=r.u(2.3, 2.45), chin_d=r.u(0.36, 0.375),
                chin_z=r.u(-0.48, -0.465), jaw_z=r.u(-0.29, -0.275))


def helmet(r, fac, age):
    metal = r.c(fac["metal"])
    col, light = METAL[metal]
    return dict(kind="helmet", color=col, brim_z=r.u(0.15, 0.19), lift=r.u(0.032, 0.042),
                peak=r.u(0.06, 0.14), ribs=r.c([4, 6, 8]),
                tassel=r.b(0.8), tassel_color=r.c(["cinnabar", "cinnabar", "ink", "white"]),
                tassel_len=r.u(0.14, 0.21), guard_drop=r.u(0.42, 0.55),
                guard_flare=r.u(0.3, 0.45), open_t=r.u(1.0, 1.1),
                guard_color=r.c([col, "cinnabar_d", "indigo"]),
                guard_pattern=dict(kind="lamellar", w=0.045, h=0.06, light=light,
                                   lace=r.c(["cinnabar", "gold", "white"])))


def armour(r, fac):
    metal = r.c(fac["metal"])
    col, light = METAL[metal]
    return dict(color=col, light=light, lace=r.c(["cinnabar", "gold", "white", "indigo"]),
                collar_color=r.c(["cinnabar", "indigo", "ink_wash", "gold"]),
                collar_pattern=dict(kind="brocade", motif="dots", color="gold", period=0.05),
                mirror_z=r.u(-1.36, -1.28), mirror_x=r.u(0.34, 0.42), mirror_r=r.u(0.12, 0.16),
                mirrors=r.b(0.7), top_z=-0.84, strap=False)


# =============================================================================================
# archetypes
# =============================================================================================
def m_warrior(r, age, off, fac):
    age = age if age is not None else int(r.u(24, 56))
    ep = (off.get("epithet", "") + " " + off.get("bio", "")).lower()
    steppe = off.get("faction") == "wolf_riders" or "steppe" in ep or "khan" in ep
    big = (off.get("martial", 75) - 70) / 30.0
    sp = dict(skin=r.c(["weathered", "bronzed", "warm"], [0.5, 0.25, 0.25] if not steppe else [0.3, 0.6, 0.1]),
              head=m_head(r, 1.0 + big * 0.5),
              neck=dict(w=r.u(0.26, 0.29), d=r.u(0.21, 0.23)),
              torso=dict(shoulder_w=r.u(1.0, 1.1) + 0.04 * big, slope=r.u(0.25, 0.5),
                         bulk=r.u(1.0, 1.06), neck_w=0.29))
    eye = r.c(["tiger", "steady", "phoenix"], [0.3, 0.4, 0.3])
    brow = r.c(["silkworm", "sword", "calm"], [0.35, 0.45, 0.2])
    sp["face"] = dict(eye=eye, brow=brow, nose=r.c(["strong", "straight", "broad"]),
                      mouth="firm", knit=r.u(0.0, 0.9), gaze=r.u(0.75, 0.9),
                      brow_color="ink" if age < 55 else "grey",
                      mouth_mod=dict(corner=r.u(-0.008, 0.002), w=r.u(0.09, 0.105)),
                      rouge=dict(color="#C2735E", alpha=r.u(0.08, 0.15), r=0.13),
                      whites=0.1, socket=r.u(0.24, 0.34), wrinkles=age_face(r, age))
    # beard by age
    bc = beard_color(age)
    if age < 26:
        sp["beard"] = dict(color=bc, stubble=r.u(0.0, 0.08)) if r.b(0.5) else None
    else:
        style = r.c(["full", "goatee", "moustache", "long", "stubble"],
                    [0.35, 0.25, 0.12, 0.13 if age > 38 else 0.02, 0.15])
        sp["beard"] = beard(r, style, bc)
    sp["hair"] = dict(kind="topknot", color=hair_color(age, r), line_z=r.u(0.34, 0.38))
    hg = r.c(["helmet", "guan", "headband", "none"], [0.55, 0.15, 0.18, 0.12])
    if steppe:
        hg = r.c(["fur_hat", "helmet", "headband"], [0.55, 0.3, 0.15])
    if hg == "helmet":
        sp["headgear"] = helmet(r, fac, age)
    elif hg == "fur_hat":
        sp["headgear"] = dict(kind="fur_hat", color=r.c(["ochre_d", "teal", "cinnabar_d", "umber"]),
                              fur=r.c(["#8A6A48", "#6A5A4A", "#A08A6A"]), peak=r.u(0.06, 0.14),
                              tassel_color=r.c(["cinnabar", "gold", "ink"]))
    elif hg == "guan":
        sp["headgear"] = dict(kind="guan", color=r.c(["gold", "ink", "#9A7A3A"]))
    elif hg == "headband":
        sp["headgear"] = dict(kind="headband", color=r.c(["cinnabar", "ink_wash", "indigo", "ochre_d"]),
                              jewel=r.c([None, "jade", "gold"]))
    robe = r.c(fac["robe"])
    cos = dict(robe=dict(color=robe), collar=collar(r, fac, robe))
    if r.b(0.75) or hg == "helmet":
        cos["armour"] = armour(r, fac)
        cos["collar"]["layers"] = cos["collar"]["layers"][:2]
    if r.b(0.45):
        cos["cloak"] = dict(color=r.c(["cinnabar_d", "indigo", "ink_wash", "ochre_d"]))
    sp["costume"] = cos
    return sp


def beard(r, style, color):
    if style == "full":
        return dict(color=color, moustache=dict(len=r.u(0.1, 0.13), droop=r.u(0.04, 0.08),
                                                angle=r.u(24, 34), density=1.0, thick=1.1),
                    chin=dict(len=r.u(0.25, 0.42), width=r.u(0.2, 0.25), shape="full",
                              density=1.4),
                    cheeks=dict(density=r.u(0.8, 1.1), len=0.1, top=r.u(-0.12, -0.06), depth=0.06),
                    tuft=dict(len=0.05), stubble=r.u(0.05, 0.12))
    if style == "goatee":
        return dict(color=color, moustache=dict(len=r.u(0.08, 0.12), droop=r.u(0.03, 0.07),
                                                angle=r.u(26, 38), density=0.8),
                    chin=dict(len=r.u(0.12, 0.28), width=r.u(0.06, 0.09), shape="pointed",
                              density=0.8),
                    tuft=dict(len=0.04), stubble=r.u(0.0, 0.08))
    if style == "moustache":
        return dict(color=color, moustache=dict(len=r.u(0.1, 0.14), droop=r.u(0.05, 0.1),
                                                angle=r.u(28, 40), density=0.9),
                    stubble=r.u(0.03, 0.1))
    if style == "long":
        return dict(color=color, moustache=dict(len=r.u(0.11, 0.14), droop=r.u(0.07, 0.1),
                                                angle=r.u(30, 40), density=1.0),
                    chin=dict(len=r.u(0.5, 0.75), width=r.u(0.12, 0.16), shape=r.c(["pointed", "forked"]),
                              density=1.6),
                    cheeks=dict(density=0.6, len=0.1, top=-0.12, depth=0.05),
                    tuft=dict(len=0.05), strand_w=0.5)
    return dict(color=color, stubble=r.u(0.12, 0.22))


def m_scholar(r, age, off, fac):
    age = age if age is not None else int(r.u(22, 55))
    sp = dict(skin=r.c(["fair", "warm"], [0.6, 0.4]), head=m_head(r, 0.6),
              neck=dict(w=r.u(0.23, 0.25), d=0.2),
              torso=dict(shoulder_w=r.u(0.92, 1.0), slope=r.u(0.5, 0.7)))
    sp["head"]["jaw_w"] = r.u(0.235, 0.262)
    sp["face"] = dict(eye=r.c(["phoenix", "almond", "steady"], [0.5, 0.2, 0.3]),
                      brow=r.c(["calm", "sword", "crescent"], [0.45, 0.35, 0.2]),
                      nose=r.c(["straight", "small", "straight"]), mouth="gentle",
                      gaze=r.u(0.7, 0.85), knit=r.u(0.0, 0.3),
                      mouth_mod=dict(corner=r.u(-0.002, 0.006)),
                      rouge=dict(color="#D08A80", alpha=r.u(0.06, 0.12)), whites=0.2,
                      wrinkles=age_face(r, age))
    bc = beard_color(age)
    if age < 25:
        sp["beard"] = None
    else:
        sp["beard"] = beard(r, r.c(["goatee", "moustache", "long", "none"],
                                   [0.55, 0.15, 0.15 if age > 40 else 0.03, 0.15]), bc) \
            if r.b(0.9) else None
        if sp["beard"] and sp["beard"].get("chin"):
            sp["beard"]["chin"]["width"] = min(sp["beard"]["chin"]["width"], 0.1)
            sp["beard"]["strand_w"] = 0.45
    sp["hair"] = dict(kind="topknot", color=hair_color(age, r), line_z=r.u(0.34, 0.38))
    hg = r.c(["futou", "guan", "dongpo", "none"], [0.4, 0.3, 0.1, 0.2])
    if hg == "futou":
        sp["headgear"] = dict(kind="futou", wings=r.b(0.7), wing_len=r.u(0.4, 0.6))
    elif hg == "guan":
        sp["headgear"] = dict(kind="guan", color=r.c(["gold", "ink", "jade"]))
    elif hg == "dongpo":
        sp["headgear"] = dict(kind="dongpo")
    robe = r.c(fac["robe"] + ["malachite", "azurite", "plum", "teal"])
    pat = None
    if r.b(0.35):
        pat = dict(kind="roundels", period=r.u(0.14, 0.2), size=r.u(0.2, 0.28),
                   color=r.c(["gold", "white", "azurite_l"]), color2="gold_l", alpha=0.35)
    sp["costume"] = dict(robe=dict(color=robe, pattern=pat),
                         collar=collar(r, fac, robe, r.c(["plain", "dark", "rich"], [0.4, 0.4, 0.2])))
    return sp


def m_elder(r, age, off, fac):
    age = age if age is not None else int(r.u(58, 76))
    sp = dict(skin="elder", head=m_head(r, 0.5), neck=dict(w=0.24, d=0.2),
              torso=dict(shoulder_w=r.u(0.92, 1.0), slope=r.u(0.5, 0.7)),
              ear=dict(h=r.u(0.27, 0.3), w=0.13))
    sp["head"]["cheek_full"] = r.u(-0.015, 0.0)
    sp["face"] = dict(eye=r.c(["kind", "steady"], [0.6, 0.4]),
                      brow=r.c(["longevity", "calm"], [0.6, 0.4]), nose=r.c(["strong", "straight"]),
                      mouth="elder", gaze=r.u(0.6, 0.8), brow_color=r.c(["white", "grey"]),
                      rouge=dict(color="#D08A7E", alpha=0.08), whites=0.14, socket=0.26,
                      knit=r.u(0.0, 0.5),
                      wrinkles=dict(age_face(r, max(age, 60)), forehead=2, bags=0.8))
    sp["beard"] = beard(r, r.c(["long", "full", "goatee"], [0.6, 0.25, 0.15]),
                        "white" if age > 62 else "grey")
    sp["hair"] = dict(kind="elder", color="white_hair" if age > 62 else "grey_hair",
                      strand="#8E8880", line_z=r.u(0.36, 0.42), temple_z=r.u(0.14, 0.2))
    hg = r.c(["dongpo", "guan", "futou", "none"], [0.35, 0.3, 0.2, 0.15])
    if hg == "dongpo":
        sp["headgear"] = dict(kind="dongpo")
    elif hg == "guan":
        sp["headgear"] = dict(kind="guan", color=r.c(["ink", "gold", "jade"]))
    elif hg == "futou":
        sp["headgear"] = dict(kind="futou", wings=r.b(0.6))
    robe = r.c(["#6F8F86", "ink_grey", "ochre", "azurite_d", "plum", "#8A7A62", "teal"])
    sp["costume"] = dict(robe=dict(color=robe), collar=collar(r, fac, robe, "dark"))
    return sp


def m_monk(r, age, off, fac):
    age = age if age is not None else int(r.u(25, 65))
    sp = dict(skin=r.c(["warm", "weathered"]), head=m_head(r, 0.8),
              neck=dict(w=r.u(0.25, 0.28), d=0.21),
              torso=dict(shoulder_w=r.u(1.0, 1.1), slope=r.u(0.3, 0.5)))
    sp["head"].update(skull_w=r.u(0.345, 0.355), crown=0.44, back=0.42)
    sp["face"] = dict(eye=r.c(["steady", "kind", "tiger"], [0.4, 0.3, 0.3]), dots=r.c([0, 6, 9]),
                      brow=r.c(["calm", "silkworm", "longevity" if age > 55 else "calm"]),
                      nose=r.c(["broad", "straight"]), mouth=r.c(["gentle", "firm"]),
                      gaze=r.u(0.6, 0.85), brow_color="ink" if age < 50 else "grey",
                      wrinkles=age_face(r, age), whites=0.12)
    sp["beard"] = dict(color="black", stubble=r.u(0.04, 0.12)) if r.b(0.6) else None
    sp["hair"] = dict(kind="bald")
    sp["costume"] = dict(robe=dict(color=r.c(["ochre", "#C08A3E", "ink_grey", "#8A7A62"])),
                         collar=dict(neck_z=-0.74, cross_z=-1.02, x_neck=0.15,
                                     layers=[dict(color="white", w=0.03),
                                             dict(color=r.c(["ochre_d", "umber"]), w=0.07)]),
                         kasaya=dict(color=r.c(["cinnabar", "cinnabar_d", "ochre"]),
                                     side=r.c([-1, 1])),
                         beads=dict(r=r.u(0.024, 0.032), color=r.c(["#5A3A26", "#3A2A20", "#7A4A2A"])))
    return sp


def m_rogue(r, age, off, fac):
    age = age if age is not None else int(r.u(22, 50))
    sp = m_warrior(r, age, off, fac)
    sp["skin"] = r.c(["weathered", "bronzed"])
    sp["face"]["eye"] = r.c(["steady", "phoenix", "tiger"])
    sp["face"]["brow"] = r.c(["sword", "silkworm", "calm"])
    sp["beard"] = beard(r, r.c(["stubble", "full", "goatee", "moustache"]), beard_color(age)) \
        if age >= 24 else None
    sp["hair"] = dict(kind="topknot", color=hair_color(age, r), line_z=r.u(0.34, 0.38))
    sp["headgear"] = r.c([dict(kind="headband", color=r.c(["ink_wash", "cinnabar", "indigo", "ochre_d"])),
                          dict()], [0.6, 0.4])
    robe = r.c(["ochre", "umber", "indigo_d", "ink_wash", "leather"])
    cos = dict(robe=dict(color=robe), collar=collar(r, fac, robe))
    if r.b(0.35):
        cos["armour"] = dict(armour(r, fac), mirrors=False, color="leather", light="ochre_l",
                             lace=r.c(["cinnabar", "ochre_l"]))
    sp["costume"] = cos
    return sp


def f_common(r, age):
    sp = dict(skin=r.c(["ivory", "fair"], [0.7, 0.3]), head=f_head(r),
              neck=dict(w=r.u(0.2, 0.215), d=0.18),
              torso=dict(shoulder_w=r.u(0.9, 0.97), shoulder_z=-1.0, slope=r.u(0.6, 0.8),
                         chest_d=0.40, neck_w=0.225, neck_base=-0.645),
              ear=dict(h=0.25, w=0.115))
    sp["face"] = dict(eye=r.c(["almond", "phoenix"], [0.55, 0.45]),
                      brow=r.c(["willow", "crescent"]), nose="small",
                      mouth=r.c(["cherry", "gentle"], [0.7, 0.3]), gaze=r.u(0.7, 0.85),
                      eye_mod=dict(w=r.u(0.136, 0.144), tilt=r.u(0.05, 0.09)),
                      mouth_mod=dict(z=-0.278, corner=r.u(0.0, 0.008)),
                      rouge=dict(color=r.c(["#E08A88", "#D88A92", "#E09A8A"]), alpha=r.u(0.2, 0.32),
                                 r=0.13, x=0.17, z=-0.12),
                      eye_rouge=r.u(0.0, 0.14), whites=r.u(0.22, 0.32), socket=0.16,
                      mark=r.c([None, dict(kind="drop", color="cinnabar"),
                                dict(kind="petals", color="cinnabar"),
                                dict(kind="drop", color="malachite")]),
                      wrinkles=age_face(r, age, "f"))
    return sp


def lady_hair(r, color="hair", style=None):
    style = style or r.c(["high", "double", "low", "tilted"])
    base = dict(kind="lady", color=color, line_z=r.u(0.33, 0.36), arch=r.u(0.02, 0.035),
                temple_z=r.u(0.23, 0.26), side_z=-0.02, over_ear_z=0.05, nape_z=-0.15,
                side_puff=r.u(0.05, 0.1), puff_t=1.45, puff_z=0.09, volume=0.016,
                top_volume=0.03, widow=r.u(0.0, 0.015), flow_n=64)
    pins = [dict(kind="pin", a=(0.10, 0.10, 0.62), b=(0.31, -0.02, 0.78), r=0.009,
                 head=r.u(0.022, 0.032), head_color=r.c(["gold", "malachite", "cinnabar"]),
                 dangles=r.c([0, 2, 3]), dangle_len=0.14, dangle_color=r.c(["cinnabar", "gold"]))]
    flower = dict(kind="flower", c=(r.u(-0.2, 0.05), -0.06, r.u(0.55, 0.8)), r=r.u(0.05, 0.08),
                  color=r.c(["lotus", "cinnabar_l", "white", "plum_l"]), petals=r.c([6, 7, 8]))
    if style == "high":
        base.update(knot_at=(0.0, 0.08, 0.66),
                    buns=[dict(kind="ellipsoid", c=(0.0, 0.10, 0.50), r=(0.22, 0.20, 0.11)),
                          dict(kind="ellipsoid", c=(0.0, 0.07, 0.70), r=(0.16, 0.15, 0.19),
                               tilt=-12, flow_n=14)])
        orn = pins + [flower, dict(kind="comb", c=(0.0, -0.11, 0.60), w=0.15, h=0.06,
                                   color="gold", tilt=-35)]
    elif style == "double":
        base.update(knot_at=(0.0, 0.08, 0.62),
                    buns=[dict(kind="ellipsoid", c=(0.0, 0.10, 0.52), r=(0.22, 0.20, 0.11)),
                          dict(kind="loop", c=(-0.08, 0.05, 0.66), R=0.10, r=0.045, yaw=-25,
                               tilt=5, a0=-0.05, a1=1.05),
                          dict(kind="loop", c=(0.09, 0.07, 0.66), R=0.10, r=0.045, yaw=25,
                               tilt=-5, a0=-0.05, a1=1.05)])
        orn = [flower, dict(pins[0], b=(0.28, 0.0, 0.72))]
    elif style == "low":
        base.update(knot_at=(0.0, 0.25, 0.25), side_puff=r.u(0.03, 0.06),
                    buns=[dict(kind="ellipsoid", c=(0.0, 0.38, 0.12), r=(0.17, 0.13, 0.15))])
        orn = [dict(kind="pin", a=(0.05, 0.38, 0.25), b=(0.26, 0.36, 0.30), r=0.008,
                    head=0.024, head_color=r.c(["gold", "jade"]))]
    else:   # tilted (堕马髻)
        base.update(knot_at=(0.12, 0.10, 0.58),
                    buns=[dict(kind="ellipsoid", c=(0.0, 0.10, 0.50), r=(0.22, 0.20, 0.11)),
                          dict(kind="ellipsoid", c=(0.13, 0.08, 0.62), r=(0.17, 0.14, 0.13),
                               tilt=-10, flow_n=12)])
        orn = [dict(flower, c=(-0.12, -0.05, 0.6)), pins[0]]
    base["ornaments"] = orn
    return base


def f_scholar(r, age, off, fac):
    age = age if age is not None else int(r.u(19, 40))
    sp = f_common(r, age)
    if r.b(0.6):
        sp["earrings"] = dict(color=r.c(["pearl", "jade", "cinnabar"]), metal="gold")
    sp["frame"] = dict(head_frac=0.45, min_head=0.88, eye_frac=0.40)
    sp["hair"] = lady_hair(r, hair_color(age, r))
    robe = r.c(fac["robe"] + ["azurite", "malachite", "plum", "lotus"])
    pat = dict(kind="roundels", period=r.u(0.14, 0.18), size=r.u(0.2, 0.26),
               color=r.c(["azurite_l", "gold", "white", "lotus_l"]), color2="gold_l",
               alpha=0.35) if r.b(0.6) else None
    sp["costume"] = dict(robe=dict(color=robe, pattern=pat),
                         collar=dict(collar(r, fac, robe, "rich"), neck_z=-0.66, cross_z=-0.98,
                                     x_neck=0.12),
                         shawl=dict(color=r.c(["malachite_l", "lotus_l", "azurite_l",
                                               "gold_l"]), w=0.3) if r.b(0.7) else None)
    return sp


def f_warrior(r, age, off, fac):
    age = age if age is not None else int(r.u(18, 36))
    sp = f_common(r, age)
    sp["face"].update(brow=r.c(["sword", "willow"], [0.6, 0.4]), knit=r.u(0.1, 0.6),
                      mouth="gentle", eye=r.c(["phoenix", "almond"], [0.6, 0.4]))
    sp["face"]["rouge"]["alpha"] = r.u(0.14, 0.24)
    sp["face"]["mark"] = None
    sp["hair"] = dict(kind="lady", color="hair", line_z=0.345, arch=0.03, temple_z=0.24,
                      side_z=-0.02, over_ear_z=0.05, nape_z=-0.15, side_puff=0.03,
                      volume=0.016, top_volume=0.03, knot_at=(0.0, 0.1, 0.6),
                      buns=[dict(kind="ellipsoid", c=(0.0, 0.10, 0.56), r=(0.12, 0.11, 0.10))])
    hg = r.c(["helmet", "headband", "crown"], [0.4, 0.35, 0.25])
    if hg == "helmet":
        sp["headgear"] = dict(helmet(r, fac, age), guard_drop=0.4, guard_flare=0.3, peak=0.08,
                              tassel_color=r.c(["cinnabar", "white"]))
    elif hg == "headband":
        sp["headgear"] = dict(kind="headband", color=r.c(["cinnabar", "ink_wash", "indigo", "white"]),
                              jewel=r.c([None, "jade", "gold"]))
    else:
        sp["headgear"] = dict(kind="guan", color="gold", r=0.06, h=0.06)
    robe = r.c(fac["robe"])
    cos = dict(robe=dict(color=robe), collar=collar(r, fac, robe))
    cos["armour"] = dict(armour(r, fac), mirror_r=0.11, mirror_x=0.32)
    cos["collar"]["layers"] = cos["collar"]["layers"][:2]
    if r.b(0.6):
        cos["cloak"] = dict(color=r.c(["cinnabar", "white", "indigo", "malachite_d"]))
    sp["costume"] = cos
    return sp


def f_elder(r, age, off, fac):
    age = age if age is not None else int(r.u(58, 74))
    sp = f_common(r, age)
    sp["skin"] = "elder"
    sp["face"].update(eye=r.c(["kind", "almond"]), brow=r.c(["crescent", "calm"]),
                      mouth="elder", brow_color=r.c(["grey", "white"]), mark=None,
                      rouge=dict(color="#D08A7E", alpha=0.08, r=0.12, x=0.17, z=-0.12),
                      eye_mod={}, wrinkles=dict(age_face(r, max(age, 60)), forehead=2, bags=0.7))
    sp["head"]["cheek_full"] = r.u(-0.01, 0.006)
    hc = "white_hair" if age > 64 else "grey_hair"
    sp["hair"] = dict(kind="lady", color=hc, strand="#8E8880", line_z=0.36, arch=0.03,
                      temple_z=0.25, side_z=-0.02, over_ear_z=0.05, nape_z=-0.15,
                      side_puff=r.u(0.03, 0.05), puff_t=1.45, puff_z=0.09, volume=0.016,
                      top_volume=0.03, knot_at=(0.0, 0.1, 0.58),
                      buns=[dict(kind="ellipsoid", c=(0.0, 0.12, 0.54), r=(0.16, 0.14, 0.11))],
                      ornaments=[dict(kind="pin", a=(0.06, 0.12, 0.58), b=(0.26, 0.04, 0.66),
                                      r=0.008, head=0.022, head_color=r.c(["jade", "gold"]))])
    sp["headgear"] = dict(kind="headband", color=r.c(["ink_wash", "#2A2622", "indigo_d"]),
                          z=0.235, h=0.05, lift=0.035, knot=False,
                          jewel=r.c(["jade", "gold", "malachite"]))
    robe = r.c(["ink_grey", "plum", "#6F8F86", "azurite_d", "#8A7A62"])
    sp["costume"] = dict(robe=dict(color=robe), collar=collar(r, fac, robe, "dark"))
    return sp


def unknown(r, age, off, fac):
    return dict(name="unknown", seed=7, silhouette=True, skin="warm", head=m_head(r, 0.5),
                hair=dict(kind="topknot", color="hair"), face=dict(),
                costume=dict(robe=dict(color="ink_grey"), collar=dict(layers=[dict(color="white", w=0.04)])),
                pose=dict(body_yaw=-28.0, head_yaw=6.0))


BUILDERS = dict(m_warrior=m_warrior, m_scholar=m_scholar, m_elder=m_elder, m_monk=m_monk,
                m_rogue=m_rogue, f_warrior=f_warrior, f_scholar=f_scholar, f_elder=f_elder,
                unknown=unknown)


def all_keys():
    keys = []
    for arch, n in COUNTS.items():
        keys += ["%s_%02d" % (arch, i) for i in range(1, n + 1)]
    return keys + ["unknown"]


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--keys"]:
        print(" ".join(all_keys()))
        sys.exit(0)
    for k in sys.argv[1:] or all_keys():
        s = spec_for(k)
        print(k, s.get("officer"), s.get("skin"), s.get("face", {}).get("eye"),
              s.get("headgear", {}) and s.get("headgear", {}).get("kind"),
              (s.get("beard") or {}).get("color"))

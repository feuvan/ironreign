"""MakeHuman (CC0 data) loader for the portrait pipeline - our own implementation, numpy only.

Reads the hm08 base mesh, sparse ``.target`` morph files and ``.mhclo`` proxy fits from the fetched
MakeHuman data folder (``Tools/BlenderArt/.cache/makehuman``, see third_party/fetch_makehuman.sh)
and caches everything as ``.npz`` under ``Tools/BlenderArt/.cache/portraits_B``.

Coordinates: MakeHuman is y-up, z-forward, decimetres.  :func:`to_blender` converts to Blender
metres, z-up, face looking down -Y.

Macro model (documented MakeHuman behaviour, re-implemented):
  gender g in [0,1] (0 female, 1 male); age in years -> slider 0..1 (1 y = 0, 11 y = 0.1875,
  25 y = 0.5, 90 y = 1); muscle / weight sliders 0..1 with 0.5 = average.  The ethnic targets
  ``<race>-<gender>-<age>`` are weighted race * gender * age, the ``universal-<gender>-<age>-
  <muscle>muscle-<weight>weight`` targets gender * age * muscle * weight.
"""

import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", ".."))
MH_DATA = os.path.join(TOOLS, ".cache", "makehuman", "makehuman", "data")
CACHE = os.path.join(TOOLS, ".cache", "portraits_B")

GENDERS = ("female", "male")
AGES = ("baby", "child", "young", "old")
RACES = ("african", "asian", "caucasian")
LEVELS = ("min", "average", "max")


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, re.sub(r"[^A-Za-z0-9_.-]", "_", name) + ".npz")


# ---------------------------------------------------------------------------------------------
# base mesh
# ---------------------------------------------------------------------------------------------
class Base:
    """hm08 base mesh: ``verts`` (N,3) MH coords, ``faces`` (F,4) (quads; tris repeat the last
    index), ``fuv`` (F,4) uv indices, ``uvs`` (T,2), ``fgroup`` (F,) group id, ``groups`` names."""

    def __init__(self, d):
        self.verts = d["verts"]
        self.faces = d["faces"]
        self.fuv = d["fuv"]
        self.uvs = d["uvs"]
        self.fgroup = d["fgroup"]
        self.groups = list(d["groups"])

    def group_faces(self, *names):
        ids = [i for i, g in enumerate(self.groups) if g in names]
        return np.nonzero(np.isin(self.fgroup, ids))[0]

    def group_verts(self, *names):
        f = self.faces[self.group_faces(*names)]
        return np.unique(f.ravel())


def load_base():
    cp = _cache_path("base_hm08")
    if os.path.exists(cp):
        return Base(np.load(cp, allow_pickle=False))
    verts, uvs, faces, fuv, fgroup, groups = [], [], [], [], [], []
    gid = {}
    cur = 0
    with open(os.path.join(MH_DATA, "3dobjs", "base.obj")) as fh:
        for line in fh:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                uvs.append([float(x) for x in line.split()[1:3]])
            elif line.startswith("g "):
                name = line.split()[1].strip()
                if name not in gid:
                    gid[name] = len(groups)
                    groups.append(name)
                cur = gid[name]
            elif line.startswith("f "):
                vs, ts = [], []
                for tok in line.split()[1:]:
                    p = tok.split("/")
                    vs.append(int(p[0]) - 1)
                    ts.append(int(p[1]) - 1 if len(p) > 1 and p[1] else -1)
                while len(vs) < 4:
                    vs.append(vs[-1])
                    ts.append(ts[-1])
                faces.append(vs[:4])
                fuv.append(ts[:4])
                fgroup.append(cur)
    d = dict(verts=np.array(verts, np.float32), uvs=np.array(uvs, np.float32),
             faces=np.array(faces, np.int32), fuv=np.array(fuv, np.int32),
             fgroup=np.array(fgroup, np.int32), groups=np.array(groups))
    np.savez(cp, **d)
    return Base(d)


# ---------------------------------------------------------------------------------------------
# targets
# ---------------------------------------------------------------------------------------------
_TCACHE = {}


def load_target(rel):
    """``rel`` relative to data/targets, e.g. 'nose/nose-hump-incr'. Returns (idx, delta)."""
    rel = rel if rel.endswith(".target") else rel + ".target"
    if rel in _TCACHE:
        return _TCACHE[rel]
    cp = _cache_path("t_" + rel)
    if os.path.exists(cp):
        d = np.load(cp)
        res = (d["idx"], d["delta"])
    else:
        idx, dl = [], []
        path = os.path.join(MH_DATA, "targets", rel)
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = line.split()
                idx.append(int(p[0]))
                dl.append([float(p[1]), float(p[2]), float(p[3])])
        res = (np.array(idx, np.int32), np.array(dl, np.float32).reshape(-1, 3))
        np.savez(cp, idx=res[0], delta=res[1])
    _TCACHE[rel] = res
    return res


def target_exists(rel):
    rel = rel if rel.endswith(".target") else rel + ".target"
    return os.path.exists(os.path.join(MH_DATA, "targets", rel))


def age_slider(years):
    """Age in years -> MakeHuman macro slider value 0..1."""
    y = float(years)
    if y < 11:
        return max(0.0, (y - 1.0) / 10.0 * 0.1875)
    if y < 25:
        return 0.1875 + (y - 11.0) / 14.0 * (0.5 - 0.1875)
    return min(1.0, 0.5 + (y - 25.0) / 65.0 * 0.5)


def _age_weights(a):
    w = dict.fromkeys(AGES, 0.0)
    if a < 0.1875:
        w["child"] = a / 0.1875
        w["baby"] = 1 - w["child"]
    elif a < 0.5:
        w["young"] = (a - 0.1875) / (0.5 - 0.1875)
        w["child"] = 1 - w["young"]
    else:
        w["old"] = (a - 0.5) / 0.5
        w["young"] = 1 - w["old"]
    return w


def _level_weights(v):
    w = dict.fromkeys(LEVELS, 0.0)
    if v < 0.5:
        w["average"] = v / 0.5
        w["min"] = 1 - w["average"]
    else:
        w["max"] = (v - 0.5) / 0.5
        w["average"] = 1 - w["max"]
    return w


def macro_targets(gender=1.0, age_years=30.0, muscle=0.5, weight=0.5, race=None):
    """List of (target rel path, weight) for the macro model."""
    race = race or {"asian": 1.0}
    gw = {"female": 1.0 - gender, "male": gender}
    aw = _age_weights(age_slider(age_years))
    mw = _level_weights(muscle)
    ww = _level_weights(weight)
    out = []
    for r, rv in race.items():
        for g, gv in gw.items():
            for a, av in aw.items():
                w = rv * gv * av
                if w > 1e-4:
                    out.append(("macrodetails/%s-%s-%s" % (r, g, a), w))
    for g, gv in gw.items():
        for a, av in aw.items():
            for m, mv in mw.items():
                for k, kv in ww.items():
                    w = gv * av * mv * kv
                    if w > 1e-4:
                        rel = "macrodetails/universal-%s-%s-%smuscle-%sweight" % (g, a, m, k)
                        if target_exists(rel):
                            out.append((rel, w))
    return out


#: friendly slider name -> (decr target, incr target); value in [-1, 1].  Symmetric l/r pairs are
#: expanded automatically when the name contains '{s}'.
SLIDERS = {
    "head_age": ("head/head-age-decr", "head/head-age-incr"),
    "head_fat": ("head/head-fat-decr", "head/head-fat-incr"),
    "head_angle": ("head/head-angle-in", "head/head-angle-out"),
    "head_oval": (None, "head/head-oval"),
    "head_round": (None, "head/head-round"),
    "head_square": (None, "head/head-square"),
    "head_rect": (None, "head/head-rectangular"),
    "head_triangular": (None, "head/head-triangular"),
    "head_invtriangular": (None, "head/head-invertedtriangular"),
    "head_diamond": (None, "head/head-diamond"),
    "head_width": ("head/head-scale-horiz-decr", "head/head-scale-horiz-incr"),
    "head_height": ("head/head-scale-vert-decr", "head/head-scale-vert-incr"),
    "head_depth": ("head/head-scale-depth-decr", "head/head-scale-depth-incr"),
    "head_back": ("head/head-back-scale-depth-decr", "head/head-back-scale-depth-incr"),
    "forehead_height": ("forehead/forehead-scale-vert-decr", "forehead/forehead-scale-vert-incr"),
    "forehead_slope": ("forehead/forehead-trans-backward", "forehead/forehead-trans-forward"),
    "forehead_bulge": ("forehead/forehead-nubian-decr", "forehead/forehead-nubian-incr"),
    "temples": ("forehead/forehead-temple-decr", "forehead/forehead-temple-incr"),
    "brow_angle": ("eyebrows/eyebrows-angle-down", "eyebrows/eyebrows-angle-up"),
    "brow_height": ("eyebrows/eyebrows-trans-down", "eyebrows/eyebrows-trans-up"),
    "brow_ridge": ("eyebrows/eyebrows-trans-backward", "eyebrows/eyebrows-trans-forward"),
    "eye_bag": ("eyes/{s}-eye-bag-decr", "eyes/{s}-eye-bag-incr"),
    "eye_epicanthus": ("eyes/{s}-eye-epicanthus-out", "eyes/{s}-eye-epicanthus-in"),
    "eye_fold": ("eyes/{s}-eye-eyefold-down", "eyes/{s}-eye-eyefold-up"),
    "eye_fold_angle": ("eyes/{s}-eye-eyefold-angle-down", "eyes/{s}-eye-eyefold-angle-up"),
    "eye_fold_convex": ("eyes/{s}-eye-eyefold-concave", "eyes/{s}-eye-eyefold-convex"),
    "eye_height1": ("eyes/{s}-eye-height1-decr", "eyes/{s}-eye-height1-incr"),
    "eye_height2": ("eyes/{s}-eye-height2-decr", "eyes/{s}-eye-height2-incr"),
    "eye_height3": ("eyes/{s}-eye-height3-decr", "eyes/{s}-eye-height3-incr"),
    "eye_corner_in": ("eyes/{s}-eye-corner1-down", "eyes/{s}-eye-corner1-up"),
    "eye_corner_out": ("eyes/{s}-eye-corner2-down", "eyes/{s}-eye-corner2-up"),
    "eye_push1": ("eyes/{s}-eye-push1-in", "eyes/{s}-eye-push1-out"),
    "eye_push2": ("eyes/{s}-eye-push2-in", "eyes/{s}-eye-push2-out"),
    "eye_scale": ("eyes/{s}-eye-scale-decr", "eyes/{s}-eye-scale-incr"),
    "eye_spacing": ("eyes/{s}-eye-trans-in", "eyes/{s}-eye-trans-out"),
    "eye_vert": ("eyes/{s}-eye-trans-down", "eyes/{s}-eye-trans-up"),
    "nose_width": ("nose/nose-scale-horiz-decr", "nose/nose-scale-horiz-incr"),
    "nose_length": ("nose/nose-scale-vert-decr", "nose/nose-scale-vert-incr"),
    "nose_depth": ("nose/nose-scale-depth-decr", "nose/nose-scale-depth-incr"),
    "nose_hump": ("nose/nose-hump-decr", "nose/nose-hump-incr"),
    "nose_curve": ("nose/nose-curve-concave", "nose/nose-curve-convex"),
    "nose_flare": ("nose/nose-flaring-decr", "nose/nose-flaring-incr"),
    "nose_greek": ("nose/nose-greek-decr", "nose/nose-greek-incr"),
    "nose_point_width": ("nose/nose-point-width-decr", "nose/nose-point-width-incr"),
    "nose_tip": ("nose/nose-point-down", "nose/nose-point-up"),
    "nose_base": ("nose/nose-base-down", "nose/nose-base-up"),
    "nostril_width": ("nose/nose-nostrils-width-decr", "nose/nose-nostrils-width-incr"),
    "nose_compress": ("nose/nose-compression-uncompress", "nose/nose-compression-compress"),
    "nose_vert": ("nose/nose-trans-down", "nose/nose-trans-up"),
    "nose_forward": ("nose/nose-trans-backward", "nose/nose-trans-forward"),
    "mouth_width": ("mouth/mouth-scale-horiz-decr", "mouth/mouth-scale-horiz-incr"),
    "mouth_height": ("mouth/mouth-scale-vert-decr", "mouth/mouth-scale-vert-incr"),
    "mouth_depth": ("mouth/mouth-scale-depth-decr", "mouth/mouth-scale-depth-incr"),
    "mouth_vert": ("mouth/mouth-trans-down", "mouth/mouth-trans-up"),
    "mouth_forward": ("mouth/mouth-trans-backward", "mouth/mouth-trans-forward"),
    "mouth_corners": ("mouth/mouth-angles-down", "mouth/mouth-angles-up"),
    "lip_upper_vol": ("mouth/mouth-upperlip-volume-decr", "mouth/mouth-upperlip-volume-incr"),
    "lip_lower_vol": ("mouth/mouth-lowerlip-volume-decr", "mouth/mouth-lowerlip-volume-incr"),
    "lip_upper_h": ("mouth/mouth-upperlip-height-decr", "mouth/mouth-upperlip-height-incr"),
    "lip_lower_h": ("mouth/mouth-lowerlip-height-decr", "mouth/mouth-lowerlip-height-incr"),
    "lip_upper_w": ("mouth/mouth-upperlip-width-decr", "mouth/mouth-upperlip-width-incr"),
    "lip_lower_w": ("mouth/mouth-lowerlip-width-decr", "mouth/mouth-lowerlip-width-incr"),
    "cupid": ("mouth/mouth-cupidsbow-decr", "mouth/mouth-cupidsbow-incr"),
    "philtrum": ("mouth/mouth-philtrum-volume-decr", "mouth/mouth-philtrum-volume-incr"),
    "laugh_lines": ("mouth/mouth-laugh-lines-in", "mouth/mouth-laugh-lines-out"),
    "dimples": ("mouth/mouth-dimples-in", "mouth/mouth-dimples-out"),
    "chin_prominent": ("chin/chin-prominent-decr", "chin/chin-prominent-incr"),
    "chin_width": ("chin/chin-width-decr", "chin/chin-width-incr"),
    "chin_height": ("chin/chin-height-decr", "chin/chin-height-incr"),
    "chin_bones": ("chin/chin-bones-decr", "chin/chin-bones-incr"),
    "chin_jut": ("chin/chin-prognathism-decr", "chin/chin-prognathism-incr"),
    "chin_cleft": ("chin/chin-cleft-decr", "chin/chin-cleft-incr"),
    "jaw_drop": ("chin/chin-jaw-drop-decr", "chin/chin-jaw-drop-incr"),
    "chin_triangle": (None, "chin/chin-triangle"),
    "cheek_bones": ("cheek/{s}-cheek-bones-decr", "cheek/{s}-cheek-bones-incr"),
    "cheek_inner": ("cheek/{s}-cheek-inner-decr", "cheek/{s}-cheek-inner-incr"),
    "cheek_volume": ("cheek/{s}-cheek-volume-decr", "cheek/{s}-cheek-volume-incr"),
    "cheek_vert": ("cheek/{s}-cheek-trans-down", "cheek/{s}-cheek-trans-up"),
    "ear_scale": ("ears/{s}-ear-scale-decr", "ears/{s}-ear-scale-incr"),
    "ear_flap": ("ears/{s}-ear-flap-decr", "ears/{s}-ear-flap-incr"),
    "ear_lobe": ("ears/{s}-ear-lobe-decr", "ears/{s}-ear-lobe-incr"),
    "ear_wing": ("ears/{s}-ear-wing-decr", "ears/{s}-ear-wing-incr"),
    "neck_width": ("neck/neck-scale-horiz-decr", "neck/neck-scale-horiz-incr"),
    "neck_depth": ("neck/neck-scale-depth-decr", "neck/neck-scale-depth-incr"),
    "neck_height": ("neck/neck-scale-vert-decr", "neck/neck-scale-vert-incr"),
    "neck_double": ("neck/neck-double-decr", "neck/neck-double-incr"),
    "torso_vshape": ("torso/torso-vshape-decr", "torso/torso-vshape-incr"),
    "torso_width": ("torso/torso-scale-horiz-decr", "torso/torso-scale-horiz-incr"),
    "pectoral": ("torso/torso-muscle-pectoral-decr", "torso/torso-muscle-pectoral-incr"),
}

#: expression units (per race folder): value 0..1
EXPRESSIONS = (
    "eye-{s}-closure", "eye-{s}-opened-up", "eye-{s}-slit", "eyebrows-{s}-down",
    "eyebrows-{s}-extern-up", "eyebrows-{s}-inner-up", "eyebrows-{s}-up", "mouth-compression",
    "mouth-corner-puller", "mouth-depression-retraction", "mouth-depression", "mouth-elevation",
    "mouth-eversion", "mouth-open", "mouth-parling", "mouth-part-later", "mouth-protusion",
    "mouth-pursing", "mouth-retraction", "mouth-upward-retraction", "neck-platysma",
    "nose-compression", "nose-depression", "nose-{s}-dilatation", "nose-{s}-elevation",
)


def slider_targets(name, value):
    """(target, weight) list for a named face slider; '<name>_l' / '<name>_r' address one side
    of a symmetric slider."""
    side = None
    base = name
    if name.endswith("_l") or name.endswith("_r"):
        base, side = name[:-2], name[-1]
    if base not in SLIDERS:
        raise KeyError("unknown slider %r" % name)
    dec, inc = SLIDERS[base]
    t = inc if value >= 0 else dec
    if t is None:
        return []
    w = abs(float(value))
    if "{s}" in t:
        sides = [side] if side else ["l", "r"]
        return [(t.format(s=s), w) for s in sides]
    return [(t, w)]


def expression_targets(name, value, race="asian"):
    side = None
    base = name
    if name.endswith("_l") or name.endswith("_r"):
        base, side = name[:-2], name[-1]
    key = base if base in EXPRESSIONS else None
    if key is None:
        cand = [e for e in EXPRESSIONS if e.replace("-{s}", "") == base]
        if not cand:
            raise KeyError("unknown expression %r" % name)
        key = cand[0]
    sides = [{"l": "left", "r": "right"}[side]] if side else ["left", "right"]
    if "{s}" in key:
        return [("expression/units/%s/%s" % (race, key.format(s=s)), float(value)) for s in sides]
    return [("expression/units/%s/%s" % (race, key), float(value))]


def apply_targets(verts, targets):
    v = verts.astype(np.float64).copy()
    for rel, w in targets:
        if abs(w) < 1e-6:
            continue
        idx, d = load_target(rel)
        np.add.at(v, idx, d * w)
    return v.astype(np.float32)


# ---------------------------------------------------------------------------------------------
# proxies (.mhclo)
# ---------------------------------------------------------------------------------------------
class Proxy:
    def __init__(self, d):
        self.refs = d["refs"]
        self.weights = d["weights"]
        self.offsets = d["offsets"]
        self.scale_refs = d["scale_refs"]
        self.scale_vals = d["scale_vals"]
        self.verts = d["verts"]
        self.faces = d["faces"]
        self.fuv = d["fuv"]
        self.uvs = d["uvs"]

    def fit(self, base_verts):
        """Proxy vertex positions (MH coords) for deformed base vertices."""
        b = base_verts
        sc = np.ones(3, np.float32)
        for ax in range(3):
            a, c = self.scale_refs[ax]
            sc[ax] = abs(b[a, ax] - b[c, ax]) / self.scale_vals[ax]
        p = (b[self.refs] * self.weights[..., None]).sum(1)
        return p + self.offsets * sc


def load_proxy(rel):
    """``rel`` relative to data, e.g. 'eyes/high-poly/high-poly.mhclo'."""
    cp = _cache_path("p_" + rel)
    if os.path.exists(cp):
        return Proxy(np.load(cp))
    path = os.path.join(MH_DATA, rel)
    refs, wts, offs = [], [], []
    scale_refs = [[0, 0], [0, 0], [0, 0]]
    scale_vals = [1.0, 1.0, 1.0]
    obj = None
    in_verts = False
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            p = s.split()
            if p[0] in ("x_scale", "y_scale", "z_scale"):
                ax = "xyz".index(p[0][0])
                scale_refs[ax] = [int(p[1]), int(p[2])]
                scale_vals[ax] = float(p[3])
            elif p[0] == "obj_file":
                obj = p[1]
            elif p[0] == "verts":
                in_verts = True
            elif in_verts and re.match(r"^-?\d", p[0]):
                if len(p) >= 9:
                    refs.append([int(p[0]), int(p[1]), int(p[2])])
                    wts.append([float(p[3]), float(p[4]), float(p[5])])
                    offs.append([float(p[6]), float(p[7]), float(p[8])])
                elif len(p) == 1:
                    refs.append([int(p[0])] * 3)
                    wts.append([1.0, 0.0, 0.0])
                    offs.append([0.0, 0.0, 0.0])
            elif in_verts:
                in_verts = False
    verts, uvs, faces, fuv = [], [], [], []
    with open(os.path.join(os.path.dirname(path), obj)) as fh:
        for line in fh:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                uvs.append([float(x) for x in line.split()[1:3]])
            elif line.startswith("f "):
                vs, ts = [], []
                for tok in line.split()[1:]:
                    q = tok.split("/")
                    vs.append(int(q[0]) - 1)
                    ts.append(int(q[1]) - 1 if len(q) > 1 and q[1] else -1)
                while len(vs) < 4:
                    vs.append(vs[-1])
                    ts.append(ts[-1])
                faces.append(vs[:4])
                fuv.append(ts[:4])
    d = dict(refs=np.array(refs, np.int32), weights=np.array(wts, np.float32),
             offsets=np.array(offs, np.float32), scale_refs=np.array(scale_refs, np.int32),
             scale_vals=np.array(scale_vals, np.float32), verts=np.array(verts, np.float32),
             faces=np.array(faces, np.int32), fuv=np.array(fuv, np.int32),
             uvs=np.array(uvs, np.float32))
    np.savez(cp, **d)
    return Proxy(d)


def to_blender(v):
    """MH (dm, y-up, +z forward) -> Blender (m, z-up, face towards -Y)."""
    v = np.asarray(v, np.float32)
    return np.stack([v[..., 0], -v[..., 2], v[..., 1]], -1) * 0.1

"""MakeHuman (CC0 data) reader for the gongbi portraits - our own numpy implementation.

Only the *data* (base mesh + sparse morph targets) is used.  Nothing here imports bpy, so it also
runs under the system python.

Policy (hard rule): the ethnicity macros are NEVER exposed.  The race blend is fixed at
MakeHuman's neutral default (1/3 african, 1/3 asian, 1/3 caucasian); every face is designed with
the bipolar feature targets from the classical figure-painting canon (see canon.py) instead.

Conventions: MakeHuman units are decimetres, +Y up, face toward +Z.  :func:`to_blender` converts
to metres, +Z up, face toward -Y.
"""

import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", ".."))
MH_DATA = os.path.join(TOOLS, ".cache", "makehuman", "makehuman", "data")
CACHE = os.path.join(TOOLS, ".cache", "portraits_gongbiA")
N_BODY = 13380  # vertices 0..13379 are the skin; helpers follow

#: fixed neutral race blend (MakeHuman's default).  Not a parameter, on purpose.
_NEUTRAL_RACE = {"african": 1.0 / 3.0, "asian": 1.0 / 3.0, "caucasian": 1.0 / 3.0}


def _cp(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


class Base:
    def __init__(self, verts, faces, face_group):
        self.verts = verts
        self.faces = faces
        self.face_group = face_group


def load_base():
    """Body skin only: verts (N,3) MH units, quads (F,4) int, group per face."""
    cp = _cp("base_body.npz")
    src = os.path.join(MH_DATA, "3dobjs", "base.obj")
    if os.path.exists(cp) and os.path.getmtime(cp) >= os.path.getmtime(src):
        d = np.load(cp)
        return Base(d["verts"], d["faces"], None)
    verts, faces = [], []
    group = None
    with open(src) as f:
        for line in f:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f ") and group == "body":
                vs = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
                if len(vs) == 3:
                    vs.append(vs[2])
                faces.append(vs)
    verts = np.array(verts, np.float64)
    faces = np.array(faces, np.int64)
    np.savez(cp, verts=verts, faces=faces)
    return Base(verts, faces, None)


_TC = {}


def target_path(rel):
    rel = rel if rel.endswith(".target") else rel + ".target"
    return os.path.join(MH_DATA, "targets", rel)


def exists(rel):
    return os.path.exists(target_path(rel))


def load_target(rel):
    if rel in _TC:
        return _TC[rel]
    src = target_path(rel)
    cp = _cp("t_" + re.sub(r"[^A-Za-z0-9_.-]", "_", rel) + ".npz")
    if os.path.exists(cp):
        d = np.load(cp)
        r = (d["i"].astype(np.int64), d["d"].astype(np.float64))
    else:
        idx, dl = [], []
        with open(src) as f:
            for line in f:
                if not line.strip() or line[0] == "#":
                    continue
                p = line.split()
                if len(p) < 4:
                    continue
                idx.append(int(p[0]))
                dl.append((float(p[1]), float(p[2]), float(p[3])))
        r = (np.array(idx, np.int64), np.array(dl, np.float64).reshape(-1, 3))
        np.savez(cp, i=r[0].astype(np.int32), d=r[1].astype(np.float32))
    _TC[rel] = r
    return r


def apply(verts, weights):
    out = verts.copy()
    for rel, w in weights.items():
        if abs(w) < 1e-6:
            continue
        i, d = load_target(rel)
        m = i < len(out)
        out[i[m]] += w * d[m]
    return out


def _hat3(v):
    if v < 0.5:
        return {"min": 1.0 - 2.0 * v, "average": 2.0 * v, "max": 0.0}
    return {"min": 0.0, "average": 2.0 - 2.0 * v, "max": 2.0 * v - 1.0}


def _age_w(years):
    """Adults only: 18..25 -> young, 25..90 blends to old."""
    years = max(18.0, min(90.0, years))
    old = max(0.0, (years - 25.0) / 65.0)
    return {"young": 1.0 - old, "old": old}


def macro_weights(gender=1.0, years=30.0, muscle=0.5, weight=0.5):
    """Macro lattice target weights at the neutral race blend."""
    out = {}
    gw = {"female": 1.0 - gender, "male": gender}
    aw = _age_w(years)
    mw, ww = _hat3(muscle), _hat3(weight)
    for r, wr in _NEUTRAL_RACE.items():
        for g, wg in gw.items():
            for a, wa in aw.items():
                w = wr * wg * wa
                if w > 1e-5:
                    out["macrodetails/%s-%s-%s" % (r, g, a)] = w
    for g, wg in gw.items():
        for a, wa in aw.items():
            for m, wm in mw.items():
                for k, wk in ww.items():
                    w = wg * wa * wm * wk
                    rel = "macrodetails/universal-%s-%s-%smuscle-%sweight" % (g, a, m, k)
                    if w > 1e-5 and exists(rel):
                        out[rel] = out.get(rel, 0.0) + w
    return out


def modifier_weights(mods):
    """{"group/stem-lo|hi": v in [-1,1]} -> target weights; "{s}" expands to l and r."""
    out = {}
    for name, v in mods.items():
        if abs(v) < 1e-6:
            continue
        if "ethnic" in name or "asian" in name or "african" in name or "caucasian" in name:
            raise ValueError("ethnicity targets are forbidden in the gongbi pipeline: %s" % name)
        sides = ["l", "r"] if "{s}" in name else [None]
        for s in sides:
            n = name.replace("{s}", s) if s else name
            if "|" in n:
                stem, hi = n.split("|")
                base, lo = stem.rsplit("-", 1)
                rel = "%s-%s" % (base, hi if v > 0 else lo)
                out[rel] = out.get(rel, 0.0) + abs(v)
            else:
                out[n] = out.get(n, 0.0) + v
    return out


def to_blender(v):
    v = np.asarray(v, np.float64)
    return np.stack([v[..., 0], -v[..., 2], v[..., 1]], -1) * 0.1


_JOINTS = None


def joint_index():
    """{joint group name: vertex indices} for the helper joint cubes in base.obj."""
    global _JOINTS
    if _JOINTS is not None:
        return _JOINTS
    cp = _cp("joints.npz")
    src = os.path.join(MH_DATA, "3dobjs", "base.obj")
    if os.path.exists(cp):
        d = np.load(cp)
        _JOINTS = {k: d[k] for k in d.files}
        return _JOINTS
    out = {}
    group = None
    with open(src) as f:
        for line in f:
            if line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f ") and group and group.startswith("joint-"):
                s = out.setdefault(group, set())
                s.update(int(t.split("/")[0]) - 1 for t in line.split()[1:])
    _JOINTS = {k: np.array(sorted(v), np.int64) for k, v in out.items()}
    np.savez(cp, **_JOINTS)
    return _JOINTS


def body_verts(gender, years, muscle=0.5, weight=0.5, mods=None):
    """Shaped body: (skin verts (N,3) Blender metres, quads, {joint: centre})."""
    b = load_base()
    w = macro_weights(gender, years, muscle, weight)
    if mods:
        for k, v in modifier_weights(mods).items():
            w[k] = w.get(k, 0.0) + v
    va = apply(b.verts, w)
    joints = {k: to_blender(va[ix].mean(0)) for k, ix in joint_index().items()}
    return to_blender(va[:N_BODY]), b.faces, joints

"""MakeHuman (CC0 data) reader for the portrait pipeline - our own implementation, numpy only.

Reads the hm08 base mesh, sparse ``.target`` morph files and ``.mhclo`` proxy fittings from the
fetched MakeHuman data (see Tools/BlenderArt/third_party/fetch_makehuman.sh).  Nothing here needs
``bpy`` so it also runs under the system python.

Conventions
* MakeHuman units are decimetres, +Y up, the face looks toward +Z.  :func:`to_blender` converts to
  metres, +Z up, face toward -Y (Blender's "front").
* Targets are cached as ``.npz`` (indices int32, deltas float32) under ``.cache/portraits_A``.

Macro model (age / gender / muscle / weight / ethnicity) - the macro sliders blend a lattice of
targets; each corner target's weight is the product of the per-axis weights:

    gender  g in [0,1]: female = 1-g, male = g
    age     a in [0,1]: 0 -> 1 yr, 0.1875 -> 11 yr, 0.5 -> 25 yr, 1 -> 90 yr (piecewise linear)
            baby/child/young/old are hat functions over those knots
    muscle  m, weight w in [0,1]: 0.5 is "average"; min/average/max hat functions
    race    african / asian / caucasian, normalised to sum 1
"""

import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", ".."))
MH_DATA = os.path.join(TOOLS, ".cache", "makehuman", "makehuman", "data")
CACHE = os.path.join(TOOLS, ".cache", "portraits_A")

N_BODY = 13380  # vertices 0..13379 are the skin; helpers follow


# --------------------------------------------------------------------------------------- base mesh
class BaseMesh:
    """Parsed base.obj: ``verts`` (N,3) MH units, ``uvs`` (M,2), ``faces`` list of vertex-index
    tuples, ``face_uvs`` matching uv-index tuples, ``face_group`` group name per face."""

    def __init__(self, verts, uvs, faces, face_uvs, face_group):
        self.verts = verts
        self.uvs = uvs
        self.faces = faces
        self.face_uvs = face_uvs
        self.face_group = face_group

    def group_faces(self, *names):
        names = set(names)
        return [i for i, g in enumerate(self.face_group) if g in names]

    def group_verts(self, *names):
        s = set()
        for i in self.group_faces(*names):
            s.update(self.faces[i])
        return np.array(sorted(s), np.int64)


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


def load_base():
    cp = _cache_path("base_hm08.npz")
    src = os.path.join(MH_DATA, "3dobjs", "base.obj")
    if os.path.exists(cp) and os.path.getmtime(cp) >= os.path.getmtime(src):
        d = np.load(cp, allow_pickle=False)
        fl = d["face_len"]
        fv = np.split(d["face_v"], np.cumsum(fl)[:-1])
        fu = np.split(d["face_uv"], np.cumsum(fl)[:-1])
        groups = list(d["group_names"])
        fg = [groups[i] for i in d["face_gi"]]
        return BaseMesh(d["verts"], d["uvs"], [tuple(x) for x in fv], [tuple(x) for x in fu], fg)
    verts, uvs, faces, fuv, fg = [], [], [], [], []
    group = "body"
    with open(src) as f:
        for line in f:
            if line.startswith("v "):
                verts.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("vt "):
                uvs.append([float(x) for x in line.split()[1:3]])
            elif line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f "):
                vs, us = [], []
                for t in line.split()[1:]:
                    p = t.split("/")
                    vs.append(int(p[0]) - 1)
                    us.append(int(p[1]) - 1 if len(p) > 1 and p[1] else -1)
                faces.append(tuple(vs))
                fuv.append(tuple(us))
                fg.append(group)
    verts = np.array(verts, np.float64)
    uvs = np.array(uvs, np.float64)
    groups = sorted(set(fg))
    gi = np.array([groups.index(g) for g in fg], np.int32)
    np.savez(cp, verts=verts, uvs=uvs, face_len=np.array([len(f) for f in faces], np.int32),
             face_v=np.concatenate([np.array(f, np.int32) for f in faces]),
             face_uv=np.concatenate([np.array(f, np.int32) for f in fuv]),
             group_names=np.array(groups), face_gi=gi)
    return BaseMesh(verts, uvs, faces, fuv, fg)


# ------------------------------------------------------------------------------------------ targets
_TCACHE = {}


def target_path(rel):
    rel = rel if rel.endswith(".target") else rel + ".target"
    return os.path.join(MH_DATA, "targets", rel)


def load_target(rel):
    """Sparse target -> (idx int64 array, delta (k,3) float64)."""
    if rel in _TCACHE:
        return _TCACHE[rel]
    src = target_path(rel)
    cp = _cache_path("t_" + re.sub(r"[^A-Za-z0-9_.-]", "_", rel) + ".npz")
    if os.path.exists(cp):
        d = np.load(cp)
        r = (d["i"].astype(np.int64), d["d"].astype(np.float64))
    else:
        idx, dl = [], []
        with open(src) as f:
            for line in f:
                if not line or line[0] == "#":
                    continue
                p = line.split()
                if len(p) < 4:
                    continue
                idx.append(int(p[0]))
                dl.append((float(p[1]), float(p[2]), float(p[3])))
        r = (np.array(idx, np.int64), np.array(dl, np.float64).reshape(-1, 3))
        np.savez(cp, i=r[0].astype(np.int32), d=r[1].astype(np.float32))
    _TCACHE[rel] = r
    return r


def exists(rel):
    return os.path.exists(target_path(rel))


def apply_targets(verts, weights):
    """verts += sum(w * target).  ``weights``: {relpath: w}; zero weights skipped."""
    out = verts.copy()
    for rel, w in weights.items():
        if abs(w) < 1e-6:
            continue
        i, d = load_target(rel)
        out[i] += w * d
    return out


# ------------------------------------------------------------------------------------ macro model
def _hat3(v):
    """min/average/max weights for a 0..1 slider with 0.5 = average."""
    if v < 0.5:
        return {"min": 1.0 - 2.0 * v, "average": 2.0 * v, "max": 0.0}
    return {"min": 0.0, "average": 2.0 - 2.0 * v, "max": 2.0 * v - 1.0}


def age_weights(a):
    """baby/child/young/old weights for the MH age slider value ``a``."""
    if a < 0.5:
        young = max(0.0, (a - 0.1875) / (0.5 - 0.1875))
        baby = max(0.0, 1.0 - a / 0.1875)
        child = max(0.0, min(1.0, a / 0.1875) - young)
        return {"baby": baby, "child": child, "young": young, "old": 0.0}
    old = (a - 0.5) / 0.5
    return {"baby": 0.0, "child": 0.0, "young": 1.0 - old, "old": old}


def age_slider(years):
    """Years -> MH age slider.  Ours, not MakeHuman's: adults from 18 use the young target fully
    (MH's own curve keeps 18-24 year olds half "child", which reads as a teenager)."""
    if years >= 25:
        return min(1.0, 0.5 + 0.5 * (years - 25.0) / 65.0)
    if years >= 16:
        # 16 -> 0.44, 25 -> 0.5: young weight 0.81 .. 1
        return 0.44 + 0.06 * (years - 16.0) / 9.0
    return 0.1875 + (0.5 - 0.1875) * max(0.0, years - 11.0) / 14.0


def macro_weights(gender=1.0, age=0.5, muscle=0.5, weight=0.5, african=0.0, asian=1.0,
                  caucasian=0.0):
    """Return {target relpath: weight} for the macro lattice (race + universal)."""
    out = {}
    gw = {"female": 1.0 - gender, "male": gender}
    aw = age_weights(age)
    mw = _hat3(muscle)
    ww = _hat3(weight)
    s = african + asian + caucasian
    rw = {"african": african / s, "asian": asian / s, "caucasian": caucasian / s}
    for r, wr in rw.items():
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


# ----------------------------------------------------------------------------- bipolar modifiers
def modifier_weights(mods):
    """{name: value in [-1, 1]} -> target weights.

    ``name`` is "group/stem" with the two ends separated by '|', e.g. "nose/nose-hump-decr|incr"
    or a single target "head/head-square" (one-sided, value 0..1).  Left/right pairs written as
    "eyes/{s}-eye-height2-decr|incr" (the ``{s}`` expands to l and r)."""
    out = {}
    for name, v in mods.items():
        if abs(v) < 1e-6:
            continue
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


# --------------------------------------------------------------------------------------- proxies
class Proxy:
    """A .mhclo fitted proxy (e.g. the high-poly eyes)."""

    def __init__(self, path):
        self.path = path
        self.dir = os.path.dirname(path)
        self.refs = []      # (i0,i1,i2, w0,w1,w2, dx,dy,dz)
        self.scales = {}
        self.obj = None
        self.material = None
        with open(path) as f:
            in_verts = False
            for line in f:
                if line.startswith("#"):
                    continue
                p = line.split()
                if not p:
                    continue
                if in_verts:
                    if len(p) == 9:
                        self.refs.append([float(x) for x in p])
                        continue
                    if len(p) == 1 and p[0].isdigit():
                        i = int(p[0])
                        self.refs.append([i, i, i, 1, 0, 0, 0, 0, 0])
                        continue
                    in_verts = False
                k = p[0]
                if k == "verts":
                    in_verts = True
                elif k in ("x_scale", "y_scale", "z_scale"):
                    self.scales[k[0]] = (int(p[1]), int(p[2]), float(p[3]))
                elif k == "obj_file":
                    self.obj = os.path.join(self.dir, p[1])
                elif k == "material":
                    self.material = os.path.normpath(os.path.join(self.dir, p[1]))
        r = np.array(self.refs, np.float64)
        self.ri = r[:, :3].astype(np.int64)
        self.rw = r[:, 3:6]
        self.ro = r[:, 6:9]

    def fit(self, base_verts):
        sc = np.ones(3)
        for ax, k in enumerate("xyz"):
            if k in self.scales:
                a, b, ref = self.scales[k]
                sc[ax] = abs(base_verts[a, ax] - base_verts[b, ax]) / ref
        v = (base_verts[self.ri] * self.rw[..., None]).sum(1)
        return v + self.ro * sc

    def load_obj(self):
        verts, uvs, faces, fuv = [], [], [], []
        with open(self.obj) as f:
            for line in f:
                if line.startswith("v "):
                    verts.append([float(x) for x in line.split()[1:4]])
                elif line.startswith("vt "):
                    uvs.append([float(x) for x in line.split()[1:3]])
                elif line.startswith("f "):
                    vs, us = [], []
                    for t in line.split()[1:]:
                        p = t.split("/")
                        vs.append(int(p[0]) - 1)
                        us.append(int(p[1]) - 1 if len(p) > 1 and p[1] else -1)
                    faces.append(tuple(vs))
                    fuv.append(tuple(us))
        return np.array(verts), np.array(uvs), faces, fuv


def eyes_proxy():
    return Proxy(os.path.join(MH_DATA, "eyes", "high-poly", "high-poly.mhclo"))


# ----------------------------------------------------------------------------------- conversion
def to_blender(v):
    """MH decimetres (+Y up, face +Z) -> metres (+Z up, face -Y)."""
    v = np.asarray(v, np.float64)
    return np.stack([v[..., 0], -v[..., 2], v[..., 1]], -1) * 0.1

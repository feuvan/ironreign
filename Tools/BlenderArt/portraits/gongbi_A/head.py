"""The bust's head and shoulders from the MakeHuman base mesh (neutral race blend, see mh.py),
reshaped by the canon's feature targets, plus closed eye surfaces and landmarks.

The head is only a *form* for Freestyle contours and soft 晕染; every facial feature is drawn
as a brush decal (face.py), so the MakeHuman eyelids, lips and nostrils are face-marked and never
produce lines.
"""

import math

import bpy
import numpy as np

import geo
import mh


class Head:
    pass


def build(canon, col_skin, col_hidden, skin_mat, parent):
    """canon: dict with gender, years, muscle, weight, mods.  Returns Head with obj, eyes,
    landmarks and a projection Surface."""
    v, f, j = mh.body_verts(canon["gender"], canon["years"], canon.get("muscle", 0.5),
                            canon.get("weight", 0.5), canon.get("mods"))
    H = Head()
    eL, eR = j["joint-l-eye"], j["joint-r-eye"]
    H.eye_l, H.eye_r = eL, eR
    eye_z = 0.5 * (eL[2] + eR[2])
    H.eye_z = eye_z
    # crop: head, neck and shoulders down to the upper chest
    cut = eye_z - canon.get("crop", 0.34)
    keep = np.all(v[f][:, :, 2] > cut, axis=1) & np.all(np.abs(v[f][:, :, 0]) < 0.26, axis=1)
    F = f[keep]
    used = np.unique(F)
    remap = -np.ones(len(v), np.int64)
    remap[used] = np.arange(len(used))
    V = v[used]
    F = remap[F]
    faces = [tuple(q) if q[2] != q[3] else tuple(q[:3]) for q in F]
    ob = geo.mesh_obj("Head", V, faces, col_skin, skin_mat, smooth=True, parent=parent)
    H.obj = ob
    H.verts = V
    # eyeball caps: fill the MakeHuman eye pockets so the decal eyes sit on a smooth surface
    eyes = []
    for k, c in (("L", eL), ("R", eR)):
        r = canon.get("eyeball_r", 0.0128)
        prof = [(r * math.sin(a), r * math.cos(a)) for a in np.linspace(0, math.pi, 14)]
        vv, ff = geo.lathe(prof, 24)
        # lathe around Z; rotate so the pole points to -Y (front)
        vv = np.stack([vv[:, 0], -vv[:, 2], vv[:, 1]], 1) + c
        eyes.append(geo.mesh_obj("Eyeball" + k, vv, ff, col_hidden, skin_mat, parent=parent))
    H.eyeballs = eyes
    # face marks: eyelids, lips and nostrils never get Freestyle lines
    me = ob.data
    cen = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    H.surf = geo.Surface([ob] + eyes)
    lm = landmarks(H)
    H.lm = lm
    mark = np.zeros(len(cen), bool)
    for c in (eL, eR):
        d = (cen - c) / np.array([0.021, 0.03, 0.0145])
        mark |= (np.einsum("ij,ij->i", d, d) < 1.0) & (cen[:, 1] < c[1] + 0.004)
    mz = lm["mouth"][2]
    d = (cen - np.array([0, lm["mouth"][1], mz])) / np.array([0.032, 0.03, 0.011])
    mark |= np.einsum("ij,ij->i", d, d) < 1.0
    nt = lm["nose_tip"]
    d = (cen - np.array([0, nt[1] + 0.012, nt[2] - 0.009])) / np.array([0.021, 0.022, 0.011])
    mark |= np.einsum("ij,ij->i", d, d) < 1.0
    me.polygons.foreach_set("use_freestyle_mark", mark.tolist())
    me.update()
    return H


def landmarks(H):
    """Midline profile by ray casting (robust to any target mix)."""
    s = H.surf
    ez = H.eye_z
    zs = np.arange(ez - 0.16, ez + 0.14, 0.0005)
    ys = np.array([s.hit(0.0, z)[0][1] for z in zs])
    lm = {}

    def front(z0, z1):
        m = (zs >= z0) & (zs <= z1)
        i = np.argmin(np.where(m, ys, 9))
        return np.array([0.0, ys[i], zs[i]])

    def back(z0, z1):
        m = (zs >= z0) & (zs <= z1)
        i = np.argmax(np.where(m, ys, -9))
        return np.array([0.0, ys[i], zs[i]])

    lm["nose_tip"] = front(ez - 0.06, ez - 0.02)
    nt = lm["nose_tip"]
    lm["nasion"] = back(ez - 0.012, ez + 0.012)
    lm["subnasale"] = back(nt[2] - 0.022, nt[2] - 0.006)
    sn = lm["subnasale"]
    lm["upper_lip"] = front(sn[2] - 0.02, sn[2] - 0.004)
    ul = lm["upper_lip"]
    lm["mouth"] = back(ul[2] - 0.012, ul[2] - 0.002)
    mo = lm["mouth"]
    lm["lower_lip"] = front(mo[2] - 0.016, mo[2] - 0.002)
    ll = lm["lower_lip"]
    lm["chin_dent"] = back(ll[2] - 0.022, ll[2] - 0.006)
    lm["chin"] = front(lm["chin_dent"][2] - 0.03, lm["chin_dent"][2] - 0.004)
    # menton: lowest point of the face on the midline (ray down from in front of the chin)
    from mathutils import Vector
    ch = lm["chin"]
    loc = s.bvh.ray_cast(Vector((0, ch[1] + 0.012, ch[2] - 0.08)), Vector((0, 0, 1)))[0]
    lm["menton"] = np.array(loc) if loc is not None else ch - np.array([0, -0.01, 0.02])
    lm["forehead"] = front(ez + 0.03, ez + 0.06)
    top = s.bvh.ray_cast(Vector((0, -0.03, ez + 0.4)), Vector((0, 0, -1)))[0]
    lm["crown"] = np.array(top)
    lm["eye_l"], lm["eye_r"] = H.eye_l, H.eye_r
    return lm

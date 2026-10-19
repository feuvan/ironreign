"""Build a gongbi_C bust from a character spec (Blender side).

    stage = b_stage.Stage(...)
    build.bust(stage, spec)          # head, ears, neck, torso + collar, costume, hair, headgear
    stage.camera(...); stage.ink(); ps, secs = stage.render(dir); stage.export(dir, ps)

The spec format is documented in :mod:`specs`.
"""

import math

import numpy as np

import b_body as BB
import b_gear as BG
import b_mats as MT
import b_mesh as M
from looks import PAL, SKIN, mix, deepen


def skin_mats(spec):
    light, deep = SKIN[spec.get("skin", "warm")]
    face = MT.wash("PC_SkinFace", light, deep, region="face", face=1, skin=1, blend=0.30,
                   lo=0.22, hi=1.0, power=1.6, form=0.05)
    body = MT.wash("PC_Skin", light, deep, region="skin", skin=1, blend=0.30, lo=0.22, hi=1.0,
                   power=1.6, form=0.05)
    return face, body


def robe_mats(cos):
    """Materials for the torso faces: [skin-in-opening, robe body] + collar bands per layer."""
    robe = cos.get("robe", {})
    c = robe.get("color", "azurite")
    d = robe.get("deep", None) or deepen(c, 0.62)
    pat = None
    if robe.get("roundels"):
        r = robe["roundels"]
        pat = MT.roundels(period=r.get("period", 0.075), color=r.get("color", "gold"),
                          alpha=r.get("alpha", 0.35))
    body = MT.wash("PC_Robe", c, d, region="robe", blend=0.45, lo=0.08, hi=1.0, ao=0.0,
                   pattern=pat, form=0.08)
    return body


def band_mat(i, L):
    c = L.get("color", "white")
    d = L.get("deep", None) or deepen(c, 0.75)
    pat = None
    if L.get("brocade"):
        b = L["brocade"]
        pat = MT.brocade(period=b.get("period", 0.02), width=L.get("band_w", 0.016) + 0.0025,
                         motif=b.get("motif", "gold"), edge=b.get("edge", "gold"),
                         edge_w=b.get("edge_w", 0.0012), size=b.get("size", 0.32),
                         kind=b.get("kind", "lozenge"))
    return MT.wash("PC_Band%d" % i, c, d, region="band" if i == 0 else ("band2" if i == 1 else "band3"),
                   blend=0.5, lo=0.1, hi=1.0, pattern=pat, form=0.05)


def bust(st, spec):
    pose = spec.get("pose", {})
    hs = BB.head_params(spec.get("head", {}))["scale"]
    st.pose_head(yaw=pose.get("head_yaw", 0.0), pitch=pose.get("head_pitch", 0.0),
                 roll=pose.get("head_roll", 0.0), drop=(1.0 - hs) * 0.115)
    face_m, skin_m = skin_mats(spec)
    # ---------------- head, ears, neck ----------------
    head, H = BB.build_head(spec.get("head", {}), st.col("face"), face_m, st.rig)
    st.head, st.H3 = head, H
    ears = {}
    hair_spec = spec.get("hair", {})
    gear = spec.get("headgear", {})
    show_ears = spec.get("ears", True)
    if show_ears:
        for side in (-1, 1):
            obj, curves = BB.build_ear(H, side, st.col("face"), skin_m, st.rig, spec.get("ear"))
            ears[side] = obj
            for nm, pts in curves.items():
                st.add_curve("ear_%s_%+d" % (nm, side), "ear", pts, head_local=True)
    torso = BB.Torso(spec.get("body", {}), H.s)
    BB.build_neck(H, torso, st.col("face"), skin_m, neck_k=spec.get("body", {}).get("neck", 1.0))
    # ---------------- torso + collar ----------------
    cos = spec.get("costume", {})
    build_torso_and_collar(st, torso, cos, skin_m)
    # ---------------- costume extras ----------------
    if cos.get("armour"):
        BG.armour(st, torso, cos["armour"])
    if cos.get("cloak"):
        BG.cloak(st, torso, cos["cloak"])
    if cos.get("shawl"):
        BG.shawl(st, torso, cos["shawl"])
    if cos.get("beads"):
        BG.beads(st, torso, cos["beads"])
    # ---------------- hair and headgear ----------------
    BG.hair(st, H, hair_spec, spec)
    if gear.get("kind"):
        BG.headgear(st, H, gear, spec)
    if spec.get("earrings"):
        BG.earrings(st, H, spec["earrings"])
    return H, torso


def build_torso_and_collar(st, torso, cos, skin_m):
    cp = cos.get("collar")
    robe_m = robe_mats(cos)
    layers = BB.collar_layers(cp) if cp else []
    folds = cos.get("robe", {}).get("folds", [])

    def region(x, z, a):
        front = np.cos(a) > 0
        if not layers:
            return np.ones_like(x, dtype=int)
        inside = BB.inside_v(x, z, layers[0]) & front
        # no torso inside the innermost V and above the collar: the neck object shows there
        inside |= z > cp["neck_z"] + 0.006
        return np.where(inside, -1, 1)

    obj = BB.build_torso(torso, st.col("robe"), [skin_m, robe_m], region, folds=folds)
    st.anchors["torso"] = obj.name
    # fold crest curves for the 2D stage (drawn as tapered 兰叶描 strokes)
    for i, f in enumerate(folds):
        if not f.get("line", True):
            continue
        pts = M.resample(np.array(f["pts"]), 40)
        P = torso.point(pts[:, 0], pts[:, 1], f.get("amp", 0.0) * 0.6 + 0.001)
        st.add_curve("fold%d" % i, f.get("style", "fold"), P, weight=f.get("weight", 1.0),
                     region=f.get("region", "robe"), side=f.get("side", 1))
    # collar bands, innermost first (each a little higher above the body than the last)
    for lay in layers:
        L = lay["L"]
        bm = band_mat(lay["k"], L)
        for nm, fin, fout in BB.band_paths(torso, lay, stand=L.get("stand", 0.024)):
            off = 0.003 + 0.0022 * lay["k"]
            Pin = torso.point(fin[:, 0], fin[:, 1], off + 0.0006)
            Pout = torso.point(fout[:, 0], fout[:, 1], off)
            M.strip("Band%d_%s" % (lay["k"], nm), Pin, Pout, st.col("band"), mat=bm)
    return obj

"""Approach B portrait builder: Spec -> Blender scene -> Cycles passes -> painterly compositor.

    blender -b --factory-startup -noaudio -P portrait.py -- <spec name|json> <out_dir> [--preview]

A *spec* (see :mod:`specs`) is plain data: identity (MakeHuman macro + face sliders + skin),
groom (beard/moustache/brows/scalp/bun parameters), outfit (builder name + palette), light
tweaks and background tint.  Everything visual is produced by the builders here, so 103 portraits
are 103 small specs, not 103 scenes.
"""

import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

from . import costume as C
from . import hair as HR
from . import head, mh, rig, shading, outfits, compositor
from .identity import Identity


def build_identity(d):
    i = Identity()
    for k, v in d.items():
        setattr(i, k, v)
    return i


def groom(spec, b, surf, mats, rng, col, helmet_info=None):
    g = spec.get("groom", {})
    lm = b["lm"]
    objs = []
    hm = mats["hair"]
    if g.get("brows", True):
        objs.append(HR.make("Brows", HR.brows(surf, lm, rng, **g.get("brows_kw", {})), mats["brow"], col))
    objs.append(HR.make("Lashes", HR.lashes(surf, lm, rng, **g.get("lash_kw", {})), mats["lash"], col))
    if g.get("beard"):
        objs.append(HR.make("Beard", HR.beard(surf, lm, rng, **g["beard"]), mats["beard"], col))
    if g.get("moustache"):
        objs.append(HR.make("Moustache", HR.moustache(surf, lm, rng, **g["moustache"]), mats["beard"], col))
    sc = g.get("scalp")
    if sc:
        knot = np.asarray(lm["eye_c"], np.float32) + np.asarray(sc.get("knot", (0, 0.035, 0.125)), np.float32)
        kw = {k: v for k, v in sc.items() if k not in ("knot", "bun", "buns")}
        objs.append(HR.make("Scalp", HR.scalp_to_knot(surf, lm, rng, knot, **kw), hm, col))
        for i, bn in enumerate(sc.get("buns", [sc["bun"]] if sc.get("bun") else [])):
            bk = dict(bn)
            off = np.asarray(bk.pop("offset", (0, 0, 0.012)), np.float32)
            objs.append(HR.make("Bun%d" % i, HR.bun(knot + off, rng, **bk), hm, col))
    if g.get("side_locks"):
        objs.append(HR.make("Locks", HR.side_locks(surf, lm, rng, **g["side_locks"]), hm, col))
    return [o for o in objs if o is not None]


def hair_mats(spec, key_dir):
    i = spec["identity"]
    g = spec.get("groom", {})
    mel = i.get("hair_melanin", 0.95)
    red = i.get("hair_redness", 0.15)
    grey = i.get("grey", 0.0)
    hm = HR.hair_material("Hair", melanin=mel, redness=red, grey=grey, roughness=g.get("rough", 0.36))
    bm = HR.hair_material("BeardHair", melanin=mel, redness=red, grey=min(1.0, grey * g.get("beard_grey", 1.2)),
                          roughness=g.get("rough", 0.36) + 0.04)
    br = HR.hair_material("BrowHair", melanin=min(1.0, mel + 0.03), redness=red,
                          grey=grey * g.get("brow_grey", 0.8), roughness=0.45)
    la = HR.hair_material("LashHair", melanin=1.0, redness=0.1, roughness=0.5)
    return dict(hair=hm, beard=bm, brow=br, lash=la)


def build(spec, preview=False, out=None):
    t0 = time.time()
    times = {}
    rig.reset()
    W, H = 384, 480
    ss = spec.get("ss", 2)
    spp = spec.get("spp", 64)
    if preview:
        ss, spp = 1, max(16, spp // 3)
    sc = rig.cycles(samples=spp, w=W, h=H, ss=ss, transparent=True,
                    look=spec.get("look", "Medium Contrast"), exposure=spec.get("exposure", 0.0))
    ident = build_identity(spec["identity"])
    rng = np.random.default_rng(spec.get("seed", 1))
    col = bpy.context.scene.collection
    b = head.build(ident, subdiv=2)
    lm = b["lm"]
    cam_kw = dict(yaw_deg=22.0, pitch_deg=-3.0, head_frac=0.48, eye_line=0.38)
    cam_kw.update(spec.get("camera", {}))
    cam = rig.portrait_camera(lm["eye_c"], **cam_kw)
    head.aim_eyes(b["eyes"], cam.location, spec.get("gaze", 0.85), spec.get("gaze_up", 0.0))
    lk = dict(spec.get("light", {}))
    r = rig.light_rig(cam, lm["eye_c"], **lk)
    kd = tuple(r["key_dir"])
    # materials for the head
    b["body"].data.materials.append(shading.skin(ident, kd))
    em = shading.eyes(ident, tex_path=os.path.join(mh.MH_DATA, "eyes/materials/brown_eye.png"))
    cm = shading.cornea()
    for e in b["eyes"]:
        e.data.materials.append(em)
        e.data.materials.append(cm)
        e.pass_index = 2
    b["body"].pass_index = 1
    times["head"] = time.time() - t0
    # body surface for fitting + collisions
    t1 = time.time()
    surf = HR.Surface([b["body"]], attrs=["z_beard", "z_moustache", "z_brow", "z_lash", "z_scalp", "z_goatee"])
    outfit = getattr(outfits, spec["outfit"]["builder"])
    cost = outfit(spec, b, surf, kd, rng, col)
    times["costume"] = time.time() - t1
    t2 = time.time()
    # hair collides with skin + costume
    csurf = HR.Surface([b["body"]] + cost.get("collide", []),
                       attrs=["z_beard", "z_moustache", "z_brow", "z_lash", "z_scalp", "z_goatee"])
    hm = hair_mats(spec, kd)
    hobjs = groom(spec, b, csurf, hm, rng, col, cost.get("helmet"))
    for o in hobjs:
        o.pass_index = 3
    times["hair"] = time.time() - t2
    # helmet / headwear decorations that need hair-like strands (tassels, fur)
    for f in cost.get("post", []):
        f(csurf, rng, col)
    # centre the bust horizontally on head + shoulders
    _center(cam, [b["body"]] + cost.get("frame", []), lm)
    comp = compositor.setup(spec, sc, out or "/tmp", ss)
    return dict(scene=sc, cam=cam, lm=lm, b=b, rig=r, times=times, comp=comp, ss=ss)


def _center(cam, objs, lm):
    # keep the face at a fixed horizontal position: eye centre slightly left of centre so the
    # turned face has room in front of it (the face looks screen-left into the key)
    sc = bpy.context.scene
    x, y, _ = rig.world_to_px(cam, lm["eye_c"])
    W = sc.render.resolution_x
    target = 0.53 * W
    cam.data.shift_x += (x - target) / max(W, sc.render.resolution_y)
    bpy.context.view_layer.update()


def render(spec, out, preview=False):
    os.makedirs(out, exist_ok=True)
    st = build(spec, preview, out)
    sc = st["scene"]
    name = spec["name"]
    raw = os.path.join(out, "%s_raw.png" % name)
    sc.render.filepath = raw
    t = time.time()
    bpy.ops.render.render(write_still=True)
    st["times"]["render"] = time.time() - t
    print("[B] %s times %s" % (name, {k: round(v, 1) for k, v in st["times"].items()}))
    return st


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    from . import specs
    name = argv[0]
    out = argv[1]
    spec = specs.get(name)
    render(spec, out, preview="--preview" in argv)

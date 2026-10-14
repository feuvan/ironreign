"""Outfit builders (one per costume family).  Each returns a dict:

    collide  objects the hair must stay outside of (armour, collars, robes)
    frame    objects that define the bust silhouette (for framing)
    helmet   helmet info (finial etc.) or None
    post     callables(surf, rng, col) run after the groom (tassels, fur trims, hair ornaments)
"""

import math

import bpy
import numpy as np

from . import costume as C
from . import hair as HR
from . import meshutil as MU
from . import shading


def _norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def _robe_collar(shell, lm, mats, col, axis, z_top, depth=0.11, width=0.034, out=0.004, name="Collar",
                 left_over=True, rows=3):
    """Crossed (jiaoling) collar band: from behind the neck, over each shoulder, down to the chest
    where the left panel crosses over the right (youren).  Returns band objects."""
    objs = []
    cx, cy = axis
    zt = z_top
    for side in (1, -1):
        # parameter path: back of neck (theta 180) -> side (90) -> front crossing point
        pts, nrs = [], []
        cross_z = zt - depth
        for t in np.linspace(0.0, 1.0, 40):
            if t < 0.45:
                # around the neck from the back to the front-side
                th = math.radians(178 - (178 - 40) * (t / 0.45))
                z = zt - 0.004 * (t / 0.45)
            else:
                f = (t - 0.45) / 0.55
                # descend diagonally across the chest to the far side
                th = math.radians(40 - (40 + 22) * f)
                z = zt - 0.004 - (depth) * f
            th *= side
            p, n = shell.hit((cx, cy, z), (math.sin(th), -math.cos(th), 0))
            if p is None:
                continue
            pts.append(p)
            nrs.append(n)
        pts = np.array(pts)
        nrs = _norm(np.array(nrs))
        o = out + (0.004 if (side > 0) == left_over else 0.0)
        ob = C.ribbon(pts + nrs * o, nrs, width, name="%s_%s" % (name, "l" if side > 0 else "r"),
                      mats=mats, col=col, thickness=0.004, rows=rows)
        objs.append(ob)
    return objs


def warlord_armour(spec, b, surf, kd, rng, col):
    o = spec["outfit"]
    lm = b["lm"]
    bust = b["body"]
    pal = o.get("palette", {})
    M = shading.costume_materials(kd, pal)
    robe = shading.cloth("Robe", o.get("robe", "#5A1712"), sheen=0.5, rough=0.6, key_dir=kd,
                         pattern="cloud", pattern_color=o.get("robe_pattern", "#8A3A22"),
                         pattern_scale=14.0)
    collar_m = shading.cloth("CollarSilk", o.get("collar", "#7A1A12"), sheen=0.6, rough=0.55, key_dir=kd,
                             border="v", border_color=o.get("trim", "#B08A3A"), border_width=0.3,
                             pattern_scale=10.0)
    axis = (0.0, float(lm["j_neck"][1]) + 0.005)
    nz = float(lm["j_neck"][2])
    objs = []
    # 1. padded under-robe shell (shows at the neck)
    under = C.body_shell(bust, surf, lm, thickness=0.012, neck_z=nz + 0.006, front_dip=0.05,
                         name="UnderRobe")
    uo = under.obj([robe], col, solidify=0.003, subdiv=1)
    objs.append(uo)
    # 2. armour shell
    arm = C.body_shell(bust, surf, lm, thickness=0.032, neck_z=nz - 0.022, front_dip=0.035,
                       name="ArmourShell", widen=0.04)
    ao = arm.obj([M["leather"]], col, solidify=0.004, subdiv=1)
    objs.append(ao)
    # lamellar rows on the chest / back
    z_top = nz - 0.035
    rows = [z_top - k * 0.031 for k in range(9)]
    pl = C.lamellar(arm, axis, rows, (-150, 150), plate_w=0.022, plate_h=0.05, overlap_u=0.4,
                    name="Lamellar", mats=[M["iron"]], col=col, rng=rng, extra_out=0.002)
    objs.append(pl)
    lac = C.lacing_rows(arm, axis, [z + 0.018 for z in rows], (-150, 150), out=0.0075,
                        width=0.0032, mats=[M["lacing"]], col=col, rng=rng)
    if lac:
        objs.append(lac)
    # bronze-edged collar ring of the cuirass
    ring_p, ring_n = C.shell_curve(arm, axis, lambda t: nz - 0.024 - 0.03 * max(0, math.cos(math.radians(t))) ** 2,
                                   np.arange(-180, 181, 4), out=0.006)
    if len(ring_p) > 4:
        objs.append(C.ribbon(ring_p, ring_n, 0.022, up=np.tile([0, 0, 1.0], (len(ring_p), 1)),
                             name="CuirassRim", mats=[M["bronze"]], col=col, thickness=0.003, rows=3))
    # 3. standing silk collar + crossed robe collar
    objs += _robe_collar(under, lm, [collar_m], col, axis, nz + 0.004, depth=0.07, width=0.03,
                         out=0.006)
    # 4. chest mirror
    cm_z = nz - 0.13
    p, n = arm.hit((axis[0], axis[1], cm_z), (0, -1, 0))
    if p is not None and o.get("mirror", True):
        objs.append(C.disc(p + n * 0.012, n, 0.05, "ChestMirror", [M["gold"]], col, dome=0.008))
        objs.append(C.disc(p + n * 0.016, n, 0.034, "ChestMirrorIn", [M["iron_plain"]], col, dome=0.006))
    # 5. pauldrons
    pd = C.pauldrons(arm, lm, [M["iron_plain"]], col, lames=o.get("lames", 4), lame_h=0.034,
                     span=(15, 165), out0=0.012)
    objs += pd
    # 6. helmet
    hinfo = None
    if o.get("helmet", True):
        hobjs, hinfo = C.helmet(bust, lm, dict(iron=M["iron_plain"], bronze=M["bronze"], gold=M["gold"],
                                               leather=M["leather"], lacing=M["lacing"]), col,
                                clearance=0.014, rng=rng, guard_rows=3)
        objs += hobjs
    post = []
    if hinfo is not None and o.get("tassel", True):
        def tassel(surf2, rng2, col2, hinfo=hinfo):
            root = hinfo["finial"] - np.array([0, 0, 0.012], np.float32)
            S = 1600
            roots = root + rng2.normal(size=(S, 3)).astype(np.float32) * np.array([0.004, 0.004, 0.002], np.float32)
            ang = rng2.random(S) * 6.283
            d = np.stack([np.cos(ang), np.sin(ang), np.full(S, 0.35)], 1).astype(np.float32)
            L = 0.09 * (0.7 + 0.5 * rng2.random(S))
            pts = HR.grow(roots, d, L, 12, gravity=0.85, stiff=0.7, rng=rng2, noise=0.05)
            pts = HR.clump(pts, 40, 0.5, rng2)
            pts = HR.collide(surf2, pts, 0.003)
            tm = HR.hair_material("Tassel", melanin=0.25, redness=1.0, roughness=0.32,
                                  tint=(1.0, 0.15, 0.1), random_color=0.15)
            ob = HR.curves_object("Tassel", pts, 0.00028, 0.0001, tm, col2)
            ob.pass_index = 3
        post.append(tassel)
    if o.get("fur", True):
        def fur(surf2, rng2, col2):
            # fur mantle on the shoulders behind the neck
            S = 9000
            th = np.radians(rng2.uniform(-150, 150, S))
            th = np.where(np.abs(th) < np.radians(55), np.sign(th) * np.radians(55) + th * 0.0, th)
            zz = nz - 0.035 + rng2.normal(size=S) * 0.012
            roots = []
            nrs = []
            for t, z in zip(th, zz):
                p, n = arm.hit((axis[0], axis[1], z), (math.sin(t), -math.cos(t), 0.25))
                if p is None:
                    p, n = np.array([0, axis[1], z], np.float32), np.array([0, 0, 1], np.float32)
                roots.append(p + _norm(n) * 0.012)
                nrs.append(_norm(n))
            roots = np.array(roots, np.float32)
            nrs = np.array(nrs, np.float32)
            d = nrs * 0.7 + np.array([0, 0, 0.5], np.float32)
            L = 0.035 * (0.6 + 0.6 * rng2.random(S))
            pts = HR.grow(roots, d, L, 7, gravity=0.6, stiff=0.6, rng=rng2, noise=0.15, curl=0.1)
            pts = HR.clump(pts, 300, 0.45, rng2)
            fm = HR.hair_material("Fur", melanin=0.55, redness=0.55, roughness=0.5, grey=0.25,
                                  grey_melanin=0.15, random_color=0.25)
            ob = HR.curves_object("Fur", pts, 0.00035, 0.00012, fm, col2)
            ob.pass_index = 4
        post.append(fur)
    collide = [o2 for o2 in objs if o2 is not None and o2.type == "MESH"]
    return dict(collide=collide, frame=[ao], helmet=hinfo, post=post)

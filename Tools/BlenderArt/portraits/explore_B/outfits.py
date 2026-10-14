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
    zfn0 = neckline(nz + 0.004, 0.07)

    def keep0(V):
        th = np.degrees(np.arctan2(np.abs(V[:, 0]), -(V[:, 1] - axis[1])))
        return V[:, 2] < np.array([zfn0(t) for t in th]) + 0.012
    under = C.body_shell(bust, surf, lm, thickness=0.012, neck_z=nz + 0.2, front_dip=0.0, keep_fn=keep0,
                         name="UnderRobe")
    uo = under.obj([robe], col, solidify=0.0, subdiv=1)
    objs.append(uo)
    # 2. armour shell
    arm = C.body_shell(bust, surf, lm, thickness=0.032, neck_z=nz - 0.022, front_dip=0.035,
                       name="ArmourShell", widen=0.04)
    ao = arm.obj([M["leather"]], col, solidify=0.0, subdiv=1)
    objs.append(ao)
    # lamellar rows on the chest / back
    z_top = nz - 0.035
    rows = [z_top - k * 0.033 for k in range(9)]
    pl = C.lamellar(arm, axis, rows, (-150, 150), plate_w=0.017, plate_h=0.056, overlap_u=0.42,
                    name="Lamellar", mats=[M["iron"]], col=col, rng=rng, extra_out=0.002)
    objs.append(pl)
    lac = C.lacing_rows(arm, axis, [z + 0.02 for z in rows], (-150, 150), out=0.0072,
                        width=0.0024, mats=[M["lacing"]], col=col, rng=rng)
    if lac:
        objs.append(lac)
    # bronze-edged collar ring of the cuirass
    ring_p, ring_n = C.shell_curve(arm, axis, lambda t: nz - 0.024 - 0.03 * max(0, math.cos(math.radians(t))) ** 2,
                                   np.arange(-180, 181, 4), out=0.006)
    if len(ring_p) > 4:
        objs.append(C.ribbon(ring_p, ring_n, 0.022, up=np.tile([0, 0, 1.0], (len(ring_p), 1)),
                             name="CuirassRim", mats=[M["bronze"]], col=col, thickness=0.003, rows=3))
    # 3. standing silk collar + crossed robe collar
    zfn = neckline(nz + 0.004, 0.07)
    for side in (1, -1):
        p, n = _collar_path(under, axis, lambda t: zfn(t) - 0.003, side)
        if len(p) > 3:
            objs.append(C.ribbon(p + n * (0.006 + 0.003 * (side > 0)), n, 0.03, name="Collar_%d" % side,
                                 mats=[collar_m], col=col, thickness=0.004, rows=3))
    # 4. chest mirror
    cm_z = nz - 0.13
    p, n = arm.hit((axis[0], axis[1], cm_z), (0, -1, 0))
    if p is not None and o.get("mirror", True):
        objs.append(C.disc(p + n * 0.012, n, 0.036, "ChestMirror", [M["bronze"]], col, dome=0.006))
        objs.append(C.disc(p + n * 0.015, n, 0.028, "ChestMirrorIn", [M["gold"]], col, dome=0.006))
    # 5. pauldrons
    pd = C.pauldrons(arm, lm, [M["iron_plain"]], col, lames=o.get("lames", 4), lame_h=0.034,
                     span=(15, 165), out0=0.012)
    objs += pd
    # 6. helmet
    hinfo = None
    if o.get("helmet", True):
        hobjs, hinfo = C.helmet(bust, lm, dict(iron=M["iron_inlay"], guard=M["iron"], bronze=M["bronze"], gold=M["gold"],
                                               leather=M["leather"], lacing=M["lacing"]), col,
                                clearance=0.014, rng=rng, guard_rows=3)
        objs += hobjs
    post = []
    if hinfo is not None and o.get("tassel", True):
        def tassel(surf2, rng2, col2, hinfo=hinfo):
            root = hinfo["top"] + np.array([0, 0, 0.03], np.float32)
            S = 2200
            ang = rng2.random(S) * 6.283
            rr = 0.010 * np.sqrt(rng2.random(S))
            roots = root + np.stack([np.cos(ang) * rr, np.sin(ang) * rr, np.zeros(S)], 1).astype(np.float32)
            d = np.stack([np.cos(ang), np.sin(ang), np.full(S, 1.1)], 1).astype(np.float32)
            L = 0.10 * (0.75 + 0.4 * rng2.random(S))
            pts = HR.grow(roots, d, L, 16, gravity=1.0, stiff=0.45, rng=rng2, noise=0.015)
            pts = HR.clump(pts, 60, 0.55, rng2)
            pts = HR.collide(surf2, pts, 0.004)
            tm = HR.hair_material("Tassel", melanin=0.05, redness=1.0, roughness=0.3,
                                  tint=(0.85, 0.05, 0.03), random_color=0.1)
            ob = HR.curves_object("Tassel", pts, 0.0003, 0.00015, tm, col2)
            ob.pass_index = 3
        post.append(tassel)
    if o.get("fur", True):
        def fur(surf2, rng2, col2):
            # fur mantle on the shoulders behind the neck
            S = 6000
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


def neckline(zb, depth, cross=0.35):
    """Crossed-collar edge height as a function of theta (deg, 0 front, +-180 back) for the
    band coming from the ``theta > 0`` side; it continues past the front (theta < 0) while
    descending (the crossing)."""
    def f(th):
        t = math.radians(abs(th)) if th >= 0 else 0.0
        g = ((1 + math.cos(t)) / 2) ** 3
        z = zb - depth * 0.8 * g
        if th < 0:
            z -= depth * (0.2 + cross * (-th / 30.0))
        else:
            z -= depth * 0.2 * g ** 4
        return z
    return f


def _collar_path(shell, axis, z_fn, side, cross_to=-24.0, steps=56):
    cx, cy = axis
    pts, nrs = [], []
    for th_d in np.linspace(178, cross_to, steps):
        z = z_fn(th_d)
        th = math.radians(th_d) * side
        p, n = shell.hit((cx, cy, z), (math.sin(th), -math.cos(th), 0))
        if p is None:
            continue
        if pts and np.linalg.norm(p - pts[-1]) > 0.03:
            continue          # a ray that slipped past the surface: skip, keep the band continuous
        pts.append(p)
        nrs.append(n)
    return np.array(pts, np.float32), _norm(np.array(nrs, np.float32))


def robe(spec, b, surf, kd, rng, col):
    """Layered silk robe with crossed (jiaoling, left-over-right) collars; options: shawl, beads,
    fur, headwear ('crown' for scholars/sages, 'pins' for court ladies)."""
    o = spec["outfit"]
    lm = b["lm"]
    bust = b["body"]
    axis = (0.0, float(lm["j_neck"][1]) + 0.004)
    nz = float(lm["j_neck"][2])
    objs = []
    layers = o["layers"]
    shells = []
    M = shading.costume_materials(kd, o.get("palette", {}))
    for i, L in enumerate(layers):
        mat = shading.cloth("Robe%d" % i, L["color"], sheen=L.get("sheen", 0.5), rough=L.get("rough", 0.6),
                            key_dir=kd, pattern=L.get("pattern"), pattern_color=L.get("pattern_color"),
                            pattern_scale=L.get("pattern_scale", 14.0))
        bw = L.get("band_w", 0.02 + 0.007 * i)
        zfn = neckline(nz + L.get("collar_z", 0.012 - 0.006 * i), L.get("depth", 0.06 + 0.035 * i))
        cyx = axis[1]

        def keep(V, zfn=zfn, bw=bw):
            th = np.degrees(np.arctan2(np.abs(V[:, 0]), -(V[:, 1] - cyx)))
            zc = np.array([zfn(t) for t in th]) + bw * 0.45
            return V[:, 2] < zc
        sh = C.body_shell(bust, surf, lm, thickness=L.get("thickness", 0.006 + 0.006 * i),
                          neck_z=nz + 0.2, front_dip=0.0, keep_fn=keep,
                          name="RobeShell%d" % i, widen=L.get("widen", 0.03 * i))
        if L.get("folds", 0) > 0:
            C.robe_folds(sh, lm, amount=L["folds"], count=L.get("fold_count", 9), seed=i + 3)
        if shells:
            C.push_outside(sh, shells[-1], L.get("gap", 0.004))
        shells.append(sh)
        objs.append(sh.obj([mat], col, solidify=0.0, subdiv=1, name="Robe%d" % i))
        # collar band of this layer
        band = shading.cloth("Band%d" % i, L.get("band", L["color"]), sheen=0.5, rough=0.55, key_dir=kd,
                             border="v", border_color=L.get("border", "#C9A24A"),
                             border_width=L.get("border_width", 0.28), pattern_scale=L.get("band_scale", 9.0))
        for side in (1, -1):
            over = (side > 0)
            p, n = _collar_path(sh, axis, lambda t, zfn=zfn, bw=bw: zfn(t) - bw * 0.1, side,
                                cross_to=L.get("cross_to", -22.0 - 3 * i))
            if len(p) < 4:
                continue
            outo = 0.004 + (0.003 if over else 0.0)
            objs.append(C.ribbon(p + n * outo, n, bw,
                                 name="Band%d_%s" % (i, "l" if over else "r"), mats=[band], col=col,
                                 thickness=0.004, rows=3))
    outer = shells[-1]
    post = []
    if o.get("beads"):
        bk = o["beads"]
        drop = bk.get("drop", 0.16)
        th = np.radians(np.linspace(-175, 175, 90))
        P, N = [], []
        for t in th:
            z = nz - 0.012 - drop * (math.cos(t / 2) ** 2.2)
            p, n = outer.hit((axis[0], axis[1], z), (math.sin(t), -math.cos(t), 0))
            if p is not None:
                P.append(p + _norm(n) * 0.010)
                N.append(_norm(n))
        if len(P) > 3:
            bm = shading.metal("Bead", bk.get("color", (0.12, 0.045, 0.02)), rough=0.35) if bk.get("metal") else \
                shading.cloth("BeadWood", bk.get("hex", "#4A2416"), sheen=0.0, rough=0.3, painter=False)
            objs.append(C.beads(np.array(P), np.array(N), bk.get("r", 0.0055), "Beads", [bm], col,
                                big_every=bk.get("big_every", 0)))
    hw = o.get("headwear")
    hinfo = None
    if hw == "crown":
        from .portrait import knot_point
        top = knot_point(lm, o.get("crown_at", (0, 0.02, 0.012)))
        cm = shading.cloth("CrownWood", o.get("crown_color", "#1E1612"), sheen=0.1, rough=0.35, painter=False)
        objs += C.crown(top, "Crown", [cm], col, scale=o.get("crown_scale", 1.0), pin_mat=M["gold"],
                        tilt=0.1)
        hinfo = {"top": top}
    if hw == "pins":
        from .portrait import knot_point
        knot = knot_point(lm, spec["groom"]["scalp"].get("knot"))

        def pins(surf2, rng2, col2, knot=knot):
            gold = M["gold"]
            jade = shading.cloth("Jade", "#5F9E86", sheen=0.0, rough=0.15, painter=False)
            pearl = shading.cloth("Pearl", "#E8E0D0", sheen=0.3, rough=0.2, painter=False)
            petal = shading.cloth("Petal", o.get("flower", "#E7A3B0"), sheen=0.6, rough=0.5, painter=False)
            bun_c = knot + np.array([0, 0, 0.02], np.float32)
            out = []
            for k, (ang, el, L, side) in enumerate([(200, 25, 0.12, 1), (-20, 20, 0.11, -1), (160, 40, 0.09, 1),
                                                    (30, 35, 0.08, -1)]):
                a = math.radians(ang)
                d = np.array([math.cos(a), math.sin(a) * 0.4, math.sin(math.radians(el))], np.float32)
                d /= np.linalg.norm(d)
                p0 = bun_c + d * 0.065
                p1 = bun_c - d * (L - 0.065)
                out += C.rod(p0, p1, 0.0016, "Pin%d" % k, [gold if k % 2 == 0 else jade], col2, head=0.0)
                # ornament head: flower or jade bead
                if k % 2 == 0:
                    out += C.flower(p0, d, 0.010, "PinFl%d" % k, [gold], col2, petals=6, center_mat=pearl)
                    if k == 0:
                        out += C.dangle(p0 + d * 0.004, 0.06, "Buyao", [gold], col2, n_beads=7, r=0.0019,
                                        sway=(0.004, -0.006))
                        out += C.dangle(p0 + d * 0.004 + np.array([0.006, 0, 0]), 0.05, "Buyao2", [pearl], col2,
                                        n_beads=6, r=0.0021, sway=(0.008, -0.004))
                else:
                    out.append(C.sphere(p0, 0.0045, "PinB%d" % k, [jade], col2))
            # silk flowers tucked at the side of the bun
            for k, off in enumerate([(-0.045, -0.012, 0.0), (-0.038, 0.005, 0.018), (0.042, 0.0, 0.005)]):
                c = bun_c + np.array(off, np.float32)
                n = _norm(c - bun_c + np.array([0, -0.03, 0.01], np.float32))
                out += C.flower(c, n, 0.013 - 0.002 * k, "Flower%d" % k, [petal], col2, center_mat=gold)
            for ob in out:
                if ob is not None:
                    ob.pass_index = 5
        post.append(pins)
    collide = [x for x in objs if x is not None and x.type == "MESH"]
    return dict(collide=collide, frame=[outer.obj] if False else [], helmet=hinfo, post=post)

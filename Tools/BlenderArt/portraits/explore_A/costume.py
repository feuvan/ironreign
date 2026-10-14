"""Period costume builders on top of :mod:`shell`: layered cross-collar robes (jiaoling), round
collars, lamellar armour with real plates + lacing, shoulder guards, chest mirror, neck scarf,
helmets, scholar crowns, hairpins and jewellery (bpy + numpy)."""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import hair as HR
import shell as SH


def torso_origin(lm):
    nc = np.array(lm["neck_c"])
    return nc + np.array([0.0, 0.025, -0.16])


class Frame:
    """Reference heights for necklines, from the landmarks."""

    def __init__(self, lm):
        self.chin = float(lm["chin"][2])
        self.neck = float(lm["neck_c"][2])
        self.ipd = float(lm["ipd"])
        # neck base (jugular notch) ~ 1.45 IPD below the chin; shoulders slightly lower
        self.notch = self.chin - 0.078
        self.side = self.chin - 0.050
        self.back = self.chin - 0.022


def cross_cut(fr, depth=0.16, w=52.0, apex_az=-14.0, top_drop=0.0, back_up=0.0):
    """Asymmetric cross-collar neckline (right-over-left, youren): the top panel's edge runs from
    the character's left neck side down past the centre to an apex on the right chest."""
    z_side = fr.side - top_drop
    z_back = fr.back - top_drop + back_up
    z_apex = z_side - depth

    def L1(az):
        return z_side + (z_apex - z_side) * (w - np.asarray(az, float)) / (w - apex_az)

    def L2(az):
        return z_side + (z_apex - z_side) * np.clip((np.asarray(az, float) + w) / (apex_az + w), 0, 1)

    def cut(az):
        a = ((np.asarray(az, float) + 180) % 360) - 180
        aa = np.abs(a)
        zt = np.interp(aa, [0, w, 110, 180], [z_side, z_side, z_back, z_back])
        v = np.where(a >= apex_az, L1(np.clip(a, apex_az, w)), L2(np.clip(a, -w, apex_az)))
        return np.where(aa < w, np.minimum(zt, v), zt)
    return cut, L1, L2, z_side, z_back


def round_cut(fr, drop=0.0, back_up=0.01):
    def cut(az):
        a = np.abs(((np.asarray(az) + 180) % 360) - 180)
        return np.interp(a, [0, 60, 120, 180], [fr.notch - drop, fr.side - drop * 0.5, fr.back + back_up, fr.back + back_up])
    return cut


def _folds(seed, amp=0.0025, freq=0.3):
    rng = np.random.default_rng(seed)
    ph = rng.random(4) * 6.28

    def f(az, t):
        a = np.radians(az)
        w = (np.sin(az * freq * 0.0174533 * 9 + ph[0] + 0.8 * np.sin(a * 3 + ph[1]))
             + 0.5 * np.sin(az * freq * 0.0174533 * 23 + ph[2]))
        return amp * (0.6 + 0.6 * w) * (1 - t) ** 1.5  # outward only: never sinks into inner layers
    return f


def cross_robe(shell, fr, layers, coll=None, seed=0):
    """Stacked cross-collar layers (innermost first), each a full hull layer with an integral
    raised collar band along its neckline; the outer layers also get the top panel's band
    continuing past the crossing (the 'y' overlap).  layer dict keys:
        mat, band_mat, offset, depth, band (width m), w, apex, folds, run (deg), top_drop"""
    objs = []
    for k, L in enumerate(layers):
        depth = L.get("depth", 0.16)
        w = L.get("w", 52.0)
        apex = L.get("apex", -14.0)
        cut, L1, L2, z_side, z_back = cross_cut(fr, depth, w, apex, L.get("top_drop", 0.0), L.get("back_up", 0.0))
        off = L.get("offset", 0.006)
        fa = L.get("folds", 0.002)
        folds = _folds(seed + k, fa) if fa else None
        bw = L.get("band", 0.03)
        mats = [L["mat"], L.get("band_mat") or L["mat"]]
        fl = L.get("flare", 0.02)

        def flare(az, t, fl=fl):
            # garments hang wider toward the bottom and over the arms (sleeves)
            return fl * (1 - t) ** 2 * (0.4 + 0.6 * np.abs(np.sin(np.radians(az))))
        ob = shell.layer("Robe%d" % k, cut, off, rows=L.get("rows", 90), el_bottom=L.get("el_bottom"),
                         folds=folds, mats=mats, band=(bw, L.get("band_lift", 0.003), True), coll=coll,
                         seed=seed + k, flare=flare)
        ob.pass_index = 5
        objs.append(ob)
        run = L.get("run", 0.0)
        if run > 0 and L.get("band_mat") is not None:
            # the top panel's collar keeps going past the crossing, lying over the under panel
            a1 = np.linspace(apex + 6.0, apex - run, 24)
            z_apex = z_side - depth
            slope = (z_apex - z_side) / (apex - w)
            z1 = z_apex + (a1 - apex) * slope - bw * 0.45
            sa, *_ = shell.strip("CollarRun%d" % k, a1, z1, bw, off + L.get("band_lift", 0.003) + 0.0015,
                                 L["band_mat"], coll, n=60, thick=0.003)
            sa.pass_index = 5
            objs.append(sa)
    return objs


def round_robe(shell, fr, mat, band_mat, offset=0.008, coll=None, seed=0, drop=0.0):
    cut = round_cut(fr, drop)
    ob = shell.layer("RoundRobe", cut, offset, rows=70, folds=_folds(seed, 0.002), mats=[mat, band_mat],
                     band=(0.022, 0.004, True), coll=coll)
    ob.pass_index = 5
    return [ob]


# ----------------------------------------------------------------------------------- armour
class ArcGrid:
    """Shell points indexed by (arc length below a cut line, azimuth): rows of armour plates
    wrap smoothly over the shoulders."""

    def __init__(self, shell, cut, offset, az_range=(-180, 180), az_step=0.5, s_max=0.45,
                 s_step=0.002, el_bottom=None):
        self.az = np.arange(az_range[0], az_range[1] + 1e-6, az_step)
        el_top = shell.el_at(self.az, cut(self.az))
        e0 = shell.el[0] if el_bottom is None else el_bottom
        n = 220
        t = np.linspace(1, 0, n)  # from the top edge downward
        EL = e0 + (el_top - e0)[None, :] * t[:, None]
        AZ = np.broadcast_to(self.az[None, :], EL.shape)
        off = offset(AZ, EL) if callable(offset) else offset
        P = shell.point(AZ, EL, off)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=-1)
        S = np.vstack([np.zeros((1, P.shape[1])), np.cumsum(seg, axis=0)])
        self.s = np.arange(0, s_max, s_step)
        G = np.zeros((len(self.s), len(self.az), 3))
        Nn = np.zeros_like(G)
        Nf = shell.normal(AZ, EL)
        for j in range(len(self.az)):
            for k in range(3):
                G[:, j, k] = np.interp(self.s, S[:, j], P[:, j, k])
                Nn[:, j, k] = np.interp(self.s, S[:, j], Nf[:, j, k])
        self.G = G
        self.N = Nn / (np.linalg.norm(Nn, axis=-1, keepdims=True) + 1e-12)
        self.smax_col = S[-1]

    def at(self, s, az):
        s = np.asarray(s, float)
        az = np.asarray(az, float)
        fi = np.clip(s / (self.s[1] - self.s[0]), 0, len(self.s) - 1.001)
        fj = np.clip((az - self.az[0]) / (self.az[1] - self.az[0]), 0, len(self.az) - 1.001)
        i0, j0 = np.floor(fi).astype(int), np.floor(fj).astype(int)
        ti, tj = (fi - i0)[..., None], (fj - j0)[..., None]

        def bl(A):
            return ((A[i0, j0] * (1 - tj) + A[i0, j0 + 1] * tj) * (1 - ti)
                    + (A[i0 + 1, j0] * (1 - tj) + A[i0 + 1, j0 + 1] * tj) * ti)
        n = bl(self.N)
        return bl(self.G), n / (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-12)

    def row_azimuths(self, s, width, overlap=0.15):
        """Azimuth starts of plates along a row at arc depth s (spacing by real distance)."""
        P, _ = self.at(np.full(self.az.shape, s), self.az)
        d = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        step = width * (1 - overlap)
        starts = np.arange(0, d[-1] - width, step)
        a0 = np.interp(starts, d, self.az)
        a1 = np.interp(starts + width, d, self.az)
        return a0, a1


def lamellar(shell, plate_mat, lace_mat, cut, offset=0.016, row_h=0.03, plate_w=0.016,
             overlap=0.4, s_max=0.3, coll=None, seed=0, az_range=(-180, 180), name="Lamellar",
             tilt=1.0, flare=0.0, edge_mat=None, lace=True):
    """Real lamellar: rows of small curved plates (3x4 vertex patches with thickness) placed by
    arc length below ``cut`` (so rows wrap over the shoulders), each lower row lying over the
    one above, laced with cords along each row (hair curves); optional trim along the top."""
    rng = np.random.default_rng(seed)
    AG = ArcGrid(shell, cut, offset, az_range, s_max=s_max + row_h)
    verts, faces = [], []
    cords = []
    nrows = int(s_max / (row_h * (1 - overlap)))
    for r in range(nrows):
        s0 = r * row_h * (1 - overlap)
        a0s, a1s = AG.row_azimuths(s0 + row_h * 0.5, plate_w, 0.12)
        if r % 2:
            sh_ = (a1s[0] - a0s[0]) * 0.5 if len(a0s) else 0
            a0s, a1s = a0s + sh_, a1s + sh_
        lift = 0.0011 * r + flare * (s0 / max(s_max, 1e-3)) ** 2
        for a0, a1 in zip(a0s, a1s):
            if a1 > AG.az[-1]:
                continue
            ss = np.linspace(s0, s0 + row_h, 4)
            aa = np.linspace(a0, a1, 3)
            SS, AA = np.meshgrid(ss, aa, indexing="ij")
            P, N = AG.at(SS, AA)
            across = np.cos(np.linspace(-1.1, 1.1, 3))[None, :] * 0.0005
            down = np.linspace(0.0, 0.0016, 4)[:, None]  # bottom edge stands off (tile overlap)
            tw = rng.standard_normal(2) * 0.0009 * tilt
            twist = np.linspace(-1, 1, 3)[None, :] * tw[0] + np.linspace(-1, 1, 4)[:, None] * tw[1]
            P = P + N * (lift + across + down + twist)[..., None]
            base = len(verts)
            verts.extend(P.reshape(-1, 3).tolist())
            for i in range(3):
                for j in range(2):
                    v0 = base + i * 3 + j
                    faces.append((v0, v0 + 1, v0 + 4, v0 + 3))
        if lace and len(a0s) > 1:
            for fy in (0.22, 0.7):
                sl = s0 + row_h * fy
                aa = np.linspace(a0s[0] + 0.3, min(a1s[-1], AG.az[-1]) - 0.3, max(12, len(a0s) * 4))
                cp, cn = AG.at(np.full(aa.shape, sl), aa)
                cp = cp + cn * (lift + 0.0026 + 0.0016 * fy)
                # small zig-zag stitches through the plate holes
                cp = cp + cn * (0.0006 * np.sin(np.arange(len(aa)) * 2.1))[:, None]
                cords.append(cp)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(plate_mat)
    ob = bpy.data.objects.new(name, me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    sol = ob.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.0013
    sol.offset = -1.0
    ob.pass_index = 4
    out = [ob]
    if cords:
        out.append(HR.curves_object(name + "Lace", cords, 0.00065, 0.00065, lace_mat, coll, pass_index=5))
    if edge_mat is not None:
        aa = np.linspace(AG.az[0] + 0.5, AG.az[-1] - 0.5, 200)
        tp, tn = AG.at(np.full(aa.shape, 0.004), aa)
        out.append(HR.curves_object(name + "Edge", [tp + tn * 0.003], 0.004, 0.004, edge_mat, coll, pass_index=4))
    return out


def pauldron(shell, side, plate_mat, lace_mat, edge_mat, offset=0.03, coll=None, seed=0,
             width=70.0, length=0.17, z_top=None, fr=None):
    """Shoulder guard: a lamellar skirt hanging over the shoulder and upper arm, flaring out."""
    az_c = 90.0 * side
    zt = (fr.side - 0.035) if z_top is None else z_top

    def cut(az):
        a = np.asarray(az, float)
        return zt - 0.02 * ((a - az_c) / width) ** 2 * 4

    return lamellar(shell, plate_mat, lace_mat, cut, offset=offset, row_h=0.028, plate_w=0.018,
                    overlap=0.38, s_max=length, coll=coll, seed=seed,
                    az_range=(az_c - width / 2, az_c + width / 2), name="Pauldron%s" % ("L" if side > 0 else "R"),
                    flare=0.035, edge_mat=edge_mat)


def chest_mirror(shell, fr, mat, rim_mat, az=0.0, z=None, radius=0.055, offset=0.03, coll=None):
    """Round polished mirror plate (huxinjing) with a raised rim and a boss."""
    z = fr.notch - 0.12 if z is None else z
    el = shell.el_at(np.array([az]), np.array([z]))[0]
    c = shell.point(np.array(az), np.array(el), offset)
    n = shell.normal(np.array([az]), np.array([el]))[0]
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=radius, depth=0.006, location=tuple(c))
    disc = bpy.context.active_object
    disc.name = "Mirror"
    disc.rotation_euler = Vector(n).to_track_quat("Z", "Y").to_euler()
    # domed front
    for v in disc.data.vertices:
        if v.co.z > 0:
            rr = math.hypot(v.co.x, v.co.y) / radius
            v.co.z += 0.006 * (1 - rr * rr)
    disc.data.materials.append(mat)
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=0.0045, location=tuple(c))
    rim = bpy.context.active_object
    rim.name = "MirrorRim"
    rim.rotation_euler = disc.rotation_euler
    rim.data.materials.append(rim_mat)
    for o in (disc, rim):
        for p in o.data.polygons:
            p.use_smooth = True
        o.pass_index = 4
        if coll:
            for c_ in o.users_collection:
                c_.objects.unlink(o)
            coll.objects.link(o)
    return [disc, rim]


def neck_scarf(shell, cut, mat, offset=0.012, height=0.04, folds=11, coll=None, seed=0, rise=0.012,
               front_dip=0.0):
    """Rolled silk scarf tucked along a neckline ``cut(az)`` (sits on top of the armour edge)."""
    rng = np.random.default_rng(seed)
    az = np.linspace(-180, 180, 241)
    rows = 14
    zc = cut(az) + rise - front_dip * np.clip(np.cos(np.radians(az)), 0, 1) ** 2
    zz = np.linspace(-height / 2, height / 2, rows)
    ph = rng.random(3) * 6.28
    verts = []
    for z in zz:
        el = shell.el_at(az, zc + z)
        prof = np.cos(z / height * math.pi * 0.95)
        fold = 0.003 * np.sin(np.radians(az) * folds + ph[0] + 2 * np.sin(np.radians(az) * 3 + ph[1]))
        P = shell.point(az, el, offset + prof * 0.011 + fold * prof)
        verts.append(P)
    V = np.stack(verts)
    nr, nc = V.shape[:2]
    faces = [(i * nc + j, i * nc + (j + 1) % nc, (i + 1) * nc + (j + 1) % nc, (i + 1) * nc + j)
             for i in range(nr - 1) for j in range(nc - 1)]
    me = bpy.data.meshes.new("Scarf")
    me.from_pydata(V.reshape(-1, 3).tolist(), [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    loop_v = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loop_v)
    ii, jj = np.divmod(np.arange(nr * nc), nc)
    uv = np.stack([jj / nc * 0.5, ii / nr * height], 1)[loop_v]
    uvl.data.foreach_set("uv", uv.astype(np.float32).ravel())
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new("Scarf", me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    ob.pass_index = 5
    return ob


# ---------------------------------------------------------------------------------- headgear
def _skull_shell(surf, C, az, el):
    """Ray-cast the head from the cranium centre: radius grid (el x az)."""
    from mathutils.bvhtree import BVHTree
    D = SH._dir(*np.meshgrid(az, el))
    # here az=0 is front (-Y)
    r = np.full(D.shape[:2], np.nan)
    O = Vector(C)
    for i in range(D.shape[0]):
        for j in range(D.shape[1]):
            loc, nrm, idx, dist = surf.bvh.ray_cast(O, Vector(D[i, j]), 1.0)
            if loc is not None:
                r[i, j] = dist
    for i in range(r.shape[0]):
        row = r[i]
        bad = ~np.isfinite(row)
        if bad.all():
            r[i] = np.nanmean(r)
        elif bad.any():
            r[i, bad] = np.interp(np.where(bad)[0], np.where(~bad)[0], row[~bad])
    return D, r


def helmet(surf, b, C, mats, coll=None, seed=0, brim_el=None, style="bowl", flaps=True,
           tassel=True, ridge=True, height=1.0, brim_raise=0.0):
    """Chinese helmet fitted to the skull: smoothed bowl (ray-cast skull + clearance), brim band
    with rivets, front brow plate, ridge, finial with a red horsehair tassel, lamellar/quilted
    neck-and-ear flaps (dunxiang).  mats: bowl, trim, rivet, flap, flap_trim, tassel"""
    rng = np.random.default_rng(seed)
    lm = b["lm"]
    import regions as R
    az = np.linspace(-180, 180, 145)
    el = np.linspace(-30, 90, 61)
    D, r = _skull_shell(surf, C, az, el)
    rs = SH._blur2(r, 3.0, 3.0)
    # hairline-ish brim: front just above the brows, sides above the ears, back at the nape
    eye_c = np.array(lm["eye_c"])
    brow_z = eye_c[2] + 0.70 * lm["ipd"] + brim_raise

    def brim_z(a):
        aa = np.abs(a)
        return np.interp(aa, [0, 40, 75, 110, 180], [brow_z, brow_z + 0.004, brow_z - 0.005, brow_z - 0.012, brow_z - 0.02])
    clearance = 0.009
    rows = []
    elv = np.linspace(-30, 90, 61)
    # helmet surface: rows from the brim up to the apex
    nr = 40
    AZ = np.linspace(-180, 180, 145)
    P = np.zeros((nr, len(AZ), 3))
    for j, a in enumerate(AZ):
        col = C + D[:, j] * (rs[:, j] + clearance)[:, None]
        zc = col[:, 2]
        e0 = np.interp(brim_z(a), zc, elv)
        es = np.linspace(e0, 90, nr)
        rr = np.interp(es, elv, rs[:, j]) + clearance
        # dome a bit taller and rounder than the skull; flare the brim slightly outward
        t = np.linspace(0, 1, nr)
        rr = rr * (1 + 0.04 * height * np.sin(t * math.pi * 0.5)) + 0.004 * (1 - t) ** 4
        dirs = SH._dir(np.full(nr, a), es)
        P[:, j] = C + dirs * rr[:, None]
    # apex lift
    P[..., 2] += (np.linspace(0, 1, nr) ** 3)[:, None] * 0.012 * height
    nc = len(AZ)
    faces = [(i * nc + j, i * nc + (j + 1) % nc, (i + 1) * nc + (j + 1) % nc, (i + 1) * nc + j)
             for i in range(nr - 1) for j in range(nc - 1)]
    me = bpy.data.meshes.new("Helmet")
    me.from_pydata(P.reshape(-1, 3).tolist(), [], faces)
    # vertical ridges (bowl made of riveted segments): material index for alternating gores
    mi = []
    for i in range(nr - 1):
        for j in range(nc - 1):
            mi.append(0)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["bowl"])
    hel = bpy.data.objects.new("Helmet", me)
    (coll or bpy.context.scene.collection).objects.link(hel)
    sol = hel.modifiers.new("thick", "SOLIDIFY")
    sol.thickness = 0.002
    hel.modifiers.new("sub", "SUBSURF").levels = 1
    hel.pass_index = 4
    objs = [hel]
    # brim band (thick torus-like strip along the bottom row)
    ring = P[0]
    nrm_out = ring - C
    nrm_out /= np.linalg.norm(nrm_out, axis=1, keepdims=True)
    band_h = 0.022
    bv = []
    for k, (dz, do) in enumerate(((-0.004, 0.003), (0.0, 0.0055), (band_h * 0.5, 0.0065), (band_h, 0.0055), (band_h + 0.004, 0.002))):
        bv.append(ring + nrm_out * do + np.array([0, 0, dz]) + nrm_out * (dz * 0.15))
    BV = np.stack(bv)
    faces = [(i * nc + j, i * nc + (j + 1) % nc, (i + 1) * nc + (j + 1) % nc, (i + 1) * nc + j)
             for i in range(len(bv) - 1) for j in range(nc - 1)]
    me = bpy.data.meshes.new("Brim")
    me.from_pydata(BV.reshape(-1, 3).tolist(), [], faces)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["trim"])
    brim = bpy.data.objects.new("Brim", me)
    (coll or bpy.context.scene.collection).objects.link(brim)
    brim.pass_index = 4
    objs.append(brim)
    # rivets on the band
    for j in range(0, nc - 1, 4):
        p = ring[j] + nrm_out[j] * 0.0072 + np.array([0, 0, band_h * 0.5])
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.0028, location=tuple(p))
        rv = bpy.context.active_object
        rv.data.materials.append(mats["rivet"])
        rv.pass_index = 4
        objs.append(rv)
    # ridges: meridian strips every 30 deg (raised ribs)
    if ridge:
        for a in np.arange(-180, 180, 30):
            j = int(np.argmin(np.abs(AZ - a)))
            line = P[:, j]
            nrm = line - C
            nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
            pts = line + nrm * 0.0028
            o = HR.curves_object("Rib", [pts[2:-2]], 0.0022, 0.0018, mats["trim"], coll, pass_index=4)
            objs.append(o)
    # brow plate: a pointed visor at the front (downward point between the brows)
    j0 = int(np.argmin(np.abs(AZ)))
    front = ring[j0]
    fn = nrm_out[j0]
    pts = []
    for k, a in enumerate(np.linspace(-38, 38, 15)):
        j = int(np.argmin(np.abs(AZ - a)))
        dip = 0.008 * max(0, 1 - abs(a) / 38) ** 1.5
        pts.append(ring[j] + nrm_out[j] * 0.0075 + np.array([0, 0, -dip + 0.002]))
    vis = np.array(pts)
    top = vis + np.array([0, 0, 0.012])
    V2 = np.concatenate([vis, top])
    n15 = len(vis)
    faces = [(i, i + 1, n15 + i + 1, n15 + i) for i in range(n15 - 1)]
    me = bpy.data.meshes.new("Visor")
    me.from_pydata(V2.tolist(), [], faces)
    me.materials.append(mats["trim"])
    vo = bpy.data.objects.new("Visor", me)
    (coll or bpy.context.scene.collection).objects.link(vo)
    so = vo.modifiers.new("t", "SOLIDIFY")
    so.thickness = 0.003
    vo.modifiers.new("s", "SUBSURF").levels = 2
    vo.pass_index = 4
    objs.append(vo)
    # finial + tassel
    apex = P[-1].mean(0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.006, depth=0.04, location=tuple(apex + np.array([0, 0, 0.02])))
    st = bpy.context.active_object
    st.data.materials.append(mats["trim"])
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.011, location=tuple(apex + np.array([0, 0, 0.008])))
    kb = bpy.context.active_object
    kb.data.materials.append(mats["trim"])
    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.006, radius2=0.0005, depth=0.05, location=tuple(apex + np.array([0, 0, 0.065])))
    sp = bpy.context.active_object
    sp.data.materials.append(mats["trim"])
    for o in (st, kb, sp):
        for p in o.data.polygons:
            p.use_smooth = True
        o.pass_index = 4
        objs.append(o)
    if tassel:
        n = 2600
        top = apex + np.array([0, 0, 0.034])
        strands = []
        for i in range(n):
            ang = rng.random() * 2 * math.pi
            r0 = top + np.array([math.cos(ang), math.sin(ang), 0]) * 0.004
            outd = np.array([math.cos(ang), math.sin(ang), 0])
            L = 0.06 + 0.035 * rng.random()
            t = np.linspace(0, 1, 12)
            reach = 0.028 + 0.012 * rng.random()
            pts = (r0[None] + outd[None] * (reach * np.sin(t * math.pi / 2))[:, None]
                   + np.array([0, 0, 1.0])[None] * (0.008 * np.sin(t * math.pi) - L * t ** 1.6)[:, None])
            pts += rng.standard_normal((12, 3)) * 0.0012 * t[:, None]
            strands.append(pts)
        strands = np.array(strands)
        # drape over the dome: keep strands outside the bowl
        dg = bpy.context.evaluated_depsgraph_get()
        from mathutils.bvhtree import BVHTree
        tree = BVHTree.FromObject(hel, dg)
        for si in range(len(strands)):
            for k in range(1, 12):
                p = Vector(strands[si, k])
                loc, nrm, _, _ = tree.find_nearest(p)
                if loc is not None and (p - loc).dot(nrm) < 0.003:
                    strands[si, k] = loc + nrm * 0.003
        to = HR.curves_object("Tassel", strands, 0.00026, 0.0001, mats["tassel"], coll, pass_index=6)
        objs.append(to)
    # neck & ear flaps: quilted/lamellar curtain hanging from the brim at sides and back
    if flaps:
        fa = AZ[np.abs(AZ) >= 62]
        rows = 14
        L = 0.10
        verts = []
        jj = [int(np.argmin(np.abs(AZ - a))) for a in fa]
        order = np.argsort(np.where(fa > 0, fa, fa + 360))
        fa = fa[order]
        jj = [jj[k] for k in order]
        for i in range(rows):
            t = i / (rows - 1)
            row = []
            for a, j in zip(fa, jj):
                base = ring[j] + nrm_out[j] * 0.006 + np.array([0, 0, 0.002])
                outw = nrm_out[j] * np.array([1, 1, 0])
                outw /= np.linalg.norm(outw) + 1e-9
                p = base + np.array([0, 0, -L * t]) + outw * (0.012 * t ** 1.3)
                p = p + outw * 0.003 * math.sin(i * 1.6)  # quilted ridges
                row.append(p)
            verts.append(row)
        V3 = np.array(verts)
        ncol = V3.shape[1]
        faces = [(i * ncol + j, i * ncol + j + 1, (i + 1) * ncol + j + 1, (i + 1) * ncol + j)
                 for i in range(rows - 1) for j in range(ncol - 1)]
        me = bpy.data.meshes.new("Flaps")
        me.from_pydata(V3.reshape(-1, 3).tolist(), [], faces)
        uvl = me.uv_layers.new(name="UVMap")
        loop_v = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", loop_v)
        ii, jj2 = np.divmod(np.arange(V3.shape[0] * ncol), ncol)
        uv = np.stack([jj2 / ncol * 0.6, ii / rows * L], 1)[loop_v]
        uvl.data.foreach_set("uv", uv.astype(np.float32).ravel())
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(mats["flap"])
        fo = bpy.data.objects.new("Flaps", me)
        (coll or bpy.context.scene.collection).objects.link(fo)
        so = fo.modifiers.new("t", "SOLIDIFY")
        so.thickness = 0.004
        fo.pass_index = 5
        objs.append(fo)
        # trim along the bottom edge
        o = HR.curves_object("FlapTrim", [V3[-1]], 0.0035, 0.0035, mats.get("flap_trim", mats["trim"]), coll, pass_index=5)
        objs.append(o)
    return objs, brim_z


def topknot_crown(apex, axis, fwd, mats, coll=None, size=1.0, pin=True):
    """Crescent crown (yanyue guan) standing over the topknot, pinned through crosswise."""
    import bmesh
    objs = []
    axis = np.array(axis, float) / np.linalg.norm(axis)
    fwd = np.array(fwd, float) / np.linalg.norm(fwd)
    side = np.cross(axis, fwd)
    R0 = 0.024 * size
    wdt = 0.032 * size
    th = 0.0025
    bm = bmesh.new()
    rows = []
    n = 24
    for i in range(n + 1):
        a = np.pi * (0.06 + 0.88 * i / n)  # arch from back to front over the bun
        ring = []
        for sw, rr in ((-1, R0), (1, R0), (1, R0 + th), (-1, R0 + th)):
            p = np.array(apex) + (np.cos(a) * fwd + np.sin(a) * axis) * rr + side * sw * wdt / 2 * (1 - 0.25 * np.cos(a) ** 2)
            p = p - axis * R0 * 0.35
            ring.append(bm.verts.new(tuple(p)))
        rows.append(ring)
    for i in range(n):
        for k in range(4):
            a0, a1 = rows[i][k], rows[i][(k + 1) % 4]
            b0, b1 = rows[i + 1][k], rows[i + 1][(k + 1) % 4]
            bm.faces.new((a0, a1, b1, b0))
    bm.faces.new(rows[0][::-1])
    bm.faces.new(rows[-1])
    me = bpy.data.meshes.new("Guan")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mats["crown"])
    cr = bpy.data.objects.new("Guan", me)
    (coll or bpy.context.scene.collection).objects.link(cr)
    cr.modifiers.new("s", "SUBSURF").levels = 1
    cr.pass_index = 4
    objs.append(cr)
    if pin:
        L = 0.10 * size
        c = np.array(apex) + axis * R0 * 0.15
        p0 = c - side * L / 2
        p1 = c + side * L / 2
        po = HR.curves_object("Pin", [np.linspace(p0, p1, 6)], 0.0016, 0.0013, mats["pin"], coll, pass_index=7)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.004, location=tuple(p1))
        kn = bpy.context.active_object
        kn.data.materials.append(mats["pin"])
        kn.pass_index = 7
        objs += [po, kn]
    return objs


def hairpin(p0, direction, length, mats, coll=None, head="flower", dangles=0, rng=None, scale=1.0):
    """Gold hairpin with an ornament head (flower of jade/pearl petals) and optional dangling
    strings of beads (buyao)."""
    rng = rng or np.random.default_rng(0)
    d = np.array(direction, float)
    d /= np.linalg.norm(d)
    p1 = np.array(p0) + d * length
    objs = [HR.curves_object("Pin", [np.linspace(p0, p1, 6)], 0.0012 * scale, 0.0009 * scale, mats["gold"], coll, pass_index=7)]
    if head == "flower":
        c = p1
        for k in range(6):
            a = k / 6 * 2 * math.pi
            off = np.array([math.cos(a), math.sin(a), 0.3]) * 0.007 * scale
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.0042 * scale, location=tuple(c + off))
            pt = bpy.context.active_object
            pt.scale = (1.0, 0.7, 0.5)
            pt.data.materials.append(mats["petal"])
            objs.append(pt)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.0035 * scale, location=tuple(c + np.array([0, 0, 0.002])))
        ct = bpy.context.active_object
        ct.data.materials.append(mats["pearl"])
        objs.append(ct)
    elif head == "ball":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.005 * scale, location=tuple(p1))
        kb = bpy.context.active_object
        kb.data.materials.append(mats["jade"])
        objs.append(kb)
    for k in range(dangles):
        start = p1 + np.array([(k - dangles / 2) * 0.004, 0, -0.002])
        L = (0.03 + 0.015 * rng.random()) * scale
        chain = np.linspace(start, start + np.array([0, 0, -L]), 7)
        objs.append(HR.curves_object("Dangle", [chain], 0.0005, 0.0005, mats["gold"], coll, pass_index=7))
        for t in (0.5, 1.0):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.0022 * scale, location=tuple(start + np.array([0, 0, -L * t])))
            bd = bpy.context.active_object
            bd.data.materials.append(mats["pearl"] if t == 1.0 else mats["jade"])
            objs.append(bd)
    for o in objs:
        if o.type == "MESH":
            for p in o.data.polygons:
                p.use_smooth = True
            o.pass_index = 7
    return objs


def prayer_beads(shell, fr, mat, offset=0.03, coll=None, radius=0.0075, drop=0.17, big=None):
    """A string of large wooden beads around the neck hanging in a U over the chest."""
    az = np.concatenate([np.linspace(180, 60, 20), np.linspace(60, -60, 40), np.linspace(-60, -180, 20)])
    z = np.where(np.abs(az) > 60, np.interp(np.abs(az), [60, 180], [fr.side - 0.02, fr.back - 0.01]),
                 fr.side - 0.02 - drop * np.cos(np.radians(az) * 1.5) ** 2)
    el = shell.el_at(az, z)
    P = shell.point(az, el, offset)
    seg = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    n = int(seg[-1] / (radius * 2.05))
    ts = np.linspace(0, seg[-1], n)
    pts = np.stack([np.interp(ts, seg, P[:, k]) for k in range(3)], 1)
    objs = []
    me_all = None
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=radius, location=(0, 0, 0))
    proto = bpy.context.active_object
    proto.data.materials.append(mat)
    for p in proto.data.polygons:
        p.use_smooth = True
    for k, p in enumerate(pts):
        o = proto.copy()
        o.location = tuple(p)
        r = radius * (1.6 if big and k == len(pts) // 2 else 1.0)
        o.scale = (r / radius,) * 3
        (coll or bpy.context.scene.collection).objects.link(o)
        o.pass_index = 7
        objs.append(o)
    bpy.data.objects.remove(proto)
    return objs


def fur_collar(shell, cut, mat, rng, offset=0.02, count=6000, length=0.045, band=0.05, coll=None):
    """Fur trim along a neckline: clumped strands rooted in a band below ``cut``."""
    az = rng.uniform(-180, 180, count)
    dz = rng.uniform(0, band, count)
    z = cut(az) - dz
    el = shell.el_at(az, z)
    root = shell.point(az, el, offset)
    n = shell.normal(az, el)
    K = 6
    L = length * (0.6 + 0.8 * rng.random(count))
    down = np.array([0, 0, -1.0])
    t = np.linspace(0, 1, K)[None, :, None]
    d = n * 0.8 + down[None] * 0.5
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    pts = root[:, None, :] + d[:, None, :] * L[:, None, None] * t + down[None, None, :] * (L[:, None, None] * 0.4 * t ** 2)
    pts = HR.clump(pts, rng, count // 25, 0.6, 1.0)
    pts = HR.frizz(pts, rng, 0.002, 2.0)
    return HR.curves_object("Fur", pts, 0.00025, 0.00006, mat, coll, pass_index=6)


def headband(surf, b, C, mat, coll=None, width=0.03, height_ipd=0.95, knot=True):
    """Cloth band tied around the head over the forehead (ze / mojie)."""
    lm = b["lm"]
    eye_c = np.array(lm["eye_c"])
    az = np.linspace(-180, 180, 145)
    el = np.linspace(-30, 90, 61)
    D, r = _skull_shell(surf, C, az, el)
    rs = SH._blur2(r, 2.0, 2.0)
    zc = eye_c[2] + height_ipd * lm["ipd"]
    rows = []
    for dz in (-width / 2, -width / 4, 0, width / 4, width / 2):
        row = []
        for j, a in enumerate(az):
            col = C + D[:, j] * (rs[:, j] + 0.006)[:, None]
            zz = zc + dz - 0.012 * (1 - np.cos(np.radians(a))) * 0.5
            e = np.interp(zz, col[:, 2], el)
            rr = np.interp(e, el, rs[:, j]) + 0.006 + 0.002 * math.cos(dz / width * math.pi)
            row.append(C + SH._dir(np.array(a), np.array(e)) * rr)
        rows.append(row)
    V = np.array(rows)
    nr, nc = V.shape[:2]
    faces = [(i * nc + j, i * nc + j + 1, (i + 1) * nc + j + 1, (i + 1) * nc + j) for i in range(nr - 1) for j in range(nc - 1)]
    me = bpy.data.meshes.new("Headband")
    me.from_pydata(V.reshape(-1, 3).tolist(), [], faces)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new("Headband", me)
    (coll or bpy.context.scene.collection).objects.link(ob)
    ob.pass_index = 5
    return ob


def cape(shell, fr, mat, coll=None, offset=0.055, front_az=58.0, seed=0, folds=0.006):
    """War cloak hanging from the shoulders behind the pauldrons (two halves, open in front)."""
    rng = np.random.default_rng(seed)
    objs = []
    ph = rng.random(3) * 6.28

    def cut(az):
        a = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
        return np.interp(a, [front_az, 100, 180], [fr.side - 0.035, fr.side - 0.005, fr.back - 0.01])

    def off(az, t):
        a = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
        f = folds * (0.5 + 0.5 * np.sin(np.radians(a) * 11 + ph[0] + 1.5 * np.sin(np.radians(a) * 3 + ph[1]))) * (1 - t) ** 1.2
        return offset + f + 0.03 * (1 - t) ** 2 + 0.01 * np.clip((front_az + 25 - a) / 25, 0, 1)
    for k, rngz in enumerate(((front_az, 179.9), (-179.9, -front_az))):
        ob = shell.layer("Cape%d" % k, cut, off, rows=60, mats=[mat], coll=coll, az_range=rngz,
                         band=(0.025, 0.004, True))
        ob.data.materials.append(mat)
        sol = ob.modifiers.new("t", "SOLIDIFY")
        sol.thickness = 0.003
        ob.pass_index = 5
        objs.append(ob)
    return objs

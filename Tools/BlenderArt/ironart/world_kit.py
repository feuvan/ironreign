"""World Models family: Chinese architecture kit at real (exaggerated map) scale, in metres.

Builds into :class:`ironart.geometry.MeshBuilder` with explicit **metre UVs** (the ``MetreUV``
layer the :mod:`ironart.world_mats` materials read) and ``W_*`` material slot names.  Every
builder works in its own local frame (+Z up, front = -Y) and is placed with a transform, so the
same code makes prototypes for :mod:`ironart.world_bake` (one atlas, instanced) and one-offs.

Contents
    sweep / beam / column / platform / steps     low-level parts with good UVs
    roof            hip / hip_gable / gable / pyramid roofs: concave slopes, upturned corners,
                    geometric cover-tile rows, main ridge with chiwen, hip & gable ridges with
                    beasts, fascia with painted rafter ends, soffit
    ngon_roof       octagonal / square pagoda and pavilion eaves
    hall            platform + steps + red columns + lattice bays + painted beams + dougong
                    brackets + single or double eave roof
    gate_base       battered gate block with a real arched tunnel and studded doors
    wall_segment    crenellated battered city wall (outer face -Y), earth wall variant
    pagoda          octagonal brick pagoda with dense eaves, balconies, gilt spire
    house           courtyard dwellings (gable roofs with tile rows)
    balustrade / railing, bridge, watchtower, drum tower, corner tower, paifang

Triangle economy: ``tile_seg`` / ``tile_faces`` / ``pitch`` control the tile rows, the main
cost of a roof (see :func:`roof`).
"""

import math
import random

from mathutils import Matrix, Vector

from .geometry import MeshBuilder

TAU = math.tau


def T(x=0.0, y=0.0, z=0.0, rz=0.0, s=1.0):
    m = Matrix.Translation(Vector((x, y, z))) @ Matrix.Rotation(rz, 4, "Z")
    if s != 1.0:
        m = m @ Matrix.Scale(s, 4)
    return m


def place(mb, start, m):
    mb.transform(start, m)


# ---------------------------------------------------------------------------------------------
# low level
# ---------------------------------------------------------------------------------------------
def quad(mb, pts, mat, uvs=None, smooth=False):
    ids = [mb.v(p) for p in pts]
    mb.face(ids, mat, uvs, smooth)
    return ids


def sweep(mb, path, section, mat, closed_section=False, caps=True, smooth=True, up=(0, 0, 1),
          cap_mat=None, scale_fn=None):
    """Sweep a 2D ``section`` [(side, up), ...] along a 3D polyline ``path``.

    The frame per point: tangent T, U = ``up`` made perpendicular to T, S = T x U... (S points to
    the right of the direction of travel when ``up`` is +Z).  UVs: u = section perimeter (m),
    v = path length (m).  ``scale_fn(t)`` scales the section along the path (tapers)."""
    P = [Vector(p) for p in path]
    n = len(P)
    upv = Vector(up)
    rings = []
    vlen = 0.0
    vs = []
    for i in range(n):
        a = P[max(0, i - 1)]
        b = P[min(n - 1, i + 1)]
        t = (b - a).normalized()
        u = (upv - t * upv.dot(t))
        if u.length < 1e-6:
            u = Vector((0, 1, 0)) - t * t.y
        u.normalize()
        s_ = t.cross(u).normalized()
        if i > 0:
            vlen += (P[i] - P[i - 1]).length
        vs.append(vlen)
        k = scale_fn(i / (n - 1)) if scale_fn else 1.0
        rings.append([mb.v(P[i] + s_ * (sx * k) + u * (sy * k)) for sx, sy in section])
    m = len(section)
    per = [0.0]
    for j in range(1, m):
        per.append(per[-1] + math.hypot(section[j][0] - section[j - 1][0], section[j][1] - section[j - 1][1]))
    if closed_section:
        per.append(per[-1] + math.hypot(section[0][0] - section[-1][0], section[0][1] - section[-1][1]))
    segs = m if closed_section else m - 1
    for i in range(n - 1):
        for j in range(segs):
            jj = (j + 1) % m
            mb.face((rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]), mat,
                    [(per[j], vs[i]), (per[j + 1], vs[i]), (per[j + 1], vs[i + 1]), (per[j], vs[i + 1])],
                    smooth)
    if caps:
        mb.face(rings[0][::-1], cap_mat or mat)
        mb.face(rings[-1], cap_mat or mat)
    return rings


def box_uv(mb, c, size, mat, rz=0.0, top=None, skip=(), taper=(0.0, 0.0), origin_uv=True):
    """Box with bottom at c[2]; UVs from its own local frame (so patterns start at the box
    corner, independent of where it is placed)."""
    s = mb.n
    sx, sy, sz = size
    mb.box((sx / 2.0 if origin_uv else 0.0, sy / 2.0 if origin_uv else 0.0, 0.0), size, mat,
           taper=taper, skip=skip, top_mat=top)
    off = Matrix.Translation(Vector((-sx / 2.0, -sy / 2.0, 0.0))) if origin_uv else Matrix.Identity(4)
    mb.transform(s, T(c[0], c[1], c[2], rz) @ off)
    return s


def beam(mb, p0, p1, z0, h, t, mat, uv_norm=True):
    """Rectangular beam from p0 to p1 (xy), bottom at z0, height h, thickness t.  Long faces get
    u normalised 0..1 along the beam (one painted panel set per bay, see world_mats.beam_paint)
    and v = metres up."""
    a, b = Vector((p0[0], p0[1], 0)), Vector((p1[0], p1[1], 0))
    d = b - a
    Ln = d.length
    if Ln < 1e-6:
        return
    x = d.normalized()
    y = Vector((-x.y, x.x, 0))
    ht = t / 2.0
    corners = []
    for zz in (z0, z0 + h):
        for (px, py) in ((0, -ht), (Ln, -ht), (Ln, ht), (0, ht)):
            corners.append(a + x * px + y * py + Vector((0, 0, zz)))
    ids = [mb.v(c) for c in corners]
    U = (lambda f: f) if uv_norm else (lambda f: f * Ln)
    # front (-y side) / back
    mb.face((ids[0], ids[1], ids[5], ids[4]), mat, [(U(0), 0), (U(1), 0), (U(1), h), (U(0), h)])
    mb.face((ids[2], ids[3], ids[7], ids[6]), mat, [(U(0), 0), (U(1), 0), (U(1), h), (U(0), h)])
    mb.face((ids[4], ids[5], ids[6], ids[7]), mat, [(U(0), 0), (U(1), 0), (U(1), t), (U(0), t)])
    mb.face((ids[3], ids[2], ids[1], ids[0]), mat, [(U(0), 0), (U(1), 0), (U(1), t), (U(0), t)])
    mb.face((ids[0], ids[4], ids[7], ids[3]), mat, [(0, 0), (0, h), (t, h), (t, 0)])
    mb.face((ids[1], ids[2], ids[6], ids[5]), mat, [(0, 0), (t, 0), (t, h), (0, h)])


def column(mb, x, y, z0, h, r, mat="W_Lacquer", seg=10, base_mat="W_Marble", base=True):
    if base:
        mb.lathe([(r * 1.45, 0.0), (r * 1.45, 0.12), (r * 1.25, 0.24), (r * 1.05, 0.28)], base_mat,
                 seg, center=(x, y, z0), smooth=True, cap_top=False)
    mb.lathe([(r, 0.0), (r * 0.94, h)], mat, seg, center=(x, y, z0 + (0.26 if base else 0.0)),
             smooth=True)


def platform(mb, w, d, h, mat="W_Marble", top="W_Paving", chamfer=0.15, z0=0.0, skirt=1.5,
             cx=0.0, cy=0.0, plinth=True):
    """Stone podium with a moulded plinth course and a chamfered coping; extends ``skirt`` m
    below the ground so it sits on uneven terrain."""
    s = mb.n
    mb.box((0, 0, -skirt), (w + 0.2, d + 0.2, skirt + 0.25), mat, skip=("bottom",))
    mb.box((0, 0, 0.25), (w, d, h - 0.25 - chamfer), mat, skip=("bottom",))
    mb.box((0, 0, h - chamfer), (w + 0.08, d + 0.08, chamfer), mat, top_mat=top,
           taper=(0.04, 0.04), skip=("bottom",))
    mb.transform(s, T(cx, cy, z0))


def steps(mb, x, y, z0, width, rise, n, run=0.38, mat="W_Marble", rz=0.0, cheeks=True):
    """Flight of ``n`` steps rising ``rise`` metres, climbing towards +y (local), lowest step
    front edge at y (local).  ``rz`` rotates the flight about (x, y)."""
    s = mb.n
    hstep = rise / n
    for i in range(n):
        d = run * (n - i)
        mb.box((0, d / 2.0, i * hstep), (width, d, hstep), mat, skip=("bottom",))
    if cheeks:
        L = run * n
        for sx in (-1, 1):
            pts = [(sx * (width / 2 + 0.2), 0.0), (sx * (width / 2 + 0.2), L + 0.1)]
            lo = [mb.v((pts[0][0] - 0.2, 0, 0)), mb.v((pts[0][0] + 0.2, 0, 0)),
                  mb.v((pts[0][0] + 0.2, L + 0.1, 0)), mb.v((pts[0][0] - 0.2, L + 0.1, 0))]
            hi = [mb.v((pts[0][0] - 0.2, 0, 0.18)), mb.v((pts[0][0] + 0.2, 0, 0.18)),
                  mb.v((pts[0][0] + 0.2, L + 0.1, rise + 0.18)), mb.v((pts[0][0] - 0.2, L + 0.1, rise + 0.18))]
            mb.face((lo[0], lo[1], hi[1], hi[0]), mat)
            mb.face((lo[1], lo[2], hi[2], hi[1]), mat)
            mb.face((lo[3], lo[0], hi[0], hi[3]), mat)
            mb.face((hi[0], hi[1], hi[2], hi[3]), mat)
    mb.transform(s, T(x, y, z0, rz))


# ---------------------------------------------------------------------------------------------
# roofs
# ---------------------------------------------------------------------------------------------
class RoofSpec:
    """Per-roof parameters (see :func:`roof`)."""

    def __init__(self, **kw):
        self.style = "hip_gable"
        self.overhang = 1.4
        self.lift = 0.7
        self.flare = 0.35
        self.curve = 1.75
        self.thick = 0.32
        self.pitch = 0.55
        self.tiles = True
        self.tile_seg = 5
        self.tile_faces = 3
        self.nv = 6
        self.gable_frac = 0.5
        self.v_max = 1.0
        self.mat = "W_Tile"
        self.ridge_mat = "W_Ridge"
        self.under_mat = "W_WoodDark"
        self.fascia_mat = "W_Fascia"
        self.gable_mat = "W_Gable"
        self.ridge_h = None
        self.chiwen = True
        self.beasts = 0
        self.finial = None           # pyramid apex: 'gold' / 'tile'
        self.finial_mat = "W_Gold"
        self.ridge_ends = "chiwen"   # 'chiwen' | 'curl' (southern upturned) | 'plain'
        for k, v in kw.items():
            if not hasattr(self, k):
                raise AttributeError("RoofSpec has no %r" % k)
            setattr(self, k, v)


def roof(mb, center, w, d, H, spec=None, rz=0.0, **kw):
    """Chinese roof over a ``w`` x ``d`` eave-support rectangle (overhang added), ridge ``H``
    above the eave line at ``center`` (x, y, z = eave line).  Front slope faces -y.

    Styles: 'hip' (wudian), 'hip_gable' (xieshan), 'gable' (xuanshan: slopes overhang the gable
    walls), 'pyramid' (cuanjian).  Cover-tile rows run straight down the slopes every
    ``pitch`` m (fanning out at the lifted corners like real tile courses) and end at the hips;
    each row is ``tile_seg`` segments x ``tile_faces`` faces + a round end tile at the eave.
    Returns the vertex start index."""
    sp = spec or RoofSpec()
    for k, v in kw.items():
        setattr(sp, k, v)
    s0 = mb.n
    A = w / 2.0 + sp.overhang
    B = d / 2.0 + sp.overhang
    swap = B > A and sp.style != "pyramid"
    if swap:
        A, B = B, A
    if sp.style == "pyramid":
        A = B = max(A, B)
    vg = {"hip": 1.0, "pyramid": 1.0, "hip_gable": sp.gable_frac, "gable": 0.0}[sp.style]
    xg = max(0.0, A - B * vg)
    gable = sp.style == "gable"
    vmax = sp.v_max
    nv = sp.nv
    pexp = 3.0
    lift, flare = sp.lift, sp.flare
    if gable:
        lift, flare = lift * 0.35, flare * 0.2

    def prof(v):
        return H * (v ** sp.curve)

    def lift_at(s, v):
        k = (1.0 - v) ** 2
        return lift * (s ** pexp) * k, flare * (s ** pexp) * k

    def xe(v):
        return A if gable else max(A - B * v, xg)

    def front_pt(x, v, side):
        """side +1 = front slope (-y), -1 = back slope."""
        e = xe(v)
        s = min(1.0, abs(x) / e) if e > 1e-6 else 1.0
        lz, fl = lift_at(s, v)
        sx = 1.0 if x >= 0 else -1.0
        return Vector((x + sx * fl * (1 if abs(x) > 1e-6 else 0), side * (-B * (1 - v) - fl), prof(v) + lz))

    def side_pt(y, v, side):
        """side +1 = +x hip end, -1 = -x."""
        e = B * (1 - v)
        s = min(1.0, abs(y) / e) if e > 1e-6 else 1.0
        lz, fl = lift_at(s, v)
        sy = 1.0 if y >= 0 else -1.0
        return Vector((side * (A - B * v + fl), y + sy * fl * (1 if abs(y) > 1e-6 else 0), prof(v) + lz))

    def arc(v_end, n=24):
        """slope length from the eave to v (for UV v in metres)"""
        tot, prev = 0.0, None
        out = []
        for i in range(n + 1):
            v = v_end * i / n
            p = Vector((0.0, -B * (1 - v), prof(v)))
            if prev is not None:
                tot += (p - prev).length
            out.append(tot)
            prev = p
        return lambda v: out[min(n, int(round(v / max(v_end, 1e-6) * n)))] if v_end > 0 else 0.0

    slope_len = arc(1.0, 48)

    def surface(fn, nu, umin_fn, umax_fn, v1, flip, mat):
        """Grid over u in [umin(v), umax(v)], v in [0, v1]; returns (top rows, edge ids)."""
        rows = []
        for j in range(nv + 1):
            v = v1 * j / nv
            a, b = umin_fn(v), umax_fn(v)
            rows.append([(a + (b - a) * i / nu, v) for i in range(nu + 1)])
        ids = [[mb.v(fn(u, v)) for (u, v) in r] for r in rows]
        for j in range(nv):
            for i in range(nu):
                q = [ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]]
                uv = [(rows[j][i][0], slope_len(rows[j][i][1])), (rows[j][i + 1][0], slope_len(rows[j][i + 1][1])),
                      (rows[j + 1][i + 1][0], slope_len(rows[j + 1][i + 1][1])), (rows[j + 1][i][0], slope_len(rows[j + 1][i][1]))]
                if flip:
                    q, uv = q[::-1], uv[::-1]
                mb.face(q, mat, uv, True)
        return rows, ids

    def underside(fn, nu, umin_fn, umax_fn, v1, flip):
        th = Vector((0, 0, sp.thick))
        nvu = max(2, nv // 2)
        rows = []
        for j in range(nvu + 1):
            v = v1 * j / nvu
            a, b = umin_fn(v), umax_fn(v)
            rows.append([fn(a + (b - a) * i / nu, v) - th for i in range(nu + 1)])
        ids = [[mb.v(p) for p in r] for r in rows]
        for j in range(nvu):
            for i in range(nu):
                q = [ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]]
                mb.face(q if flip else q[::-1], sp.under_mat, None, True)
        return ids

    def fascia_strip(top_pts, bot_pts, flip):
        acc = 0.0
        prev = None
        us = []
        for p in top_pts:
            if prev is not None:
                acc += (p - prev).length
            us.append(acc)
            prev = p
        tid = [mb.v(p) for p in top_pts]
        bid = [mb.v(p) for p in bot_pts]
        for i in range(len(tid) - 1):
            q = [tid[i], tid[i + 1], bid[i + 1], bid[i]]
            uv = [(us[i], sp.thick), (us[i + 1], sp.thick), (us[i + 1], 0.0), (us[i], 0.0)]
            if flip:
                q, uv = q[::-1], uv[::-1]
            mb.face(q, sp.fascia_mat, uv, False)

    th = Vector((0, 0, sp.thick))
    nu_f = max(8, min(28, int(2 * A / 1.2)))
    nu_s = max(6, min(18, int(2 * B / 1.2)))
    # ---- front / back slopes ----
    v1f = vmax
    for side in (1, -1):
        fn = (lambda u, v, sd=side: front_pt(u, v, sd))
        flip = side < 0
        surface(fn, nu_f, lambda v: -xe(v), lambda v: xe(v), v1f, flip, sp.mat)
        underside(fn, max(4, nu_f // 2), lambda v: -xe(v), lambda v: xe(v), v1f, flip)
        eave = [front_pt(-A + 2 * A * i / nu_f, 0.0, side) for i in range(nu_f + 1)]
        fascia_strip(eave, [p - th for p in eave], not flip)
        if gable:
            # rake fascia along the gable ends
            for sx in (-1, 1):
                rk = [front_pt(sx * A, v1f * j / nv, side) for j in range(nv + 1)]
                fascia_strip(rk, [p - th for p in rk], (sx * side) > 0)
    # ---- hip ends ----
    if vg > 0 and not gable:
        v1s = min(vmax, vg)
        for side in (1, -1):
            fn = (lambda u, v, sd=side: side_pt(u, v, sd))
            flip = side < 0
            surface(fn, nu_s, lambda v: -B * (1 - v), lambda v: B * (1 - v), v1s, flip, sp.mat)
            underside(fn, max(3, nu_s // 2), lambda v: -B * (1 - v), lambda v: B * (1 - v), v1s, flip)
            eave = [side_pt(-B + 2 * B * i / nu_s, 0.0, side) for i in range(nu_s + 1)]
            fascia_strip(eave, [p - th for p in eave], not flip)

    # ---- cover-tile rows ----
    tr = sp.pitch * 0.26
    if sp.tile_faces >= 3:
        sec = [(-tr, -0.02), (-tr * 0.62, tr * 0.72), (tr * 0.62, tr * 0.72), (tr, -0.02)]
    else:
        sec = [(-tr, -0.02), (0.0, tr * 0.8), (tr, -0.02)]

    def tile_row(pt_fn, v_end, outward):
        """pt_fn(v) -> surface point; outward: horizontal unit vector pointing down-slope."""
        if v_end < 0.12:
            return
        n = sp.tile_seg
        vs = [v_end * (i / n) * 0.985 for i in range(n + 1)]
        P = [pt_fn(v) for v in vs]
        rings = []
        for i, v in enumerate(vs):
            a = P[max(0, i - 1)]
            b = P[min(n, i + 1)]
            t = (b - a).normalized()                       # up-slope
            side = t.cross(Vector((0, 0, 1)))
            if side.length < 1e-6:
                side = Vector((1, 0, 0))
            side.normalize()
            nrm = side.cross(t).normalized()
            if nrm.z < 0:
                nrm = -nrm
                side = -side
            rings.append([mb.v(P[i] + side * sx + nrm * (sy + 0.015)) for sx, sy in sec])
        m = len(sec)
        for i in range(n):
            for j in range(m - 1):
                mb.face((rings[i][j], rings[i][j + 1], rings[i + 1][j + 1], rings[i + 1][j]), sp.mat,
                        None, True)
        # round tile end at the eave (faces down-slope)
        cap = rings[0][::-1]
        mb.face(cap, sp.ridge_mat, None, False)

    if sp.tiles and vmax > 0.2:
        p = sp.pitch
        nxx = int(A / p)
        for side in (1, -1):
            for k in range(-nxx, nxx + 1):
                x = k * p
                if abs(x) > A - p * 0.35:
                    continue
                if gable or abs(x) <= xg:
                    ve = vmax
                else:
                    ve = min(vmax, (A - abs(x)) / B)
                tile_row(lambda v, xx=x, sd=side: front_pt(xx, v, sd), ve, side)
        if vg > 0 and not gable:
            nyy = int(B / p)
            for side in (1, -1):
                for k in range(-nyy, nyy + 1):
                    y = k * p
                    if abs(y) > B - p * 0.35:
                        continue
                    ve = min(vmax, vg, 1.0 - abs(y) / B)
                    tile_row(lambda v, yy=y, sd=side: side_pt(yy, v, sd), ve, side)

    # ---- ridges ----
    rh = sp.ridge_h if sp.ridge_h is not None else max(0.35, min(1.4, B * 0.085))
    rw = rh * 0.62
    if vmax >= 0.999:
        if xg > 0.05 and sp.style != "pyramid":
            sec_main = [(-rw / 2, -0.25 * rh), (-rw / 2, 0.7 * rh), (-rw * 0.3, rh), (rw * 0.3, rh),
                        (rw / 2, 0.7 * rh), (rw / 2, -0.25 * rh)]
            ext = xg + (sp.overhang * 0.15 if gable else rw * 0.3)
            path = [(-ext + 2 * ext * i / 6, 0.0, H) for i in range(7)]
            sweep(mb, path, sec_main, sp.ridge_mat, caps=True, smooth=False)
            for sx in (-1, 1):
                if sp.ridge_ends == "chiwen":
                    _chiwen(mb, Vector((sx * ext, 0, H)), sx, rh, sp.ridge_mat)
                elif sp.ridge_ends == "curl":
                    pts = [(sx * (ext - 0.05), 0, H + rh * 0.4), (sx * (ext + rh * 0.5), 0, H + rh * 0.9),
                           (sx * (ext + rh * 0.8), 0, H + rh * 1.7)]
                    sweep(mb, pts, [(-rw * 0.4, -rh * 0.4), (-rw * 0.3, rh * 0.3), (rw * 0.3, rh * 0.3),
                                    (rw * 0.4, -rh * 0.4)], sp.ridge_mat,
                          scale_fn=lambda t: 1.0 - 0.55 * t, up=(-sx, 0, 0.3))
        if sp.style == "pyramid" and sp.finial:
            _finial(mb, Vector((0, 0, H)), rh, sp.finial_mat)
    # hip ridges (from v_top down to the corner, with an upturned tip and beasts)
    sec_hip = [(-rw * 0.36, -0.2 * rh), (-rw * 0.36, 0.45 * rh), (0.0, 0.62 * rh),
               (rw * 0.36, 0.45 * rh), (rw * 0.36, -0.2 * rh)]
    if not gable:
        v_top = min(vmax, vg)
        nseg = 8
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts = []
                for j in range(nseg + 1):
                    v = v_top * (1 - j / nseg)
                    x = sx * (A - B * v)
                    p = front_pt(x, v, -sy)
                    pts.append(p)
                tip = pts[-1]
                outd = Vector((sx, sy, 0)).normalized()
                pts.append(tip + outd * rh * 0.7 + Vector((0, 0, rh * 0.75)))
                sweep(mb, pts, sec_hip, sp.ridge_mat, caps=True, smooth=False,
                      scale_fn=lambda t: 1.0 if t < 0.85 else 1.0 - (t - 0.85) * 2.5)
                for b in range(min(sp.beasts, nseg - 2)):
                    q = pts[nseg - 1 - b]
                    mb.lathe([(rh * 0.18, 0), (rh * 0.2, rh * 0.25), (rh * 0.1, rh * 0.5), (0.0, rh * 0.62)],
                             sp.ridge_mat, 5, center=(q.x, q.y, q.z + rh * 0.4), smooth=True)
    # gable (vertical) ridges and gable boards
    if sp.style == "hip_gable" and vmax >= 0.999:
        for sx in (-1, 1):
            for side in (1, -1):
                pts = [front_pt(sx * xg, vg + (1 - vg) * (1 - j / 6), side) for j in range(7)]
                pts = [p + Vector((sx * 0.02, 0, 0)) for p in pts]
                sweep(mb, pts, sec_hip, sp.ridge_mat, caps=True, smooth=False)
            pts = []
            for j in range(nv + 1):
                v = vg + (1 - vg) * j / nv
                pts.append((sx * (xg - 0.05), -B * (1 - v), prof(v) - sp.thick * 0.5))
            for j in range(nv - 1, -1, -1):
                v = vg + (1 - vg) * j / nv
                pts.append((sx * (xg - 0.05), B * (1 - v), prof(v) - sp.thick * 0.5))
            ids = [mb.v(p) for p in pts]
            uvs = [(p[1], p[2]) for p in pts]
            mb.face(ids[::-1] if sx > 0 else ids, sp.gable_mat, uvs[::-1] if sx > 0 else uvs)
    if gable and vmax >= 0.999:
        # barge ridges down both rakes
        for sx in (-1, 1):
            for side in (1, -1):
                pts = [front_pt(sx * (A - 0.05), 1.0 - j / 6, side) for j in range(7)]
                sweep(mb, pts, [(-rw * 0.3, -0.15 * rh), (-rw * 0.3, 0.38 * rh), (rw * 0.3, 0.38 * rh),
                                (rw * 0.3, -0.15 * rh)], sp.ridge_mat, caps=True, smooth=False)
    mb.transform(s0, T(center[0], center[1], center[2], rz + (math.pi / 2 if swap else 0.0)))
    return s0


def _chiwen(mb, base, sx, rh, mat):
    """Ridge-end dragon (chiwen): a tall curled horn turning inwards plus a fin."""
    pts = [base + Vector((sx * -0.1 * rh, 0, 0.3 * rh)), base + Vector((sx * 0.25 * rh, 0, 1.2 * rh)),
           base + Vector((sx * 0.2 * rh, 0, 2.0 * rh)), base + Vector((sx * -0.25 * rh, 0, 2.35 * rh)),
           base + Vector((sx * -0.6 * rh, 0, 2.05 * rh)), base + Vector((sx * -0.55 * rh, 0, 1.65 * rh))]
    sec = [(-0.22 * rh, -0.42 * rh), (-0.24 * rh, 0.0), (-0.16 * rh, 0.36 * rh), (0.16 * rh, 0.36 * rh),
           (0.24 * rh, 0.0), (0.22 * rh, -0.42 * rh)]
    sweep(mb, pts, sec, mat, caps=True, smooth=True, up=(sx, 0, 0.0001),
          scale_fn=lambda t: 1.15 - 0.75 * t)
    # body block
    mb.box((base.x - sx * 0.25 * rh, 0, base.z - 0.1 * rh), (0.7 * rh, 0.5 * rh, 1.0 * rh), mat)


def _finial(mb, top, rh, mat):
    """Gilt finial (baoding) on a pyramid apex."""
    mb.lathe([(rh * 0.75, -0.2 * rh), (rh * 0.8, 0.2 * rh), (rh * 0.45, 0.5 * rh), (rh * 0.55, 0.8 * rh),
              (rh * 0.3, 1.1 * rh), (rh * 0.42, 1.4 * rh), (rh * 0.3, 1.75 * rh), (0.0, 2.2 * rh)],
             mat, 10, center=tuple(top), smooth=True)


def ngon_roof(mb, center, R, H, n=8, v_max=1.0, curve=1.6, lift=0.5, flare=0.3, thick=0.25,
              mat="W_Tile", ridge_mat="W_Ridge", under_mat="W_WoodDark", fascia_mat="W_Fascia",
              finial=None, nv=4, nu=4, ridge_h=None, rot=0.0, finial_mat="W_Gold", tiles=0.0,
              tile_seg=3):
    """Polygonal pyramid roof / skirt eave (pagoda tiers, pavilions): ``R`` = corner radius at
    the eave line, ``n`` sides, corner lift, concave profile.  ``v_max`` < 1 makes a skirt (the
    upper body pierces it).  ``tiles`` > 0 adds cover rows every ``tiles`` m."""
    s0 = mb.n
    corners = [Vector((R * math.cos(rot + TAU * (k + 0.5) / n), R * math.sin(rot + TAU * (k + 0.5) / n), 0.0))
               for k in range(n)]

    def prof(v):
        return H * (v ** curve)

    def pt(k, t, v):
        a, b = corners[k], corners[(k + 1) % n]
        e = a.lerp(b, t)
        p = e * (1.0 - v)
        s = abs(2 * t - 1)
        kk = (1 - v) ** 2
        lz = lift * s ** 3 * kk
        fl = flare * s ** 3 * kk
        rad = Vector((p.x, p.y, 0))
        if rad.length > 1e-6:
            p = p + rad.normalized() * fl
        return Vector((p.x, p.y, prof(v) + lz))

    th = Vector((0, 0, thick))
    edge_len = (corners[0] - corners[1]).length
    for k in range(n):
        ids = [[mb.v(pt(k, i / nu, v_max * j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
        for j in range(nv):
            for i in range(nu):
                v0, v1 = v_max * j / nv, v_max * (j + 1) / nv
                uv = [(edge_len * i / nu, v0 * R), (edge_len * (i + 1) / nu, v0 * R),
                      (edge_len * (i + 1) / nu, v1 * R), (edge_len * i / nu, v1 * R)]
                mb.face((ids[j][i], ids[j][i + 1], ids[j + 1][i + 1], ids[j + 1][i]), mat, uv, True)
        bot = [[mb.v(pt(k, i / nu, v_max * j / 2) - th) for i in range(nu + 1)] for j in range(3)]
        for j in range(2):
            for i in range(nu):
                mb.face((bot[j][i], bot[j + 1][i], bot[j + 1][i + 1], bot[j][i + 1]), under_mat, None, True)
        top = [pt(k, i / nu, 0.0) for i in range(nu + 1)]
        tid = [mb.v(p) for p in top]
        bid = [mb.v(p - th) for p in top]
        for i in range(nu):
            mb.face((tid[i], bid[i], bid[i + 1], tid[i + 1]), fascia_mat,
                    [(edge_len * i / nu, thick), (edge_len * i / nu, 0), (edge_len * (i + 1) / nu, 0),
                     (edge_len * (i + 1) / nu, thick)], False)
        if tiles > 0:
            m = int(edge_len / tiles)
            tr = tiles * 0.26
            for q in range(1, m):
                t = q / m
                pts = [pt(k, t, v_max * 0.985 * j / tile_seg) for j in range(tile_seg + 1)]
                sweep(mb, pts, [(-tr, -0.02), (0.0, tr * 0.8), (tr, -0.02)], mat, caps=False, smooth=True)
    rh = ridge_h if ridge_h is not None else max(0.25, R * 0.07)
    sec = [(-rh * 0.3, -0.2 * rh), (-rh * 0.3, 0.45 * rh), (0, 0.6 * rh), (rh * 0.3, 0.45 * rh), (rh * 0.3, -0.2 * rh)]
    for k in range(n):
        pts = [pt(k, 0.0, v_max * (1 - j / 6)) for j in range(7)]
        tip = pts[-1]
        rad = Vector((tip.x, tip.y, 0)).normalized()
        pts.append(tip + rad * rh * 0.6 + Vector((0, 0, rh * 0.7)))
        sweep(mb, pts, sec, ridge_mat, caps=True, smooth=False,
              scale_fn=lambda t: 1.0 if t < 0.85 else 1.0 - (t - 0.85) * 2.5)
    if finial and v_max >= 0.999:
        _finial(mb, Vector((0, 0, H)), rh * 1.2, finial_mat)
    mb.transform(s0, T(*center))
    return s0


# ---------------------------------------------------------------------------------------------
# hall bodies
# ---------------------------------------------------------------------------------------------
def bracket_set(mb, x, y, z0, nx, ny, k=1.0, mat="W_Bracket"):
    """Dougong cluster at (x, y, z0) projecting outward along (nx, ny) (unit, horizontal):
    bottom block, two stepped arm tiers along the facade, two cantilevers out."""
    s = mb.n
    mb.box((0, 0, 0), (0.42 * k, 0.42 * k, 0.24 * k), mat, skip=("bottom",))
    mb.box((0, 0, 0.24 * k), (1.15 * k, 0.24 * k, 0.2 * k), mat, skip=("bottom",))
    mb.box((0, -0.22 * k, 0.24 * k), (0.24 * k, 0.9 * k, 0.2 * k), mat, skip=("bottom",))
    mb.box((0, 0, 0.44 * k), (1.6 * k, 0.24 * k, 0.2 * k), mat, skip=("bottom",))
    mb.box((0, -0.42 * k, 0.44 * k), (0.24 * k, 1.3 * k, 0.2 * k), mat, skip=("bottom",))
    for sx in (-0.65, 0.0, 0.65):
        mb.box((sx * k, -0.05 * k, 0.64 * k), (0.3 * k, 0.3 * k, 0.16 * k), mat, skip=("bottom",))
    ang = math.atan2(ny, nx) + math.pi / 2       # local -y points along (nx, ny)
    mb.transform(s, T(x, y, z0, ang))


class HallSpec:
    def __init__(self, **kw):
        self.bays = (5, 3)
        self.bay = 4.2
        self.depth_bay = None
        self.col_h = 5.2
        self.col_r = 0.32
        self.plat_h = 1.2
        self.plat_margin = 1.8
        self.plat_mat = "W_Marble"
        self.plat_top = "W_Paving"
        self.steps = True
        self.wall_mat = "W_RedWall"
        self.front = "lattice"         # lattice | wall | open
        self.side = "wall"             # wall | lattice
        self.front_inset = 0.9         # porch depth (front columns stand free)
        self.brackets = True
        self.bracket_k = 1.0
        self.beam_mat = "W_BeamPaint"
        self.roof = RoofSpec()
        self.roof_h = None
        self.double = False
        self.upper_h = 3.0
        self.balustrade = False
        self.bal_mat = "W_Marble"
        self.col_mat = "W_Lacquer"
        self.tiers = 1                 # extra platform tiers (palace terraces)
        for k, v in kw.items():
            if not hasattr(self, k):
                raise AttributeError("HallSpec has no %r" % k)
            setattr(self, k, v)


def _body(mb, W, D, z0, hs, col_h, front, inset, bays, cols=True):
    """Columns, walls, lattice bays, beam band, brackets for a W x D column grid at z0.
    Returns the eave-support height (top of brackets)."""
    nx, ny = bays
    xs = [-W / 2 + W * i / nx for i in range(nx + 1)]
    ys = [-D / 2 + D * j / ny for j in range(ny + 1)]
    r = hs.col_r
    if cols:
        for x in xs:
            for y in (ys[0], ys[-1]):
                column(mb, x, y, z0, col_h, r, hs.col_mat)
        for y in ys[1:-1]:
            for x in (xs[0], xs[-1]):
                column(mb, x, y, z0, col_h, r, hs.col_mat)
    wall_top = z0 + col_h - 0.7
    wt = 0.45
    fy = ys[0] + inset
    # back and side walls (between corner columns)
    box_uv(mb, (xs[0] + r * 0.3, ys[-1] - wt / 2, z0), (W - r * 0.6, wt, wall_top - z0), hs.wall_mat)
    for x in (xs[0], xs[-1]):
        box_uv(mb, (x - wt / 2, fy, z0), (wt, ys[-1] - fy, wall_top - z0), hs.wall_mat)
    # front: lattice bays or wall
    for i in range(nx):
        x0, x1 = xs[i] + r * 0.9, xs[i + 1] - r * 0.9
        if front == "lattice":
            s = mb.n
            mb.box(((x1 - x0) / 2, 0.08, 0), (x1 - x0, 0.16, wall_top - z0), "W_Lattice", skip=("bottom",))
            mb.transform(s, T(x0, fy - 0.08, z0))
            # transom board
        elif front == "wall":
            box_uv(mb, (x0, fy - wt / 2, z0), (x1 - x0, wt, wall_top - z0), hs.wall_mat)
    if inset > 0.2:
        # porch ceiling band (keeps the porch from being a hole) + inner columns line
        box_uv(mb, (xs[0], ys[0], wall_top), (W, inset, 0.12), "W_WoodDark")
    # beam band (architrave) all around, flush with the column line
    bh = 0.62 * hs.bracket_k
    bz = z0 + col_h - bh + 0.05
    for i in range(nx):
        beam(mb, (xs[i], ys[0]), (xs[i + 1], ys[0]), bz, bh, 0.5, hs.beam_mat)
        beam(mb, (xs[i + 1], ys[-1]), (xs[i], ys[-1]), bz, bh, 0.5, hs.beam_mat)
    for j in range(ny):
        beam(mb, (xs[-1], ys[j]), (xs[-1], ys[j + 1]), bz, bh, 0.5, hs.beam_mat)
        beam(mb, (xs[0], ys[j + 1]), (xs[0], ys[j]), bz, bh, 0.5, hs.beam_mat)
    top = z0 + col_h + 0.05
    # flat board over the beams (pingbanfang)
    box_uv(mb, (xs[0] - 0.3, ys[0] - 0.3, top), (W + 0.6, D + 0.6, 0.18), "W_WoodDark", skip=("bottom",))
    top += 0.18
    if hs.brackets:
        k = hs.bracket_k
        for i in range(nx + 1):
            for (y, ny_) in ((ys[0], -1), (ys[-1], 1)):
                bracket_set(mb, xs[i], y, top, 0, ny_, k)
                if i < nx:
                    bracket_set(mb, (xs[i] + xs[i + 1]) / 2, y, top, 0, ny_, k)
        for j in range(1, ny):
            for (x, nx_) in ((xs[0], -1), (xs[-1], 1)):
                bracket_set(mb, x, ys[j], top, nx_, 0, k)
        for j in range(ny):
            for (x, nx_) in ((xs[0], -1), (xs[-1], 1)):
                bracket_set(mb, x, (ys[j] + ys[j + 1]) / 2, top, nx_, 0, k)
        # corner brackets diagonal
        top += 0.8 * k
    else:
        top += 0.1
    # solid core under the roof (hides the space between beams and the soffit)
    box_uv(mb, (xs[0] + 0.3, ys[0] + 0.3, z0 + col_h - 0.8), (W - 0.6, D - 0.6, top - (z0 + col_h - 0.8) + 0.3),
           "W_WoodDark", skip=("bottom",))
    return top


def hall(mb, center=(0, 0, 0), hs=None, rz=0.0, **kw):
    """Timber hall on a stone platform (palace hall, yamen, temple, gate-tower pavilion).
    Returns (start index, info dict with 'top' (ridge z), 'eave', 'plat')."""
    hs = hs or HallSpec()
    for k, v in kw.items():
        setattr(hs, k, v)
    s0 = mb.n
    nx, ny = hs.bays
    W = nx * hs.bay
    D = ny * (hs.depth_bay or hs.bay)
    z = 0.0
    m = hs.plat_margin
    if hs.plat_h > 0:
        for t in range(hs.tiers):
            g = (hs.tiers - 1 - t) * 3.0
            platform(mb, W + 2 * m + 2 * g, D + 2 * m + 2 * g, hs.plat_h, hs.plat_mat, hs.plat_top,
                     z0=z, skirt=1.5 if t == 0 else 0.2)
            if hs.balustrade:
                bw, bd = W + 2 * m + 2 * g - 0.4, D + 2 * m + 2 * g - 0.4
                gap = 6.0 if hs.steps else 0.0
                balustrade_rect(mb, bw, bd, z + hs.plat_h, gap=gap, mat=hs.bal_mat)
            if hs.steps:
                nst = max(3, int(round(hs.plat_h / 0.17)))
                steps(mb, 0, -(D / 2 + m + g) - nst * 0.38 + 0.02, z, min(W * 0.36, 5.0), hs.plat_h,
                      nst, 0.38, hs.plat_mat)
            z += hs.plat_h
    top = _body(mb, W, D, z, hs, hs.col_h, hs.front, hs.front_inset, hs.bays)
    rs = hs.roof
    rh = hs.roof_h if hs.roof_h is not None else D * 0.36
    info = {"plat": z, "eave": top}
    if hs.double:
        # lower skirt eave; the upper storey (inset half a bay) rises through the skirt slope
        lower = RoofSpec(**{k: getattr(rs, k) for k in vars(rs)})
        lower.style = "hip"
        lower.chiwen = False
        dbay = hs.depth_bay or hs.bay
        ix, iy = hs.bay * 0.5, dbay * 0.5
        Wu, Du = W - 2 * ix, D - 2 * iy
        Bl = min(W, D) / 2 + lower.overhang
        lower.v_max = min(0.8, (lower.overhang + max(ix, iy) + 0.35) / Bl)
        rl = rh * 0.85
        roof(mb, (0, 0, top), W, D, rl, lower)
        vw = (lower.overhang + min(ix, iy)) / Bl
        zu = top + rl * (vw ** lower.curve) - 0.35
        ub = (max(1, nx - 1) if nx > 2 else nx, max(1, ny - 1) if ny > 2 else ny)
        top2 = _body(mb, Wu, Du, zu, hs, hs.upper_h + 0.35, "lattice", 0.0, ub, cols=True)
        roof(mb, (0, 0, top2), Wu, Du, rh, rs)
        info["top"] = top2 + rh
    else:
        roof(mb, (0, 0, top), W, D, rh, rs)
        info["top"] = top + rh
    mb.transform(s0, T(center[0], center[1], center[2], rz))
    return s0, info


# ---------------------------------------------------------------------------------------------
# balustrades and railings
# ---------------------------------------------------------------------------------------------
def balustrade(mb, p0, p1, z0, h=1.05, spacing=1.7, mat="W_Marble", post=0.24):
    """Carved marble balustrade along p0 -> p1: posts with cloud caps, solid panels, sill."""
    a, b = Vector((p0[0], p0[1], 0)), Vector((p1[0], p1[1], 0))
    d = b - a
    Ln = d.length
    if Ln < 0.5:
        return
    n = max(1, int(round(Ln / spacing)))
    ang = math.atan2(d.y, d.x)
    s = mb.n
    mb.box((Ln / 2, 0, 0), (Ln, 0.36, 0.14), mat, skip=("bottom",))
    for i in range(n + 1):
        x = Ln * i / n
        mb.box((x, 0, 0.14), (post, post, h - 0.14), mat, skip=("bottom",))
        mb.lathe([(post * 0.62, 0.0), (post * 0.7, 0.12), (post * 0.4, 0.26), (0.0, 0.34)], mat, 6,
                 center=(x, 0, h), smooth=True)
        if i < n:
            x0, x1 = x + post / 2, Ln * (i + 1) / n - post / 2
            mb.box(((x0 + x1) / 2, 0, 0.14), (x1 - x0, 0.12, h * 0.62), mat, skip=("bottom",))
            mb.box(((x0 + x1) / 2, 0, 0.14 + h * 0.62), (x1 - x0, 0.17, 0.12), mat, skip=("bottom",))
    mb.transform(s, T(a.x, a.y, z0, ang))


def balustrade_rect(mb, w, d, z0, gap=0.0, mat="W_Marble", h=1.05):
    hw, hd = w / 2, d / 2
    if gap > 0:
        balustrade(mb, (-hw, -hd), (-gap / 2, -hd), z0, h, mat=mat)
        balustrade(mb, (gap / 2, -hd), (hw, -hd), z0, h, mat=mat)
    else:
        balustrade(mb, (-hw, -hd), (hw, -hd), z0, h, mat=mat)
    balustrade(mb, (hw, -hd), (hw, hd), z0, h, mat=mat)
    balustrade(mb, (hw, hd), (-hw, hd), z0, h, mat=mat)
    balustrade(mb, (-hw, hd), (-hw, -hd), z0, h, mat=mat)


def railing(mb, p0, p1, z0, h=1.0, spacing=1.4, mat="W_Lacquer"):
    """Timber balcony railing: posts, top and mid rails, short balusters."""
    a, b = Vector((p0[0], p0[1], 0)), Vector((p1[0], p1[1], 0))
    d = b - a
    Ln = d.length
    if Ln < 0.3:
        return
    n = max(1, int(round(Ln / spacing)))
    ang = math.atan2(d.y, d.x)
    s = mb.n
    for i in range(n + 1):
        x = Ln * i / n
        mb.box((x, 0, 0), (0.14, 0.14, h + 0.1), mat, skip=("bottom",))
    mb.box((Ln / 2, 0, h - 0.08), (Ln, 0.12, 0.1), mat)
    mb.box((Ln / 2, 0, h * 0.45), (Ln, 0.08, 0.08), mat)
    for i in range(n):
        for q in (0.33, 0.66):
            x = Ln * (i + q) / n
            mb.box((x, 0, h * 0.45), (0.06, 0.06, h * 0.47), mat, skip=("bottom", "top"))
    mb.transform(s, T(a.x, a.y, z0, ang))


def railing_rect(mb, w, d, z0, h=1.0, mat="W_Lacquer"):
    hw, hd = w / 2, d / 2
    for p0, p1 in (((-hw, -hd), (hw, -hd)), ((hw, -hd), (hw, hd)), ((hw, hd), (-hw, hd)), ((-hw, hd), (-hw, -hd))):
        railing(mb, p0, p1, z0, h, mat=mat)


# ---------------------------------------------------------------------------------------------
# walls and gates
# ---------------------------------------------------------------------------------------------
def wall_segment(mb, L, H, T_, batter=0.9, mat="W_Stone", top="W_Paving", par="W_Brick",
                 merlon=(1.5, 1.05, 0.75), crenel=0.65, par_h=0.85, inner_h=0.9, skirt=2.0,
                 drains=False, earth=False):
    """City wall segment along x in [-L/2, L/2], outer face towards -y (battered by
    ``batter`` m over the height), inner face +y (battered by half).  Top: paved walk, outer
    parapet with merlons and loopholes, low inner parapet.  ``earth`` = rammed earth town wall
    (no crenels, a tiled coping on a thin parapet)."""
    s0 = mb.n
    hy = T_ / 2
    z0 = -skirt
    # cross-section (y, z) from outer foot to inner foot
    ob = batter
    ib = batter * 0.5
    prof = [(-hy, z0), (-hy + ob, H), (hy - ib, H), (hy, z0)]
    # outer face, top, inner face as quads along x with metre UVs
    xa, xb = -L / 2, L / 2

    def facequad(p, q, mat_, flip=False):
        ids = [mb.v((xa, p[0], p[1])), mb.v((xb, p[0], p[1])), mb.v((xb, q[0], q[1])), mb.v((xa, q[0], q[1]))]
        lu = math.hypot(q[0] - p[0], q[1] - p[1])
        uv = [(xa, p[1]), (xb, p[1]), (xb, p[1] + lu), (xa, p[1] + lu)]
        if flip:
            ids, uv = ids[::-1], uv[::-1]
        mb.face(ids, mat_, uv)

    facequad(prof[0], prof[1], mat, flip=False)          # outer (faces -y)
    # top walk
    ids = [mb.v((xa, prof[1][0], H)), mb.v((xb, prof[1][0], H)), mb.v((xb, prof[2][0], H)), mb.v((xa, prof[2][0], H))]
    mb.face(ids, top, [(xa, prof[1][0]), (xb, prof[1][0]), (xb, prof[2][0]), (xa, prof[2][0])])
    facequad(prof[3], prof[2], mat, flip=True)           # inner (faces +y)
    # string course at the top of the outer face
    mb.box((0, prof[1][0] - 0.05, H - 0.35), (L, 0.3, 0.3), par if not earth else mat, skip=("bottom",))
    oy = prof[1][0] + 0.32
    if earth:
        mb.box((0, oy, H), (L, 0.5, par_h + 0.3), mat, skip=("bottom",))
        roof(mb, (0, oy, H + par_h + 0.3), L - 0.0, 0.5, 0.35, RoofSpec(
            style="gable", overhang=0.22, lift=0.0, flare=0.0, thick=0.08, pitch=0.45, tile_seg=2,
            tile_faces=2, nv=2, ridge_h=0.14, ridge_ends="plain", mat="W_TileDark",
            fascia_mat="W_WoodDark"))
    else:
        mw, mh, mt = merlon
        mb.box((0, oy, H), (L, mt, par_h), par, skip=("bottom",))
        n = max(1, int(round(L / (mw + crenel))))
        pitch = L / n
        for i in range(n):
            x = -L / 2 + pitch * (i + 0.5)
            s = mb.n
            mb.box((0, 0, 0), (pitch - crenel, mt, mh), par)
            mb.transform(s, T(x, oy, H + par_h))
        mb.box((0, prof[2][0] - 0.25, H), (L, 0.4, inner_h), par, skip=("bottom",))
    if drains:
        for x in (-L * 0.25, L * 0.25):
            mb.box((x, prof[2][0] + 0.15, H - 0.7), (0.3, 0.6, 0.25), "W_Marble", skip=("bottom",))
    return s0


def arch_ring(mb, cx, y, z0, w, h, W, Hh, mat, facing=-1, segs=12, bx=None):
    """Face of a block (width ``W`` centred at ``bx``, height ``Hh`` from ``z0``) at ``y`` with an
    arched opening (width ``w``, crown height ``h``, centred at ``cx``), built as a quad ring:
    the left block edge pairs with the left jamb and the arch up to 135 deg, the top edge with
    the crown (135..45 deg), the right edge with the rest - so the block corners stay exact.
    ``facing`` -1: the face looks to -y.  Returns the opening outline [(x, z), ...]."""
    bx = cx if bx is None else bx
    r = w / 2.0
    spring = h - r
    inner = [(cx - r, z0)]
    for i in range(segs + 1):
        a = math.pi - math.pi * i / segs
        inner.append((cx + r * math.cos(a), z0 + spring + r * math.sin(a)))
    inner.append((cx + r, z0))
    kL = 1 + segs // 4
    kR = 1 + 3 * segs // 4
    hw = W / 2.0
    corners = [(bx - hw, z0), (bx - hw, z0 + Hh), (bx + hw, z0 + Hh), (bx + hw, z0)]

    def spread(i0, i1, pa, pb):
        seg = [0.0]
        for i in range(i0 + 1, i1 + 1):
            seg.append(seg[-1] + math.hypot(inner[i][0] - inner[i - 1][0], inner[i][1] - inner[i - 1][1]))
        tot = max(seg[-1], 1e-9)
        return [(pa[0] + (pb[0] - pa[0]) * t / tot, pa[1] + (pb[1] - pa[1]) * t / tot) for t in seg]

    outer = spread(0, kL, corners[0], corners[1])[:-1] + spread(kL, kR, corners[1], corners[2])[:-1] + \
        spread(kR, len(inner) - 1, corners[2], corners[3])
    iid = [mb.v((p[0], y, p[1])) for p in inner]
    oid = [mb.v((p[0], y, p[1])) for p in outer]
    for i in range(len(inner) - 1):
        q = [oid[i], oid[i + 1], iid[i + 1], iid[i]]
        uv = [outer[i], outer[i + 1], inner[i + 1], inner[i]]
        if facing < 0:
            q, uv = q[::-1], uv[::-1]
        mb.face(q, mat, list(uv))
    return inner


def gate_base(mb, W, D, H, arch_w, arch_h, mat="W_Stone", top="W_Paving", par="W_Brick",
              batter=0.8, skirt=2.0, doors=True, crenels=True, n_arches=1, spacing=None):
    """Gate block (chengtai): battered stone mass with ``n_arches`` real tunnels front to back,
    studded red doors a third of the way in, paved top with crenellated front parapet and a low
    rear parapet.  Front faces -y.  Returns the top z."""
    s0 = mb.n
    hd = D / 2
    spacing = spacing or arch_w * 1.9
    cxs = [(i - (n_arches - 1) / 2) * spacing for i in range(n_arches)]
    # front / back faces: one ring per arch, in vertical strips of width spacing (or W)
    strips = []
    if n_arches == 1:
        strips = [(0.0, W)]
    else:
        edges = [-W / 2] + [(cxs[i] + cxs[i + 1]) / 2 for i in range(n_arches - 1)] + [W / 2]
        strips = [((edges[i] + edges[i + 1]) / 2, edges[i + 1] - edges[i]) for i in range(n_arches)]
    for (bxc, sw), ax in zip(strips, cxs):
        for facing, yy in ((-1, -hd), (1, hd)):
            inner = arch_ring(mb, ax, yy, 0.0, arch_w, arch_h, sw, H, mat, facing=facing, bx=bxc)
            if facing < 0:
                fi = [mb.v((p[0], -hd, p[1])) for p in inner]
                bi = [mb.v((p[0], hd, p[1])) for p in inner]
                acc = 0.0
                for i in range(len(inner) - 1):
                    seg = math.hypot(inner[i + 1][0] - inner[i][0], inner[i + 1][1] - inner[i][1])
                    mb.face((fi[i], bi[i], bi[i + 1], fi[i + 1]), mat,
                            [(acc, -hd), (acc, hd), (acc + seg, hd), (acc + seg, -hd)])
                    acc += seg
                mb.face((fi[0], fi[-1], bi[-1], bi[0]), top,
                        [(inner[0][0], -hd), (inner[-1][0], -hd), (inner[-1][0], hd), (inner[0][0], hd)])
                if doors:
                    yd = -hd + D * 0.3
                    poly = [(ax + (p[0] - ax) * 0.995, yd, p[1]) for p in inner]
                    ids = [mb.v(p) for p in poly]
                    mb.face(ids[::-1], "W_GateDoor", [(p[0] - ax + arch_w / 2, p[2]) for p in poly][::-1])
                    mb.box((ax, yd - 0.04, 0), (0.08, 0.1, arch_h * 0.92), "W_WoodDark", skip=("bottom",))
    # sides (battered) and skirt
    for sx in (-1, 1):
        x = sx * W / 2
        ids = [mb.v((x, -hd, -skirt)), mb.v((x, hd, -skirt)), mb.v((x, hd, H)), mb.v((x, -hd, H))]
        uv = [(-hd, -skirt), (hd, -skirt), (hd, H), (-hd, H)]
        mb.face(ids if sx > 0 else ids[::-1], mat, uv if sx > 0 else uv[::-1])
    for facing, yy in ((-1, -hd), (1, hd)):
        ids = [mb.v((-W / 2, yy, -skirt)), mb.v((W / 2, yy, -skirt)), mb.v((W / 2, yy, 0)), mb.v((-W / 2, yy, 0))]
        uv = [(-W / 2, -skirt), (W / 2, -skirt), (W / 2, 0), (-W / 2, 0)]
        mb.face(ids if facing < 0 else ids[::-1], mat, uv if facing < 0 else uv[::-1])
    # top
    ids = [mb.v((-W / 2, -hd, H)), mb.v((W / 2, -hd, H)), mb.v((W / 2, hd, H)), mb.v((-W / 2, hd, H))]
    mb.face(ids, top, [(-W / 2, -hd), (W / 2, -hd), (W / 2, hd), (-W / 2, hd)])
    # string course + parapets
    mb.box((0, -hd - 0.12, H - 0.35), (W + 0.3, 0.3, 0.35), par, skip=("bottom",))
    if crenels:
        mb.box((0, -hd + 0.3, H), (W, 0.6, 0.85), par, skip=("bottom",))
        n = max(2, int(round(W / 2.15)))
        pitch = W / n
        for i in range(n):
            x = -W / 2 + pitch * (i + 0.5)
            mb.box((x, -hd + 0.3, H + 0.85), (pitch - 0.65, 0.6, 1.0), par)
    mb.box((0, hd - 0.25, H), (W, 0.4, 0.9), par, skip=("bottom",))
    return H


# ---------------------------------------------------------------------------------------------
# towers
# ---------------------------------------------------------------------------------------------
def pagoda(mb, center=(0, 0, 0), tiers=7, R=4.2, base_h=5.5, tier_h=3.2, taper=0.9,
           body_mat="W_Brick", roof_mat="W_TileDark", ridge_mat="W_Ridge", n=8, balcony=True,
           plinth_mat="W_Marble", spire=True, eave_k=1.0, lacquer_frames=True, rz=0.0):
    """Octagonal pagoda: stone plinth, brick body tiers each with a corbelled eave (polygonal
    roof skirt), door / window niches, balcony railings on the lower tiers, gilt spire with
    rings.  ``R`` = body corner radius of the first tier.  Returns top z."""
    s0 = mb.n
    # plinth (octagonal, two steps)
    pr = R * 1.55
    mb.lathe([(pr, -1.5), (pr, 0.6), (pr * 0.94, 0.75), (pr * 0.94, 1.3)], plinth_mat, n,
             smooth=False, cap_top=True)
    z = 1.3
    r = R
    for t in range(tiers):
        h = base_h if t == 0 else tier_h * (1.0 - 0.02 * t)
        # body
        mb.lathe([(r, 0.0), (r * 0.985, h)], body_mat, n, center=(0, 0, z), smooth=False)
        # lacquer frame posts at the corners + door niches (dark) on 4 faces
        for k in range(n):
            a = TAU * (k + 0.5) / n
            cxp, cyp = r * math.cos(a) * 0.985, r * math.sin(a) * 0.985
            if lacquer_frames:
                mb.box((cxp, cyp, z), (0.28, 0.28, h - 0.3), "W_Lacquer", rz=a)
        for k in range(n):
            a = TAU * k / n
            if (k + t) % 2:
                continue
            ap = r * math.cos(math.pi / n)
            dw, dh = r * 0.45, min(h * 0.55, 2.4)
            s = mb.n
            arch_door_flat(mb, dw, dh, "W_Dark")
            mb.transform(s, T(math.cos(a) * (ap + 0.02), math.sin(a) * (ap + 0.02), z + (0.6 if t == 0 else 0.35),
                              a + math.pi / 2))
        z += h
        # corbelled band + eave
        mb.lathe([(r * 0.985, 0.0), (r * 1.08, 0.25), (r * 1.12, 0.45)], "W_Bracket" if lacquer_frames else body_mat, n,
                 center=(0, 0, z), smooth=False)
        er = r * 1.12 + 1.2 * eave_k
        eh = er * 0.42
        vm = 1.0 if t == tiers - 1 else 0.5
        ngon_roof(mb, (0, 0, z + 0.45), er / math.cos(math.pi / n), eh, n=n, v_max=vm, lift=0.55 * eave_k,
                  flare=0.35 * eave_k, thick=0.28, mat=roof_mat, ridge_mat=ridge_mat,
                  finial=None, nv=3, nu=3, rot=0.0)
        z += 0.45 + eh * (vm ** 1.6) - 0.15
        if balcony and t < tiers - 1 and t < 3:
            rr = r * taper * 1.12
            pts = [(rr * math.cos(TAU * (k + 0.5) / n), rr * math.sin(TAU * (k + 0.5) / n)) for k in range(n)]
            for k in range(n):
                railing(mb, pts[k], pts[(k + 1) % n], z, 0.9, spacing=1.6, mat="W_Lacquer")
        r *= taper
    # spire
    if spire:
        sh = R * 2.2
        mb.lathe([(r * 0.75, 0.0), (r * 0.8, 0.5), (r * 0.45, 0.9), (r * 0.5, 1.4), (0.28, 1.6)],
                 "W_Gold", 10, center=(0, 0, z), smooth=True, cap_top=False)
        mb.cylinder((0, 0, z + 1.5), (0, 0, z + sh), 0.18, 0.1, "W_Gold", 8)
        for i in range(6):
            zz = z + 2.0 + i * (sh - 3.2) / 6
            rr = 0.85 - i * 0.08
            mb.lathe([(0.15, -0.08), (rr, -0.04), (rr, 0.04), (0.15, 0.08)], "W_Gold", 12,
                     center=(0, 0, zz), smooth=True)
        mb.sphere((0, 0, z + sh + 0.35), 0.38, "W_Gold", 10, 6)
        z += sh + 0.75
    mb.transform(s0, T(center[0], center[1], center[2], rz))
    return z


def arch_door_flat(mb, w, h, mat, segs=6):
    """Flat arched niche (polygon) in the local xz plane at y = 0, facing -y."""
    r = w / 2
    pts = [(-r, 0.0), (r, 0.0), (r, h - r)]
    for i in range(1, segs):
        a = math.pi * i / segs
        pts.append((r * math.cos(a), h - r + r * math.sin(a)))
    pts.append((-r, h - r))
    ids = [mb.v((p[0], 0.0, p[1])) for p in pts]
    mb.face(ids, mat, [(p[0], p[1]) for p in pts])


# ---------------------------------------------------------------------------------------------
# dwellings
# ---------------------------------------------------------------------------------------------
class HouseSpec:
    def __init__(self, **kw):
        self.w = 9.0
        self.d = 5.6
        self.h = 3.4
        self.base = 0.45
        self.wall = "W_Brick"
        self.upper = "W_Plaster"       # plaster panel above the brick dado
        self.dado = 1.1
        self.front = "lattice"
        self.roof = RoofSpec(style="gable", overhang=0.75, lift=0.2, flare=0.08, thick=0.2,
                             pitch=0.6, tile_seg=3, tile_faces=2, nv=4, ridge_h=0.38,
                             ridge_ends="curl", mat="W_Tile", fascia_mat="W_WoodDark",
                             under_mat="W_WoodDark")
        self.roof_h = None
        self.cols = True
        self.stories = 1
        for k, v in kw.items():
            if not hasattr(self, k):
                raise AttributeError("HouseSpec has no %r" % k)
            setattr(self, k, v)


def house(mb, center=(0, 0, 0), hs=None, rz=0.0, **kw):
    """Courtyard dwelling facing -y: stone sill, brick dado + plaster walls, gable end walls up
    to the roof, timber front with columns and lattice bays, gable roof with tile rows.
    Returns (start, ridge z)."""
    hs = hs or HouseSpec()
    for k, v in kw.items():
        setattr(hs, k, v)
    s0 = mb.n
    w, d, h = hs.w, hs.d, hs.h
    b = hs.base
    mb.box((0, 0, -1.0), (w + 0.5, d + 0.5, 1.0 + b), "W_Stone", top_mat="W_Paving", skip=("bottom",))
    # walls: back + sides full (brick dado + plaster above), front recessed timber bays
    for (cx, cy, sx, sy) in ((0, d / 2 - 0.2, w, 0.4), (-w / 2 + 0.2, 0.0, 0.4, d), (w / 2 - 0.2, 0.0, 0.4, d)):
        box_uv(mb, (cx - sx / 2, cy - sy / 2, b), (sx, sy, hs.dado), hs.wall, skip=("bottom",))
        box_uv(mb, (cx - sx / 2 + 0.02, cy - sy / 2 + 0.02, b + hs.dado), (sx - 0.04, sy - 0.04, h - hs.dado), hs.upper,
               skip=("bottom",))
    fy = -d / 2 + 0.55
    nb = max(2, int(round(w / 3.0)))
    xs = [-w / 2 + 0.4 + (w - 0.8) * i / nb for i in range(nb + 1)]
    for i in range(nb):
        x0, x1 = xs[i] + 0.12, xs[i + 1] - 0.12
        s = mb.n
        mb.box(((x1 - x0) / 2, 0.06, 0), (x1 - x0, 0.12, h - 0.45), "W_Lattice" if (i == nb // 2 or hs.front == "lattice") else hs.wall,
               skip=("bottom",))
        mb.transform(s, T(x0, fy - 0.06, b))
    if hs.cols:
        for x in xs:
            column(mb, x, -d / 2 + 0.15, b, h, 0.16, "W_LacquerDark", seg=6, base=False)
    beam(mb, (-w / 2, -d / 2 + 0.15), (w / 2, -d / 2 + 0.15), b + h - 0.4, 0.4, 0.3, "W_WoodDark", uv_norm=False)
    # roof core (fills between wall top and roof soffit) + gable triangles
    rh = hs.roof_h if hs.roof_h is not None else d * 0.38
    rs = hs.roof
    box_uv(mb, (-w / 2 + 0.05, -d / 2 + 0.05, b + h - 0.05), (w - 0.1, d - 0.1, 0.3), "W_WoodDark", skip=("bottom",))
    for sx in (-1, 1):
        x = sx * (w / 2 - 0.05)
        pts = [(x, -d / 2, b + h), (x, d / 2, b + h)]
        k = 6
        prof = []
        B = d / 2 + rs.overhang
        for j in range(k + 1):
            v = j / k
            yy = B * (1 - v)
            if yy > d / 2:
                continue
            prof.append((yy, b + h + 0.25 + rh * (v ** rs.curve) - rs.thick - 0.05))
        poly = [(x, -d / 2, b + h + 0.25)] + [(x, -yy, z) for (yy, z) in prof] + \
               [(x, yy, z) for (yy, z) in reversed(prof)] + [(x, d / 2, b + h + 0.25)]
        ids = [mb.v(p) for p in poly]
        uvs = [(p[1], p[2]) for p in poly]
        mb.face(ids[::-1] if sx > 0 else ids, hs.upper, uvs[::-1] if sx > 0 else uvs)
    roof(mb, (0, 0, b + h + 0.25), w, d, rh, rs)
    mb.transform(s0, T(center[0], center[1], center[2], rz))
    return s0, b + h + 0.25 + rh


def courtyard_wall(mb, L, h=2.6, t=0.45, mat="W_Brick", cap="W_TileDark", top_mat="W_Plaster"):
    """Compound wall segment along x in [-L/2, L/2] with a small tiled coping."""
    s0 = mb.n
    mb.box((0, 0, -1.0), (L, t, 1.0 + h - 0.6), mat, skip=("bottom",))
    mb.box((0, 0, h - 0.6), (L, t - 0.04, 0.6), top_mat, skip=("bottom",))
    roof(mb, (0, 0, h), L, t, 0.32, RoofSpec(style="gable", overhang=0.22, lift=0.0, flare=0.0,
                                            thick=0.07, pitch=0.5, tile_seg=2, tile_faces=2, nv=2,
                                            ridge_h=0.14, ridge_ends="plain", mat=cap,
                                            fascia_mat="W_WoodDark", under_mat="W_WoodDark"))
    return s0


def gatehouse_small(mb, w=4.2, d=3.0, h=3.2, rz=0.0, center=(0, 0, 0)):
    """Compound gate (menlou): brick piers, red studded door, small gable roof with curled
    ridge ends.  Faces -y."""
    s0 = mb.n
    for sx in (-1, 1):
        box_uv(mb, (sx * (w / 2 - 0.4) - 0.4, -d / 2, -1.0), (0.8, d, h + 1.0), "W_Brick")
    s = mb.n
    mb.box((0, 0, 0), (w - 1.6, 0.14, h - 0.6), "W_GateDoor", skip=("bottom",))
    mb.transform(s, T(0, -0.1, 0))
    box_uv(mb, (-w / 2, -d / 2, h - 0.6), (w, d, 0.6), "W_WoodDark", skip=("bottom",))
    roof(mb, (0, 0, h), w, d, d * 0.42, RoofSpec(style="gable", overhang=0.6, lift=0.15, flare=0.05,
                                                thick=0.16, pitch=0.5, tile_seg=3, tile_faces=2,
                                                nv=3, ridge_h=0.3, ridge_ends="curl", mat="W_TileDark",
                                                fascia_mat="W_Fascia"))
    mb.transform(s0, T(center[0], center[1], center[2], rz))
    return s0


def bridge(mb, L=14.0, W=6.0, rise=2.4, z_bank=0.0, mat="W_Marble", arch_w=6.0, segs=10):
    """Arched marble bridge along y (crossing a canal running along x): humped deck, side
    balustrades, an arch opening in each face.  Deck ends at y = +-L/2 at z_bank."""
    s0 = mb.n
    hw = W / 2

    def deck_z(y):
        t = y / (L / 2)
        return z_bank + rise * (1 - t * t) + 0.6

    ys = [-L / 2 + L * i / segs for i in range(segs + 1)]
    for sx in (-1, 1):
        # side faces with arch: approximate by quads down to the canal bed except under the arch
        ids_top = [mb.v((sx * hw, y, deck_z(y))) for y in ys]
        ids_bot = []
        for y in ys:
            if abs(y) < arch_w / 2:
                a = math.acos(max(-1.0, min(1.0, y / (arch_w / 2))))
                zb = z_bank - 1.5 + (rise + 1.2) * math.sin(a)
            else:
                zb = z_bank - 1.8
            ids_bot.append(mb.v((sx * hw, y, zb)))
        for i in range(segs):
            q = [ids_bot[i], ids_bot[i + 1], ids_top[i + 1], ids_top[i]]
            uv = [(ys[i], 0), (ys[i + 1], 0), (ys[i + 1], 2), (ys[i], 2)]
            if sx < 0:
                q, uv = q[::-1], uv[::-1]
            mb.face(q, mat, uv)
    # deck (steps feel from the bump in the paving texture)
    for i in range(segs):
        y0, y1 = ys[i], ys[i + 1]
        quad(mb, [(-hw, y0, deck_z(y0)), (hw, y0, deck_z(y0)), (hw, y1, deck_z(y1)), (-hw, y1, deck_z(y1))],
             "W_Paving", [(-hw, y0), (hw, y0), (hw, y1), (-hw, y1)])
    # arch soffit
    ids_l, ids_r = [], []
    for i in range(segs + 1):
        a = math.pi * i / segs
        y = (arch_w / 2) * math.cos(a)
        z = z_bank - 1.5 + (rise + 1.2) * math.sin(a)
        ids_l.append(mb.v((-hw, y, z)))
        ids_r.append(mb.v((hw, y, z)))
    for i in range(segs):
        mb.face((ids_l[i], ids_r[i], ids_r[i + 1], ids_l[i + 1]), mat)
    # balustrades following the hump
    for sx in (-1, 1):
        for i in range(segs):
            y0, y1 = ys[i], ys[i + 1]
            s = mb.n
            Ln = math.hypot(y1 - y0, deck_z(y1) - deck_z(y0))
            mb.box((Ln / 2, 0, 0), (Ln, 0.18, 0.75), mat, skip=("bottom",))
            mb.box((0, 0, 0), (0.24, 0.24, 1.05), mat, skip=("bottom",))
            ang = math.atan2(deck_z(y1) - deck_z(y0), y1 - y0)
            mb.transform(s, T(sx * (hw - 0.15), y0, deck_z(y0)) @ Matrix.Rotation(math.pi / 2, 4, "Z")
                         @ Matrix.Rotation(-ang, 4, "Y"))
    return s0


def paifang(mb, w=9.0, h=7.0, center=(0, 0, 0), rz=0.0, mat_col="W_Lacquer", roof_mat="W_TileGreen"):
    """Three-bay memorial gateway with small hip roofs over the bays."""
    s0 = mb.n
    xs = [-w / 2, -w / 6, w / 6, w / 2]
    for x in xs:
        mb.box((x, 0, -0.5), (1.0, 1.4, 1.6), "W_Marble", skip=("bottom",))
        column(mb, x, 0, 1.1, h - 1.1, 0.3, mat_col, base=False)
    for i in range(3):
        hz = h if i == 1 else h - 1.2
        beam(mb, (xs[i], 0), (xs[i + 1], 0), hz - 1.4, 0.9, 0.5, "W_BeamPaint")
        mb.box(((xs[i] + xs[i + 1]) / 2, 0, hz - 0.5), (xs[i + 1] - xs[i] + 0.4, 0.8, 0.5), "W_Bracket")
        roof(mb, ((xs[i] + xs[i + 1]) / 2, 0, hz), xs[i + 1] - xs[i] - 0.4, 1.0, 1.2,
             RoofSpec(style="hip", overhang=0.8, lift=0.35, flare=0.2, thick=0.18, pitch=0.5, tile_seg=3,
                      tile_faces=2, nv=4, ridge_h=0.35, mat=roof_mat, ridge_mat="W_RidgeGreen",
                      chiwen=False, ridge_ends="curl"))
    mb.transform(s0, T(center[0], center[1], center[2], rz))
    return s0

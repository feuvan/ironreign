"""Procedural geometry: a fast ``MeshBuilder`` plus reusable Koei-style builders.

Everything is built into a :class:`MeshBuilder` (plain python lists -> one mesh in one call), so a
whole walled city with hundreds of parts becomes a single object with a few material slots.
Material slots are referenced by *name* while building and resolved to real materials at
:meth:`MeshBuilder.build`.

UVs are written in **metres** (see :mod:`ironart.materials`): boxes get planar box-mapping, roofs
get u along the eave / v up the slope, tubes u around / v along.

Units: 1 unit = 1 m.  A city sprite is ~12 m across, a hex tile 2 m across (r = 1), a portrait
head ~0.24 m tall.  Builders take a ``rng`` (``random.Random``) wherever randomness is involved so
results are deterministic.
"""

import math
import random

import bpy
from mathutils import Matrix, Vector

TAU = math.tau


def _smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


class MeshBuilder:
    """Accumulates vertices/faces/UVs/material indices/smooth flags; ``build()`` makes an object.

    Methods return the vertex index range they created so callers can post-transform pieces
    (``mb.transform(start, matrix)``).
    """

    def __init__(self):
        self.verts = []
        self.faces = []
        self.face_mat = []
        self.face_smooth = []
        self.face_uv = []
        self.mat_names = []
        self.vattr = {}          # name -> {vert_index: value}

    # -- low level ------------------------------------------------------------------------------
    def mat(self, name):
        if name not in self.mat_names:
            self.mat_names.append(name)
        return self.mat_names.index(name)

    @property
    def n(self):
        return len(self.verts)

    def v(self, co):
        self.verts.append(Vector(co))
        return len(self.verts) - 1

    def face(self, idx, mat, uv=None, smooth=False):
        """Add a face (vertex indices CCW seen from outside). ``uv`` list per corner or 'auto'."""
        if len(set(idx)) < 3:
            return
        self.faces.append(tuple(idx))
        self.face_mat.append(self.mat(mat))
        self.face_smooth.append(smooth)
        if uv is None or uv == "auto":
            uv = self._auto_uv(idx)
        self.face_uv.append(tuple(uv))

    def _auto_uv(self, idx):
        pts = [self.verts[i] for i in idx]
        nrm = Vector((0, 0, 0))
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            nrm += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        ax = max(range(3), key=lambda k: abs(nrm[k]))
        if ax == 2:
            return [(p.x, p.y) for p in pts]
        if ax == 1:
            return [(p.x, p.z) for p in pts]
        return [(p.y, p.z) for p in pts]

    def set_attr(self, name, start, end, value):
        d = self.vattr.setdefault(name, {})
        for i in range(start, end):
            d[i] = value

    def transform(self, start, matrix, end=None):
        """Apply a 4x4 matrix to vertices ``start:end`` (default: to the end)."""
        m = Matrix(matrix)
        for i in range(start, end if end is not None else len(self.verts)):
            self.verts[i] = m @ self.verts[i]

    def extend(self, other, matrix=None):
        """Append another builder (optionally transformed)."""
        base = len(self.verts)
        m = Matrix(matrix) if matrix is not None else Matrix.Identity(4)
        self.verts.extend(m @ v for v in other.verts)
        for f, mi, sm, uv in zip(other.faces, other.face_mat, other.face_smooth, other.face_uv):
            self.faces.append(tuple(i + base for i in f))
            self.face_mat.append(self.mat(other.mat_names[mi]))
            self.face_smooth.append(sm)
            self.face_uv.append(uv)
        for k, d in other.vattr.items():
            dd = self.vattr.setdefault(k, {})
            for i, val in d.items():
                dd[i + base] = val

    def build(self, name, materials=None, col=None, auto_smooth_deg=40.0, merge_dist=0.0):
        """Create the mesh object. ``materials``: {slot_name: bpy Material} (missing -> grey)."""
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        me.polygons.foreach_set("material_index", self.face_mat)
        me.polygons.foreach_set("use_smooth", self.face_smooth)
        uvl = me.uv_layers.new(name="UVMap")
        flat = []
        for uv in self.face_uv:
            for c in uv:
                flat.extend(c)
        if len(flat) == len(uvl.data) * 2:
            uvl.data.foreach_set("uv", flat)
        for k, d in self.vattr.items():
            a = me.attributes.new(k, "FLOAT", "POINT")
            vals = [0.0] * len(self.verts)
            for i, val in d.items():
                vals[i] = val
            a.data.foreach_set("value", vals)
        if auto_smooth_deg is not None:
            me.use_auto_smooth = True
            me.auto_smooth_angle = math.radians(auto_smooth_deg)
        me.validate(clean_customdata=False)
        me.update()
        for nm in self.mat_names:
            m = (materials or {}).get(nm)
            if m is None:
                m = bpy.data.materials.get(nm) or bpy.data.materials.new(nm)
            me.materials.append(m)
        obj = bpy.data.objects.new(name, me)
        (col or bpy.context.scene.collection).objects.link(obj)
        if merge_dist > 0:
            import bmesh
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
            bm.to_mesh(me)
            bm.free()
        return obj

    # -- primitives -----------------------------------------------------------------------------
    def quad_strip(self, ring_a, ring_b, mat, closed=True, smooth=True):
        """Quads between two vertex-index rings of equal length (auto UVs)."""
        n = len(ring_a)
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            self.face((ring_a[i], ring_a[j], ring_b[j], ring_b[i]), mat, None, smooth)

    def box(self, center, size, mat, rot_z=0.0, taper=(0.0, 0.0), skip=(), smooth=False,
            top_mat=None):
        """Axis box centred at ``center`` (x, y) with bottom at ``center[2]``.

        size   (sx, sy, sz)
        taper  (tx, ty) inset of the top face on each side (battered walls, plinths)
        skip   faces to omit: any of 'top', 'bottom', '-x', '+x', '-y', '+y'
        """
        sx, sy, sz = size
        hx, hy = sx / 2.0, sy / 2.0
        tx, ty = taper
        s = self.n
        corners = [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0),
                   (-hx + tx, -hy + ty, sz), (hx - tx, -hy + ty, sz), (hx - tx, hy - ty, sz),
                   (-hx + tx, hy - ty, sz)]
        for c in corners:
            self.v(c)
        f = {
            "bottom": (0, 3, 2, 1), "top": (4, 5, 6, 7), "-y": (0, 1, 5, 4), "+x": (1, 2, 6, 5),
            "+y": (2, 3, 7, 6), "-x": (3, 0, 4, 7)}
        mw = Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z, 4, "Z")
        self.transform(s, mw)
        for k, idx in f.items():
            if k in skip:
                continue
            self.face([s + i for i in idx], top_mat if (k == "top" and top_mat) else mat,
                      smooth=smooth)
        return s

    def lathe(self, profile, mat, segments=24, center=(0, 0, 0), smooth=True, cap_top=False,
              cap_bottom=False, scale_xy=(1.0, 1.0), angle_range=(0.0, TAU)):
        """Surface of revolution. ``profile`` = [(radius, z), ...] bottom to top."""
        cx, cy, cz = center
        full = abs(angle_range[1] - angle_range[0] - TAU) < 1e-6
        nseg = segments if full else segments + 1
        rings = []
        uvs = []
        length = 0.0
        prev = None
        for (r, z) in profile:
            if prev is not None:
                length += math.hypot(r - prev[0], z - prev[1])
            prev = (r, z)
            ring = []
            uvr = []
            for i in range(nseg):
                a = angle_range[0] + (angle_range[1] - angle_range[0]) * i / segments
                ring.append(self.v((cx + r * math.cos(a) * scale_xy[0], cy + r * math.sin(a) * scale_xy[1],
                                    cz + z)))
                uvr.append((a * max(r, 0.01), length))
            rings.append(ring)
            uvs.append(uvr)
        for k in range(len(rings) - 1):
            for i in range(nseg if full else nseg - 1):
                j = (i + 1) % nseg
                uj = uvs[k][j][0] if j else (angle_range[1] * max(profile[k][0], 0.01))
                ujb = uvs[k + 1][j][0] if j else (angle_range[1] * max(profile[k + 1][0], 0.01))
                self.face((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]), mat,
                          ((uvs[k][i]), (uj, uvs[k][j][1]), (ujb, uvs[k + 1][j][1]), uvs[k + 1][i]),
                          smooth)
        if cap_bottom and profile[0][0] > 1e-6:
            self.face(list(reversed(rings[0])), mat)
        if cap_top and profile[-1][0] > 1e-6:
            self.face(rings[-1], mat)
        return rings

    def cylinder(self, p0, p1, r0, r1=None, mat="Default", segments=12, caps=True, smooth=True):
        """Cylinder/cone between two world points."""
        r1 = r0 if r1 is None else r1
        a, b = Vector(p0), Vector(p1)
        d = b - a
        L = d.length
        s = self.n
        rings = self.lathe([(r0, 0.0), (r1, L)], mat, segments, smooth=smooth,
                           cap_bottom=caps, cap_top=caps and r1 > 1e-6)
        q = d.normalized().to_track_quat("Z", "Y")
        self.transform(s, Matrix.Translation(a) @ q.to_matrix().to_4x4())
        return s

    def sphere(self, center, radius, mat, segments=16, rings=10, smooth=True, scale=(1, 1, 1),
               displace=None):
        """UV sphere; ``displace(dir_vector) -> radial factor`` for lumpy shapes."""
        prof = []
        for k in range(rings + 1):
            t = math.pi * k / rings
            prof.append((math.sin(t), -math.cos(t)))
        s = self.n
        rr = self.lathe([(max(r, 1e-5) if 0 < k < rings else 0.0, z) for k, (r, z) in enumerate(prof)],
                        mat, segments, smooth=smooth)
        for i in range(s, self.n):
            v = self.verts[i]
            f = displace(v.normalized() if v.length > 0 else v) if displace else 1.0
            self.verts[i] = Vector((center[0] + v.x * radius * scale[0] * f,
                                    center[1] + v.y * radius * scale[1] * f,
                                    center[2] + v.z * radius * scale[2] * f))
        return s

    def grid(self, fn, nu, nv, mat, uv_fn=None, smooth=True, flip=False):
        """Parametric surface ``fn(u, v) -> (x, y, z)`` for u, v in [0, 1]. Returns index grid."""
        idx = [[self.v(fn(i / nu, j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
        for j in range(nv):
            for i in range(nu):
                q = (idx[j][i], idx[j][i + 1], idx[j + 1][i + 1], idx[j + 1][i])
                uv = None
                if uv_fn:
                    uv = [uv_fn(i / nu, j / nv), uv_fn((i + 1) / nu, j / nv),
                          uv_fn((i + 1) / nu, (j + 1) / nv), uv_fn(i / nu, (j + 1) / nv)]
                if flip:
                    q = q[::-1]
                    uv = uv[::-1] if uv else None
                self.face(q, mat, uv, smooth)
        return idx

    def prism(self, pts2d, z0, z1, mat, top_mat=None, cap_bottom=False, smooth=False):
        """Extrude a CCW 2D polygon from z0 to z1 (side walls + top cap)."""
        n = len(pts2d)
        lo = [self.v((x, y, z0)) for x, y in pts2d]
        hi = [self.v((x, y, z1)) for x, y in pts2d]
        for i in range(n):
            j = (i + 1) % n
            self.face((lo[i], lo[j], hi[j], hi[i]), mat, smooth=smooth)
        self.face(hi, top_mat or mat)
        if cap_bottom:
            self.face(lo[::-1], mat)
        return lo, hi

    def tube(self, points, radius, mat, segments=6, caps=True, smooth=True, radius_fn=None):
        """Sweep a circle along a polyline (parallel-transport frames). ``radius_fn(t)`` tapers."""
        pts = [Vector(p) for p in points]
        n = len(pts)
        if n < 2:
            return
        tangents = []
        for i in range(n):
            a = pts[max(0, i - 1)]
            b = pts[min(n - 1, i + 1)]
            tangents.append((b - a).normalized())
        ref = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((1, 0, 0))
        nrm = tangents[0].cross(ref).normalized()
        rings = []
        acc = 0.0
        for i in range(n):
            if i > 0:
                t0, t1 = tangents[i - 1], tangents[i]
                ax = t0.cross(t1)
                if ax.length > 1e-8:
                    ang = t0.angle(t1)
                    nrm = Matrix.Rotation(ang, 3, ax.normalized()) @ nrm
                acc += (pts[i] - pts[i - 1]).length
            bn = tangents[i].cross(nrm).normalized()
            r = radius * (radius_fn(i / (n - 1)) if radius_fn else 1.0)
            ring = []
            for k in range(segments):
                a = TAU * k / segments
                ring.append(self.v(pts[i] + (nrm * math.cos(a) + bn * math.sin(a)) * r))
            rings.append(ring)
        for i in range(n - 1):
            self.quad_strip(rings[i], rings[i + 1], mat, True, smooth)
        if caps:
            self.face(rings[0][::-1], mat)
            self.face(rings[-1], mat)
        return rings


# ---------------------------------------------------------------------------------------------
# Chinese roofs
# ---------------------------------------------------------------------------------------------
def chinese_roof(mb, center, width, depth, height, overhang=0.3, lift=0.25, flare=0.12,
                 style="hip", gable_frac=0.45, thickness=0.06, curve=1.7, res=(16, 8),
                 mat="RoofTile", ridge_mat="RoofRidge", ridge=True, rot_z=0.0, v_max=1.0,
                 ornaments=True, gable_mat="Plaster", finial_mat="Gold"):
    """Chinese roof with concave slopes and upturned eave corners.

    center     (x, y, z) - z is the eave height (bottom of the roof)
    width      footprint along X (walls), depth along Y; ``overhang`` added on every side
    height     ridge height above the eave
    lift       how far the eave corners curl up (m);  ``flare`` pushes the corners outward
    style      'hip' (庑殿), 'hip_gable' (歇山, gable triangle above ``gable_frac`` of the slope),
               'gable' (悬山), 'pyramid' (攒尖; width == depth, ridge collapses to a point)
    curve      slope concavity exponent (1 = straight, 1.7 = Koei curve)
    v_max      < 1 builds only the lower skirt (double-eave towers)
    Returns the vertex start index.
    """
    s0 = mb.n
    A = width / 2.0 + overhang
    B = depth / 2.0 + overhang
    swap = B > A and style != "pyramid"
    if swap:
        A, B = B, A
    if style == "pyramid":
        A = B = max(A, B)
    H = height
    vg = {"hip": 1.0, "pyramid": 1.0, "hip_gable": gable_frac, "gable": 0.0}[style]
    xg = A - B * vg                      # half-length of the ridge
    nu, nv = res
    pexp = 3.0

    def prof(v):
        return H * (v ** curve)

    def lift_at(s, v):
        k = (1.0 - v) ** 2
        return lift * (s ** pexp) * k, flare * (s ** pexp) * k

    def x_edge(v):
        return max(A - B * v, xg) if style != "gable" else A

    vmax = v_max

    def front(u, v, sign):
        v *= vmax
        xe = x_edge(v)
        x = -xe + 2 * xe * u
        y = sign * (-B * (1 - v))
        s = abs(2 * u - 1)
        lz, fl = lift_at(s, v)
        x += math.copysign(fl, x) * (1 if abs(x) > 1e-6 else 0)
        y += sign * -fl
        return (x, y, prof(v) + lz)

    def side(u, v, sign):
        v *= min(vmax, vg)
        x = sign * (A - B * v)
        ye = B * (1 - v)
        y = -ye + 2 * ye * u
        s = abs(2 * u - 1)
        lz, fl = lift_at(s, v)
        x += sign * fl
        y += math.copysign(fl, y) * (1 if abs(y) > 1e-6 else 0)
        return (x, y, prof(v) + lz)

    def build_face(fn, uvfn, flip):
        top = mb.grid(fn, nu, nv, mat, uvfn, smooth=True, flip=flip)
        # fascia + underside: a thin skin offset down
        bot = mb.grid(lambda u, v: tuple(Vector(fn(u, v)) - Vector((0, 0, thickness))), nu, nv,
                      mat, uvfn, smooth=True, flip=not flip)
        row_t, row_b = top[0], bot[0]
        for i in range(nu):
            q = (row_t[i], row_t[i + 1], row_b[i + 1], row_b[i])
            mb.face(q if flip else q[::-1], ridge_mat, smooth=False)

    # front (-y) and back (+y)
    for sign in (1, -1):
        build_face(lambda u, v, s=sign: front(u, v, s),
                   lambda u, v, s=sign: ((-x_edge(v * vmax) + 2 * x_edge(v * vmax) * u), v * vmax * (B + H)),
                   flip=(sign < 0))
    # hip ends
    if vg > 0:
        for sign in (1, -1):
            build_face(lambda u, v, s=sign: side(u, v, s),
                       lambda u, v: ((-1 + 2 * u) * B, v * min(vmax, vg) * (B + H)),
                       flip=(sign < 0))
    # gable triangles (vertical) above the hips
    if style in ("hip_gable", "gable") and vmax >= 1.0:
        for sign in (1, -1):
            pts = []
            steps = nv
            for j in range(steps + 1):
                v = vg + (1 - vg) * j / steps
                pts.append((sign * xg, -B * (1 - v), prof(v)))
            for j in range(steps - 1, -1, -1):
                v = vg + (1 - vg) * j / steps
                pts.append((sign * xg, B * (1 - v), prof(v)))
            ids = [mb.v(p) for p in pts]
            mb.face(ids[::-1] if sign > 0 else ids, gable_mat)
    # ridges
    if ridge and vmax >= 1.0:
        rw = max(0.05, B * 0.09)
        if xg > 0.01:
            mb.box((0, 0, H - rw * 0.3), (2 * xg + rw, rw, rw * 1.6), ridge_mat)
            if ornaments:
                for sign in (1, -1):
                    pts = [(sign * (xg + rw * 0.2), 0, H), (sign * (xg + rw * 0.9), 0, H + rw * 1.5),
                           (sign * (xg + rw * 0.6), 0, H + rw * 3.0)]
                    mb.tube(pts, rw * 0.55, ridge_mat, 5, radius_fn=lambda t: 1.0 - 0.6 * t)
        elif style == "pyramid":
            mb.lathe([(rw * 1.2, H - 0.01), (rw * 1.4, H + rw), (rw * 0.6, H + rw * 2.2),
                      (rw * 0.9, H + rw * 3.0), (0.0, H + rw * 5.0)], finial_mat, 8)
        # hip ridges follow the hip lines up to the gable/ridge
        if vg > 0:
            for sx in (1, -1):
                for sy in (1, -1):
                    pts = []
                    for j in range(nv + 1):
                        v = vg * j / nv
                        x = sx * (A - B * v)
                        y = sy * (-B * (1 - v))
                        lz, fl = lift_at(1.0, v)
                        pts.append((x + sx * fl, y - sy * fl, prof(v) + lz + rw * 0.25))
                    end = Vector(pts[0])
                    pts.insert(0, tuple(end + Vector((sx * rw * 0.6, -sy * rw * 0.6, rw * 1.1))))
                    mb.tube(pts, rw * 0.42, ridge_mat, 5, caps=True)
        if style in ("hip_gable", "gable"):
            # barge ridges along the gable rakes
            for sx in (1, -1):
                for sy in (1, -1):
                    pts = []
                    for j in range(nv + 1):
                        v = vg + (1 - vg) * j / nv
                        pts.append((sx * xg, sy * -B * (1 - v), prof(v) + rw * 0.2))
                    mb.tube(pts, rw * 0.35, ridge_mat, 5)
    m = Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z + (math.pi / 2 if swap else 0.0), 4, "Z")
    mb.transform(s0, m)
    return s0


# ---------------------------------------------------------------------------------------------
# walls, towers, buildings
# ---------------------------------------------------------------------------------------------
def wall_segment(mb, p0, p1, height=1.6, thickness=0.9, mat="Stone", top_mat="StoneDark",
                 batter=0.12, crenels=True, merlon=(0.32, 0.22, 0.3), gap=0.26, outer=-1,
                 parapet=0.12):
    """Battered stone wall from p0 to p1 (ground points) with crenellated outer parapet.

    outer = -1 puts the merlons on the right-hand side of p0->p1 (the outside when walls are
    traced counter-clockwise), +1 on the left.
    """
    a, b = Vector(p0).to_2d(), Vector(p1).to_2d()
    d = b - a
    L = d.length
    ang = math.atan2(d.y, d.x)
    s = mb.n
    mb.box((L / 2, 0, 0), (L, thickness, height), mat, taper=(0.0, batter))
    if crenels:
        mw, mt, mh = merlon
        yo = outer * -(thickness / 2 - batter - mt / 2)
        # continuous low parapet + merlons
        mb.box((L / 2, yo, height), (L, mt, parapet), mat)
        n = max(1, int((L + gap) // (mw + gap)))
        pitch = L / n
        for i in range(n):
            x = pitch * (i + 0.5)
            mb.box((x, yo, height + parapet), (min(mw, pitch * 0.62), mt, mh - parapet), mat)
    mb.transform(s, Matrix.Translation(Vector((a.x, a.y, Vector(p0).z if len(p0) > 2 else 0.0)))
                 @ Matrix.Rotation(ang, 4, "Z"))
    return s


def wall_ring(mb, width, depth, height=1.6, thickness=0.9, gate_gap=2.2, corner_towers=True,
              tower=1.5, tower_roof=True, mat="Stone", **kw):
    """Rectangular city wall centred at the origin; the gate gap is in the front (-y) wall."""
    hx, hy = width / 2, depth / 2
    c = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    # front wall in two halves (gate gap in the middle); others full.  CCW -> outside on right.
    g = gate_gap / 2
    wall_segment(mb, (-hx, -hy), (-g, -hy), height, thickness, mat, **kw)
    wall_segment(mb, (g, -hy), (hx, -hy), height, thickness, mat, **kw)
    wall_segment(mb, (hx, -hy), (hx, hy), height, thickness, mat, **kw)
    wall_segment(mb, (hx, hy), (-hx, hy), height, thickness, mat, **kw)
    wall_segment(mb, (-hx, hy), (-hx, -hy), height, thickness, mat, **kw)
    if corner_towers:
        for (x, y) in c:
            mb.box((x, y, 0), (tower, tower, height + 0.35), mat, taper=(0.1, 0.1))
            if tower_roof:
                mb.box((x, y, height + 0.35), (tower * 0.62, tower * 0.62, 0.55), "Plaster")
                chinese_roof(mb, (x, y, height + 0.9), tower * 0.62, tower * 0.62, 0.45,
                             overhang=0.22, lift=0.12, flare=0.06, style="pyramid", thickness=0.04,
                             res=(8, 5))


def arch_door(mb, center, width, height, mat="DoorDark", facing=-1, segments=10, slope=0.0):
    """Arched doorway panel (flat polygon) at ``center`` (bottom middle) facing -y (``facing=-1``)
    or +y.  ``slope`` = dy/dz to follow a battered (tapered) wall face."""
    cx, cy, cz = center
    r = width / 2
    pts = [(cx - r, cz), (cx + r, cz)]
    for i in range(segments + 1):
        a = math.pi * i / segments
        pts.append((cx + r * math.cos(a), cz + height - r + r * math.sin(a)))
    ids = [mb.v((x, cy - facing * slope * (z - cz), z)) for x, z in pts]
    mb.face(ids if facing < 0 else ids[::-1], mat)


def pavilion(mb, center, width, depth, height, cols=(4, 2), pillar_r=0.07, mat_pillar="PillarRed",
             mat_wall="Plaster", mat_beam="PillarRed", wall_inset=0.18, lattice=True):
    """Timber hall body: red pillars on the perimeter, recessed plaster/lattice walls, beams."""
    cx, cy, cz = center
    hx, hy = width / 2, depth / 2
    nx, ny = cols
    mb.box((cx, cy, cz), (width - 2 * wall_inset, depth - 2 * wall_inset, height), mat_wall)
    xs = [-hx + width * i / (nx - 1) for i in range(nx)] if nx > 1 else [0]
    ys = [-hy + depth * j / (ny - 1) for j in range(ny)] if ny > 1 else [0]
    for x in xs:
        for y in (-hy, hy):
            mb.cylinder((cx + x, cy + y, cz), (cx + x, cy + y, cz + height), pillar_r, mat=mat_pillar,
                        segments=8)
    for y in ys[1:-1]:
        for x in (-hx, hx):
            mb.cylinder((cx + x, cy + y, cz), (cx + x, cy + y, cz + height), pillar_r, mat=mat_pillar,
                        segments=8)
    bh = max(0.06, height * 0.12)
    mb.box((cx, cy, cz + height - bh), (width + pillar_r * 2, depth + pillar_r * 2, bh), mat_beam)
    if lattice:
        # dark window lattices on the front between pillars
        for i in range(len(xs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            w = (x1 - x0) * 0.62
            mb.box((cx + (x0 + x1) / 2, cy - hy + wall_inset - 0.01, cz + height * 0.3),
                   (w, 0.02, height * 0.45), "DoorDark")


def gate_tower(mb, center=(0, 0, 0), width=3.2, depth=1.8, base_h=1.9, hall_h=0.75,
               two_storey=True, mat="Stone", door=True):
    """City gate: battered stone base with an arched tunnel + red-pillared tower hall with a
    double-eave hip-gable roof.  ``center`` is the ground centre (gate faces -y).
    ``door=False`` gives a keep / drum tower on a solid stone podium."""
    cx, cy, cz = center
    mb.box((cx, cy, cz), (width, depth, base_h), mat, taper=(0.12, 0.1))
    if door:
        arch_door(mb, (cx, cy - depth / 2 - 0.004, cz), width * 0.26, base_h * 0.62, "DoorDark",
                  slope=0.1 / base_h)
    # walkway platform
    top = cz + base_h
    mb.box((cx, cy, top), (width - 0.24, depth - 0.2, 0.06), "StoneDark")
    hw, hd = width * 0.72, depth * 0.62
    pavilion(mb, (cx, cy, top + 0.06), hw, hd, hall_h, cols=(4, 2))
    roof_z = top + 0.06 + hall_h
    if two_storey:
        chinese_roof(mb, (cx, cy, roof_z), hw, hd, 0.5, overhang=0.32, lift=0.16, flare=0.1,
                     style="hip", v_max=0.42, thickness=0.05, res=(14, 4))
        up_z = roof_z + 0.18
        pavilion(mb, (cx, cy, up_z), hw * 0.78, hd * 0.78, hall_h * 0.62, cols=(3, 2),
                 lattice=False)
        chinese_roof(mb, (cx, cy, up_z + hall_h * 0.62), hw * 0.78, hd * 0.78, 0.62,
                     overhang=0.34, lift=0.2, flare=0.12, style="hip_gable", thickness=0.05,
                     res=(16, 7))
    else:
        chinese_roof(mb, (cx, cy, roof_z), hw, hd, 0.6, overhang=0.32, lift=0.18, flare=0.1,
                     style="hip_gable", thickness=0.05, res=(16, 7))


def house(mb, center, width=1.2, depth=0.9, height=0.55, roof_h=0.42, rot_z=0.0,
          style="gable", wall="Plaster", roof="RoofTile", lift=0.06):
    """Simple dwelling: plaster box on a timber sill + curved tile roof."""
    s = mb.n
    mb.box((0, 0, 0), (width, depth, 0.08), "Timber")
    mb.box((0, 0, 0.08), (width * 0.96, depth * 0.96, height - 0.08), wall)
    mb.box((0, -depth * 0.48 - 0.005, 0.08), (width * 0.22, 0.01, height * 0.55), "DoorDark")
    chinese_roof(mb, (0, 0, height), width, depth, roof_h, overhang=0.14, lift=lift,
                 flare=lift * 0.5, style=style, thickness=0.035, res=(8, 4), mat=roof,
                 ornaments=False)
    mb.transform(s, Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z, 4, "Z"))
    return s


def hall(mb, center, width=3.0, depth=1.8, height=0.9, roof_h=0.9, rot_z=0.0, platform=0.25):
    """Main hall on a stone platform with a hip-gable roof (palace / yamen)."""
    s = mb.n
    mb.box((0, 0, 0), (width + 0.6, depth + 0.5, platform), "Stone", taper=(0.04, 0.04))
    pavilion(mb, (0, 0, platform), width, depth, height, cols=(5, 3))
    chinese_roof(mb, (0, 0, platform + height), width, depth, roof_h, overhang=0.36, lift=0.2,
                 flare=0.12, style="hip_gable", res=(16, 7))
    mb.transform(s, Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z, 4, "Z"))
    return s


def pagoda(mb, center, tiers=5, base_w=1.4, tier_h=0.55, taper=0.82, octagonal=False):
    """Stacked pagoda: stone plinth, tiers each with body + flared roof, golden finial."""
    cx, cy, cz = center
    mb.box((cx, cy, cz), (base_w * 1.35, base_w * 1.35, 0.18), "Stone")
    z = cz + 0.18
    w = base_w
    for i in range(tiers):
        h = tier_h * (1.0 if i == 0 else 0.62)
        mb.box((cx, cy, z), (w, w, h), "Plaster" if i == 0 else "PillarRed")
        z += h
        chinese_roof(mb, (cx, cy, z), w, w, w * 0.32, overhang=w * 0.28, lift=w * 0.12,
                     flare=w * 0.08, style="pyramid" if i == tiers - 1 else "hip", v_max=1.0 if i == tiers - 1 else 0.55,
                     thickness=0.04, res=(8, 4), ornaments=False)
        z += w * 0.32 * (0.55 ** 1.7) if i < tiers - 1 else w * 0.32
        w *= taper
    mb.cylinder((cx, cy, z), (cx, cy, z + base_w * 0.7), 0.035, mat="Gold", segments=6)
    for k in range(3):
        mb.sphere((cx, cy, z + base_w * (0.18 + 0.15 * k)), 0.07 - 0.012 * k, "Gold", 8, 5)


# ---------------------------------------------------------------------------------------------
# nature
# ---------------------------------------------------------------------------------------------
def _lumpy(rng, amount=0.18, freq=3):
    ph = [rng.uniform(0, TAU) for _ in range(6)]

    def f(d):
        return 1.0 + amount * (math.sin(freq * d.x + ph[0]) * math.sin(freq * d.y + ph[1]) * 0.6
                               + math.sin(freq * 1.7 * d.z + ph[2]) * 0.4
                               + 0.5 * math.sin(freq * 2.3 * (d.x + d.y) + ph[3]) * math.sin(freq * 2.9 * d.z + ph[4]))
    return f


def tree_broadleaf(mb, base, height=1.0, radius=0.42, rng=None, leaf="Foliage", trunk="Trunk",
                   blobs=5, detail=1):
    """Round deciduous tree: trunk + clustered lumpy canopy blobs. ``detail`` 0 = map scale."""
    rng = rng or random.Random(0)
    bx, by, bz = base
    seg, rings = (7, 5) if detail == 0 else (12, 8)
    mb.cylinder((bx, by, bz), (bx, by, bz + height * 0.55), radius * 0.12, radius * 0.07, trunk,
                segments=5 if detail == 0 else 7)
    cz = bz + height - radius
    mb.sphere((bx, by, cz), radius * 0.8, leaf, seg, rings, displace=_lumpy(rng, 0.22))
    for i in range(blobs - 1):
        a = TAU * i / (blobs - 1) + rng.uniform(-0.4, 0.4)
        r = radius * rng.uniform(0.45, 0.62)
        d = radius * rng.uniform(0.38, 0.55)
        mb.sphere((bx + math.cos(a) * d, by + math.sin(a) * d, cz + rng.uniform(-0.25, 0.15) * radius),
                  r, leaf, seg, rings, displace=_lumpy(rng, 0.25))


def tree_pine(mb, base, height=1.2, radius=0.35, rng=None, leaf="FoliageDark", trunk="Trunk",
              tiers=3, detail=1):
    """Conifer: trunk + stacked jagged cones (Chinese pine silhouettes)."""
    rng = rng or random.Random(0)
    bx, by, bz = base
    seg = 7 if detail == 0 else 11
    mb.cylinder((bx, by, bz), (bx, by, bz + height * 0.4), radius * 0.13, radius * 0.08, trunk,
                segments=5)
    for t in range(tiers):
        f = t / max(1, tiers - 1)
        z0 = bz + height * (0.22 + 0.5 * f)
        r = radius * (1.0 - 0.55 * f)
        h = height * (0.5 - 0.12 * f)
        s = mb.n
        ring = []
        for k in range(seg):
            a = TAU * k / seg + rng.uniform(-0.15, 0.15)
            rr = r * rng.uniform(0.78, 1.08)
            ring.append(mb.v((bx + math.cos(a) * rr, by + math.sin(a) * rr, z0 + rng.uniform(-0.04, 0.03) * height)))
        mid = []
        for k in range(seg):
            a = TAU * (k + 0.5) / seg
            rr = r * 0.55
            mid.append(mb.v((bx + math.cos(a) * rr, by + math.sin(a) * rr, z0 + h * 0.35)))
        tip = mb.v((bx + rng.uniform(-0.03, 0.03), by + rng.uniform(-0.03, 0.03), z0 + h))
        bottom = mb.v((bx, by, z0 + h * 0.12))
        for k in range(seg):
            j = (k + 1) % seg
            mb.face((ring[k], ring[j], mid[k]), leaf, smooth=True)
            mb.face((mid[k], ring[j], mid[j]), leaf, smooth=True)
            mb.face((mid[k], mid[j], tip), leaf, smooth=True)
            mb.face((ring[j], ring[k], bottom), leaf, smooth=True)


def bamboo_clump(mb, base, height=1.4, radius=0.3, stems=7, rng=None, stem="Bamboo",
                 leaf="FoliageLight"):
    rng = rng or random.Random(0)
    bx, by, bz = base
    for i in range(stems):
        a = rng.uniform(0, TAU)
        d = rng.uniform(0, radius * 0.6)
        x, y = bx + math.cos(a) * d, by + math.sin(a) * d
        h = height * rng.uniform(0.75, 1.0)
        lean = Vector((rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12), 1.0)).normalized()
        top = Vector((x, y, bz)) + lean * h
        mb.cylinder((x, y, bz), top, 0.025, 0.018, stem, segments=5)
        for k in range(3):
            c = Vector((x, y, bz)) + lean * h * (0.6 + 0.17 * k)
            mb.sphere(c, radius * rng.uniform(0.25, 0.38), leaf, 7, 4, scale=(1.3, 1.3, 0.55),
                      displace=_lumpy(rng, 0.25))


def rock(mb, center, size=0.5, rng=None, mat="Rock", flatten=0.6, detail=1):
    rng = rng or random.Random(0)
    seg, rings = (8, 5) if detail == 0 else (14, 9)
    lump = _lumpy(rng, 0.28, 2.3)
    mb.sphere(center, size, mat, seg, rings, smooth=False, scale=(1.0, rng.uniform(0.7, 1.0), flatten),
              displace=lump)


def scatter(rng, n, region, min_dist=0.0, tries=30):
    """Poisson-ish scatter: ``region()`` -> random (x, y) candidate (or None to reject)."""
    pts = []
    for _ in range(n):
        for _t in range(tries):
            p = region()
            if p is None:
                continue
            if min_dist <= 0 or all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= min_dist ** 2 for q in pts):
                pts.append(p)
                break
    return pts


# ---------------------------------------------------------------------------------------------
# props: banners, hexes, UI frames
# ---------------------------------------------------------------------------------------------
def banner(mb, base, pole_h=2.4, cloth_w=0.9, cloth_h=1.3, wave=0.08, waves=1.5, segments=(12, 10),
           cloth_mat="ClothWhite", pole_mat="DarkWood", finial_mat="Gold", phase=0.0):
    """Army banner: pole + rectangular cloth hanging from a top crossbar, gentle wave.

    Returns the cloth's (x0, z0, x1, z1) rectangle in local metres (for glyph placement).
    """
    bx, by, bz = base
    mb.cylinder((bx, by, bz), (bx, by, bz + pole_h), 0.03, 0.025, pole_mat, segments=8)
    mb.cylinder((bx, by, bz + pole_h), (bx, by, bz + pole_h + 0.12), 0.03, 0.0, finial_mat, segments=8)
    top = bz + pole_h - 0.05
    mb.cylinder((bx - 0.02, by, top), (bx + cloth_w + 0.05, by, top), 0.018, mat=pole_mat, segments=6)

    def fn(u, v):
        x = bx + 0.03 + u * cloth_w
        z = top - 0.02 - v * cloth_h
        y = by + wave * math.sin(TAU * waves * u + phase + v * 1.2) * (0.25 + 0.75 * u) \
            + wave * 0.5 * v * u
        return (x, y, z)

    nu, nv = segments
    mb.grid(fn, nu, nv, cloth_mat, lambda u, v: (u * cloth_w, -v * cloth_h), smooth=True)
    mb.grid(fn, nu, nv, cloth_mat, lambda u, v: (u * cloth_w, -v * cloth_h), smooth=True, flip=True)
    return (bx + 0.03, top - 0.02 - cloth_h, bx + 0.03 + cloth_w, top - 0.02)


def hex_points(r=1.0, flat_top=True):
    """Hexagon corners (CCW). Flat-top: corners at 0, 60, ... degrees (width 2r, height sqrt3 r)."""
    off = 0.0 if flat_top else math.pi / 6
    return [(r * math.cos(off + TAU * i / 6), r * math.sin(off + TAU * i / 6)) for i in range(6)]


def hex_prism(mb, center=(0, 0, 0), r=1.0, height=0.1, mat="Ground", side_mat=None, bevel=0.0):
    """Flat-top hexagonal prism with optional chamfer on the top edge."""
    cx, cy, cz = center
    pts = hex_points(r)
    if bevel > 0:
        inner = hex_points(r - bevel)
        lo = [mb.v((cx + x, cy + y, cz)) for x, y in pts]
        mid = [mb.v((cx + x, cy + y, cz + height - bevel)) for x, y in pts]
        hi = [mb.v((cx + x, cy + y, cz + height)) for x, y in inner]
        mb.quad_strip(lo, mid, side_mat or mat, True, False)
        mb.quad_strip(mid, hi, side_mat or mat, True, False)
        mb.face(hi, mat)
    else:
        mb.prism([(cx + x, cy + y) for x, y in pts], cz, cz + height, side_mat or mat, mat)


def rounded_rect(w, h, r, inset=0.0, corner_segments=6):
    """CCW outline of a rounded rectangle centred at 0, shrunk by ``inset``.

    Always returns 4 * (corner_segments + 1) points so offset rings line up for sweeps.
    """
    hw, hh = w / 2 - inset, h / 2 - inset
    rr = max(0.0, r - inset)
    pts = []
    for k, (cx, cy, a0) in enumerate(((hw - rr, -hh + rr, -math.pi / 2), (hw - rr, hh - rr, 0.0),
                                       (-hw + rr, hh - rr, math.pi / 2), (-hw + rr, -hh + rr, math.pi))):
        for i in range(corner_segments + 1):
            a = a0 + (math.pi / 2) * i / corner_segments
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def profile_sweep(mb, w, h, r, profile, mat, corner_segments=6, z0=0.0, fill_top=False,
                  fill_mat=None, mats=None, smooth=True):
    """Sweep a cross-section around a rounded rectangle (UI frames, bevelled slabs, buttons).

    profile  [(inset_from_outer_edge, z), ...] from the outside in (e.g. a raised gold moulding:
             [(0,0), (0,0.02), (0.01,0.035), (0.03,0.035), (0.04,0.02), (0.04,0)])
    mats     optional per-segment material names (len(profile) - 1)
    fill_top closes the innermost ring with a flat face (slab tops)
    """
    rings = []
    for inset, z in profile:
        pts = rounded_rect(w, h, r, inset, corner_segments)
        rings.append([mb.v((x, y, z0 + z)) for x, y in pts])
    for k in range(len(rings) - 1):
        m = mats[k] if mats else mat
        mb.quad_strip(rings[k], rings[k + 1], m, True, smooth)
    if fill_top:
        mb.face(rings[-1], fill_mat or mat)
    return rings


def ribbon(mb, points, width, mat, z=0.0, width_fn=None):
    """Flat strip along a 2D polyline (rivers, roads). UV u across (m), v along (m)."""
    pts = [Vector((p[0], p[1])) for p in points]
    n = len(pts)
    L = 0.0
    left, right, uvl, uvr = [], [], [], []
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        t = (b - a).normalized()
        nrm = Vector((-t.y, t.x))
        if i > 0:
            L += (pts[i] - pts[i - 1]).length
        w = width * (width_fn(i / (n - 1)) if width_fn else 1.0) / 2
        pl, pr = pts[i] + nrm * w, pts[i] - nrm * w
        left.append(mb.v((pl.x, pl.y, z)))
        right.append(mb.v((pr.x, pr.y, z)))
        uvl.append((-w, L))
        uvr.append((w, L))
    for i in range(n - 1):
        mb.face((right[i], right[i + 1], left[i + 1], left[i]), mat,
                (uvr[i], uvr[i + 1], uvl[i + 1], uvl[i]), True)


# ---------------------------------------------------------------------------------------------
# hair curves
# ---------------------------------------------------------------------------------------------
def hair_curves(name, strands, material=None, root_radius=0.0004, tip_radius=0.00008,
                radii=None, col=None):
    """Build a Blender 4.x ``Curves`` (hair) object from python polylines.

    strands   list of point lists (each >= 2 points, any lengths)
    radii     optional per-strand root radius list (tip = root * tip_radius / root_radius)
    Cycles renders these as real 3D curves with the Principled Hair BSDF - the way to do beards,
    brows, horsehair plumes and fur at high quality.
    """
    import numpy as np
    strands = [s for s in strands if len(s) >= 2]
    c = bpy.data.hair_curves.new(name)
    c.add_curves([len(s) for s in strands])
    pos = np.array([tuple(p) for s in strands for p in s], np.float32)
    c.position_data.foreach_set("vector", pos.reshape(-1))
    rad = []
    for k, s in enumerate(strands):
        r0 = radii[k] if radii is not None else root_radius
        r1 = r0 * tip_radius / root_radius
        n = len(s)
        for i in range(n):
            t = i / (n - 1)
            rad.append(r0 + (r1 - r0) * t ** 0.8)
    ra = c.attributes.get("radius") or c.attributes.new("radius", "FLOAT", "POINT")
    ra.data.foreach_set("value", np.array(rad, np.float32))
    if material is not None:
        c.materials.append(material)
    obj = bpy.data.objects.new(name, c)
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


# ---------------------------------------------------------------------------------------------
# terrain
# ---------------------------------------------------------------------------------------------
def terrain_grid(name, heights, size_x, size_y, z_scale=1.0, mat=None, col=None):
    """Grid mesh from a numpy height array (rows = +y from bottom? NO: row 0 = top = +y).

    ``heights[j, i]``: j = 0 is the *top* (north, +y) row like an image; i = 0 is west.
    Size in metres; the grid is centred at the origin.  UVs map the image exactly (u = i/(W-1)).
    """
    import numpy as np
    H, W = heights.shape
    xs = np.linspace(-size_x / 2, size_x / 2, W, dtype=np.float32)
    ys = np.linspace(size_y / 2, -size_y / 2, H, dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys)
    co = np.stack([gx, gy, heights.astype(np.float32) * z_scale], -1).reshape(-1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(W * H)
    me.vertices.foreach_set("co", co)
    ii, jj = np.meshgrid(np.arange(W - 1), np.arange(H - 1))
    v0 = (jj * W + ii).reshape(-1)
    # CCW seen from above: (j+1,i) -> (j+1,i+1) -> (j,i+1) -> (j,i)   (j+1 is further south)
    quads = np.stack([v0 + W, v0 + W + 1, v0 + 1, v0], -1).reshape(-1).astype(np.int32)
    nq = (W - 1) * (H - 1)
    me.loops.add(nq * 4)
    me.loops.foreach_set("vertex_index", quads)
    me.polygons.add(nq)
    me.polygons.foreach_set("loop_start", np.arange(0, nq * 4, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(nq, 4, dtype=np.int32))
    me.polygons.foreach_set("use_smooth", np.ones(nq, dtype=bool))
    uv = me.uv_layers.new(name="UVMap")
    u = (quads % W) / (W - 1)
    v = 1.0 - (quads // W) / (H - 1)
    uv.data.foreach_set("uv", np.stack([u, v], -1).reshape(-1).astype(np.float32))
    me.update(calc_edges=True)
    me.validate()
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    if mat is not None:
        me.materials.append(mat)
    return obj

"""Build the MakeHuman bust (head, neck, shoulders) + fitted eyes in Blender from an Identity.

Everything here is driven by :class:`identity.Identity`; the topology is always the hm08 base mesh,
so per-vertex zone masks (``zones.py``) and landmarks are computed once on the base mesh and simply
ride along with the morphs.
"""

import math

import bpy
import numpy as np

from . import mh, zones

KEEP_GROUPS = ("body",)


def morph_verts(ident):
    """Deformed base vertices (MH coords) for an identity (macro + sliders + expression)."""
    base = mh.load_base()
    t = mh.macro_targets(ident.gender, ident.age, ident.muscle, ident.weight, ident.race)
    for k, v in ident.sliders.items():
        t += mh.slider_targets(k, v)
    for k, v in ident.expression.items():
        t += mh.expression_targets(k, v)
    v = mh.apply_targets(base.verts, t)
    v = lower_arms(base, v, ident.arm_drop_deg)
    v = shoulder_shape(base, v, ident.shoulder_width, ident.neck_scale)
    return v


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lower_arms(base, v, drop_deg=32.0):
    """Rotate the A-pose arms down about the shoulder joints (MH coords: y up, z forward)."""
    v = v.copy()
    for side in (1, -1):
        jn = "joint-%s-shoulder" % ("l" if side > 0 else "r")
        piv = v[base.group_verts(jn)].mean(0)
        x = v[:, 0] * side
        w = _smoothstep(abs(piv[0]) * 0.55, abs(piv[0]) * 1.05, x)
        w *= (v[:, 1] < piv[1] + 0.9)
        ang = -math.radians(drop_deg) * w * side
        dx = v[:, 0] - piv[0]
        dy = v[:, 1] - piv[1]
        c, s = np.cos(ang), np.sin(ang)
        nx = piv[0] + dx * c - dy * s
        ny = piv[1] + dx * s + dy * c
        m = w > 0
        v[m, 0] = nx[m]
        v[m, 1] = ny[m]
    return v


def shoulder_shape(base, v, width=1.0, neck=1.0):
    """Scale the shoulder girdle in x (keeps the head untouched)."""
    if abs(width - 1.0) < 1e-3 and abs(neck - 1.0) < 1e-3:
        return v
    v = v.copy()
    yn = v[base.group_verts("joint-neck")].mean(0)[1]
    below = _smoothstep(yn + 0.1, yn - 0.6, v[:, 1])
    v[:, 0] *= 1.0 + (width - 1.0) * below
    # neck girth between the jaw and the clavicles
    neckband = _smoothstep(yn + 0.9, yn + 0.3, v[:, 1]) * _smoothstep(yn - 0.7, yn - 0.2, v[:, 1])
    s = 1.0 + (neck - 1.0) * neckband
    v[:, 0] *= s
    v[:, 2] = (v[:, 2] - 0.15) * s + 0.15
    return v


def landmarks(base, v):
    """Named landmark points (Blender coords) from vertex groups and fixed base indices."""
    L = {}
    L["eye_l"] = mh.to_blender(v[base.group_verts("helper-l-eye")].mean(0))
    L["eye_r"] = mh.to_blender(v[base.group_verts("helper-r-eye")].mean(0))
    L["eye_c"] = (L["eye_l"] + L["eye_r"]) / 2
    for k, i in zones.landmark_index().items():
        L[k] = mh.to_blender(v[i])
    body = base.group_verts("body")
    hv = v[body]
    sel = np.abs(hv[:, 0]) < 0.25
    top = hv[sel][np.argmax(hv[sel][:, 1])]
    L["head_top"] = mh.to_blender(top)
    for j in ("joint-neck", "joint-head", "joint-jaw", "joint-l-shoulder", "joint-r-shoulder",
              "joint-l-clavicle", "joint-r-clavicle", "joint-head-2"):
        L[j.replace("joint-", "j_")] = mh.to_blender(v[base.group_verts(j)].mean(0))
    return L


def _mesh_from(name, verts_b, faces, uvs=None, fuv=None, smooth=True):
    """verts_b: Blender coords (N,3); faces: (F,4) with tris repeating the last index."""
    tri = faces[:, 3] == faces[:, 2]
    nloop = np.where(tri, 3, 4)
    loop_start = np.concatenate([[0], np.cumsum(nloop)[:-1]]).astype(np.int32)
    loops = np.concatenate([f[:n] for f, n in zip(faces, nloop)]).astype(np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts_b))
    me.vertices.foreach_set("co", np.asarray(verts_b, np.float32).ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops)
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", loop_start)
    me.polygons.foreach_set("loop_total", nloop.astype(np.int32))
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uidx = np.concatenate([f[:n] for f, n in zip(fuv, nloop)])
        uvl.data.foreach_set("uv", uvs[uidx].astype(np.float32).ravel())
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    return me


def build(ident, col=None, subdiv=2, crop_y=None):
    """Create the bust object + eyes. Returns dict(body, eyes, lm, verts_mh, keep_idx)."""
    base = mh.load_base()
    v = morph_verts(ident)
    body_faces = base.group_faces(*KEEP_GROUPS)
    F = base.faces[body_faces]
    FU = base.fuv[body_faces]
    # crop: keep faces whose vertices are all above crop_y (MH dm) and inside the shoulder box
    yn = v[base.group_verts("joint-neck")].mean(0)[1]
    cy = crop_y if crop_y is not None else yn - 2.3
    fv = v[F]
    keep = (fv[..., 1].min(1) > cy) & (np.abs(fv[..., 0]).max(1) < 2.6)
    F, FU = F[keep], FU[keep]
    used = np.unique(F.ravel())
    remap = -np.ones(len(v), np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    vb = mh.to_blender(v[used])
    me = _mesh_from("Bust", vb, remap[F], base.uvs, FU)
    ob = bpy.data.objects.new("Bust", me)
    (col or bpy.context.scene.collection).objects.link(ob)
    # per-vertex data: rest position (base mesh, Blender coords) and zone masks
    rest = mh.to_blender(base.verts[used])
    a = me.attributes.new("rest", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", rest.astype(np.float32).ravel())
    zm = zones.masks()
    for k, arr in zm.items():
        at = me.attributes.new("z_" + k, "FLOAT", "POINT")
        at.data.foreach_set("value", arr[used].astype(np.float32))
    if subdiv:
        m = ob.modifiers.new("Subdiv", "SUBSURF")
        m.levels = subdiv
        m.render_levels = subdiv
        m.uv_smooth = "PRESERVE_BOUNDARIES"
        m.boundary_smooth = "ALL"
        displace_wrinkles(ob, ident)
    # eyes (high-poly proxy)
    px = mh.load_proxy("eyes/high-poly/high-poly.mhclo")
    ev = mh.to_blender(px.fit(v))
    lm = landmarks(base, v)
    eyes = []
    for side, key in ((1, "eye_l"), (-1, "eye_r")):
        fsel = (ev[px.faces][:, :, 0].mean(1) * side) > 0
        Fe = px.faces[fsel]
        usedv = np.unique(Fe.ravel())
        rm = -np.ones(len(ev), np.int32)
        rm[usedv] = np.arange(len(usedv), dtype=np.int32)
        c = np.asarray(lm[key], np.float32)
        eme = _mesh_from("Eye_" + key[-1], ev[usedv] - c, rm[Fe], px.uvs, px.fuv[fsel])
        # the MH eye has a transparent cornea shell mapped to the corner disc of the texture
        fu = px.uvs[px.fuv[fsel]].mean(1)
        cornea = ((fu[:, 0] - 0.935) ** 2 + (fu[:, 1] - 0.065) ** 2) < 0.08 ** 2
        eme.polygons.foreach_set("material_index", cornea.astype(np.int32))
        eo = bpy.data.objects.new("Eye_" + key[-1], eme)
        eo.location = tuple(c)
        (col or bpy.context.scene.collection).objects.link(eo)
        em = eo.modifiers.new("Subdiv", "SUBSURF")
        em.levels = 1
        em.render_levels = 1
        eyes.append(eo)
    return dict(body=ob, eyes=eyes, lm=lm, verts_mh=v, used=used, base=base)


def displace_wrinkles(ob, ident):
    """Apply the subdivision and displace the dense mesh by the wrinkle height field."""
    from . import wrinkles
    from . import meshutil as MU
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    n = len(me.vertices)
    co = np.zeros(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    rest = np.zeros(n * 3, np.float32)
    me.attributes["rest"].data.foreach_get("vector", rest)
    rest = rest.reshape(-1, 3)
    Z = {}
    for k in ("forehead", "neck"):
        a = np.zeros(n, np.float32)
        me.attributes["z_" + k].data.foreach_get("value", a)
        Z[k] = a
    h = wrinkles.height(rest, Z, age_w=ident.wrinkles, frown=ident.frown, smile=ident.smile,
                        gaunt=ident.gaunt)
    if np.abs(h).max() > 0:
        me.update()
        nr = np.zeros(n * 3, np.float32)
        me.vertices.foreach_get("normal", nr)
        nr = nr.reshape(-1, 3)
        co = co + nr * h[:, None]
        me.vertices.foreach_set("co", co.ravel())
        me.update()
    a = me.attributes.get("wrinkle") or me.attributes.new("wrinkle", "FLOAT", "POINT")
    a.data.foreach_set("value", np.clip(-h / 0.0012, 0, 1).astype(np.float32))
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))


def aim_eyes(eyes, target, amount=0.8, up_bias=0.0):
    """Rotate each eyeball (origin = eye centre) towards ``target`` (blend from straight ahead)."""
    from mathutils import Vector
    fwd = Vector((0, -1, 0))
    for eo in eyes:
        d = (Vector(target) - eo.location).normalized()
        d = fwd.lerp(d, amount).normalized()
        d.z += up_bias
        q = fwd.rotation_difference(d.normalized())
        eo.rotation_mode = "QUATERNION"
        eo.rotation_quaternion = q

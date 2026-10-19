"""Blender side of gongbi_C: scene, emission-wash materials, mesh builders, Freestyle ink,
render passes and the scene export for the 2D stage.

Everything is built in head units (1 Blender unit = crown-to-chin).  Objects are baked into
world space (no parenting): body objects through ``M_body`` (torso yaw), head objects through
``M_head`` (body yaw + head turn about the neck pivot).  The 2D stage gets both matrices and the
ortho camera, so a point on the analytic head (``geo``) projects exactly where Blender drew it.

Passes (EXR, ``ss`` x the portrait size): ``color`` (premultiplied flat washes, film
transparent), ``line`` (Freestyle), ``depth``, AOV ``pc_mask`` (R face skin, G hair, B other
skin) and AOV ``pc_id`` (material id / 100, for 2D masks).
"""

import json
import math
import os
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ironart import scene as _scene
from ironart.scenes_look import load_exr

import palette as PL

#: Freestyle line sets: thickness in 1x px, alpha, taper, calligraphy, noise, edge types
INK = {
    "face": dict(t=0.85, a=0.92, taper=0.35, calli=0.10, noise=0.04, smooth=True,
                 edges=("silhouette", "external_contour"), lmin=1.0, color="#5A3A2A"),
    "skin": dict(t=0.80, a=0.88, taper=0.35, calli=0.10, noise=0.04, smooth=True,
                 edges=("silhouette", "external_contour", "border"), lmin=1.0, color="#5A3A2A"),
    "cloth": dict(t=1.25, a=0.95, taper=0.40, calli=0.45, noise=0.18, smooth=True,
                  edges=("silhouette", "external_contour", "border"), lmin=2.5, color="ink"),
    "band": dict(t=0.80, a=0.92, taper=0.10, calli=0.15, noise=0.04, smooth=True,
                 edges=("silhouette", "border", "external_contour"), lmin=1.5, color="ink"),
    "hard": dict(t=1.00, a=0.95, taper=0.12, calli=0.15, noise=0.05, smooth=True,
                 edges=("silhouette", "border", "crease", "external_contour"), lmin=1.5,
                 color="ink"),
    "hair": dict(t=0.90, a=0.85, taper=0.35, calli=0.25, noise=0.10, smooth=True,
                 edges=("silhouette", "external_contour", "border"), lmin=1.5, color="ink"),
    "fine": dict(t=0.60, a=0.85, taper=0.15, calli=0.0, noise=0.04, smooth=True,
                 edges=("silhouette", "border", "external_contour"), lmin=1.0, color="ink"),
}

AOVS = (("pc_mask", "COLOR"), ("pc_id", "VALUE"))


def _aov_name(node, name):
    if hasattr(node, "aov_name"):
        node.aov_name = name
    else:
        node.name = name


# =============================================================================================
# scene
# =============================================================================================
class Stage:
    def __init__(self, W=384, H=480, ss=3, samples=6, seed=0):
        _scene.reset(seed)
        self.W, self.H, self.ss = W, H, ss
        sc = _scene.setup_cycles(samples=samples, transparent=True, preset="sprite",
                                 view="Standard", look="None", adaptive_threshold=0.0,
                                 seed=seed, filter_width=1.0, clamp_indirect=1.0)
        cy = sc.cycles
        for k in ("max_bounces", "diffuse_bounces", "glossy_bounces", "transmission_bounces",
                  "volume_bounces"):
            setattr(cy, k, 0)
        cy.transparent_max_bounces = 0
        cy.use_light_tree = False
        _scene.set_resolution(W, H, ss)
        vl = sc.view_layers[0]
        vl.use_pass_z = True
        for nm, t in AOVS:
            a = vl.aovs.add()
            a.name = nm
            a.type = t
        wd = bpy.data.worlds.new("PC_World")
        wd.use_nodes = True
        wd.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.0
        sc.world = wd
        self.sc = sc
        self.cols = {}
        for k in list(INK) + ["none"]:
            c = bpy.data.collections.new("PC_" + k)
            sc.collection.children.link(c)
            self.cols[k] = c
        self.M_body = np.eye(4)
        self.M_head = np.eye(4)
        self.ids = {}          # material name -> id
        self.mats = {}
        self.anchors = {}      # named world points for the 2D stage
        self.curves = []       # designed 3D curves (world) for the 2D stage
        self.fit = []          # objects that must stay inside the frame top

    # -------------------------------------------------------------------------------- pose
    def pose(self, body_yaw=0.0, head_yaw=0.0, head_pitch=0.0, head_roll=0.0,
             pivot=(0.0, 0.10, -0.55)):
        """Body yaw (deg, + turns the figure's front towards +X / image right) and the head's
        turn relative to the body about the neck pivot (head units)."""
        Rb = Matrix.Rotation(math.radians(body_yaw), 4, "Z")
        piv = Matrix.Translation(Vector(pivot))
        Rh = (Matrix.Rotation(math.radians(head_yaw), 4, "Z")
              @ Matrix.Rotation(math.radians(head_pitch), 4, "X")
              @ Matrix.Rotation(math.radians(head_roll), 4, "Y"))
        self.M_body = np.array(Rb)
        self.M_head = np.array(Rb @ piv @ Rh @ piv.inverted())

    @staticmethod
    def xf(M, P):
        P = np.asarray(P, np.float64)
        return P @ M[:3, :3].T + M[:3, 3]

    # ------------------------------------------------------------------------------ meshes
    def mesh(self, name, verts, faces, kind, mat, uv=None, smooth=True, M=None):
        """Create a mesh object from local verts (baked through ``M``) into ink kind ``kind``."""
        V = np.asarray(verts, np.float64).reshape(-1, 3)
        if M is not None:
            V = self.xf(M, V)
        me = bpy.data.meshes.new(name)
        me.from_pydata(V.tolist(), [], [list(map(int, f)) for f in faces])
        if uv is not None:
            uvl = me.uv_layers.new(name="UVMap")
            loops = np.array([li for f in faces for li in f], np.int64)
            UV = np.asarray(uv, np.float64).reshape(-1, 2)
            uvl.data.foreach_set("uv", UV[loops].ravel())
        me.validate(clean_customdata=False)
        me.update()
        if mat is not None:
            me.materials.append(mat)
        if smooth:
            me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        ob = bpy.data.objects.new(name, me)
        self.cols[kind].objects.link(ob)
        return ob

    def grid_mesh(self, name, G, kind, mat, closed=True, cap_top=False, cap_bot=False,
                  uv=None, M=None, smooth=True):
        """Quad mesh from a (rows, cols, 3) grid; ``closed`` wraps the columns."""
        G = np.asarray(G, np.float64)
        R, C = G.shape[:2]
        V = G.reshape(-1, 3)
        faces = []
        cc = C if closed else C - 1
        for i in range(R - 1):
            for j in range(cc):
                j2 = (j + 1) % C
                faces.append((i * C + j, i * C + j2, (i + 1) * C + j2, (i + 1) * C + j))
        extra = []
        if cap_top:
            extra.append(G[-1].mean(0))
            ci = len(V) + len(extra) - 1
            for j in range(C if closed else C - 1):
                faces.append(((R - 1) * C + j, (R - 1) * C + (j + 1) % C, ci))
        if cap_bot:
            extra.append(G[0].mean(0))
            ci = len(V) + len(extra) - 1
            for j in range(C if closed else C - 1):
                faces.append(((j + 1) % C, j, ci))
        if extra:
            V = np.concatenate([V, np.array(extra)], 0)
        UV = None
        if uv is not None:
            UV = np.asarray(uv, np.float64).reshape(-1, 2)
            if extra:
                UV = np.concatenate([UV, np.zeros((len(extra), 2))], 0)
        return self.mesh(name, V, faces, kind, mat, uv=UV, smooth=smooth, M=M)

    def strip(self, name, A, Bp, kind, mat, M=None, uv_len=True):
        """Ribbon between two polylines A and B (n, 3)."""
        A = np.asarray(A, np.float64)
        Bp = np.asarray(Bp, np.float64)
        G = np.stack([A, Bp], 0)
        n = len(A)
        uv = None
        if uv_len:
            s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(A, axis=0), axis=1))])
            uv = np.stack([np.stack([s, np.zeros(n)], -1), np.stack([s, np.ones(n)], -1)], 0)
        return self.grid_mesh(name, G, kind, mat, closed=False, uv=uv, M=M)

    def tube(self, name, P, radius, kind, mat, n=10, M=None, closed=False):
        """Tube along polyline P with per-point radius."""
        P = np.asarray(P, np.float64)
        r = np.broadcast_to(np.asarray(radius, np.float64), (len(P),))
        T = np.gradient(P, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        up = np.array([0.0, 0.0, 1.0])
        rings = []
        for k in range(len(P)):
            a = np.cross(T[k], up)
            if np.linalg.norm(a) < 1e-4:
                a = np.cross(T[k], np.array([1.0, 0, 0]))
            a /= np.linalg.norm(a)
            b = np.cross(T[k], a)
            t = np.linspace(0, 2 * math.pi, n, endpoint=False)
            rings.append(P[k] + r[k] * (np.cos(t)[:, None] * a + np.sin(t)[:, None] * b))
        return self.grid_mesh(name, np.array(rings), kind, mat, closed=True,
                              cap_top=True, cap_bot=True, M=M)

    def ellipsoid(self, name, c, r, kind, mat, M=None, n=(24, 32), rot=None):
        c = np.asarray(c, np.float64)
        r = np.asarray(r, np.float64)
        th = np.linspace(-math.pi / 2, math.pi / 2, n[0])[1:-1]
        ph = np.linspace(0, 2 * math.pi, n[1], endpoint=False)
        G = np.stack([np.cos(th)[:, None] * np.sin(ph)[None], -np.cos(th)[:, None] * np.cos(ph)[None],
                      np.sin(th)[:, None] * np.ones_like(ph)[None]], -1) * r
        if rot is not None:
            G = G @ np.asarray(rot).T
        G = G + c
        return self.grid_mesh(name, G, kind, mat, closed=True, cap_top=True, cap_bot=True, M=M)

    # --------------------------------------------------------------------------- materials
    def mat(self, name, light, deep=None, power=1.6, blend=0.45, lo=0.0, hi=1.0, mask=(0, 0, 0),
            pattern=None, light_dir=None, form=0.0):
        """Emission wash: ``light`` facing the viewer deepening to ``deep`` towards the contour
        (分染 / 晕染).  ``pattern`` = callable(nt, color_socket) -> color_socket."""
        if name in self.mats:
            return self.mats[name]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = blend
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = lo
        mr.inputs["From Max"].default_value = hi
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = power
        nt.links.new(lw.outputs["Facing"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], pw.inputs[0])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = PL.lin4(light)
        mix.inputs["B"].default_value = PL.lin4(deep if deep is not None else PL.deepen(light, 0.7))
        nt.links.new(pw.outputs[0], mix.inputs["Factor"])
        col = mix.outputs["Result"]
        if form > 0 and light_dir is not None:
            # gentle painter's light (no cast shadows): colour *= 1 - form * (1 - N.L) / 2
            geo_n = nt.nodes.new("ShaderNodeNewGeometry")
            dp = nt.nodes.new("ShaderNodeVectorMath")
            dp.operation = "DOT_PRODUCT"
            dp.inputs[1].default_value = Vector(light_dir).normalized()
            nt.links.new(geo_n.outputs["Normal"], dp.inputs[0])
            mp = nt.nodes.new("ShaderNodeMapRange")
            mp.inputs["From Min"].default_value = -1.0
            mp.inputs["From Max"].default_value = 1.0
            mp.inputs["To Min"].default_value = 1.0 - form
            mp.inputs["To Max"].default_value = 1.0
            nt.links.new(dp.outputs["Value"], mp.inputs["Value"])
            mm = nt.nodes.new("ShaderNodeMix")
            mm.data_type = "RGBA"
            mm.blend_type = "MULTIPLY"
            mm.inputs["Factor"].default_value = 1.0
            nt.links.new(col, mm.inputs["A"])
            nt.links.new(mp.outputs["Result"], mm.inputs["B"])
            col = mm.outputs["Result"]
        if pattern is not None:
            col = pattern(nt, col)
        nt.links.new(col, em.inputs["Color"])
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        # AOVs
        a1 = nt.nodes.new("ShaderNodeOutputAOV")
        _aov_name(a1, "pc_mask")
        a1.inputs["Color"].default_value = (mask[0], mask[1], mask[2], 1.0)
        a2 = nt.nodes.new("ShaderNodeOutputAOV")
        _aov_name(a2, "pc_id")
        mid = len(self.ids) + 1
        self.ids[name] = mid
        a2.inputs["Value"].default_value = mid / 100.0
        self.mats[name] = m
        return m

    # ------------------------------------------------------------------------------ camera
    def camera(self, yaw=0.0, pitch=-3.0, eye_frac=0.38, head_frac=0.48, x_frac=0.5,
               head_objs=(), top_margin_px=5, min_head=0.80):
        """Ortho camera on -Y looking at the figure, orbited by ``yaw`` (deg, + moves the camera
        towards +X).  Eye line at ``eye_frac`` from the top, crown-to-chin = ``head_frac`` of
        the frame height; shrinks (down to ``min_head`` x) to keep ``self.fit`` in frame."""
        sc = self.sc
        cd = bpy.data.cameras.new("PC_Cam")
        cd.type = "ORTHO"
        cd.sensor_fit = "VERTICAL"
        cam = bpy.data.objects.new("PC_Cam", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        y, p = math.radians(yaw), math.radians(pitch)
        d = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
        look = -d
        cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        R = np.array(cam.rotation_euler.to_matrix())
        right, up = R[:, 0], R[:, 1]
        eye = self.xf(self.M_head, [0, -0.3, 0.0])
        # horizontal centre: middle of the head's projected extent
        hv = []
        for o in head_objs:
            hv.append(self.obj_verts(o))
        hv = np.concatenate(hv, 0) if hv else eye[None]
        hx = hv @ right
        hcx = 0.5 * (hx.min() + hx.max())
        scale0 = 1.0 / head_frac

        def place(scale):
            cd.ortho_scale = scale
            dy = (0.5 - eye_frac) * scale
            dx = (x_frac - 0.5) * scale * self.W / self.H
            c = eye + right * (hcx - eye @ right - dx) - up * dy
            cam.location = Vector(c - np.array(look) * 20.0)
            cd.clip_start = 1.0
            cd.clip_end = 40.0
            bpy.context.view_layer.update()
        scale = scale0
        place(scale)
        if self.fit:
            for _ in range(4):
                top = self.top_px(self.fit)
                if top is None or top >= top_margin_px * self.ss:
                    break
                eye_y = eye_frac * self.H * self.ss
                need = (eye_y - top_margin_px * self.ss) / (eye_y - top)
                scale = min(scale / need, scale0 / min_head)
                place(scale)
                if scale >= scale0 / min_head - 1e-9:
                    break
        self.cam = cam
        self.look = np.array(look)
        return cam

    def obj_verts(self, o):
        dg = bpy.context.evaluated_depsgraph_get()
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        Mw = np.array(o.matrix_world)
        return self.xf(Mw, co.reshape(-1, 3))

    def matrices(self):
        cam = self.sc.camera
        V = np.array(cam.matrix_world.inverted())
        return V, float(cam.data.ortho_scale)

    def project(self, Pw):
        V, scale = self.matrices()
        c = self.xf(V, Pw)
        Wr, Hr = self.W * self.ss, self.H * self.ss
        sx = scale * self.W / self.H
        return np.stack([(c[..., 0] / sx + 0.5) * Wr, (0.5 - c[..., 1] / scale) * Hr, -c[..., 2]], -1)

    def top_px(self, objs):
        best = None
        for o in objs:
            if isinstance(o, np.ndarray):
                y = self.project(o)[:, 1].min()
            else:
                y = self.project(self.obj_verts(o))[:, 1].min()
            best = y if best is None else min(best, y)
        return best

    # --------------------------------------------------------------------------------- ink
    def ink(self, scale=1.0, overrides=None):
        from ironart import ink as _ink
        from ironart import scenes_gongbi as GB
        _ink._patch_freestyle()
        sc = self.sc
        sc.render.use_freestyle = True
        sc.render.line_thickness_mode = "ABSOLUTE"
        sc.render.line_thickness = 1.0
        vl = sc.view_layers[0]
        vl.use_freestyle = True
        fs = vl.freestyle_settings
        fs.mode = "EDITOR"
        fs.as_render_pass = True
        fs.crease_angle = math.radians(120.0)
        fs.use_culling = True
        fs.use_smoothness = True
        while len(fs.linesets) > 0:
            fs.linesets.remove(fs.linesets[0])
        for kind, spec in INK.items():
            if not self.cols[kind].all_objects:
                continue
            spec = dict(spec, **((overrides or {}).get(kind, {})))
            spec.setdefault("dist", (0.0, 100.0, 1.0, 1.0))
            spec.setdefault("wobble", 0.0)
            spec["color"] = PL.hexof(spec["color"])
            st = GB._linestyle("PC_Ink_" + kind, spec, self.ss, scale, 7 + len(fs.linesets) * 13)
            ls = fs.linesets.new("PC_" + kind)
            ls.linestyle = st
            ls.select_by_visibility = True
            ls.visibility = "VISIBLE"
            ls.select_by_edge_types = True
            e = spec["edges"]
            ls.select_silhouette = "silhouette" in e
            ls.select_border = "border" in e
            ls.select_crease = "crease" in e
            ls.select_contour = "contour" in e
            ls.select_external_contour = "external_contour" in e
            ls.select_material_boundary = "material_boundary" in e
            ls.select_suggestive_contour = False
            ls.select_ridge_valley = False
            ls.select_by_collection = True
            ls.collection = self.cols[kind]
            ls.collection_negation = "INCLUSIVE"

    # ------------------------------------------------------------------------------ render
    def render(self, out_dir):
        sc = self.sc
        os.makedirs(out_dir, exist_ok=True)
        for f in os.listdir(out_dir):
            if f.endswith(".exr"):
                os.remove(os.path.join(out_dir, f))
        sc.use_nodes = True
        sc.render.use_compositing = True
        nt = sc.node_tree
        nt.nodes.clear()
        rl = nt.nodes.new("CompositorNodeRLayers")
        comp = nt.nodes.new("CompositorNodeComposite")
        comp.use_alpha = True
        nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
        fo = nt.nodes.new("CompositorNodeOutputFile")
        fo.base_path = out_dir
        fo.format.file_format = "OPEN_EXR"
        fo.format.color_depth = "32"
        fo.format.exr_codec = "ZIP"
        fo.format.color_mode = "RGBA"
        fo.file_slots.clear()
        names = [("color", "Image"), ("depth", "Depth"), ("line", "Freestyle"),
                 ("mask", "pc_mask"), ("id", "pc_id")]
        for fname, sock in names:
            if sock not in rl.outputs:
                continue
            fo.file_slots.new(fname)
            nt.links.new(rl.outputs[sock], fo.inputs[fname])
        sc.render.filepath = os.path.join(out_dir, "beauty.png")
        t0 = time.time()
        bpy.ops.render.render(write_still=False)
        secs = time.time() - t0
        ps = {}
        for f in sorted(os.listdir(out_dir)):
            if f.endswith(".exr"):
                key = f[:-8] if f[-8:-4].isdigit() else f[:-4]
                ps[key] = load_exr(os.path.join(out_dir, f))
                os.remove(os.path.join(out_dir, f))
        return ps, secs

    def export(self, out_dir, ps, extra=None):
        V, scale = self.matrices()
        meta = dict(W=self.W, H=self.H, ss=self.ss, view=V.tolist(), ortho=scale,
                    M_body=self.M_body.tolist(), M_head=self.M_head.tolist(),
                    look=self.look.tolist(), ids=self.ids, anchors=self.anchors,
                    curves=self.curves)
        if extra:
            meta.update(extra)
        z = np.zeros(ps["color"].shape[:2], np.float32)
        np.savez_compressed(os.path.join(out_dir, "scene.npz"),
                            color=ps["color"].astype(np.float32),
                            line=ps["line"].astype(np.float32) if "line" in ps else
                            np.zeros_like(ps["color"]),
                            depth=ps["depth"][..., 0].astype(np.float32) if "depth" in ps else z,
                            mask=ps["mask"][..., :3].astype(np.float32),
                            id=ps["id"][..., 0].astype(np.float32))
        with open(os.path.join(out_dir, "scene.json"), "w") as f:
            json.dump(meta, f)
        return meta

    def add_curve(self, name, style, P_world, **kw):
        d = dict(name=name, style=style, pts=np.asarray(P_world, np.float64).tolist())
        d.update(kw)
        self.curves.append(d)

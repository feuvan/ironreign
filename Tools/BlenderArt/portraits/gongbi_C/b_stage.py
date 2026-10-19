"""Scene, camera, Freestyle ink and pass export for the gongbi_C bust (Blender side).

The 3D stage renders, at ``ss`` x the portrait size:

* ``color``  premultiplied emission washes (film transparent: alpha = painted coverage)
* ``line``   Freestyle ink (one line set per collection kind, :data:`INK`)
* ``depth``  view depth (to depth-test the 2D strokes drawn on 3D curves)
* ``region`` / ``mask`` AOVs (see :mod:`b_mats`)

and exports everything the 2D stage needs into ``scene.npz`` + ``scene.json``: the camera
matrices, the head pose, the head height grid (the face surface in face space, so the 2D face
strokes wrap round the real 3D head), a drape grid (front-most surface, for beards) and every
designed 3D curve (folds, ear detail, plume and tassel strands).
"""

import json
import math
import os
import time

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ironart import scene as _scene
from ironart import scenes_gongbi as GB
from ironart.scenes_look import load_exr

#: Freestyle per collection kind; thickness in FINAL (1x) px, colour token of looks.PAL or hex
INK = {
    "face": dict(t=0.80, a=0.92, taper=0.40, calli=0.15, noise=0.06, wobble=0.0, smooth=True,
                 edges=("silhouette", "external_contour"), lmin=1.5, color="#4A3024"),
    "robe": dict(t=1.30, a=0.95, taper=0.42, calli=0.45, noise=0.22, wobble=0.0, smooth=True,
                 edges=("silhouette", "external_contour"), lmin=3.0, color="#1E1A16"),
    "band": dict(t=0.80, a=0.90, taper=0.12, calli=0.15, noise=0.05, wobble=0.0, smooth=True,
                 edges=("silhouette", "border", "external_contour"), lmin=2.0, color="#1E1A16"),
    "armour": dict(t=1.00, a=0.95, taper=0.12, calli=0.15, noise=0.06, wobble=0.0, smooth=True,
                   edges=("silhouette", "border", "crease", "external_contour"), lmin=2.0,
                   color="#1E1A16"),
    "hair": dict(t=0.85, a=0.80, taper=0.35, calli=0.25, noise=0.10, wobble=0.0, smooth=True,
                 edges=("silhouette", "external_contour"), lmin=2.0, color="#1E1A16"),
    "gear": dict(t=0.95, a=0.95, taper=0.18, calli=0.20, noise=0.06, wobble=0.0, smooth=True,
                 edges=("silhouette", "border", "crease", "external_contour"), lmin=1.5,
                 color="#1E1A16"),
    "fine": dict(t=0.60, a=0.85, taper=0.15, calli=0.0, noise=0.05, wobble=0.0, smooth=True,
                 edges=("silhouette", "border", "external_contour"), lmin=1.0, color="#1E1A16"),
}

AOVS = (("pc_region", "VALUE"), ("pc_mask", "COLOR"))


class Stage:
    """Collections, curves and anchors collected while building a bust."""

    def __init__(self, W=384, H=480, ss=3, samples=8, seed=0):
        _scene.reset(seed)
        self.W, self.H, self.ss = W, H, ss
        sc = _scene.setup_cycles(samples=samples, transparent=True, preset="sprite",
                                 view="Standard", look="None", adaptive_threshold=0.05,
                                 seed=seed, filter_width=1.2, clamp_indirect=1.0)
        cy = sc.cycles
        for k in ("max_bounces", "diffuse_bounces", "glossy_bounces", "transmission_bounces",
                  "volume_bounces"):
            setattr(cy, k, 0)
        cy.transparent_max_bounces = 2
        cy.use_light_tree = False
        cy.adaptive_min_samples = 4
        _scene.set_resolution(W, H, ss)
        vl = sc.view_layers[0]
        vl.use_pass_z = True
        for nm, t in AOVS:
            a = vl.aovs.add()
            a.name = nm
            a.type = t
        wd = bpy.data.worlds.new("PC_World")
        wd.use_nodes = True
        bg = wd.node_tree.nodes.get("Background")
        bg.inputs["Strength"].default_value = 0.0
        sc.world = wd
        self.sc = sc
        self.cols = {}
        for k in list(INK) + ["none"]:
            c = bpy.data.collections.new("PC_" + k)
            sc.collection.children.link(c)
            self.cols[k] = c
        self.curves = []          # dicts: name, style, pts (world), test (depth test)
        self.anchors = {}
        self.rig = bpy.data.objects.new("HeadRig", None)
        sc.collection.objects.link(self.rig)
        self.head = None
        self.H3 = None

    # -----------------------------------------------------------------------------------------
    def col(self, kind):
        return self.cols[kind]

    def head_matrix(self):
        bpy.context.view_layer.update()
        return np.array(self.rig.matrix_world)

    def to_world_head(self, pts):
        """Head-local points -> world (through the rig pose)."""
        Mh = self.head_matrix()
        P = np.asarray(pts, np.float64)
        return P @ Mh[:3, :3].T + Mh[:3, 3]

    def add_curve(self, name, style, pts, head_local=False, test=True, **kw):
        P = np.asarray(pts, np.float64)
        if head_local:
            P = self.to_world_head(P)
        d = dict(name=name, style=style, pts=P.tolist(), test=bool(test))
        d.update(kw)
        self.curves.append(d)

    def pose_head(self, yaw=0.0, pitch=0.0, roll=0.0, pivot=(0.0, 0.012, -0.10), drop=0.0):
        """Turn the head about the top of the neck (degrees; yaw + turns the face to +X).
        ``drop`` lowers a smaller head so its jaw still meets the neck."""
        piv = Vector(pivot)
        R = (Matrix.Rotation(math.radians(yaw), 4, "Z") @ Matrix.Rotation(math.radians(pitch), 4, "X")
             @ Matrix.Rotation(math.radians(roll), 4, "Y"))
        self.rig.matrix_world = (Matrix.Translation((0, 0, -drop)) @ Matrix.Translation(piv) @ R
                                 @ Matrix.Translation(-piv))
        bpy.context.view_layer.update()

    # -----------------------------------------------------------------------------------------
    def camera(self, yaw=22.0, pitch=-3.0, eye_frac=0.38, head_frac=0.48, head_height=0.232,
               x_frac=0.5, fit_objs=(), top_margin_px=6, lens=None, min_head=0.88):
        """Ortho camera orbiting the bust: eye line at ``eye_frac`` from the top, head (crown to
        chin) ``head_frac`` of the frame height; shrinks to keep ``fit_objs`` inside the top."""
        sc = self.sc
        cam_data = bpy.data.cameras.new("PC_Cam")
        lens = lens if lens is not None else float(os.environ.get("PC_LENS", "400"))
        cam_data.type = "PERSP" if lens > 0 else "ORTHO"
        cam_data.sensor_fit = "VERTICAL"
        if lens > 0:
            cam_data.sensor_height = 24.0
            cam_data.lens = lens
        cam = bpy.data.objects.new("PC_Cam", cam_data)
        sc.collection.objects.link(cam)
        sc.camera = cam
        y, p = math.radians(yaw), math.radians(pitch)
        # camera elevation ``pitch`` (negative = slightly below, looking up); yaw + = camera
        # moves to +X, so the face turns towards the image left
        d = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
        look = -d
        rot = look.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot.to_euler()
        eye = Vector(self.to_world_head([[0, -0.08, 0.0]])[0])
        bpy.context.view_layer.update()
        R = cam.rotation_euler.to_matrix()
        right = Vector(R.col[0])
        up = Vector(R.col[1])
        scale = head_height * self.H3.s / head_frac if self.H3 else head_height / head_frac

        def place(scale):
            cam_data.ortho_scale = scale
            # frame height = scale (vertical fit); eye at eye_frac from top
            dy = (0.5 - eye_frac) * scale
            hc = Vector(self.to_world_head([[0, 0.0, 0.0]])[0])
            # horizontal: centre of the cranium at x_frac
            off_r = (hc - eye).dot(right)
            dx = (x_frac - 0.5) * scale * self.W / self.H
            centre = eye + right * (off_r - dx) - up * dy
            dist = scale * lens / 24.0 if lens > 0 else 3.0
            cam.location = centre - look * dist
            cam_data.clip_start = max(0.05, dist - 1.0)
            cam_data.clip_end = dist + 1.5
            bpy.context.view_layer.update()
        place(scale)
        scale0 = scale
        if fit_objs:
            for _ in range(3):
                top = self.top_px(fit_objs)
                if top is None or top >= top_margin_px * self.ss:
                    break
                eye_y = eye_frac * self.H * self.ss
                need = (eye_y - top_margin_px * self.ss) / (eye_y - top)
                scale = min(scale / need, scale0 / min_head)
                if scale >= scale0 / min_head - 1e-9:
                    place(scale)
                    break
                place(scale)
        self.cam = cam
        self.look = np.array(look)
        return cam

    def matrices(self):
        dg = bpy.context.evaluated_depsgraph_get()
        cam = self.sc.camera
        V = np.array(cam.matrix_world.inverted())
        P = np.array(cam.calc_matrix_camera(dg, x=self.W * self.ss, y=self.H * self.ss))
        return V, P

    def project(self, Pw):
        V, Pm = self.matrices()
        Pw = np.asarray(Pw, np.float64)
        h = np.concatenate([Pw, np.ones(Pw.shape[:-1] + (1,))], -1)
        c = h @ V.T
        clip = c @ Pm.T
        ndc = clip[..., :3] / clip[..., 3:4]
        Wr, Hr = self.W * self.ss, self.H * self.ss
        return np.stack([(ndc[..., 0] + 1) / 2 * Wr, (1 - ndc[..., 1]) / 2 * Hr, -c[..., 2]], -1)

    def top_px(self, objs):
        dg = bpy.context.evaluated_depsgraph_get()
        best = None
        for cv in self.curves:
            if cv["style"] in ("strand", "chain"):
                y = self.project(np.array(cv["pts"]))[:, 1].min()
                best = y if best is None else min(best, y)
        for o in objs:
            if o is None or o.type != "MESH":
                continue
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            n = len(me.vertices)
            co = np.empty(n * 3)
            me.vertices.foreach_get("co", co)
            ev.to_mesh_clear()
            Mw = np.array(o.matrix_world)
            Pw = co.reshape(-1, 3) @ Mw[:3, :3].T + Mw[:3, 3]
            y = self.project(Pw)[:, 1].min()
            best = y if best is None else min(best, y)
        return best

    # -----------------------------------------------------------------------------------------
    def ink(self, scale=1.0, overrides=None):
        from ironart import ink as _ink
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
        fs.crease_angle = math.radians(128.0)
        fs.use_culling = True
        fs.use_smoothness = True
        while len(fs.linesets) > 0:
            fs.linesets.remove(fs.linesets[0])
        for kind, spec in INK.items():
            if not self.cols[kind].all_objects:
                continue
            spec = dict(spec, **((overrides or {}).get(kind, {})))
            spec.setdefault("dist", (0.0, 100.0, 1.0, 1.0))
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

    # -----------------------------------------------------------------------------------------
    def grids(self):
        """Face-space height grids by ray casting along the head's forward axis.

        ``h_head`` = forward height of the head surface (head object only) and ``h_front`` =
        front-most surface of the whole bust (beards drape over it), at (u, v) head-local."""
        from mathutils.bvhtree import BVHTree
        dg = bpy.context.evaluated_depsgraph_get()
        s = self.H3.s if self.H3 else 1.0
        us = np.arange(-0.095, 0.0951, 0.0025) * s
        vs = np.arange(-0.40, 0.14, 0.0025) * s
        head_ev = self.head.evaluated_get(dg)
        bvh = BVHTree.FromObject(head_ev, dg)          # object (head-local) space
        Mh = self.head_matrix()
        Rh = Mh[:3, :3]
        h_head = np.full((len(vs), len(us)), np.nan, np.float32)
        h_front = np.full((len(vs), len(us)), np.nan, np.float32)
        d_local = Vector((0, 1, 0))                      # backwards (+Y) from in front
        d_world = Vector(tuple(Rh @ np.array([0, 1.0, 0])))
        hide = [o for o in self.cols["none"].all_objects]
        for o in hide:
            o.hide_set(True)
        for i, v in enumerate(vs):
            for j, u in enumerate(us):
                if v > -0.13 * s:
                    loc, nrm, idx, dist = bvh.ray_cast(Vector((u, -0.4, v)), d_local, 1.0)
                    if loc is not None:
                        h_head[i, j] = -loc.y
                o_w = Vector(tuple(Mh[:3, :3] @ np.array([u, -0.45, v]) + Mh[:3, 3]))
                hit, loc, nrm, idx, ob, mw = self.sc.ray_cast(dg, o_w, d_world, distance=1.2)
                if hit:
                    pl = np.linalg.solve(Rh, np.array(loc) - Mh[:3, 3])
                    h_front[i, j] = -pl[1]
        for o in hide:
            o.hide_set(False)
        return us, vs, h_head, h_front

    # -----------------------------------------------------------------------------------------
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
                 ("region", "pc_region"), ("mask", "pc_mask")]
        used = []
        for fname, sock in names:
            if sock not in rl.outputs:
                continue
            fo.file_slots.new(fname)
            nt.links.new(rl.outputs[sock], fo.inputs[fname])
            used.append(fname)
        sc.render.filepath = os.path.join(out_dir, "beauty.png")
        _scene.check_render_settings()
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
        V, P = self.matrices()
        us, vs, hh, hf = self.grids()
        Mh = self.head_matrix()
        cam_w = np.array(self.sc.camera.matrix_world)
        # camera direction in head-local coordinates (for the gaze)
        look_local = np.linalg.solve(Mh[:3, :3], np.array(self.look))
        meta = dict(W=self.W, H=self.H, ss=self.ss, view=V.tolist(), proj=P.tolist(),
                    head=Mh.tolist(), cam=cam_w.tolist(), look_local=look_local.tolist(),
                    head_scale=self.H3.s if self.H3 else 1.0, anchors=self.anchors,
                    curves=self.curves, grid_u=us.tolist(), grid_v=vs.tolist())
        if extra:
            meta.update(extra)
        np.savez_compressed(os.path.join(out_dir, "scene.npz"),
                            color=ps["color"].astype(np.float32),
                            line=ps.get("line", np.zeros_like(ps["color"])).astype(np.float32),
                            depth=ps["depth"][..., 0].astype(np.float32),
                            region=ps["region"][..., 0].astype(np.float32),
                            mask=ps["mask"][..., :3].astype(np.float32),
                            h_head=hh, h_front=hf)
        with open(os.path.join(out_dir, "scene.json"), "w") as f:
            json.dump(meta, f)
        return meta

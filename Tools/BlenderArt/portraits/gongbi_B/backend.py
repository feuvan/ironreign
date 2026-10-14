"""Blender backend: renders a :class:`canvas.Canvas` flat in an orthographic Cycles camera.

All primitives become ONE mesh (z = draw order) with a point-domain float colour attribute
``col`` (linear RGB + opacity) and two materials:

* paint  Mix(Transparent white, Emission col, fac = opacity)  -> "over" (mineral colour, ink)
* glaze  Transparent BSDF tinted lerp(white, col, opacity)     -> multiply (water-colour wash)

Behind everything an emissive plane carries the aged-silk texture.  Emission + transparency only:
camera rays are deterministic, samples are only for anti-aliasing, so 4-6 spp at 3x supersample
give clean lines.  Cycles CPU, no denoiser, Standard view (palette colours exact).
"""

import math
import os
import time

import bpy
import numpy as np

from ironart import scene as S

import silk as silkmod


def _material_paint():
    m = bpy.data.materials.new("paint")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "col"
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr.inputs["Color"].default_value = (1, 1, 1, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(vc.outputs["Color"], em.inputs["Color"])
    nt.links.new(vc.outputs["Alpha"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    return m


def _material_glaze():
    m = bpy.data.materials.new("glaze")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "col"
    mixc = nt.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    mixc.blend_type = "MIX"
    mixc.inputs[6].default_value = (1, 1, 1, 1)      # A
    nt.links.new(vc.outputs["Alpha"], mixc.inputs[0])
    nt.links.new(vc.outputs["Color"], mixc.inputs[7])  # B
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    nt.links.new(mixc.outputs[2], tr.inputs["Color"])
    nt.links.new(tr.outputs[0], out.inputs["Surface"])
    return m


def _material_silk(img):
    m = bpy.data.materials.new("silk")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def build_mesh(cv):
    """Concatenate all primitives into numpy buffers for one Blender mesh."""
    verts, cols, loops, starts, totals, mats = [], [], [], [], [], []
    nv = 0
    nl = 0
    for p in cv.prims:
        n = len(p.V)
        V3 = np.empty((n, 3))
        V3[:, 0] = p.V[:, 0]
        V3[:, 1] = -p.V[:, 1]
        V3[:, 2] = p.z
        verts.append(V3)
        C = np.empty((n, 4))
        if p.C is not None:
            C[:, :3] = p.C
        else:
            C[:, :3] = p.col[None, :]
        C[:, 3] = np.clip(p.Al, 0, 1)
        cols.append(C)
        mi = 0 if p.mode == "paint" else 1
        if p.ngon:
            loops.append(np.arange(n, dtype=np.int64) + nv)
            starts.append(np.array([nl]))
            totals.append(np.array([n]))
            mats.append(np.array([mi]))
            nl += n
        else:
            T = np.asarray(p.tris, np.int64)
            k = len(T)
            loops.append((T + nv).reshape(-1))
            starts.append(nl + 3 * np.arange(k))
            totals.append(np.full(k, 3))
            mats.append(np.full(k, mi))
            nl += 3 * k
        nv += n
    return (np.vstack(verts), np.vstack(cols), np.concatenate(loops), np.concatenate(starts),
            np.concatenate(totals), np.concatenate(mats))


def render(cv, out_png, ss=3, samples=5, silk_seed=1, threads=None):
    """Render canvas ``cv`` to ``out_png`` at ``ss`` x target size.  Returns seconds."""
    t0 = time.time()
    W, H = cv.W, cv.H
    sc = S.reset(0)
    S.setup_cycles(samples=samples, transparent=False, preset="sprite", view="Standard",
                   adaptive_threshold=0, filter_width=1.5, threads=threads)
    cy = sc.cycles
    cy.max_bounces = 0
    cy.diffuse_bounces = 0
    cy.glossy_bounces = 0
    cy.transmission_bounces = 0
    cy.volume_bounces = 0
    cy.transparent_max_bounces = 1024
    cy.min_transparent_bounces = 1024     # no Russian roulette through the glaze layers
    cy.min_light_bounces = 0
    S.set_resolution(W, H, ss, sc)
    sc.render.image_settings.color_depth = "16"
    sc.render.dither_intensity = 0.0
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0

    # silk ground
    silk_path = silkmod.silk_png(W * ss, H * ss, silk_seed)
    img = bpy.data.images.load(silk_path)
    img.colorspace_settings.name = "sRGB"
    me = bpy.data.meshes.new("silk")
    me.from_pydata([(0, 0, -1), (W, 0, -1), (W, -H, -1), (0, -H, -1)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UV")
    for i, (u, v) in enumerate([(0, 1), (1, 1), (1, 0), (0, 0)]):
        uv.data[i].uv = (u, v)
    ob = bpy.data.objects.new("silk", me)
    sc.collection.objects.link(ob)
    me.materials.append(_material_silk(img))

    # painting
    V, C, L, ST, TT, M = build_mesh(cv)
    me = bpy.data.meshes.new("art")
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(L))
    me.loops.foreach_set("vertex_index", L.astype(np.int32))
    me.polygons.add(len(ST))
    me.polygons.foreach_set("loop_start", ST.astype(np.int32))
    me.polygons.foreach_set("loop_total", TT.astype(np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("material_index", M.astype(np.int32))
    ca = me.color_attributes.new("col", "FLOAT_COLOR", "POINT")
    ca.data.foreach_set("color", C.astype(np.float32).ravel())
    me.materials.append(_material_paint())
    me.materials.append(_material_glaze())
    ob = bpy.data.objects.new("art", me)
    sc.collection.objects.link(ob)

    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = max(W, H)
    cam.clip_start = 0.1
    cam.clip_end = 1000
    co = bpy.data.objects.new("cam", cam)
    co.location = (W / 2, -H / 2, 200)
    sc.collection.objects.link(co)
    sc.camera = co
    t_build = time.time() - t0
    secs = S.render(out_png, sc, quiet=True)
    print("[gongbi] %s | build %.1fs render %.1fs (%dx%d, %d spp)" % (
        cv.stats(), t_build, secs, W * ss, H * ss, samples))
    return time.time() - t0

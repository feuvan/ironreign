"""2D fallbacks rendered from the exported World Models (DESIGN.md section 8).

    Tools/BlenderArt/render.sh Tools/BlenderArt/world_models/sprites.py [City_1 City_2 City_3 Sect Banner Flag]

Each sprite re-imports its GLB from ArtSource/Models (the exact file Unreal gets), removes the
below-ground skirts (z < 0) and renders through the shared recipes:

    City_1/2/3 (96x96), Sect (64x64)   recipe 'sprite': 3/4 ortho (elevation 35, azimuth -20), the studio
                                        sprite rig, Freestyle ink, straight-alpha Kuwahara, 4x supersample,
                                        Lanczos, contact shadow; ground centre at (0.5, 0.70) of the canvas;
                                        cities keep the pennant box x 56-83, y 0-23 clear
    Banner (64x96), Flag (32x48)        recipe 'tint_plate': the Tint cloth becomes materials.white_cloth
                                        (TintMask AOV), neutral rig, post.neutralize + neutral_check; the
                                        pole base sits left of centre like the UI's fallback drawing;
                                        Banner writes Art/Map/BannerGlyphArea.txt ('x y w h', the clean field)

Writes previews (x4 nearest + on the map plain + UI sizes) to <scratch>/sprites/.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

from ironart import cameras, materials as M, post, recipes, scene, world_bake as WB  # noqa: E402
from ironart import REPO_DIR  # noqa: E402

#: World Models sprite recipe, registered at runtime (ironart/recipes.py is not modified): the
#: 'sprite' recipe with more fill / sky (the 3D models carry physically plausible, darker albedo
#: than the hand-tuned sprite kit), silhouette-only ink (inner creases turn a dense 3D city into
#: mush at 96 px) and a slightly richer grade.
WORLD_SPRITE = recipes.get("sprite")
WORLD_SPRITE["rig"] = ("rig_sprite", dict(key=5.6, fill=0.45, rim=1.2, sky=0.38, key_angle=155.0, key_elev=52.0,
                                          top_fill=0.85, shadow_lift=0.25))
WORLD_SPRITE["ink"] = dict(thickness_px=0.8, alpha=0.85, inner_scale=0.0, crease_angle=125.0, calligraphy=0.3,
                           pressure_noise=0.15)
WORLD_SPRITE["kuwahara"] = dict(size=1.2, sharpness=0.7, eccentricity=0.8, amount=0.45)
WORLD_SPRITE["grade"] = dict(saturation=1.1, contrast=1.06, warmth=0.006)
WORLD_SPRITE["unsharp"] = (0.7, 0.35)
WORLD_SPRITE["notes"] = ("World Models 2D fallbacks rendered from the GLBs: sprite recipe with fill 0.45, sky 0.38, "
                         "zenith 0.85, key 5.6, silhouette-only ink 0.8 px, Kuwahara 1.2 px, saturation 1.1")
recipes.RECIPES.setdefault("world_sprite", WORLD_SPRITE)

SPRITES = {
    # name: (asset path, size, family, anchor (frac) or None = recipe)
    "City_1": ("Art/Map/City_1.png", (96, 96), "world_sprite", None),
    "City_2": ("Art/Map/City_2.png", (96, 96), "world_sprite", None),
    "City_3": ("Art/Map/City_3.png", (96, 96), "world_sprite", None),
    "Sect": ("Art/Map/Sect.png", (64, 64), "world_sprite", None),
    "Banner": ("Art/Map/Banner.png", (64, 96), "tint_plate", (0.24, 0.93)),
    "Flag": ("Art/Map/Flag.png", (32, 48), "tint_plate", (0.16, 0.89)),
}
#: SIronMapView draws Flag.png over this box of the 96 px city canvas
PENNANT_KEEPOUT = (56, 0, 83, 23)


def largest_rect(mask):
    """Largest axis-aligned rectangle of True cells (x, y, w, h) - maximal rectangle by histogram."""
    H, W = mask.shape
    heights = np.zeros(W, np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(H):
        heights = np.where(mask[y], heights + 1, 0)
        stack = []
        for x in range(W + 1):
            hgt = heights[x] if x < W else 0
            start = x
            while stack and stack[-1][1] >= hgt:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best[0]:
                    best = (area, sx, y - sh + 1, x - sx, sh)
                start = sx
            stack.append((start, hgt))
    return best[1:]


def cut_below_ground(obj, z=0.0):
    """Remove the below-ground skirts (they sit under the terrain in the game)."""
    scene.select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.bisect(plane_co=(0, 0, z), plane_no=(0, 0, 1), clear_inner=True, clear_outer=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def render_sprite(name, out_dir, ss=None, spp=None, ink=None):
    rel, (W, H), family, anchor = SPRITES[name]
    times = {}
    t0 = time.time()
    objs = WB.reimport(os.path.join(common.MODELS_DIR, name + ".glb"))
    obj = objs[0]
    # what scene.reset() does, without wiping the imported model
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.use_freestyle = False
    for vl in sc.view_layers:
        while len(vl.freestyle_settings.linesets) > 0:
            vl.freestyle_settings.linesets.remove(vl.freestyle_settings.linesets[0])
    scene.seed_all(31)
    cut_below_ground(obj)
    tint = family == "tint_plate"
    if tint:
        M.enable_tint_aov()
        cloth = M.white_cloth("ClothWhite")
        for i, m in enumerate(obj.data.materials):
            if m and m.name.lower().startswith("tint"):
                obj.data.materials[i] = cloth
    r = recipes.setup(family, W, H, ss=ss, spp=spp)
    cam = recipes.camera(family)
    if anchor:
        cameras.fit_ortho(cam, [obj], margin_px=recipes.get(family)["margins"], anchor_world=(0.0, 0.0, 0.0),
                          anchor_px=(W * anchor[0], H * anchor[1]))
    else:
        recipes.frame(family, cam, [obj])
    recipes.light(family, cam)
    ik = {} if ink is None else ink
    recipes.ink(family, **ik)
    nodes = recipes.paint(family)
    raw_dir = common.out("sprites", "raw")
    raw = os.path.join(raw_dir, "%s_raw_%dx.png" % (name, r["ss"]))
    mask = None
    if tint:
        post.comp_outputs(raw_dir, {"tint_%s" % name: nodes["rl"].outputs["TintMask"]})
    times["setup"] = time.time() - t0
    times["render"] = scene.render(raw)
    if tint:
        mask = post.load(post.pass_path(raw_dir, "tint_%s" % name))[..., 0]
    img = recipes.finish(family, raw, tint_mask=mask)
    qa = post.QA(name)
    qa.max("border alpha (1 px ring)", post.border_alpha_max(img), 0.0)
    if name.startswith("City_"):
        x0, y0, x1, y1 = PENNANT_KEEPOUT
        qa.max("pennant keep-out alpha", float(img[y0:y1, x0:x1, 3].max()), 0.1)
    extra = {}
    if tint:
        m8 = mask
        if m8.shape[:2] != img.shape[:2]:
            m8 = post.resize(np.dstack([m8] * 3 + [np.ones_like(m8)]), (W, H))[..., 0]
        img = post.neutralize(img, (m8 > 0.5).astype(np.float32))      # every cloth pixel R = G = B
        mean, p99 = post.neutral_check(img, m8)
        qa.max("tint neutral mean", mean, 1.0)
        qa.max("tint neutral p99", p99, 4.0)
        extra["neutral"] = (round(mean, 2), round(p99, 2))
        if name == "Banner":
            # the glyph field: the largest rectangle of clean white cloth (TintMask, eroded 1 px so
            # the glyph never touches the trim / piping), cross-checked with the projected field
            cm = m8 > 0.6
            er = cm & np.roll(cm, 1, 0) & np.roll(cm, -1, 0) & np.roll(cm, 1, 1) & np.roll(cm, -1, 1)
            x, y, w, h = largest_rect(er)
            corners = json.load(open(os.path.join(common.out(), "banner_glyph_world.json")))
            extra["glyph_field_projected"] = cameras.target_rect(cam, corners)
            txt = "%d %d %d %d\n" % (x, y, w, h)
            with open(os.path.join(REPO_DIR, "Content", "Data", "Art", "Map", "BannerGlyphArea.txt"), "w") as f:
                f.write(txt)
            cov = float((m8[y:y + h, x:x + w] > 0.5).mean())
            qa.range("glyph area on white cloth", cov, 0.98, 1.0)
            qa.range("glyph area size (px^2)", w * h, 300, 64 * 96)
            extra["glyph_area"] = (x, y, w, h)
            extra["glyph_cloth_coverage"] = round(cov, 3)
    qa.check()
    path = post.save_asset(img, rel)
    times["total"] = time.time() - t0
    # previews
    sheet = post.contact_sheet(
        [(img, "%dx%d" % (W, H)), (post.resize(img, (W * 4, H * 4), "nearest"), "x4"),
         (post.over(img, post.solid(W, H, "#97A26E")), "on plain")] +
        ([(post.over(post.resize(img, (s, s)), post.solid(s, s, "#97A26E")), "%d px (UI)" % s) for s in (46, 58, 74)]
         if name.startswith("City_") else []), cols=6)
    post.save(sheet, os.path.join(common.out("sprites"), "%s_sheet.png" % name))
    kb = os.path.getsize(path) / 1024.0
    print("[ironart] sprite %s -> %s (%dx%d, %.1f KB) render %.1fs total %.1fs %s" % (
        name, rel, W, H, kb, times["render"], times["total"], extra))
    return {"path": path, "size": (W, H), "kb": round(kb, 1), "times": {k: round(v, 1) for k, v in times.items()},
            **extra}


def main():
    fl = common.flags()
    names = [n for n in fl["names"] if n in SPRITES] or list(SPRITES)
    rep = common.Report()
    for n in names:
        rep.add(n + ".png", **render_sprite(n, common.out("sprites")))
    rep.save()


if __name__ == "__main__":
    main()

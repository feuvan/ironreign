"""Per-family recipes: the ONE place the look numbers live.

STYLE.md tables are generated from :data:`RECIPES` (``python3 -c "from ironart import recipes;
print(recipes.table_markdown())"``), the style frames call these helpers, and the library defaults
(``lights.rig_*``, ``ink.enable``, ``ink.thickness_for``) equal the values below.  An asset script
does::

    sc = scene.reset(seed=11)
    r = recipes.setup("sprite", 96, 96)          # Cycles, colour management, resolution
    ... build ...
    cam = recipes.camera("sprite")
    recipes.frame("sprite", cam, [obj])          # margins + ground-centre anchor
    recipes.light("sprite", cam)
    recipes.ink("sprite")
    recipes.paint("sprite")                      # compositor: Kuwahara (+ ink over)
    scene.render(raw)
    img = recipes.finish("sprite", raw)          # downsample, grade, unsharp, shadow, alpha
    post.save_asset(img, "Art/Map/City_2.png")

Units: Kuwahara ``size`` and ink ``thickness_px`` are in **target** pixels (the helpers multiply by
the supersample factor), margins/anchors in target pixels of the canvas.

``bpy`` is imported lazily, so the tables (and :func:`finish`) work from the system python3.
"""

import copy

#: family -> recipe.  Keys:
#:   ss, spp, preset, view, look, transparent   render settings (scene.setup_cycles)
#:   camera   (kind, kwargs)  kind: 'top' (ortho top-down), 'sprite' (3/4 ortho), 'portrait'
#:   rig      (lights function name, kwargs)
#:   ink      ink.enable kwargs or None
#:   kuwahara post.comp_painterly kwargs (size in target px) or None
#:   grade    post.grade kwargs (single values - no ranges)
#:   paper    post.apply_paper strength (0 = none); 'paper_mask' = finish() takes a mask (map land)
#:   unsharp  (radius, amount) or None
#:   shadow   post.drop_shadow kwargs or None
#:   margins  fit_ortho (left, top, right, bottom) target px, or None
#:   anchor   'ground' -> anchor_world (0,0,0) at anchor_frac x canvas; 'center'; None
#:   alpha    'cleanup' (post.alpha_cleanup), 'hex' (hex mask + cleanup), 'straight' (Fx: no shadow,
#:            no bleed beyond 2 px), None (opaque)
#:   tint     True: neutral rig, TintMask AOV, post.neutralize, no warmth/paper
#:   notes    one-line recipe notes for STYLE.md
RECIPES = {
    "map": dict(
        ss=2, spp=40, preset="map", view="Standard", look="None", transparent=False,
        camera=("top", {}),
        rig=("rig_map", dict(key=3.4, sky=0.55, elevation_deg=50.0, softness_deg=16.0)),
        ink=None,
        kuwahara=dict(size=3.5, sharpness=0.45, eccentricity=1.2, amount=0.75),
        grade=dict(saturation=0.98, contrast=1.04, warmth=0.0),
        paper=0.10, paper_mask=True, unsharp=None, shadow=None, margins=None, anchor=None,
        alpha=None, tint=False,
        notes="1 px = 1 cm, relief 0.55 m per unit height on ranges; coast ink line drawn in numpy "
              "(InkSoft, alpha 0.55); paper on land only; render the full map as ONE frame"),
    "sprite": dict(
        ss=4, spp=64, preset="sprite", view="Standard", look="None", transparent=True,
        camera=("sprite", dict(elevation_deg=35.0, azimuth_deg=-20.0)),
        rig=("rig_sprite", dict(key=4.6, fill=0.25, rim=1.2, sky=0.18, key_angle=155.0,
                                key_elev=52.0, top_fill=0.45, shadow_lift=0.2)),
        ink=dict(thickness_px=0.9, alpha=1.0, inner_scale=0.5, inner_alpha=0.5, crease_angle=125.0,
                 calligraphy=0.3, pressure_noise=0.15),
        kuwahara=dict(size=1.5, sharpness=0.7, eccentricity=0.8, amount=0.5),
        grade=dict(saturation=0.98, contrast=1.05, warmth=0.0),
        paper=0.0, unsharp=(0.8, 0.3),
        shadow=dict(offset=(2.2, 2.2), blur_px=1.6, opacity=0.35, depth_px=6.0, shear=0.15),
        margins=(2, 2, 6, 6), anchor="ground", anchor_frac=(0.5, 0.70), alpha="cleanup",
        tint=False,
        notes="City_1..3, Sect: each fitted independently to fill its canvas (the UI scales the "
              "tiers 46/58/74 px); ground centre at (0.5, 0.75) of the canvas; City pennant "
              "keep-out x 56-83, y 0-23 (alpha < 0.1)"),
    "tint_plate": dict(
        ss=4, spp=64, preset="sprite", view="Standard", look="None", transparent=True,
        camera=("sprite", dict(elevation_deg=35.0, azimuth_deg=-20.0)),
        rig=("rig_sprite", dict(key=4.6, fill=0.25, rim=1.2, sky=0.18, key_angle=155.0,
                                key_elev=52.0, top_fill=0.45, shadow_lift=0.2, neutral=True)),
        ink=dict(thickness_px=0.9, alpha=1.0, inner_scale=0.5, inner_alpha=0.5, crease_angle=125.0,
                 calligraphy=0.3, pressure_noise=0.15),
        kuwahara=dict(size=1.0, sharpness=0.7, eccentricity=0.8, amount=0.4),
        grade=dict(saturation=1.0, contrast=1.0, warmth=0.0),
        paper=0.0, unsharp=(0.8, 0.25), shadow=None,
        margins=(2, 2, 2, 2), anchor="ground", anchor_frac=(0.5, 0.9), alpha="cleanup",
        tint=True,
        notes="Banner 64x96, Flag 32x48, Unit_Base, white areas of Unit_*: white_cloth (TintMask "
              "AOV), neutral rig, post.neutralize(mask), neutral_check(mask) mean <= 1, p99 <= 4; "
              "glyph area = cameras.target_rect(banner corners) as 'x y w h'; no drop shadow "
              "(the UI composites units over Unit_Base)"),
    "hex": dict(
        ss=4, spp=48, preset="sprite", view="Standard", look="None", transparent=True,
        camera=("top", dict(width=2.0)),
        rig=("rig_map", dict(key=3.4, sky=0.6, elevation_deg=50.0, softness_deg=16.0,
                             shadow_lift=0.45)),
        ink=dict(thickness_px=0.8, alpha=0.6, inner_scale=0.0, outer_select="contour",
                 calligraphy=0.3, pressure_noise=0.2, crease=False),
        kuwahara=dict(size=1.5, sharpness=0.5, eccentricity=1.2, amount=0.85),
        grade=dict(saturation=1.0, contrast=1.05, warmth=0.0),
        paper=0.0, unsharp=None, shadow=None, margins=None, anchor=None, alpha="hex",
        tint=False,
        notes="r = 1 m, top-down; ground painted to 1.12 r and content may cross the hex edge (the "
              "mask cuts it) so neighbours meet canopy to canopy; edge density radially uniform; "
              "ink on canopy silhouettes only (collection)"),
    "portrait": dict(
        ss=2, spp=56, preset="portrait", view="Filmic", look="Medium Contrast", transparent=True,
        camera=("portrait", dict(head_height=0.232, yaw_deg=20.0, pitch_deg=-4.0, eye_line=0.38,
                                 head_frac=0.48)),
        rig=("rig_portrait", dict(key=40.0, fill=14.0, bounce=4.0, rim=26.0, key_elev=35.0)),
        ink=None,
        kuwahara=dict(size=4.0, sharpness=0.5, eccentricity=2.0, amount=0.85, detail_index=1,
                      detail_size=1.25, detail_eccentricity=1.0),
        grade=dict(saturation=0.96, contrast=1.02, warmth=0.008),
        paper=0.07, unsharp=(0.7, 0.4), vignette=0.12, shadow=None, margins=None, anchor=None,
        alpha=None, tint=False,
        notes="192x240 opaque; eyes at 38 % from the top, head 48 % of the frame, plume >= 6 px "
              "from the top; face objects pass_index 1 (fine Kuwahara), rest big directional "
              "strokes; background base (0.20,0.16,0.12) lite (0.52,0.44,0.33); targets: mean "
              "luma 65-80, shadow cheek >= 35 % of lit cheek"),
    "ui": dict(
        ss=4, spp=48, preset="ui", view="Standard", look="None", transparent=True,
        camera=("top", {}),
        rig=("rig_ui", dict(flat_gain=1.0, ambient=0.2, warm=False)),
        ink=dict(thickness_px=1.0, inner_scale=0.0, calligraphy=0.0, pressure_noise=0.0,
                 taper=False, alpha=0.85),
        kuwahara=None,
        grade=None, paper=0.0, unsharp=None, shadow=None, margins=None, anchor=None,
        alpha="cleanup", tint=False,
        notes="1 px = 1 mm; 9-slice margins: Button 20/16, Tab 20/16, Panel/PanelDark 24, "
              "Scroll 80; gold_leaf(uniform=True) and lacquer(vary=0) on edges; QA: field within "
              "3 levels of its token, per-row/column std <= 2 levels in the stretch zones"),
    "icon": dict(
        ss=4, spp=48, preset="sprite", view="Standard", look="None", transparent=True,
        camera=("sprite", dict(elevation_deg=35.0, azimuth_deg=-20.0)),
        rig=("rig_sprite", dict(key=4.6, fill=0.25, rim=1.2, sky=0.18, key_angle=155.0,
                                key_elev=52.0, top_fill=0.45, shadow_lift=0.2)),
        ink=dict(thickness_px=0.75, alpha=1.0, inner_scale=0.5, inner_alpha=0.5,
                 calligraphy=0.4, pressure_noise=0.2),
        kuwahara=dict(size=1.0, sharpness=0.7, eccentricity=0.8, amount=0.4),
        grade=dict(saturation=0.98, contrast=1.06, warmth=0.0),
        paper=0.0, unsharp=(0.6, 0.35), shadow=None,
        margins=(4, 4, 4, 4), anchor="center", alpha="cleanup", tint=False,
        notes="Icon_* 64x64: one prop per icon (sheaf, coin string, wall, scroll...), sprite camera, "
              "centred, 4 px margins, no ground shadow, ink 0.75"),
    "fx": dict(
        ss=4, spp=32, preset="fast", view="Standard", look="None", transparent=True,
        camera=("top", {}),
        rig=None,
        ink=None,
        kuwahara=dict(size=1.5, sharpness=0.5, eccentricity=1.5, amount=0.7),
        grade=dict(saturation=1.0, contrast=1.0, warmth=0.0),
        paper=0.0, unsharp=None, shadow=None, margins=(3, 3, 3, 3), anchor="center",
        alpha="straight", tint=False,
        notes="Fx_* 96x96 overlays: emission-only materials (no lights), straight-alpha Kuwahara, "
              "no drop shadow, no edge bleed beyond 2 px; additive look comes from the art, the "
              "UI draws them normally"),
    "event": dict(
        ss=2, spp=48, preset="map", view="Filmic", look="Medium Contrast", transparent=False,
        camera=("persp", dict(focal_mm=35.0)),
        rig=("rig_map", dict(key=3.4, sky=0.55, elevation_deg=35.0, softness_deg=16.0)),
        ink=dict(thickness_px=1.6, alpha=0.8, inner_scale=0.5, inner_alpha=0.5),
        kuwahara=dict(size=4.5, sharpness=0.45, eccentricity=1.5, amount=0.85),
        grade=dict(saturation=0.96, contrast=1.04, warmth=0.008),
        paper=0.08, unsharp=None, vignette=0.15, shadow=None, margins=None, anchor=None,
        alpha=None, tint=False,
        notes="Events 640x360, Duel 1280x720, Title 1920x1080, Battle background: perspective "
              "35 mm, same top-left sun at 35 deg; mist = world gradient + depth-masked blur"),
}
RECIPES["background"] = copy.deepcopy(RECIPES["event"])
RECIPES["background"]["kuwahara"]["size"] = 5.0
RECIPES["background"]["ink"]["thickness_px"] = 2.0
RECIPES["mask"] = dict(ss=1, spp=0, preset=None, view=None, look=None, transparent=True,
                       camera=None, rig=None, ink=None, kuwahara=None, grade=None, paper=0.0,
                       unsharp=None, shadow=None, margins=None, anchor=None, alpha=None, tint=True,
                       notes="Hex_Fill / Hex_Outline: pure numpy (post.hex_mask, outline = mask - "
                             "hex_mask(inset=3)), white RGB, no render")

#: canvas-specific notes for UI pieces without a style frame (STYLE.md section 11)
UI_PIECES = {
    "PanelDark": "Panel profile with LacquerDark/dark_wood field instead of paper; gold moulding "
                 "9-12 px; field = Night #1B1712 lifted to #2A2119 at the centre",
    "Tab / Tab_Active": "160x48, Button profile at 2/3 height, margins 20/16; inactive = dark_wood "
                        "field, active = Lacquer field + gold underline",
    "Frame_Portrait": "212x260, 10 px border (transparent centre 192x240 exactly): dark wood + "
                      "2.5 px gold moulding + 7x7 gold corner fittings; alpha 0 inside",
    "Seal": "128x128 extruded square, glyph carved by boolean, Lacquer #7E1F17 field with paper "
            "showing in the carved strokes, Kuwahara 0, paper 0.06, rotated 3 deg",
    "Divider": "512x16: gold moulding 2.5 px with a central cloud-scroll knot 16x16; uniform along "
               "x outside the central 64 px (it may be stretched)",
    "Scroll": "1024x640, 80 px margins: paper field (parchment, calibrated), rolled ends as "
              "dark_wood cylinders with gold caps inside the 80 px margins",
    "Title_Logo": "1200x400 transparent: extruded Heading-font letters in iron with gold bevel + "
                  "brush calligraphy as a lacquer-red emission layer; ink 2.0",
    "unknown": "192x240 portrait recipe with a matte #2A2119 silhouette bust (same head/torso), "
               "rim light only",
}


def get(family):
    """Deep copy of a family's recipe (safe to modify)."""
    if family not in RECIPES:
        raise KeyError("unknown recipe family %r (have: %s)" % (family, ", ".join(RECIPES)))
    return copy.deepcopy(RECIPES[family])


def _merge(base, override):
    out = dict(base or {})
    out.update(override or {})
    return out


# ---------------------------------------------------------------------------------------------
# Blender-side helpers
# ---------------------------------------------------------------------------------------------
def setup(family, w, h, ss=None, spp=None, **overrides):
    """``scene.setup_cycles`` + ``scene.set_resolution`` from the recipe. Returns the recipe."""
    from . import scene
    r = get(family)
    r.update(overrides)
    if ss is not None:
        r["ss"] = ss
    if spp is not None:
        r["spp"] = spp
    scene.setup_cycles(samples=r["spp"], transparent=r["transparent"], preset=r["preset"],
                       view=r["view"], look=r["look"])
    scene.set_resolution(w, h, r["ss"])
    r["size"] = (w, h)
    return r


def camera(family, **kw):
    """Create the family camera (ortho top-down needs the resolution set first)."""
    from . import cameras
    kind, args = get(family)["camera"]
    args = _merge(args, kw)
    if kind == "top":
        return cameras.ortho_top_down(**args)
    if kind == "sprite":
        return cameras.sprite_camera(**args)
    if kind == "portrait":
        return cameras.portrait_camera(**args)
    raise ValueError("camera kind %r needs a custom camera" % kind)


def frame(family, cam, objs, **kw):
    """``cameras.fit_ortho`` with the recipe margins and anchor rule. Returns units/px."""
    from . import cameras
    import bpy
    r = get(family)
    w, h = tuple(bpy.context.scene.get("ironart_target", (0, 0)))
    args = dict(margin_px=r["margins"] or 2.0)
    if r["anchor"] == "ground":
        fx, fy = r.get("anchor_frac", (0.5, 0.75))
        args.update(anchor_world=(0.0, 0.0, 0.0), anchor_px=(w * fx, h * fy))
    elif r["anchor"] == "center":
        args.update(anchor="center")
    args.update(kw)
    return cameras.fit_ortho(cam, objs, **args)


def light(family, cam, *args, **kw):
    """Run the recipe's light rig with its kwargs (``kw`` overrides)."""
    from . import lights
    r = get(family)
    if r["rig"] is None:
        return None
    fn, rk = r["rig"]
    return getattr(lights, fn)(cam, *args, **_merge(rk, kw))


def ink(family, **kw):
    from . import ink as _ink
    r = get(family)
    if r["ink"] is None and not kw:
        return None
    return _ink.enable(**_merge(r["ink"], kw), as_pass=True)


def paint(family, **kw):
    """Compositor painterly chain (ink laid over when the recipe has ink)."""
    from . import post
    r = get(family)
    k = _merge(r["kuwahara"] or {"size": 0}, kw)
    k.setdefault("ink", r["ink"] is not None)
    return post.comp_painterly(**k)


# ---------------------------------------------------------------------------------------------
# numpy finishing (no bpy)
# ---------------------------------------------------------------------------------------------
def finish(family, raw, paper_mask=None, tint_mask=None, seed=0, hex_size=None, **overrides):
    """Supersampled render (path or float RGBA) -> finished target-size image.

    Order: downsample -> grade -> unsharp -> paper (masked) -> vignette -> [tint: neutralize]
    -> drop shadow -> alpha (cleanup / hex mask).  ``tint_mask`` is at render or target size.
    """
    from . import post
    r = get(family)
    r.update(overrides)
    img = post.load(raw) if isinstance(raw, str) else raw
    if r["ss"] > 1:
        img = post.downsample(img, r["ss"])
    h, w = img.shape[:2]
    if r.get("grade"):
        img = post.grade(img, **r["grade"])
    if r.get("unsharp"):
        img = post.unsharp(img, *r["unsharp"])
    if r.get("paper"):
        tex = post.paper_texture(w, h, seed)
        if paper_mask is not None:
            tex = 1.0 + (tex - 1.0) * paper_mask
        img = post.apply_paper(img, tex, strength=r["paper"])
    if r.get("vignette"):
        img = post.vignette(img, r["vignette"])
    if r.get("tint") and tint_mask is not None:
        m = tint_mask
        if m.shape[:2] != (h, w):
            import numpy as np
            m = post.resize(np.dstack([m] * 3 + [np.ones_like(m)]), (w, h))[..., 0]
        img = post.neutralize(img, m)
    if r.get("shadow"):
        img = post.drop_shadow(img, **r["shadow"])
    if r.get("alpha") == "hex":
        img = post.apply_mask(img, post.hex_mask(w, h))
        img = post.alpha_cleanup(img, bleed=2)
    elif r.get("alpha") == "cleanup":
        img = post.alpha_cleanup(img)
    elif r.get("alpha") == "straight":
        img = post.alpha_cleanup(img, lo=0.01, hi=0.995, bleed=2)
    if not r["transparent"]:
        img[..., 3] = 1.0
    return img


# ---------------------------------------------------------------------------------------------
# STYLE.md tables
# ---------------------------------------------------------------------------------------------
def _fmt(d):
    if d is None:
        return "-"
    if isinstance(d, dict):
        return ", ".join("%s %s" % (k, _fmt(v)) for k, v in d.items())
    if isinstance(d, (tuple, list)):
        return "(" + ", ".join(_fmt(v) for v in d) + ")"
    if isinstance(d, float):
        return ("%.3f" % d).rstrip("0").rstrip(".")
    return str(d)


def table_markdown():
    """The STYLE.md 'Recipes' tables (render / light+ink / paint+finish / notes)."""
    fam = [f for f in RECIPES if f != "mask"]
    rows = ["| Family | Supersample | Samples | Preset | View / look | Alpha | Camera |",
            "|---|---|---|---|---|---|---|"]
    for f in fam:
        r = RECIPES[f]
        cam = "%s %s" % (r["camera"][0], _fmt(r["camera"][1]) if r["camera"][1] else "")
        rows.append("| %s | %dx | %d | %s | %s / %s | %s | %s |" % (
            f, r["ss"], r["spp"], r["preset"], r["view"], r["look"],
            r["alpha"] or "opaque", cam.strip()))
    rows += ["", "| Family | Light rig | Ink (target px) |", "|---|---|---|"]
    for f in fam:
        r = RECIPES[f]
        rig = "%s(%s)" % (r["rig"][0], _fmt(r["rig"][1])) if r["rig"] else "none (emission)"
        rows.append("| %s | %s | %s |" % (f, rig, _fmt(r["ink"])))
    rows += ["", "| Family | Kuwahara (size in target px) | Grade | Paper | Unsharp | Shadow | "
             "Margins (l, t, r, b) / anchor |", "|---|---|---|---|---|---|---|"]
    for f in fam:
        r = RECIPES[f]
        anc = r["anchor"] or "-"
        if anc == "ground":
            anc = "ground centre at %s of canvas" % _fmt(r.get("anchor_frac"))
        paper = _fmt(r["paper"]) + (" (land only)" if r.get("paper_mask") else "")
        rows.append("| %s | %s | %s | %s | %s | %s | %s / %s |" % (
            f, _fmt(r["kuwahara"]), _fmt(r["grade"]), paper, _fmt(r["unsharp"]),
            _fmt(r["shadow"]), _fmt(r["margins"]), anc))
    rows += ["", "| Family | Notes |", "|---|---|"]
    for f in RECIPES:
        rows.append("| %s | %s |" % (f, RECIPES[f]["notes"]))
    rows += ["", "| UI piece (no style frame yet) | Recipe |", "|---|---|"]
    for k, v in UI_PIECES.items():
        rows.append("| %s | %s |" % (k, v))
    return "\n".join(rows)

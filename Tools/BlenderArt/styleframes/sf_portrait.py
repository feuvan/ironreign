"""Style frame (d): 192x240 painted bust - a general in lamellar armour and helmet (recipe "portrait").

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_portrait.py [out_dir]
        [--kind warrior|scholar|female] [--preview] [--seed N]

Pipeline: ``figure.bust(kind)`` (SDF-sculpted head with lids carved around the eyeballs, philtrum,
lips and mouth line; hair-curve brows / beard / mustache / plume; helmet; lamellar torso with a
crossed red-over-cream collar, pauldrons, chest mirror) -> 85 mm portrait camera, eyes at 38 %
from the top, head 48 % of the frame, eyes aimed at the camera -> ``rig_portrait`` (key 135 / 35,
fill, warm bounce, rim) -> Cycles 2x -> compositor: over a painted umber paper background,
two-scale anisotropic Kuwahara (fine on the face objects, pass index 1; big directional strokes on
armour and background) -> numpy: downsample, unsharp, grade, vignette, paper.  Opaque output.

``--preview`` renders the same frame at 2x / 24 spp (~4x faster) - the paint scale is identical
(Kuwahara and ink are in target pixels).

QA (asserted, measured on the final image): mean luma, background luma, shadow cheek >= 35 % of
the lit cheek, armour midtones, top margin above the plume, catchlights in both eyes.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import cameras, figure as F, post, recipes, scene  # noqa: E402
from ironart import terrain as T  # noqa: E402

W, H = 192, 240


def _opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


PREVIEW = "--preview" in sys.argv
KIND = _opt("--kind", "warrior")
SEED = int(_opt("--seed", 21))


def background(path, w, h, seed):
    """Neutral dark paper: warm umber, a lighter halo behind the head on the key side, painterly
    brush mottling.  Values are display sRGB (the Filmic view lifts them slightly)."""
    x, y = T.grid(h, w)
    n = T.fbm_at(x, y, w * 0.35, 4, seed=seed)
    stroke = T.fbm_at(x * 0.25, y, w * 0.12, 3, seed=seed + 1)
    glow = np.exp(-(((x / w - 0.38) / 0.42) ** 2 + ((y / h - 0.30) / 0.45) ** 2))
    base = np.array([0.20, 0.16, 0.12], np.float32)
    lite = np.array([0.46, 0.39, 0.30], np.float32)
    col = base + (lite - base) * (glow[..., None] * 0.85)
    col = col * (1 + 0.12 * n[..., None] + 0.05 * stroke[..., None])
    img = np.dstack([np.clip(col, 0, 1), np.ones((h, w), np.float32)])
    img = post.apply_paper(img, post.paper_texture(w, h, seed, scale=2.0), strength=0.08)
    post.save(img, path, opaque=True)
    return path


def render_bust(out, kind=KIND, seed=SEED, preview=PREVIEW, tag=None, qa=True):
    """Render one archetype bust; returns (final image, times, qa or None)."""
    times = {}
    tag = tag or ("sf_portrait" if kind == "warrior" else "portrait_%s" % kind)
    scene.reset(seed=seed)
    rng = random.Random(seed)
    r = recipes.setup("portrait", W, H, spp=24 if preview else None)
    ss = r["ss"]
    with scene.timer("build", times):
        mats = F.portrait_materials(kind)
        b = F.bust(kind, rng, mats)
        bg = background(os.path.join(out, "%s_bg.png" % tag), W * ss, H * ss, seed)
    lm = b["lm"]
    eye_c = (lm["eye_l"] + lm["eye_r"]) / 2
    cam = recipes.camera("portrait", eye_point=eye_c)
    eyes = F.eyeballs(b["specs"], mats["Eye"], look_at=cam.location)
    for o in eyes:
        o.pass_index = 1
    cameras.center_on(cam, [b["head"], b["gear"]], 0.5)
    recipes.light("portrait", cam, eye_c)
    nodes = recipes.paint("portrait", background=bg)
    import bpy
    rl = nodes["rl"]
    idm = bpy.context.scene.node_tree.nodes.new("CompositorNodeIDMask")
    idm.index = 1
    bpy.context.scene.node_tree.links.new(rl.outputs["IndexOB"], idm.inputs[0])
    post.comp_outputs(out, {"%s_alpha" % tag: rl.outputs["Alpha"], "%s_face" % tag: idm.outputs[0]})
    raw = os.path.join(out, "%s_raw_%dx.png" % (tag, ss))
    times["render"] = scene.render(raw)
    with scene.timer("post", times):
        img = recipes.finish("portrait", raw, seed=seed + 1)
        final = os.path.join(out, "%s_192x240.png" % tag)
        post.save(img, final, opaque=True)
    if not qa:
        return img, times, None
    # ---- QA on the final image
    alpha = post.downsample(post.load(post.pass_path(out, "%s_alpha" % tag)), ss)[..., 0]
    face = post.downsample(post.load(post.pass_path(out, "%s_face" % tag)), ss)[..., 0]
    lum = post.luma8(img)
    q = post.QA("portrait")
    q.range("mean luma", float(lum.mean()), 65, 80)
    q.range("background luma (alpha < 0.05)", float(lum[alpha < 0.05].mean()), 45, 70)

    def px_mean(co, rad=2):
        x, y = cameras.world_to_target_px(cam, co)
        x, y = int(round(x)), int(round(y))
        return float(lum[max(0, y - rad):y + rad + 1, max(0, x - rad):x + rad + 1].mean()), (x, y)
    from mathutils import Vector
    sy = lm["surf_y"]
    lit, lp = px_mean(Vector((-0.040, sy(-0.040, -0.004) - 0.001, -0.004)))
    shd, sp = px_mean(Vector((0.046, sy(0.046, -0.004) - 0.001, -0.004)))
    print("[ironart] cheeks lit %.0f at %s, shadow %.0f at %s" % (lit, lp, shd, sp))
    q.range("shadow cheek / lit cheek", shd / max(lit, 1.0), 0.35, 0.80)
    body = (alpha > 0.95) & (face < 0.05)
    rows = np.arange(H)[:, None] >= int(H * 0.72)
    q.range("armour / robe midtone luma (bottom 28 %)", float(np.median(lum[body & rows])), 55, 95)
    top = int(np.argmax((alpha > 0.1).any(1)))
    q.range("top margin above the headwear (px)", top, 6, 60)
    for o in eyes:
        ex, ey = cameras.world_to_target_px(cam, o.matrix_world.translation)
        ex, ey = int(round(ex)), int(round(ey))
        patch = lum[ey - 3:ey + 4, ex - 4:ex + 5]
        q.range("catchlight %s (max luma near the iris)" % o.name, float(patch.max()), 120, 255)
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})
    return img, times, q


def main():
    a = [x for x in scene.args() if not x.startswith("--")]
    a = [x for x in a if x not in (KIND, str(SEED))]
    out = a[0] if a else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    img, times, q = render_bust(out)
    tag = "sf_portrait" if KIND == "warrior" else "portrait_%s" % KIND
    on_ui = post.solid(W + 24, H + 24, "Night")
    on_ui = post.paste(on_ui, img, 12, 12)
    sheet = post.contact_sheet([(img, "192x240"), (post.resize(img, (384, 480), "lanczos"), "x2 view"),
                                (on_ui, "on Night #1B1712")], cols=3)
    post.save(sheet, os.path.join(out, "%s_sheet.png" % tag))
    if q is not None:
        q.check()


if __name__ == "__main__":
    main()

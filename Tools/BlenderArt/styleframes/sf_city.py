"""Style frame (b): 96x96 walled city sprite (City_2), transparent, ground-centre anchored.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_city.py [out_dir] [--size N]

Pipeline (recipe "sprite"): ``geometry.walled_city`` -> 3/4 ortho camera fitted with margins
(2, 2, 5, 4) and the ground centre on (48, 72) -> ``rig_sprite`` -> Cycles 4x + Freestyle ink
pass -> compositor: straight-alpha Kuwahara (1.5 target px) + ink over -> numpy: Lanczos
downsample, grade, unsharp, footprint contact shadow towards 315 deg, alpha clean-up -> 96x96.

QA (asserted): plane values measured per target pixel by ray casting (wall tops / west / south
faces - east and north faces are not visible from the sprite camera - and lit / shadow roof
slopes), clear 1 px border, pennant keep-out box clear.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import cameras, geometry as geo, materials as M, post, recipes, scene  # noqa: E402

SIZE = 96
#: City_N tier rendered by this frame (City_2 = the walled city)
TIER = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 2
#: the UI draws Flag.png over this box of the 96 px canvas (SIronMapView.cpp: x = 48 + 0.08 * 96,
#: w = 0.42 * 96 * 32/48, y from -0.45 * FlagH) - keep tall structures out of it
PENNANT_KEEPOUT = (56, 0, 83, 23)


def erode(m):
    """1 px erosion: measure plane interiors, not the ink/anti-aliased boundaries."""
    p = np.pad(m, 1)
    return m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]


def plane_values(img, samples, lights_dir):
    """Median luma (8-bit) of stone planes by orientation and of roof slopes by N.L (plane
    interiors only - each class mask is eroded by 1 px)."""
    lum = post.luma8(img)
    n = samples["normal"]
    mat = samples["mat"]
    stone = np.isin(mat, ["Stone", "StoneTop"]) & (img[..., 3] > 0.9)
    roof = (mat == "RoofTile") & (img[..., 3] > 0.9)
    out = {}
    for name, m in (("tops", stone & (n[..., 2] > 0.8)),
                    ("west", stone & (n[..., 0] < -0.7)),
                    ("south", stone & (n[..., 1] < -0.7))):
        m = erode(m)
        out[name] = float(np.median(lum[m])) if m.sum() >= 4 else float("nan")
        out[name + "_n"] = int(m.sum())
    ndl = (n * np.array(lights_dir, np.float32)).sum(-1)
    # lit = the top quarter of the visible roof by N.L, shadow = the bottom 15 % (east hips,
    # north slopes): the two planes a painted roof must separate
    if roof.any():
        q_lo, q_hi = np.percentile(ndl[roof], [15, 75])
    else:
        q_lo, q_hi = -1, 2
    lit = erode(roof & (ndl >= q_hi))
    shd = roof & (ndl <= q_lo)
    out["roof_ndl_pct"] = [round(float(v), 2) for v in np.percentile(ndl[roof], [5, 25, 50, 75, 95])] if roof.any() else []
    ground = erode((mat == "Ground") & (img[..., 3] > 0.9))
    out["ground_p10"] = float(np.percentile(lum[ground], 10)) if ground.sum() >= 10 else float("nan")
    ws = stone & (n[..., 0] < -0.7) & (img[..., 3] > 0.9)
    out["west_p10"] = float(np.percentile(lum[ws], 10)) if ws.sum() >= 10 else float("nan")
    out["roof_lit"] = post.region_mean(img, mask=lit)
    out["roof_shadow"] = post.region_mean(img, mask=shd)
    return out


def main():
    a = [x for x in scene.args() if not x.startswith("--")]
    a = [x for x in a if not x.isdigit()]
    out = a[0] if a else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    times = {}
    scene.reset(seed=11)
    rng = random.Random(11)
    recipes.setup("sprite", SIZE, SIZE)
    with scene.timer("build", times):
        mats = M.architecture_set()
        mb = geo.MeshBuilder()
        geo.walled_city(mb, rng, size=TIER)
        city = mb.build("City", mats)
    cam = recipes.camera("sprite")
    recipes.frame("sprite", cam, [city])
    rig = recipes.light("sprite", cam)
    recipes.ink("sprite")
    recipes.paint("sprite")
    raw = os.path.join(out, "city%d_raw_4x.png" % TIER)
    times["render"] = scene.render(raw)
    with scene.timer("qa_rays", times):
        samples = cameras.surface_samples(cam)
        from mathutils import Vector
        key_dir = tuple((rig["key"].matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized())
    with scene.timer("post", times):
        img_noshadow = recipes.finish("sprite", raw, shadow=None, alpha=None)
        img = recipes.finish("sprite", raw)
        suffix = "" if TIER == 2 else "_%d" % TIER
        final = os.path.join(out, "sf_city%s_96.png" % suffix)
        post.save(img, final)
        pv = plane_values(img_noshadow, samples, key_dir)
        # QA visual: which pixels were measured as tops / west / south / roof lit / roof shadow
        n, m = samples["normal"], samples["mat"]
        stone = np.isin(m, ["Stone", "StoneTop"])
        cls = np.zeros((SIZE, SIZE, 4), np.float32)
        cls[..., 3] = samples["hit"] * 0.35
        for col, mk in (((1, 1, 0.2), stone & (n[..., 2] > 0.8)), ((0.2, 0.6, 1), stone & (n[..., 0] < -0.7)),
                        ((1, 0.3, 0.3), stone & (n[..., 1] < -0.7)), ((0.2, 1, 0.3), (m == "RoofTile"))):
            cls[mk, :3] = col
            cls[mk, 3] = 1.0
        post.save(post.contact_sheet([(post.resize(img_noshadow, (192, 192), "nearest"), "img"),
                                      (post.resize(cls, (192, 192), "nearest"), "classes")], cols=2),
                  os.path.join(out, "city%d_qa_classes.png" % TIER))
        on_map = post.solid(SIZE, SIZE, "#97A26E")
        sheet = post.contact_sheet(
            [(img, "96x96"), (post.resize(img, (192, 192), "nearest"), "x2"),
             (post.over(img, on_map), "on plain #97A26E"),
             (post.over(post.resize(img, (58, 58)), post.solid(58, 58, "#97A26E")), "58 px (UI)")],
            cols=4, scale=1)
        post.save(sheet, os.path.join(out, "sf_city%s_sheet.png" % suffix))
    qa = post.QA("city%d" % TIER)
    qa.range("wall tops luma", pv["tops"], 178, 205)
    qa.range("west faces luma", pv["west"], 140, 165)
    qa.range("south faces luma", pv["south"], 92, 118)
    rl_ = float(np.dot(pv["roof_lit"], (0.2126, 0.7152, 0.0722)))
    rs_ = float(np.dot(pv["roof_shadow"], (0.2126, 0.7152, 0.0722)))
    qa.range("roof lit slope luma", rl_, 105, 140)
    qa.range("roof shadow slope luma", rs_, 45, 75)
    qa.range("roof lit / shadow ratio", rl_ / max(rs_, 1.0), 1.6, 3.0)
    qa.range("courtyard in shadow (p10 luma)", pv["ground_p10"], 58, 140)
    qa.range("west face in cast shadow (p10)", pv["west_p10"], 50, 140)
    qa.max("border alpha (1 px ring)", post.border_alpha_max(img), 0.0)
    x0, y0, x1, y1 = PENNANT_KEEPOUT
    qa.max("pennant keep-out alpha", float(img[y0:y1, x0:x1, 3].max()), 0.1)
    print("[ironart] planes", {k: (round(v, 1) if isinstance(v, float) else v) for k, v in pv.items()
                               if not isinstance(v, (tuple, list))},
          "roof N.L pct", pv["roof_ndl_pct"], "roof lit", tuple(round(c, 1) for c in pv["roof_lit"]),
          "roof shadow", tuple(round(c, 1) for c in pv["roof_shadow"]))
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})
    qa.check()


if __name__ == "__main__":
    main()

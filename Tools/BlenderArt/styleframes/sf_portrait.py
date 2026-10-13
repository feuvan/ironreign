"""Style frame (d): 192x240 painted bust - bearded general in lamellar armour and helmet.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_portrait.py [out_dir]

Pipeline: figure kit (sculpted head, lids, eyeballs, brows, beard + mustache, helmet with plume and
lamellar neck guard, torso, pauldrons, chest mirror, crossed collar) -> 85 mm portrait camera with
the eyes at 38 % from the top -> dramatic portrait rig -> Cycles 3x -> compositor: over a painted
dark-paper background, anisotropic Kuwahara -> numpy: downsample, crisp-eye unsharp, paper grain,
vignette.  Opaque output.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import numpy as np  # noqa: E402

from ironart import cameras, figure as F, lights, materials as M, post, scene  # noqa: E402
from ironart import terrain as T  # noqa: E402

W, H = 192, 240
PREVIEW = "--preview" in sys.argv
SS = 2 if PREVIEW else 3
SPP = 40 if PREVIEW else 96
SEED = 21


def portrait_materials():
    return {
        "Skin": M.skin("Skin", "#A26A4C", sss=0.15, roughness=0.6, blush=0.6, vary=0.12,
                       pores=0.12, pore_scale=90.0),
        "Eye": M.eye("Eye", iris="#2E1C10", sclera="#CFC3B2"),
        "Brow": M.hair_mesh("Brow", "#1C1714", strand_scale=400, direction="X"),
        "Beard": M.hair_mesh("Beard", "#17120F", strand_scale=260, direction="Z", roughness=0.6),
        "Iron": M.iron("Iron", "#3C4148", roughness=0.42),
        "Gold": M.gold_leaf("Gold", "#A88238", roughness=0.4),
        "Bronze": M.gold_leaf("Bronze", "#8A6A3A", roughness=0.35),
        "Lamellar": M.lamellar("Lamellar", "#2A2E34", lacing="#6A1C14", plate=(0.013, 0.028),
                               metallic=0.6, roughness=0.4, specular=0.4, bump=0.6),
        "Plume": M.hair_strands("Plume", "#7A140C", roughness=0.5, random_color=0.2,
                                reflection=0.5),
        "Silk": M.cloth("Silk", "#7E1F17", sheen=0.5, roughness=0.55),
        "SilkInner": M.cloth("SilkInner", "#D8CBB0", sheen=0.3, roughness=0.7),
        "Cape": M.cloth("Cape", "#6E1A14", sheen=0.6, roughness=0.6),
        "HairBlack": M.hair_strands("HairBlack", melanin=0.98, redness=0.3, roughness=0.45,
                                    random_color=0.1, reflection=0.3),
    }


def background(path, w, h, seed):
    """Neutral dark paper: warm umber, lighter behind the head on the key side, painterly."""
    x, y = T.grid(h, w)
    n = T.fbm_at(x, y, w * 0.35, 4, seed=seed)
    stroke = T.fbm_at(x * 0.25, y, w * 0.12, 3, seed=seed + 1)
    glow = np.exp(-(((x / w - 0.36) / 0.42) ** 2 + ((y / h - 0.30) / 0.45) ** 2))
    base = np.array([0.16, 0.13, 0.10], np.float32)
    lite = np.array([0.40, 0.34, 0.26], np.float32)
    col = base + (lite - base) * (glow[..., None] * 0.85)
    col = col * (1 + 0.12 * n[..., None] + 0.05 * stroke[..., None])
    img = np.dstack([np.clip(col, 0, 1), np.ones((h, w), np.float32)])
    img = post.apply_paper(img, post.paper_texture(w, h, seed, scale=2.0), strength=0.08)
    post.save(img, path, opaque=True)
    return path


def build_general(rng):
    p = F.HeadParams(jaw=1.1, chin=1.1, brow=1.05, cheekbone=1.15, nose_len=0.92, nose_width=1.08,
                     nose_bridge=1.05, socket=1.1, eye_size=1.12, lid_upper=0.31, lid_lower=0.24,
                     age=0.45, seed=SEED)
    mb, lm = F.head(p)
    F.ears(mb, lm)
    specs = F.eyes(mb, lm)
    F.neck(mb, lm, radius=0.056)
    head_obj = mb.build("Head", MATS)
    scene.add_modifier(head_obj, "SUBSURF", levels=1, render_levels=1)
    eyes = F.eyeballs(specs, MATS["Eye"], look=(0.3, -0.04))
    gb = F.geo.MeshBuilder()
    F.beard(gb, lm, length=0.12, fullness=0.55, style="full", strands=0, rng=rng)
    helm = F.helmet(gb, lm, plume=False, rng=rng)
    F.torso(gb, lm, shoulder_w=0.44, chest_d=0.24, slope=1.5, collar=0.05)
    F.neck_scarf(gb, lm)
    F.cape(gb, lm, shoulder_w=0.44, mat="Cape")
    F.pauldrons(gb, lm, shoulder_w=0.44, tiers=3)
    F.mirror_plate(gb, lm, radius=0.034, z_offset=-0.25, y=-0.112)
    gear = gb.build("Gear", MATS)
    hair = [
        F.geo.hair_curves("Beard", F.beard_strands(lm, 10000, length=0.15, converge=0.55, bulge=1.3, rng=rng),
                          MATS["HairBlack"], 0.00042, 0.0001),
        F.geo.hair_curves("Mustache", F.mustache_strands(lm, 900, length=0.055, droop=1.2, rng=rng),
                          MATS["HairBlack"], 0.0004, 0.0001),
        F.geo.hair_curves("Brows", F.brow_strands(lm, 700, thickness=1.4, angle=0.5, rng=rng),
                          MATS["HairBlack"], 0.00035, 0.00012),
        F.geo.hair_curves("Plume", F.plume_strands(lm, 2600, length=0.045, rng=rng, radius=0.04,
                                                   top=helm["finial_z"]),
                          MATS["Plume"], 0.0005, 0.00015),
    ]
    return lm, head_obj, eyes, gear, hair


MATS = {}


def main():
    a = [x for x in scene.args() if not x.startswith("--")]
    out = a[0] if a else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    times = {}
    scene.reset(seed=SEED)
    rng = random.Random(SEED)
    scene.setup_cycles(samples=SPP, transparent=True, preset="portrait", view="Filmic",
                       look="Medium High Contrast")
    scene.set_resolution(W, H, SS)
    with scene.timer("build", times):
        MATS.update(portrait_materials())
        lm, head_obj, eyes, gear, hair = build_general(rng)
        bg = background(os.path.join(out, "portrait_bg.png"), W * SS, H * SS, SEED)
    eye_c = (lm["eye_l"] + lm["eye_r"]) / 2
    cam = cameras.portrait_camera(eye_c, head_height=0.232, yaw_deg=20, pitch_deg=-4,
                                  eye_line=0.38, head_frac=0.6)
    cameras.center_on(cam, [head_obj, gear], 0.5)
    lights.rig_portrait(cam, eye_c, fill=5.0)
    post.comp_painterly(size=7, sharpness=0.5, eccentricity=1.3, amount=0.8, background=bg,
                        ink=False)
    raw = os.path.join(out, "portrait_raw_%dx.png" % SS)
    times["render"] = scene.render(raw)
    with scene.timer("post", times):
        img = post.load(raw)
        img = post.downsample(img, SS)
        img = post.unsharp(img, 0.8, 0.45)
        img = post.grade(img, saturation=0.95, contrast=1.04, warmth=0.015)
        img = post.vignette(img, 0.3)
        img = post.apply_paper(img, post.paper_texture(W, H, SEED + 1), strength=0.04)
        img[..., 3] = 1.0
        final = os.path.join(out, "sf_portrait_192x240.png")
        post.save(img, final, opaque=True)
        sheet = post.contact_sheet([(img, "192x240"),
                                    (post.resize(img, (384, 480), "lanczos"), "x2 view")], cols=2)
        post.save(sheet, os.path.join(out, "sf_portrait_sheet.png"))
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})


main()

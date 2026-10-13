"""Style frame (b): 96x96 walled city sprite with a gate tower, transparent, bottom-centre anchored.

    Tools/BlenderArt/render.sh Tools/BlenderArt/styleframes/sf_city.py [out_dir]

Pipeline: build (MeshBuilder) -> 3/4 ortho camera fitted to the pixel frame -> sprite light rig ->
Cycles 4x supersample + Freestyle ink pass + shadow catcher -> compositor painterly (Kuwahara) ->
numpy: Lanczos downsample, grade, alpha clean-up -> 96x96 PNG.
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import bpy  # noqa: E402

from ironart import cameras, geometry as geo, ink, lights, materials as M, post, scene  # noqa: E402

SIZE = 96
SS = 4


def city_materials():
    """Material slots used by the architecture builders (names are the builder defaults)."""
    return {
        "Stone": M.stone_wall("Stone", "stone", block=(0.5, 0.25), bump=0.25),
        "StoneDark": M.principled("StoneDark", "stone_dark", 0.9, vary=0.1),
        "RoofTile": M.roof_tiles("RoofTile", "roof_tile", channel=0.2, course=0.24, glaze=0.1,
                                 roughness=0.55, bump=0.4),
        "RoofRidge": M.principled("RoofRidge", "roof_ridge", 0.55, vary=0.05),
        "PillarRed": M.lacquer("PillarRed", "pillar_red", roughness=0.45, coat=0.3,
                               coat_roughness=0.25),
        "Plaster": M.plaster("Plaster", "plaster"),
        "Timber": M.dark_wood("Timber", "timber"),
        "DoorDark": M.principled("DoorDark", "#2A1D15", 0.7),
        "Gold": M.gold_leaf("Gold"),
        "Ground": M.grass_ground("Ground", "#8C8466", "#9C8E6C", scale=0.6),
    }


def build_city(mb, rng, width=6.8, depth=5.6, wall_h=1.5):
    """Walled city (City_2 scale): wall ring + corner towers, hero gate tower, a keep on a stone
    podium at the back and a few houses.  Tall elements are kept on the centre line so the
    silhouette reads at 96 px."""
    geo.wall_ring(mb, width, depth, height=wall_h, thickness=0.85, gate_gap=2.6, tower=1.2,
                  merlon=(0.3, 0.22, 0.3), gap=0.22, batter=0.12)
    geo.gate_tower(mb, (0, -depth / 2, 0), width=3.4, depth=1.8, base_h=wall_h + 0.7,
                   hall_h=0.85)
    mb.box((0, 0, 0), (width - 0.6, depth - 0.6, 0.05), "Ground")
    geo.gate_tower(mb, (0, depth * 0.22, 0.05), width=2.6, depth=1.6, base_h=0.9, hall_h=0.8,
                   door=False)
    for (x, y, rot) in [(-2.15, -0.6, 1.5708), (2.15, -0.6, 1.5708), (-2.0, 1.4, 0.0),
                        (2.0, 1.4, 0.0)]:
        geo.house(mb, (x, y, 0.05), width=rng.uniform(1.1, 1.3), depth=0.85,
                  height=0.6, roof_h=0.45, rot_z=rot, lift=0.06)


def main():
    out = scene.args()[0] if scene.args() else os.path.join(os.environ["IRONART_OUT"], "styleframes")
    os.makedirs(out, exist_ok=True)
    times = {}
    sc = scene.reset(seed=11)
    rng = random.Random(11)
    scene.setup_cycles(samples=64, transparent=True, preset="sprite", view="Standard")
    scene.set_resolution(SIZE, SIZE, SS)
    with scene.timer("build", times):
        mats = city_materials()
        mb = geo.MeshBuilder()
        build_city(mb, rng)
        city = mb.build("City", mats)
    cam = cameras.sprite_camera(elevation_deg=35, azimuth_deg=-20)
    cameras.fit_ortho(cam, [city], margin_px=1.5, anchor="bottom_center")
    lights.rig_sprite(cam)
    ink.enable(thickness_px=0.6, alpha=0.85, inner_scale=0.6, inner_alpha=0.6, as_pass=True,
               crease_angle=125, calligraphy=0.3, pressure_noise=0.15)
    post.comp_painterly(size=4, sharpness=0.7, eccentricity=0.8, amount=0.6, saturation=1.0,
                        ink_opacity=0.9)
    raw = os.path.join(out, "city_raw_%dx.png" % SS)
    times["render"] = scene.render(raw)
    with scene.timer("post", times):
        img = post.load(raw)
        img = post.downsample(img, SS)
        img = post.grade(img, saturation=0.95, contrast=1.05, warmth=0.015)
        img = post.unsharp(img, 0.8, 0.3)
        img = post.drop_shadow(img, offset=(2.0, 1.2), blur_px=1.5, opacity=0.35, squash=0.5)
        img = post.alpha_cleanup(img)
        final = os.path.join(out, "sf_city_96.png")
        post.save(img, final)
        sheet = post.contact_sheet([(img, "96x96"), (post.resize(img, (192, 192), "nearest"), "x2"),
                                    (post.over(img, post.solid(96, 96, "#A9A86A")), "on plain")],
                                   cols=3, scale=1)
        post.save(sheet, os.path.join(out, "sf_city_sheet.png"))
    print("[ironart] TIMES", {k: round(v, 2) for k, v in times.items()})


main()

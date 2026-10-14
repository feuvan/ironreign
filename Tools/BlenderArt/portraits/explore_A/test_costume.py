"""Warlord costume test."""
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import costume as CO  # noqa: E402
import hair  # noqa: E402
import head as H  # noqa: E402
import identity as I  # noqa: E402
import mats as MA  # noqa: E402
import mh  # noqa: E402
import rig  # noqa: E402
import shell as SH  # noqa: E402
import skin  # noqa: E402
import skinmaps  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]
samples = int(args[1]) if len(args) > 1 else 32
t0 = time.time()
bpy.ops.wm.read_factory_settings(use_empty=True)
idn = I.make_identity(1, "m", 52, "warrior")
idn.expression = "stern"
b = H.build(idn)
lm = b["lm"]
print("chin", lm["chin"], "neck", lm["neck_c"], "eye", lm["eye_c"])
bstyle = {"mustache": 1.0, "chin": 1.0, "cheeks": 0.0, "jaw": 1.0, "neck": 0.5, "sideburns": 1.0, "soul": 1.0,
          "tails": 1.0, "length": 0.09, "must_len": 0.04, "cheek_len": 0.025, "taper": 0.25, "gravity": 0.7}
style = {"hair_rgb": (0.05, 0.045, 0.04), "recede": 0.15, "beard": bstyle, "beard_rgb": (0.2, 0.19, 0.18), "scalp": False}
A, Rg, Hh = skinmaps.make(b, idn, style, seed=1)
b["head"].data.materials.append(skin.skin_material_tex(idn, skinmaps.to_bpy("A", A), skinmaps.to_bpy("R", Rg, "Non-Color"), skinmaps.to_bpy("H", Hh, "Non-Color", True)))
b["head"].pass_index = 1
em, ec = skin.eye_materials(os.path.join(mh.MH_DATA, "eyes", "materials", "brown_eye.png"))
for e in b["eyes"]:
    e.data.materials.append(em)
    e.data.materials.append(ec)
    e.pass_index = 2
surf = hair.Surface(b["head"])
t1 = time.time()
sh = SH.Shell(surf, CO.torso_origin(lm))
fr = CO.Frame(lm)
print("shell", time.time() - t1, "Z range", np.nanmin(sh.Z), np.nanmax(sh.Z), "notch", fr.notch)
iron = MA.metal("Iron", (0.22, 0.22, 0.23), rough=0.4, patina=0.4)
gold = MA.metal("Gilt", (0.75, 0.55, 0.25), rough=0.3, patina=0.3)
bronze = MA.metal("Bronze", (0.55, 0.38, 0.2), rough=0.28)
lace = MA.plain("Lace", (0.45, 0.06, 0.04), rough=0.6, sheen=0.5)
red = MA.silk("RedSilk", (0.22, 0.018, 0.014), sheen=0.25, motif="clouds", motif_rgb=(0.55, 0.32, 0.1))
inner = MA.silk("Inner", (0.82, 0.78, 0.7))
band = MA.brocade("Band", (0.08, 0.06, 0.05), (0.7, 0.52, 0.25))
CO.cross_robe(sh, fr, [dict(mat=inner, band_mat=inner, offset=0.004, depth=0.10, band=0.018, el_bottom=-20),
                       dict(mat=red, band_mat=band, offset=0.008, depth=0.14, band=0.028)])
cut = CO.round_cut(fr, drop=0.03)
CO.lamellar(sh, iron, lace, cut, offset=0.018, az_range=(-178, 178), s_max=0.32, edge_mat=gold)
for sd in (1, -1):
    CO.pauldron(sh, sd, iron, lace, gold, offset=0.034, fr=fr)
CO.neck_scarf(sh, cut, red, offset=0.02)
CO.chest_mirror(sh, fr, bronze, gold, offset=0.04)
C = hair.skull_frame(surf, b)
hm = dict(bowl=iron, trim=gold, rivet=gold, flap=MA.scales("Flap"), tassel=MA.tassel(rgb=(0.32, 0.012, 0.01)))
CO.helmet(surf, b, C, hm)
rng = np.random.default_rng(1)
hmat = hair.hair_material("HairM", melanin=1.0, redness=0.1, grey=0.25)
hair.brows(surf, b, hmat, rng, count=1100, thick=1.2, arch=0.8, angle=0.25)
hair.lashes(surf, b, b["eyes"], hair.hair_material("LashM", melanin=1.0, roughness=0.5), rng)
bstyle["radius"] = 0.00012
hair.beard(surf, b, bstyle, hair.hair_material("BeardM", melanin=1.0, redness=0.1, grey=0.3), rng, count=8000)
print("build", time.time() - t0)
rig.setup_render(samples=samples)
cam = rig.camera(lm, head_frac=0.47)
H.aim_eyes(b["eyes"], cam.location, 0.15)
rig.lights(cam, lm["eye_c"])
dt = rig.render(out)
print("render", dt)

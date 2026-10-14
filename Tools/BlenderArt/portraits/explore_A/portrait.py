"""Approach A portrait generator: spec -> MakeHuman identity -> strands/costume -> Cycles ->
digital-painting finish.

    blender -b --factory-startup -noaudio -P portrait.py -- <spec.json> <out_dir> [--samples N]
        [--preview] [--no-paint]

A *spec* (dict / JSON) describes one officer; ``outfits`` and ``hairstyles`` below are the
reusable vocabulary, so 103 officers are 103 small specs (see heroes.py and cast.py).
"""

import json
import math
import os
import subprocess
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import costume as CO  # noqa: E402
import hair as HR  # noqa: E402
import head as H  # noqa: E402
import identity as I  # noqa: E402
import mats as MA  # noqa: E402
import mh  # noqa: E402
import regions as R  # noqa: E402
import rig  # noqa: E402
import shell as SH  # noqa: E402
import skin as SK  # noqa: E402
import skinmaps  # noqa: E402

EYE_PNG = os.path.join(mh.MH_DATA, "eyes", "materials", "brown_eye.png")


def _deep(d, u):
    out = dict(d)
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep(out[k], v)
        else:
            out[k] = v
    return out


DEFAULT = {
    "seed": 1, "gender": "m", "age": 40, "archetype": "warrior",
    "identity": {}, "face": {}, "expr": {}, "expression": None,
    "skin": {"weather": 0.0, "scars": [], "stubble": 0.3},
    "hair": {"style": "topknot", "grey": 0.0, "recede": 0.1, "melanin": 1.0, "count": 7000},
    "brows": {"thick": 1.0, "arch": 1.0, "angle": 0.1, "droop": 0.0, "count": 1000, "length": 1.0},
    "beard": None,
    "outfit": {"kind": "scholar"},
    "headgear": {"kind": "none"},
    "camera": {"yaw": 20.0, "pitch": -3.0, "head_frac": 0.47, "eye_line": 0.38, "x_off": 0.0},
    "light": {},
    "paint": {},
    "bg": "warm",
    "aim": 0.15,
}


# ======================================================================================== hair
def _topknot_fn(surf, b, back=-0.012, up=0.004):
    lm = b["lm"]
    ez, ey = np.array(lm["ez"]), np.array(lm["ey"])
    top = surf.P[np.argmax(surf.P[:, 2])]
    G = top + ez * up - ey * back * -1.0

    def fn(pos, fc, C):
        return [np.tile(G, (len(pos), 1))]
    return fn, G, top


def build_hair(surf, b, spec, rng, coll=None):
    hs = spec["hair"]
    style = hs["style"]
    grey = hs.get("grey", 0.0)
    lm = b["lm"]
    F = b["F"]
    ez, ey, ex = np.array(lm["ez"]), np.array(lm["ey"]), np.array(lm["ex"])
    hm = HR.hair_material("HairM", melanin=hs.get("melanin", 1.0), redness=0.1, grey=grey,
                          roughness=0.3)
    out = {"mat": hm}
    if style in ("none", "bald"):
        return out
    recede = hs.get("recede", 0.1)
    cap_rgb = (0.03, 0.025, 0.022) if grey < 0.5 else (0.35, 0.33, 0.31)
    if style == "helmet":
        # only the hair that shows under a helmet brim: temples, sideburns, nape
        def dens(a):
            az, el = R.head_angles(a["fc"], F)
            return R.scalp(a["fc"], F, recede, 1.5) * R.sstep(25, 8, el)
        HR.hair_cap(surf, b, HR.cap_material("CapM", cap_rgb, grey=grey * 0.6), recede=recede, coll=coll,
                    density=lambda A: np.where(dens(A) > 0.5, 1.0, 0.0))
        fn, G, top = _topknot_fn(surf, b)
        HR.comb(surf, b, hm, rng, fn, count=int(hs.get("count", 7000) * 0.5), recede=recede, density_fn=dens,
                coll=coll, lift=0.0012, volume=0.002, radius=0.00008, K=10)
        return out
    HR.hair_cap(surf, b, HR.cap_material("CapM", cap_rgb, grey=grey * 0.6), recede=recede, coll=coll)
    if style == "topknot":
        fn, G, top = _topknot_fn(surf, b)
        HR.comb(surf, b, hm, rng, fn, count=hs.get("count", 7000), recede=recede, coll=coll,
                lift=0.0014, volume=0.0035, radius=0.00008, K=14, clump_n=hs.get("count", 7000) // 30,
                clump_amt=0.25)
        bun_r = hs.get("bun", 0.017)
        bc = G + ez * bun_r * 0.85
        bun = HR.bun_strands(bc, ez + ey * -0.2, bun_r, bun_r * 0.75, int(1400 * (bun_r / 0.017) ** 2), rng, K=20)
        HR.curves_object("Bun", bun, 0.0001, 0.00004, hm, coll)
        out.update(bun_c=bc, bun_r=bun_r, top=top)
    elif style == "lady":
        # centre parting, sides swept out over the temples ("bin" volume) and up into a high bun
        C = HR.skull_frame(surf, b)
        top = surf.P[np.argmax(surf.P[:, 2])]
        bun_r = hs.get("bun", 0.03)
        G = top + ez * 0.006 - ey * 0.012
        rad = float(np.linalg.norm(top - C))

        def fn(pos, fc, Cc):
            az, el = R.head_angles(fc, F)
            side = np.sign(fc[:, 0] + 1e-6)
            n = len(pos)
            # temple waypoint: out over the upper ear
            a_w = np.radians(np.clip(np.abs(az), 70, 105)) * side
            wdir = np.stack([np.sin(a_w) * 0.93, -np.cos(a_w) * 0.93, np.full(n, 0.37)], 1)
            W1 = Cc + wdir * (rad * 0.92 + hs.get("puff", 0.014))
            W2 = Cc + np.stack([side * 0.55, np.full(n, 0.45), np.full(n, 0.7)], 1) * rad * 1.0
            Gt = np.tile(G, (n, 1)) + side[:, None] * ex[None] * 0.006
            front = (np.abs(az) < 115)[:, None]
            return [np.where(front, W1, (pos + W2) / 2), np.where(front, W2, W2), Gt]
        HR.comb(surf, b, hm, rng, fn, count=hs.get("count", 9000), recede=recede, coll=coll,
                lift=0.0016, volume=0.006, radius=0.00008, K=20, clump_n=hs.get("count", 9000) // 25,
                clump_amt=0.3)
        bc = G + ez * bun_r * 0.8 - ey * 0.004
        bun = HR.bun_strands(bc, ez - ey * 0.35, bun_r, bun_r * 0.7, 2600, rng, K=24, turns=1.4)
        HR.curves_object("Bun", bun, 0.0001, 0.00005, hm, coll)
        # a second, smaller loop leaning back (double-lobed court bun)
        bc2 = bc + ez * bun_r * 0.55 + ey * 0.02 - ex * 0.012
        bun2 = HR.bun_strands(bc2, ey * 0.8 + ez * 0.6, bun_r * 0.7, bun_r * 0.5, 1400, rng, K=20, turns=1.2)
        HR.curves_object("Bun2", bun2, 0.0001, 0.00005, hm, coll)
        out.update(bun_c=bc, bun_r=bun_r, bun_c2=bc2, top=top, G=G)
    return out


# ===================================================================================== outfits
def build_outfit(surf, b, spec, coll=None):
    o = spec["outfit"]
    kind = o.get("kind", "scholar")
    lm = b["lm"]
    sh = SH.Shell(surf, CO.torso_origin(lm))
    fr = CO.Frame(lm)
    res = {"shell": sh, "frame": fr}
    seed = spec["seed"]
    if kind == "armour":
        iron = MA.metal("Iron", o.get("iron", (0.16, 0.16, 0.17)), rough=0.42, patina=0.5)
        trim = MA.metal("Trim", o.get("trim", (0.62, 0.42, 0.16)), rough=0.3, patina=0.35)
        lace = MA.plain("Lace", o.get("lace", (0.07, 0.015, 0.01)), rough=0.65, sheen=0.3)
        silk = MA.silk("Silk", o.get("silk", (0.20, 0.016, 0.012)), sheen=0.25, motif="clouds",
                       motif_rgb=(0.45, 0.25, 0.08))
        inner = MA.silk("Inner", (0.62, 0.58, 0.5), sheen=0.3)
        band = MA.brocade("Band", (0.05, 0.035, 0.03), (0.55, 0.38, 0.14))
        CO.cross_robe(sh, fr, [dict(mat=inner, band_mat=inner, offset=0.004, depth=0.09, band=0.016, el_bottom=-25, folds=0),
                               dict(mat=silk, band_mat=band, offset=0.008, depth=0.12, band=0.026, el_bottom=-30)], coll=coll, seed=seed)
        cut = CO.round_cut(fr, drop=o.get("neck_drop", 0.025))
        cut2 = lambda az: cut(az) + 0.012 * np.clip(np.abs(np.sin(np.radians(az))), 0, 1)  # noqa: E731
        CO.lamellar(sh, iron, lace, cut2, offset=0.017, row_h=0.038, plate_w=0.021, s_max=0.34,
                    az_range=(-178, 178), edge_mat=trim, seed=seed, coll=coll)
        for sd in (1, -1):
            CO.pauldron(sh, sd, iron, lace, trim, offset=0.033, fr=fr, coll=coll, seed=seed + sd)
        if o.get("scarf", True):
            CO.neck_scarf(sh, cut2, silk, offset=0.019, height=0.03, rise=0.006, coll=coll)
        if o.get("mirror", True):
            CO.chest_mirror(sh, fr, MA.metal("Mirror", (0.62, 0.5, 0.36), rough=0.18, patina=0.25),
                            trim, offset=0.032, z=fr.notch - 0.135, coll=coll)
        res["mats"] = dict(iron=iron, trim=trim, silk=silk)
    elif kind == "none":
        return res
    elif kind in ("scholar", "sage", "lady"):
        outer_rgb = o.get("outer", (0.03, 0.06, 0.09))
        mid_rgb = o.get("mid", (0.35, 0.06, 0.05))
        inner_rgb = o.get("inner", (0.72, 0.68, 0.6))
        outer = MA.silk("Outer", outer_rgb, sheen=o.get("sheen", 0.35), motif=o.get("motif", "roundels"),
                        motif_rgb=o.get("motif_rgb", (0.5, 0.36, 0.14)), motif_scale=o.get("motif_scale", 7.0))
        mid = MA.silk("Mid", mid_rgb, sheen=0.4)
        inner = MA.silk("Inner", inner_rgb, sheen=0.3)
        band_rgb = o.get("band", (0.06, 0.05, 0.045))
        band = MA.brocade("Band", band_rgb, o.get("band_thread", (0.6, 0.45, 0.2)), o.get("band_motif", "fret"))
        depth = o.get("depth", 0.15)
        layers = [dict(mat=inner, band_mat=inner, offset=0.004, depth=depth * 0.6, band=0.014, el_bottom=-20, folds=0),
                  dict(mat=mid, band_mat=mid, offset=0.0075, depth=depth * 0.8, band=0.016, el_bottom=-25, folds=0.0015),
                  dict(mat=outer, band_mat=band, offset=0.012, depth=depth, band=o.get("band_w", 0.032),
                       folds=0.003, w=o.get("w", 52.0))]
        if kind == "sage":
            layers[2]["band_mat"] = MA.silk("SageBand", o.get("band", (0.62, 0.58, 0.5)), sheen=0.3)
        CO.cross_robe(sh, fr, layers, coll=coll, seed=seed)
        if kind == "lady" and o.get("shawl", True):
            shawl = MA.silk("Shawl", o.get("shawl_rgb", (0.75, 0.55, 0.45)), sheen=0.6, motif="lattice",
                            motif_rgb=(0.85, 0.7, 0.4), motif_scale=14.0)
            _shawl(sh, fr, shawl, coll)
        res["mats"] = dict(outer=outer, band=band)
    return res


def _shawl(sh, fr, mat, coll):
    """Pibo: a light silk shawl lying across the shoulders and falling down the upper arms."""
    for side in (1, -1):
        pa = np.array([side * 150, side * 120, side * 95, side * 72, side * 60])
        pz = np.array([fr.back - 0.035, fr.side - 0.025, fr.side - 0.05, fr.side - 0.12, fr.side - 0.25])
        ob, *_ = sh.strip("Shawl%d" % side, pa, pz, 0.075, 0.03, mat, coll, n=80, thick=0.006)
        ob.pass_index = 5


# =================================================================================== headgear
def build_headgear(surf, b, spec, hair_info, coll=None):
    hg = spec["headgear"]
    kind = hg.get("kind", "none")
    lm = b["lm"]
    ez, ey, ex = np.array(lm["ez"]), np.array(lm["ey"]), np.array(lm["ex"])
    if kind == "helmet":
        bowl = MA.metal("HelmIron", hg.get("bowl", (0.17, 0.17, 0.18)), rough=0.33, patina=0.4)
        trim = MA.metal("HelmTrim", hg.get("trim", (0.66, 0.46, 0.18)), rough=0.26, patina=0.3)
        mats = dict(bowl=bowl, trim=trim, rivet=trim, flap=MA.scales("Flap", lace_rgb=hg.get("lace", (0.2, 0.02, 0.015))),
                    tassel=MA.tassel(rgb=hg.get("tassel", (0.22, 0.008, 0.006))))
        C = HR.skull_frame(surf, b)
        CO.helmet(surf, b, C, mats, coll=coll, seed=spec["seed"], tassel=hg.get("tassel_on", True),
                  brim_raise=hg.get("brim_raise", 0.0))
    elif kind in ("guan", "crown"):
        crown = MA.plain("Crown", hg.get("rgb", (0.02, 0.018, 0.016)), rough=0.3, coat=0.8)
        pin = MA.metal("PinGold", hg.get("pin", (0.7, 0.5, 0.2)), rough=0.25) if hg.get("pin_metal", True) else MA.jade()
        bc = hair_info.get("bun_c")
        if bc is not None:
            CO.topknot_crown(bc + ez * 0.004, ez, -ey, dict(crown=crown, pin=pin), coll=coll, size=hg.get("size", 1.0))
    elif kind == "pins":
        gold = MA.metal("PinGold", (0.75, 0.55, 0.22), rough=0.22, patina=0.15)
        mats = dict(gold=gold, petal=MA.jade("Petal", hg.get("petal", (0.7, 0.25, 0.3))), pearl=MA.pearl(),
                    jade=MA.jade())
        rng = np.random.default_rng(spec["seed"] + 5)
        bc = hair_info.get("bun_c")
        br = hair_info.get("bun_r", 0.03)
        if bc is not None:
            # three pins fanned through the bun, one buyao with dangles on the key side
            for k, (a, el) in enumerate(((-35, 20), (10, 35), (55, 15))):
                d = np.cos(np.radians(el)) * (np.cos(np.radians(a)) * ex + np.sin(np.radians(a)) * -ey) + np.sin(np.radians(el)) * ez
                p0 = bc - d * br * 0.6
                CO.hairpin(p0, d, br * 1.9, mats, coll, head="flower" if k != 1 else "ball", rng=rng, scale=1.1)
            d = -ex * 0.7 + ez * 0.5 - ey * 0.3
            CO.hairpin(bc + ex * br * 0.5, d, br * 1.7, mats, coll, head="flower", dangles=3, rng=rng, scale=1.2)
            # front comb ornament (gold arc over the forehead side of the bun)
            fr_pt = bc - ey * br * 0.95 + ez * br * 0.1
            CO.hairpin(fr_pt - ex * br * 0.6, ex, br * 1.2, mats, coll, head="flower", rng=rng, scale=0.9)


def earrings(b, spec, coll=None):
    lm = b["lm"]
    ez = np.array(lm["ez"])
    gold = bpy.data.materials.get("PinGold") or MA.metal("PinGold", (0.75, 0.55, 0.22), rough=0.22)
    pearl = bpy.data.materials.get("Pearl") or MA.pearl()
    masks = b["masks"]
    Vb = b["Vb"][:mh.N_BODY]
    for side in (1, -1):
        em = (masks["m_ear"][:mh.N_BODY] > 0.3) & (np.sign(Vb[:, 0]) == side)
        pts = Vb[em]
        lobe = pts[np.argmin(pts[:, 2])] + np.array([0, -0.002, 0.004])
        chain = np.linspace(lobe, lobe - ez * 0.016, 5)
        HR.curves_object("EarChain", [chain], 0.0005, 0.0005, gold, coll, pass_index=7)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.0042, location=tuple(chain[-1] - ez * 0.004))
        pe = bpy.context.active_object
        pe.data.materials.append(pearl)
        pe.pass_index = 7
        for p in pe.data.polygons:
            p.use_smooth = True


# ======================================================================================= build
def make_identity(spec):
    idn = I.make_identity(spec["seed"], spec["gender"], spec["age"], spec["archetype"])
    for k, v in spec.get("identity", {}).items():
        setattr(idn, k, v)
    for k, v in spec.get("face", {}).items():
        idn.face[k] = idn.face.get(k, 0.0) + v
    if spec.get("expression"):
        idn.expression = spec["expression"]
    idn.expr_extra = dict(spec.get("expr", {}))
    return idn


def build(spec, out_dir, tag, samples=40, preview=False):
    spec = _deep(DEFAULT, spec)
    times = {}
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    idn = make_identity(spec)
    b = H.build(idn)
    lm = b["lm"]
    rng = np.random.default_rng(spec["seed"])
    # ---- skin
    hs = spec["hair"]
    grey = hs.get("grey", 0.0)
    hair_rgb = (0.04, 0.035, 0.03) if grey < 0.5 else (0.45, 0.43, 0.41)
    sk = dict(spec["skin"])
    style = {"hair_rgb": hair_rgb, "recede": hs.get("recede", 0.1), "scalp": hs["style"] not in ("bald",),
             "shaved": 1.0 if hs["style"] == "bald" else 0.0, "beard": spec["beard"],
             "beard_rgb": hair_rgb, "brow": {k: spec["brows"][k] for k in ("thick", "arch", "angle")},
             "weather": sk.get("weather", 0.0), "scars": sk.get("scars", []), "stubble": sk.get("stubble", 0.3),
             "huadian": sk.get("huadian", False)}
    A, Rg, Hh = skinmaps.make(b, idn, style, seed=spec["seed"])
    b["head"].data.materials.append(SK.skin_material_tex(
        idn, skinmaps.to_bpy("SkinA", A), skinmaps.to_bpy("SkinR", Rg, "Non-Color"),
        skinmaps.to_bpy("SkinH", Hh, "Non-Color", float_buffer=True)))
    b["head"].pass_index = rig.PASS["skin"]
    em, ec = SK.eye_materials(EYE_PNG, iris_dark=spec.get("iris", 0.5))
    for e in b["eyes"]:
        e.data.materials.append(em)
        e.data.materials.append(ec)
        e.pass_index = rig.PASS["eyes"]
    times["head"] = time.time() - t0
    # ---- strands
    t1 = time.time()
    surf = HR.Surface(b["head"])
    hinfo = build_hair(surf, b, spec, rng)
    br = spec["brows"]
    brow_mat = HR.hair_material("BrowM", melanin=hs.get("melanin", 1.0), redness=0.1,
                                grey=min(1.0, grey * br.get("grey_mul", 1.0)), roughness=0.35)
    HR.brows(surf, b, brow_mat, rng, count=br.get("count", 1000), thick=br["thick"], arch=br["arch"],
             angle=br["angle"], length=br.get("length", 1.0), droop=br.get("droop", 0.0),
             hair_len=br.get("hair_len", 0.009))
    HR.lashes(surf, b, b["eyes"], HR.hair_material("LashM", melanin=1.0, roughness=0.45), rng,
              length=spec.get("lash_len", 0.0075 if idn.female else 0.006))
    times["hair"] = time.time() - t1
    # ---- costume
    t2 = time.time()
    outfit = build_outfit(surf, b, spec)
    build_headgear(surf, b, spec, hinfo)
    if spec["outfit"].get("earrings"):
        earrings(b, spec)
    times["costume"] = time.time() - t2
    # beard last: it drapes over the costume
    if spec["beard"]:
        t3 = time.time()
        bd = dict(spec["beard"])
        cols = [o for o in bpy.data.objects if o.type == "MESH" and (o.name.startswith("Robe") or o.name.startswith("Lamellar") or o.name.startswith("Collar") or o.name.startswith("Mirror"))]
        bsurf = HR.Surface(b["head"], colliders=cols)
        bgrey = spec.get("beard_grey", grey)
        bm = HR.hair_material("BeardM", melanin=min(0.95, hs.get("melanin", 1.0)), redness=0.12, grey=bgrey,
                              roughness=0.26)
        HR.beard(bsurf, b, bd, bm, rng, count=bd.get("count", 8000))
        times["beard"] = time.time() - t3
    # ---- camera, lights
    cam_s = spec["camera"]
    rig.setup_render(samples=samples if not preview else 16, ss=2)
    hh = None
    cam = rig.camera(lm, yaw=cam_s["yaw"], pitch=cam_s["pitch"], head_frac=cam_s["head_frac"],
                     eye_line=cam_s["eye_line"], x_off=cam_s.get("x_off", 0.0))
    if spec.get("lab_res"):
        sc = bpy.context.scene
        sc.render.resolution_x, sc.render.resolution_y = spec["lab_res"]
    H.aim_eyes(b["eyes"], cam.location, spec.get("aim", 0.15), lift=spec.get("aim_lift", 0.0))
    rig.lights(cam, lm["eye_c"], **spec["light"])
    rig.compositor(out_dir, tag)
    times["build"] = time.time() - t0
    return spec, times


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    spec = json.load(open(args[0]))
    out_dir = args[1]
    samples = int(args[args.index("--samples") + 1]) if "--samples" in args else 40
    preview = "--preview" in args
    tag = spec.get("id", "portrait")
    os.makedirs(out_dir, exist_ok=True)
    spec2, times = build(spec, out_dir, tag, samples, preview)
    raw = os.path.join(out_dir, tag + "_raw.png")
    times["render"] = rig.render(raw)
    if "--blend" in args:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, tag + ".blend"))
    if "--no-paint" not in args:
        t = time.time()
        final = os.path.join(out_dir, tag)
        cmd = ["python3", os.path.join(HERE, "paint.py"), out_dir, tag, final, "--bg", spec2.get("bg", "warm"),
               "--seed", str(spec2["seed"]), "--params", json.dumps(spec2.get("paint", {}))]
        subprocess.run(cmd, check=True)
        times["paint"] = time.time() - t
    times["total"] = sum(v for k, v in times.items() if k in ("build", "render", "paint"))
    print("[portrait] %s TIMES %s" % (tag, {k: round(v, 1) for k, v in times.items()}))
    with open(os.path.join(out_dir, tag + "_times.json"), "w") as f:
        json.dump({k: round(v, 2) for k, v in times.items()}, f)


if __name__ == "__main__":
    main()

"""Face canon of gongbi_C: the classical figure-painting vocabulary as parameters.

Faces are designed from the gongbi canon itself (never from any ethnicity morph): heroic
generals with 卧蚕 / sword brows and wide-open eyes, scholars with long 丹凤 phoenix eyes,
ladies with willow-leaf brows and bright almond eyes, elders with long white 寿眉 brows.

Units: head units (crown-to-chin = 1) in head-local x / z (eye line z = 0); eye shapes are in
eye widths.  Every preset keeps the eyes clearly OPEN: ``open`` (upper-lid height / eye
width) >= 0.30, the iris and its highlight always drawn - :func:`check` asserts it.
"""

import copy

# --------------------------------------------------------------------------------------- eyes
EYES = {
    # long phoenix eye: outer corner lifted, long tapering tail, apex towards the inner third
    "phoenix": dict(w=0.138, open=0.33, lo=0.13, tilt=0.10, peak=-0.12, round=0.85,
                    tail=0.10, tail_lift=0.04, crease=0.085, crease_a=0.40, iris=0.205,
                    line=2.0, lower_a=0.45, iris_up=0.03),
    # bright almond eye
    "almond": dict(w=0.134, open=0.37, lo=0.15, tilt=0.05, peak=-0.06, round=0.85,
                   tail=0.07, tail_lift=0.02, crease=0.095, crease_a=0.45, iris=0.215,
                   line=2.0, lower_a=0.45, iris_up=0.02),
    # wide-open fierce eye of a general (环眼 tempered): rounder, strong lid, a little sclera
    "tiger": dict(w=0.136, open=0.38, lo=0.16, tilt=0.05, peak=-0.06, round=1.05,
                  tail=0.07, tail_lift=0.015, crease=0.085, crease_a=0.5, iris=0.21,
                  line=2.5, lower_a=0.6, iris_up=0.05),
    # steady eye of a seasoned man
    "steady": dict(w=0.132, open=0.35, lo=0.14, tilt=0.04, peak=-0.06, round=0.9,
                   tail=0.07, tail_lift=0.0, crease=0.09, crease_a=0.45, iris=0.21,
                   line=2.1, lower_a=0.5, iris_up=0.02),
    # kindly elder: softened, slightly hooded but clearly open, smile lines
    "kind": dict(w=0.128, open=0.32, lo=0.13, tilt=0.02, peak=-0.02, round=0.95,
                 tail=0.06, tail_lift=-0.01, crease=0.075, crease_a=0.55, iris=0.205,
                 line=1.9, lower_a=0.5, iris_up=0.0, hood=0.5),
}

# ------------------------------------------------------------------------------------- brows
#: x0/z0 inner head, x1/z1 tail, peak (fraction, height above the chord), thickness profile
BROWS = {
    "silkworm": dict(x0=0.050, z0=0.074, x1=0.262, z1=0.112, peak=(0.58, 0.020), thick=0.048,
                     shape="silkworm", hairs=1.5, wash=0.80),
    "sword": dict(x0=0.055, z0=0.078, x1=0.262, z1=0.135, peak=(0.60, 0.010), thick=0.032,
                  shape="sword", hairs=1.0, wash=0.58),
    "willow": dict(x0=0.062, z0=0.090, x1=0.250, z1=0.098, peak=(0.42, 0.028), thick=0.017,
                   shape="willow", hairs=0.55, wash=0.50),
    "crescent": dict(x0=0.060, z0=0.088, x1=0.245, z1=0.090, peak=(0.48, 0.030), thick=0.020,
                     shape="willow", hairs=0.7, wash=0.48),
    "calm": dict(x0=0.058, z0=0.086, x1=0.250, z1=0.100, peak=(0.50, 0.020), thick=0.026,
                 shape="even", hairs=0.9, wash=0.52),
    "longevity": dict(x0=0.055, z0=0.090, x1=0.255, z1=0.070, peak=(0.40, 0.018),
                      thick=0.030, shape="longevity", hairs=1.2, wash=0.35, droop=0.075),
}

# ------------------------------------------------------------------------------------- noses
NOSES = {
    "straight": dict(tip_z=-0.185, tip_w=0.033, ala_w=0.064, top_z=0.035, prot=0.085,
                     hook=0.0, line=1.0),
    "strong": dict(tip_z=-0.192, tip_w=0.038, ala_w=0.072, top_z=0.04, prot=0.095,
                   hook=0.25, line=1.15),
    "small": dict(tip_z=-0.175, tip_w=0.028, ala_w=0.054, top_z=0.025, prot=0.07,
                  hook=0.0, line=0.85),
    "broad": dict(tip_z=-0.19, tip_w=0.040, ala_w=0.078, top_z=0.035, prot=0.085,
                  hook=0.0, line=1.1),
}

# ------------------------------------------------------------------------------------ mouths
MOUTHS = {
    "firm": dict(z=-0.288, w=0.098, upper=0.022, lower=0.030, corner=-0.004, bow=0.006,
                 color="#B06A5E", alpha=0.45, line=1.0),
    "cherry": dict(z=-0.282, w=0.070, upper=0.028, lower=0.036, corner=0.003, bow=0.008,
                   color="#C0393B", alpha=0.85, line=0.9),
    "gentle": dict(z=-0.286, w=0.088, upper=0.022, lower=0.030, corner=0.002, bow=0.006,
                   color="#B87064", alpha=0.45, line=0.95),
    "elder": dict(z=-0.29, w=0.090, upper=0.016, lower=0.026, corner=0.0, bow=0.004,
                  color="#B07A6E", alpha=0.35, line=0.9),
}

FACE_DEFAULT = dict(
    eye="steady", brow="calm", nose="straight", mouth="gentle",
    eye_x=0.142, eye_z=0.0,
    gaze=0.75,                 # 0 = straight ahead in the head frame, 1 = at the viewer
    gaze_v=0.0,
    rouge=dict(color="#D98880", alpha=0.14, x=0.175, z=-0.12, r=0.12),
    eye_rouge=0.0,             # 桃花妆: rouge round the eyes (ladies)
    whites=0.22,               # 三白: lead-white glaze on forehead, nose bridge and chin
    socket=0.22,               # 眼窝 shading
    wrinkles=dict(forehead=0, crow=0, naso=0.0, bags=0.0, knit=0, mouth=0.0),
    line="skin_line",
    mark=None,                 # 花钿 forehead mark
)


def face(spec):
    """Resolve a spec's ``face`` dict against the presets (deep-merged)."""
    f = copy.deepcopy(FACE_DEFAULT)
    src = spec.get("face", {})
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(f.get(k), dict):
            f[k].update(v)
        else:
            f[k] = v
    e = dict(EYES[f["eye"]] if isinstance(f["eye"], str) else f["eye"])
    e.update(src.get("eye_mod", {}))
    b = dict(BROWS[f["brow"]] if isinstance(f["brow"], str) else f["brow"])
    b.update(src.get("brow_mod", {}))
    n = dict(NOSES[f["nose"]] if isinstance(f["nose"], str) else f["nose"])
    n.update(src.get("nose_mod", {}))
    m = dict(MOUTHS[f["mouth"]] if isinstance(f["mouth"], str) else f["mouth"])
    m.update(src.get("mouth_mod", {}))
    f.update(eyeP=e, browP=b, noseP=n, mouthP=m)
    check(f)
    return f


def check(f):
    """Hard face-design rules (the user's veto): eyes open, iris drawn, no slits."""
    e = f["eyeP"]
    assert e["open"] >= 0.30, "eyes must stay clearly open (open >= 0.30)"
    assert e["open"] <= 0.48, "eyes must not bulge (open <= 0.48)"
    assert e["iris"] >= 0.18, "iris must read (radius >= 0.18 eye widths)"
    assert 0.11 <= e["w"] <= 0.15, "eye width within the canon"
    assert -0.02 <= e["tilt"] <= 0.14, "outer-corner lift within the canon"

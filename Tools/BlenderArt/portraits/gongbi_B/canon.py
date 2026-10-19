"""The face canon as data + the hard gate every portrait passes before it is rendered.

Faces in this system are built ONLY from the classical figure-painting vocabulary (三庭五眼
proportions, 丹凤/杏/环眼 eyes, 剑/卧蚕/柳叶/寿眉 brows ...).  There is no ethnicity, race or
'type' parameter anywhere, and :func:`policy_guard` refuses any spec that tries to introduce one.

:func:`check` is the user's face-design rules as assertions (run over all 103 keys by
``cast.py --check`` and before every render):

* eyes clearly open: upper-lid height >= 0.32 eye widths, whole aperture >= 0.42, and never
  bulging (upper-lid height <= 0.40)
* iris and highlight always drawn, iris 0.40-0.50 of the eye width
* the iris is tucked under the upper lid (no white above it: no stare), even with a downward
  gaze; outer-corner tilt and eye width inside the canon
* no 'sly' face: steeply knitted brows + side-glance + downturned mouth never come together;
  the gaze is never a strong side-glance
* skin inside the warm ivory / peach / ochre gamut (never yellow, grey or orange)
"""

import colorsys

import numpy as np

import face as facemod

# ---------------------------------------------------------------------------------------------
# head-shape families (painters' face types 面型), as Head shape multipliers

HEAD_FAMILIES = {
    # 国字脸 square: broad jaw and chin, the heroic general
    "square": dict(width=1.03, jaw=1.13, chin=1.12, cheekbone=1.1, forehead=1.0, oval=0.0),
    # 甲字/长方 long rectangular: long, even width, firm chin
    "rect": dict(width=0.96, jaw=1.06, chin=1.04, cheekbone=0.9, chin_len=1.02, oval=0.0),
    # 圆脸 round: wide, full cheeks, soft jaw
    "round": dict(width=1.05, jaw=1.02, chin=1.0, cheekbone=0.7, round=0.6, oval=0.6,
                  oval_p=2.6, chin_len=0.97),
    # 鹅蛋 egg oval: the scholar's and court lady's face
    "oval": dict(width=0.97, jaw=0.98, chin=0.96, cheekbone=0.8, oval=0.8, oval_p=2.4),
    # 由字/菱形 diamond: high cheekbones, narrower brow and jaw
    "diamond": dict(width=1.0, jaw=0.95, chin=0.95, cheekbone=1.45, forehead=0.95, oval=0.3),
    # 倒三角 triangular: broad brow, narrowing to a neat chin (rogues, sharp minds)
    "triangle": dict(width=1.0, jaw=0.94, chin=0.90, cheekbone=1.0, forehead=1.04, oval=0.4,
                     oval_p=2.1),
    # ladies
    "egg": dict(width=0.94, jaw=0.97, chin=0.95, cheekbone=0.6, chin_fwd=0.85, round=0.3,
                chin_len=0.97, oval=1.0, oval_p=2.6),
    "full_egg": dict(width=0.97, jaw=1.0, chin=0.98, cheekbone=0.5, chin_fwd=0.85, round=0.5,
                     chin_len=0.96, oval=1.0, oval_p=2.8),
    "heart": dict(width=0.95, jaw=0.95, chin=0.90, cheekbone=0.7, chin_fwd=0.85, forehead=1.03,
                  round=0.2, chin_len=0.975, oval=1.0, oval_p=2.2),
    "long_egg": dict(width=0.92, jaw=0.96, chin=0.95, cheekbone=0.6, chin_fwd=0.85, round=0.2,
                     chin_len=0.99, oval=1.0, oval_p=2.5),
}

FAMILIES_BY_ARCH = {
    "m_warrior": ["square", "rect", "round", "diamond", "square"],
    "m_scholar": ["oval", "rect", "diamond", "oval", "triangle"],
    "m_elder": ["oval", "diamond", "rect", "round"],
    "m_monk": ["round", "square", "oval"],
    "m_rogue": ["triangle", "diamond", "square", "rect"],
    "f_warrior": ["egg", "heart", "long_egg", "egg"],
    "f_scholar": ["egg", "full_egg", "heart", "long_egg"],
    "f_elder": ["full_egg", "egg", "long_egg"],
}

# ---------------------------------------------------------------------------------------------
# expression presets (神态): offsets applied to a face; all keep the eyes open and the gaze
# towards the viewer

EXPRESSIONS = {
    "calm": dict(brow_knit=0.0, smile=0.05, frown=0.0),
    "stern": dict(brow_knit=0.45, smile=-0.25, frown=0.4, gaze_min=0.5),
    "fierce": dict(brow_knit=0.85, brow_lift_add=0.008, smile=-0.30, frown=0.8, eye_h_add=0.02,
                   gaze_min=0.55),
    "gentle": dict(brow_knit=-0.2, smile=0.35, frown=0.0),
    "thoughtful": dict(brow_knit=0.2, smile=0.05, frown=0.15, gaze_y=0.3),
    "confident": dict(brow_knit=0.1, smile=0.22, brow_lift_add=0.006),
    "proud": dict(brow_knit=0.15, smile=0.10, brow_lift_add=0.010, eye_h_add=-0.01),
    "kindly": dict(brow_knit=-0.3, smile=0.40, frown=0.0, eye_h_add=-0.01),
    "determined": dict(brow_knit=0.40, smile=0.0, frown=0.2, gaze_min=0.55),
}

EXPRESSIONS_BY_ARCH = {
    "m_warrior": ["stern", "fierce", "calm", "proud", "determined", "confident"],
    "m_scholar": ["calm", "gentle", "thoughtful", "confident", "calm"],
    "m_elder": ["kindly", "calm", "stern", "thoughtful"],
    "m_monk": ["calm", "kindly", "stern", "gentle"],
    "m_rogue": ["confident", "proud", "fierce", "calm", "determined"],
    "f_warrior": ["determined", "calm", "proud", "confident"],
    "f_scholar": ["gentle", "calm", "confident", "thoughtful", "gentle"],
    "f_elder": ["kindly", "calm", "gentle"],
}


def apply_expression(F, name):
    e = EXPRESSIONS[name]
    F.brow_knit = e.get("brow_knit", F.brow_knit)
    F.smile = e.get("smile", F.smile)
    F.frown = e.get("frown", F.frown)
    F.brow_lift = F.brow_lift + e.get("brow_lift_add", 0.0)
    F.eye_h = float(np.clip(F.eye_h + e.get("eye_h_add", 0.0), 0.32, 0.40))
    if "gaze_min" in e:
        F.gaze = (max(F.gaze[0], e["gaze_min"]), F.gaze[1])
    if "gaze_y" in e:
        F.gaze = (F.gaze[0], e["gaze_y"])
    # knitted brows over a downturned mouth must look straight out (stern, never sly)
    if F.brow_knit > 0.6 and F.smile < -0.2:
        F.gaze = (max(F.gaze[0], 0.52), F.gaze[1])
    return F


# ---------------------------------------------------------------------------------------------
# policy guard: no ethnicity concept may ever enter a spec

FORBIDDEN = {"asian", "african", "caucasian", "ethnic", "ethnicity", "race", "races", "racial",
             "oriental", "makehuman", "macro", "macros"}


def _tokens(x):
    import re
    return set(t for t in re.split(r"[^a-z0-9]+", str(x).lower()) if t)


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + "/" + str(k), k, v
            yield from _walk(v, path + "/" + str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, path + "[%d]" % i)
    elif hasattr(obj, "__dataclass_fields__"):
        for k in obj.__dataclass_fields__:
            v = getattr(obj, k)
            yield path + "." + k, k, v
            yield from _walk(v, path + "." + k)


def policy_guard(ch):
    """Raise if any key or string value of a character spec names an ethnicity/race concept
    (regression guard: such a parameter must never exist in this system)."""
    for p, k, v in _walk(ch):
        bad = _tokens(k) & FORBIDDEN
        if bad:
            raise ValueError("policy: forbidden key %r at %s (faces come only from the canon)"
                             % (k, p))
        if isinstance(v, str):
            bad = _tokens(v) & FORBIDDEN
            if bad:
                raise ValueError("policy: forbidden value %r at %s" % (v, p))


# ---------------------------------------------------------------------------------------------
# the hard gate


def _hex(c):
    from palette import srgb
    return srgb(c)


def skin_ok(c):
    r, g, b = _hex(c)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    hue = h * 360
    # warm ivory / peach / weathered ochre: a red-orange hue, moderate chroma, light value
    return (8.0 <= hue <= 32.0) and (0.10 <= s <= 0.42) and (v >= 0.78) and (r > g > b)


def eye_aperture(F):
    T = facemod.EYES[F.eye]
    U = facemod.g.catmull(T["U"], n=20)
    L = facemod.g.catmull(T["L"], n=20)
    u = np.linspace(0.05, 0.95, 50)
    up = np.interp(u, U[:, 0], U[:, 1])
    lo = np.interp(u, L[:, 0], L[:, 1])
    return float((up - lo).max() * F.eye_h)


def check(ch):
    """Raise AssertionError if a character breaks the face-design rules."""
    policy_guard(ch)
    F = ch.face
    k = ch.key
    assert F.eye in facemod.EYES, "%s: unknown eye template" % k
    assert F.eye_h >= 0.32, "%s: eyes must be clearly open (eye_h %.3f < 0.32)" % (k, F.eye_h)
    assert F.eye_h <= 0.40, "%s: eyes must not bulge (eye_h %.3f > 0.40)" % (k, F.eye_h)
    ap = eye_aperture(F)
    assert ap >= 0.42, "%s: eye aperture %.3f < 0.42 of the eye width" % (k, ap)
    assert 0.40 <= F.iris <= 0.50, "%s: iris %.2f outside 0.40-0.50" % (k, F.iris)
    assert 0.118 <= F.eye_w <= 0.140, "%s: eye width %.3f outside the canon" % (k, F.eye_w)
    assert -0.02 <= F.eye_tilt <= 0.13, "%s: eye tilt %.3f outside the canon" % (k, F.eye_tilt)
    # iris tucked under the upper lid: no sclera above it, even with a downward gaze
    ri_px = F.iris * F.eye_w * 230.0 / 2
    assert 0.20 <= F.iris_tuck <= 0.45, "%s: iris tuck %.2f" % (k, F.iris_tuck)
    assert F.iris_tuck * ri_px - F.gaze[1] >= 0.15 * ri_px, "%s: white above the iris" % k
    assert 0.30 <= F.gaze[0] <= 0.80, "%s: gaze %.2f is a side-glance" % (k, F.gaze[0])
    assert -0.3 <= F.brow_knit <= 1.3 and F.smile >= -0.6, "%s: expression out of range" % k
    sly = F.brow_knit > 0.6 and F.smile < -0.2 and F.gaze[0] < 0.5
    assert not sly, "%s: knitted brows + side-glance + downturned mouth (sly look)" % k
    assert skin_ok(F.skin if F.skin.startswith("#") else _named(F.skin)), \
        "%s: skin %s outside the warm ivory/peach/ochre gamut" % (k, F.skin)
    return True


def _named(name):
    from palette import P
    return P[name]


def check_drawn(fd, key="?"):
    """Second gate on the DRAWN eyes (after layout and head turn): both eyes open, the iris
    tucked under the upper lid (no white above it), resting on or near the lower lid (no
    staring white below it), highlight drawn."""
    for side in ("near", "far"):
        m = fd.lm.get("eye_metrics_" + side)
        assert m is not None, "%s: %s eye not drawn" % (key, side)
        open_ = (m["lower_y"] - m["upper_y"]) / max(m["eye_w"], 1e-6)
        assert open_ >= 0.30, "%s: %s eye opening %.2f < 0.30 of its drawn width" % (key, side, open_)
        assert m["iris_top"] < m["upper_y"], "%s: white above the %s iris" % (key, side)
        assert m["lower_y"] - m["iris_bottom"] <= 0.45 * m["iris_r"], \
            "%s: %s iris floats high (white below it)" % (key, side)
        assert m["highlight"], "%s: %s eye has no highlight" % (key, side)
    return True

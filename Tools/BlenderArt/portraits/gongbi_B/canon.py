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
* the eye types keep their canon: 环眼 'fierce' (generals) round and open >= 0.35; 丹凤
  'phoenix' (scholars) long (>= 0.13) with a lifted tail (>= 0.12), still open >= 0.32
* the 'wise old Chinaman / wispy-goatee sage' cartoon can never be assembled:
    - moustaches are 八字 (ends level with or above the mouth corners, turned out), brushed
      up, or merged into a full beard - never drooping to points below the mouth corners
    - a short goatee is >= 0.35 of the mouth width at its end and joined to the moustache by
      a sparse chin beard (no isolated narrow chin tuft)
    - hairlines curve (soft arch, temple recession or a slight widow's peak): the forehead
      hairline departs >= 0.08 head units from a straight edge, with combed strands
    - face width <= 0.82 of face height (hairline to chin) for scholars and elders, and broad
      faces carry 晕染 structure under the cheekbones and along the jaw
    - :func:`stereotype_flags` scores drooping whiskers, a bowl hairline and a broad flat face
      on every key; any two together fail the gate even if each alone is near its limit
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
    # ladies (all with the near-side jaw drawn in and a soft chin, see face.outline)
    # 鹅蛋脸 egg: the classic oval
    "egg": dict(width=0.94, jaw=0.97, chin=0.95, cheekbone=0.6, chin_fwd=0.85, round=0.3,
                chin_len=0.97, oval=1.0, oval_p=2.6, near_jaw=0.07, chin_point=0.35),
    # 圆润 round-oval: shorter and fuller, round cheeks, a small rounded chin
    "full_egg": dict(width=0.98, jaw=1.0, chin=0.97, cheekbone=0.5, chin_fwd=0.85, round=0.7,
                     chin_len=0.935, oval=1.0, oval_p=2.9, near_jaw=0.06, chin_point=0.15),
    # 瓜子脸 heart: a fuller brow and cheek tapering to a neat pointed chin
    "heart": dict(width=0.95, jaw=0.93, chin=0.86, cheekbone=0.8, chin_fwd=0.85, forehead=1.02,
                  round=0.15, chin_len=0.975, oval=1.0, oval_p=2.1, near_jaw=0.09, chin_point=0.7),
    # 长圆 longer oval: narrower and longer, a gentle jaw
    "long_egg": dict(width=0.90, jaw=0.96, chin=0.94, cheekbone=0.7, chin_fwd=0.85, round=0.15,
                     chin_len=1.0, oval=1.0, oval_p=2.4, near_jaw=0.08, chin_point=0.4),
    # matron: fuller, softer jaw (jowl), the chin less defined
    "matron": dict(width=0.98, jaw=1.04, chin=1.0, cheekbone=0.6, chin_fwd=0.92, round=0.4,
                   chin_len=0.98, oval=0.75, oval_p=2.5, near_jaw=0.04),
}

FAMILIES_BY_ARCH = {
    "m_warrior": ["square", "rect", "round", "diamond", "square"],
    "m_scholar": ["oval", "rect", "diamond", "oval", "triangle"],
    "m_elder": ["oval", "diamond", "rect", "round"],
    "m_monk": ["round", "square", "oval"],
    "m_rogue": ["triangle", "diamond", "square", "rect"],
    "f_warrior": ["egg", "heart", "long_egg", "full_egg"],
    "f_scholar": ["egg", "full_egg", "heart", "long_egg"],
    "f_elder": ["matron", "full_egg", "long_egg"],
}

# eye type by archetype (the canon's three eye types; old faces take the hooded elder eye)
EYES_BY_ARCH = {
    "m_warrior": ["fierce", "fierce", "fierce", "almond"],
    "m_scholar": ["phoenix", "phoenix", "phoenix", "almond"],
    "m_elder": ["elder"],
    "m_monk": ["phoenix", "elder", "almond"],
    "m_rogue": ["fierce", "almond", "phoenix"],
    "f_warrior": ["almond", "almond", "phoenix"],
    "f_scholar": ["almond", "phoenix", "almond"],
    "f_elder": ["elder", "almond"],
}

# per-type ranges (eye_h opening, iris, eye_w, tilt, tail) - the canon of each eye type
EYE_CANON = {
    "fierce": dict(eye_h=(0.35, 0.40), iris=(0.46, 0.50), eye_w=(0.122, 0.132),
                   tilt=(0.00, 0.06), tail=(0.0, 0.04)),
    "phoenix": dict(eye_h=(0.32, 0.35), iris=(0.40, 0.44), eye_w=(0.130, 0.140),
                    tilt=(0.05, 0.12), tail=(0.12, 0.30)),
    "almond": dict(eye_h=(0.32, 0.37), iris=(0.42, 0.48), eye_w=(0.122, 0.134),
                   tilt=(0.00, 0.07), tail=(0.0, 0.12)),
    "elder": dict(eye_h=(0.32, 0.35), iris=(0.44, 0.49), eye_w=(0.118, 0.130),
                  tilt=(-0.02, 0.04), tail=(0.0, 0.04)),
}

# brow types by archetype (per officer, a pick)
BROWS_BY_ARCH = {
    "m_warrior": ["sword", "silkworm", "flat", "sword"],
    "m_scholar": ["sword", "flat", "silkworm", "sword"],
    "m_elder": ["longevity"],
    "m_monk": ["longevity", "flat", "silkworm"],
    "m_rogue": ["sword", "silkworm", "flat"],
    "f_warrior": ["lady_sword", "willow", "crescent", "lady_sword"],
    "f_scholar": ["willow", "yuanshan", "crescent", "willow"],
    "f_elder": ["yuanshan", "willow"],
}

# face width / face height (hairline to chin) caps
FACE_RATIO_CAP = {"m_scholar": 0.82, "m_elder": 0.82, "m_monk": 0.86, "m_rogue": 0.85,
                  "m_warrior": 0.88, "f_warrior": 0.92, "f_scholar": 0.92, "f_elder": 0.93}
BEARD_HAIR_TOP = 0.205        # men's default hairline height

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
    lo, hi = EYE_CANON.get(F.eye, dict(eye_h=(0.32, 0.40)))["eye_h"]
    F.eye_h = float(np.clip(F.eye_h + e.get("eye_h_add", 0.0), lo, hi))
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


def arch_of(ch):
    """'m_scholar' ... from the key (heroes map to their scenario archetype)."""
    k = str(getattr(ch, "key", ""))
    hero = {"hero_warlord": "m_warrior", "hero_scholar": "f_scholar", "hero_elder": "m_elder"}
    if k in hero:
        return hero[k]
    a, _, idx = k.rpartition("_")
    return a if a in FACE_RATIO_CAP else ("f_scholar" if ch.face.sex == "f" else "m_scholar")


def hair_top(ch):
    h = ch.hair or {}
    if h.get("kind") == "lady":
        return h.get("hairline", 0.268)
    return h.get("top", BEARD_HAIR_TOP)


def face_ratio(F, top=BEARD_HAIR_TOP):
    """Face width (widest, between brow and mouth) / face height (hairline to chin), on the
    frontal construction - the measure behind 'a very broad, square, flat face'."""
    from head import Head
    H = Head(0.0, 0.0, 1.0, 0.0, 0.0, F.shape)
    ys = np.linspace(0.40, 0.80, 41)
    return float(2 * H.a(ys).max() / (H.chin_y - top))


def goatee_ratio(F, beard):
    """drawn width of a short goatee's end / mouth width (spec estimate, see hair.beard)."""
    import hair as hairmod
    hw = hairmod.goatee_half_width(F.mouth_w, beard.get("width", 1.0))
    return 2 * hw * 0.85 / F.mouth_w            # the tip clustering keeps ~85 % of the spread


def hairline_curve(ch):
    """departure of the forehead hairline from a straight edge (head units)."""
    import hair as hairmod
    h = ch.hair or {}
    if h.get("kind") != "male":
        return None
    return hairmod.hairline_sagitta(h.get("top", BEARD_HAIR_TOP), h.get("arch", 1.0),
                                    h.get("recede", 0.0), h.get("peak", 0.0))


def stereotype_flags(ch):
    """The 'wise old Chinaman / wispy-goatee sage' (and Fu Manchu) pattern, scored as three
    independent flags with margins wider than the individual rules: drooping or wispy
    whiskers, a straight 'bowl' hairline, a broad flat face.  Any two together fail."""
    import hair as hairmod
    F = ch.face
    flags = []
    b = ch.beard
    if b:
        mous = b.get("mous") or hairmod.default_mous(b["kind"])
        wispy = mous not in hairmod.MOUS_STYLES or b.get("droop") is not None
        if b["kind"] == "goatee":
            wispy = wispy or goatee_ratio(F, b) < 0.45 or b.get("link", 0.5) < 0.30 \
                or b.get("length", 0.2) > 0.24
        if b.get("density", 1.0) < 0.7:
            wispy = True
        if wispy:
            flags.append("drooping/wispy whiskers")
    hc = hairline_curve(ch)
    if hc is not None and (hc < 0.09 or (ch.hair or {}).get("strands", 150) < 120):
        flags.append("straight bowl hairline")
    r = face_ratio(F, hair_top(ch))
    if F.sex == "m" and (r > 0.85 or (r > 0.80 and F.cheek_shade < 0.55)):
        flags.append("broad flat face (%.2f)" % r)
    return flags


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
    # --- the canon of each eye type
    ec = EYE_CANON[F.eye]
    for name, val in (("eye_h", F.eye_h), ("iris", F.iris), ("eye_w", F.eye_w),
                      ("tilt", F.eye_tilt), ("tail", F.tail)):
        lo, hi = ec[name]
        assert lo - 1e-6 <= val <= hi + 1e-6, "%s: %s eye %s %.3f outside %.3f-%.3f" % (
            k, F.eye, name, val, lo, hi)
    # --- beards: no drooping whiskers, no isolated chin tuft
    import hair as hairmod
    b = ch.beard
    if b:
        mous = b.get("mous") or hairmod.default_mous(b["kind"])
        assert "droop" not in b, "%s: 'droop' is not a canon moustache parameter" % k
        assert mous in hairmod.MOUS_STYLES, "%s: moustache %r (drooping whiskers)" % (k, mous)
        assert mous != "merge" or b["kind"] in ("full", "long"), \
            "%s: a merged moustache needs a full or long beard" % k
        if b["kind"] == "goatee":
            gr = goatee_ratio(F, b)
            assert gr >= 0.35, "%s: goatee %.2f of the mouth width < 0.35 (chin tuft)" % (k, gr)
            assert b.get("link", 0.5) >= 0.25, \
                "%s: goatee not joined to the moustache by a chin beard" % k
    # --- hairlines curve and show strands (never a ruler-straight bowl edge)
    hc = hairline_curve(ch)
    if hc is not None:
        assert hc >= 0.08, "%s: hairline nearly straight (%.3f < 0.08)" % (k, hc)
        assert (ch.hair or {}).get("strands", 150) >= 120, "%s: hair without strands" % k
    # --- face width and structure
    arch = arch_of(ch)
    r = face_ratio(F, hair_top(ch))
    cap = FACE_RATIO_CAP[arch]
    assert r <= cap + 1e-6, "%s: face width %.3f of its height > %.2f (%s)" % (k, r, cap, arch)
    assert F.cheek_shade >= 0.35, "%s: face without 晕染 structure" % k
    if r > 0.78:
        assert F.cheek_shade >= 0.55, "%s: broad face (%.2f) needs cheek/jaw 晕染" % (k, r)
    # --- the combination gate
    fl = stereotype_flags(ch)
    assert len(fl) < 2, "%s: stereotype pattern: %s" % (k, " + ".join(fl))
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
    bd = fd.lm.get("beard")
    if bd:
        mc = bd.get("mouth_corners")
        for i, e in enumerate(bd.get("mous_ends", [])):
            if bd["mous"] in ("bazi", "up"):
                # screen y grows downward: the end may not hang below the mouth corner
                assert e[1] <= mc[i][1] + 1.0, "%s: moustache end %.1f px below the mouth corner" % (
                    key, e[1] - mc[i][1])
        if bd["kind"] == "goatee":
            Us, Ls, Lo = fd.lm["mouth"]
            mw_px = abs(Ls[-1][0] - Ls[0][0])
            assert bd["goatee_w"] >= 0.35 * mw_px, "%s: goatee %.1f px < 0.35 of the mouth %.1f px" % (
                key, bd["goatee_w"], mw_px)
            assert bd.get("link", 0) >= 0.25, "%s: goatee not joined to the moustache" % key
    return True

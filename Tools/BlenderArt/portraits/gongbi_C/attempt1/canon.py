"""Face canon for gongbi_C: classical Chinese figure-painting proportions and feature types.

All lengths are metres in *face space* for a head of scale 1 (crown to chin 0.232 m): u runs
across the face (+ = viewer's right in a frontal view), v up, origin at the middle of the eye
line on the face surface.  The 2D stage wraps these designs round the 3D head (height grid) and
the camera turns them into a true 3/4 view.

The canon is the painters' own: 三庭五眼 (three equal courts: hairline-brow, brow-nose base,
nose base-chin; the face is five eye-widths wide, the gap between the eyes is one eye), and the
feature types of 人物画 manuals:

* eyes  almond 杏眼 (bright, ladies and young men), phoenix 丹凤眼 (long, lifted outer corner,
        scholars and heroes), round 环眼 (wide open, fierce warriors), calm 睡凤眼 (heavy lid,
        elders, monks)
* brows sword 剑眉, silkworm 卧蚕眉, willow-leaf 柳叶眉, calm arch 平眉, longevity 寿眉
* beards five-lock 五绺长髯, curly 虬髯, short full 短髯, moustache + goatee 八字须, none

Hard rules (never relaxed by any preset or random variation): eyes are open almonds with a
drawn upper lid, iris, pupil and highlight (opening >= 0.30 of the eye width, iris >= 0.36);
no ethnicity presets exist anywhere; skin is warm ivory / peach / ochre with rouge.
"""

import copy
import random

# ---------------------------------------------------------------------------------------------
# base canon (young adult man) - every key the painter reads
# ---------------------------------------------------------------------------------------------
BASE = dict(
    # eyes
    eye_in=0.0152, eye_v=0.0, eye_w=0.0290, eye_h=0.36, eye_tilt=0.0012, eye_peak=0.40,
    eye_low=0.56, eye_up=0.64, eye_k=2.3, lid_fold=0.0022, lid_fold_span=(0.28, 0.92),
    tail=0.0016, tail_rise=0.0006, iris=0.42, iris_v=0.10, iris_color="#3A2A20",
    lid_w=1.55, lower_w=0.60, lower_a=0.50, bag=0.0, hood=0.0, white_below=0.0,
    gaze=(0.0, 0.0), lash=0.0,
    # brows
    brow="calm", brow_in=0.0105, brow_v=0.0150, brow_len=0.0450, brow_rise=0.0040,
    brow_arch=0.0032, brow_w=(0.0030, 0.0036, 0.0011), brow_knit=0.0, brow_color="ink",
    brow_hairs=28, brow_droop=0.0,
    # nose
    nose_len=0.0440, nose_w=0.0160, nose_h=0.0185, nose_bridge=0.0060, nose_tip=0.0058,
    nose_line=1.0, nose_fade=0.55,
    # mouth
    mouth_v=-0.0645, mouth_w=0.0225, lip_up=0.0042, lip_low=0.0058, mouth_curve=0.0,
    lip_color="#B04A4E", lip_alpha=0.32, bow=0.0010,
    # washes
    rouge=0.14, rouge_color="#C25A5E", shade=0.12, eye_shadow=0.0, eye_shadow_color="#C86A6A",
    three_whites=0.0, huadian=None, beauty_mark=None,
    # character
    age=0.0, fierce=0.0, smile=0.0,
    # hair at the temples drawn in 2D (none when a helmet covers them)
    hairline=dict(on=True, top=0.075, temple_u=0.060, temple_v=0.028, side_v=-0.020,
                  color="hair", strands=34, widow=0.0),
    beard=None,
    line_color="#4A3024",
)

#: archetype presets: overrides of BASE (randomised further by :func:`generate`)
ARCH = {
    "m_warrior": dict(eye_h=0.40, eye_tilt=0.0026, eye_peak=0.46, eye_low=0.52, iris=0.40,
                      lid_w=1.75, brow="sword", brow_w=(0.0034, 0.0046, 0.0012),
                      brow_rise=0.0060, brow_arch=0.0024, brow_knit=0.0016, fierce=0.6,
                      nose_w=0.0172, nose_h=0.0200, mouth_w=0.0235, mouth_curve=-0.0008,
                      lip_alpha=0.22, rouge=0.10, shade=0.16, line_color="#3E281E",
                      beard=dict(kind="short_full")),
    "m_scholar": dict(eye_h=0.33, eye_tilt=0.0022, eye_peak=0.38, eye_low=0.58, lid_fold=0.0,
                      tail=0.0032, tail_rise=0.0012, iris=0.42, brow="calm",
                      brow_w=(0.0026, 0.0030, 0.0009), brow_rise=0.0045, brow_arch=0.0034,
                      mouth_w=0.0215, lip_alpha=0.26, rouge=0.08,
                      beard=dict(kind="goatee")),
    "m_elder": dict(eye_h=0.31, eye_tilt=0.0004, hood=0.7, bag=0.6, iris=0.40, lid_w=1.45,
                    brow="longevity", brow_color="white", brow_w=(0.0028, 0.0034, 0.0016),
                    brow_len=0.052, brow_rise=-0.002, brow_arch=0.0030, age=0.9,
                    nose_len=0.046, mouth_w=0.0215, lip_alpha=0.16, rouge=0.07, shade=0.14,
                    beard=dict(kind="five_lock", color="white")),
    "m_monk": dict(eye_h=0.31, eye_tilt=0.0010, hood=0.35, iris=0.40, brow="calm",
                   brow_w=(0.0024, 0.0030, 0.0010), age=0.3, mouth_curve=0.0006, smile=0.3,
                   lip_alpha=0.2, beard=None),
    "m_rogue": dict(eye_h=0.37, eye_tilt=0.0020, eye_peak=0.45, iris=0.40, brow="sword",
                    brow_w=(0.0032, 0.0042, 0.0010), brow_rise=0.0065, brow_knit=0.0010,
                    fierce=0.4, mouth_curve=0.0004, smile=0.4, lip_alpha=0.22,
                    beard=dict(kind="stubble")),
    "f_warrior": dict(eye_h=0.38, eye_tilt=0.0026, eye_peak=0.40, tail=0.0026, tail_rise=0.0010,
                      lid_fold=0.0018, iris=0.44, brow="willow", brow_w=(0.0018, 0.0026, 0.0006),
                      brow_rise=0.0058, brow_arch=0.0030, brow_len=0.044, brow_hairs=18,
                      nose_len=0.0415, nose_w=0.0140, nose_h=0.0160, mouth_w=0.0185,
                      lip_up=0.0040, lip_low=0.0056, lip_alpha=0.50, rouge=0.20, nose_line=0.8,
                      nose_fade=0.75,
                      eye_shadow=0.12, three_whites=0.15, lash=0.5, line_color="#5A3828"),
    "f_scholar": dict(eye_h=0.38, eye_tilt=0.0018, eye_peak=0.40, tail=0.0022, tail_rise=0.0008,
                      lid_fold=0.0019, iris=0.45, brow="willow", brow_w=(0.0016, 0.0024, 0.0005),
                      brow_rise=0.0036, brow_len=0.0460, brow_hairs=16,
                      nose_len=0.0410, nose_w=0.0135, nose_h=0.0150, mouth_w=0.0175,
                      lip_up=0.0042, lip_low=0.0060, lip_alpha=0.58, rouge=0.24, nose_line=0.75,
                      nose_fade=0.80, brow_arch=0.0048,
                      eye_shadow=0.16, three_whites=0.25, lash=0.6, line_color="#5A3828"),
    "f_elder": dict(eye_h=0.32, hood=0.4, bag=0.4, iris=0.40, brow="willow",
                    brow_color="grey", brow_w=(0.0018, 0.0024, 0.0008), age=0.75,
                    nose_len=0.043, mouth_w=0.019, lip_alpha=0.26, rouge=0.10, shade=0.13,
                    line_color="#5A3828"),
}

#: 3D head / body presets per archetype (b_body parameters)
HEAD = {
    "m_warrior": dict(width=1.04, jaw=1.10, chin=1.10, cheek=1.03, face_len=1.0),
    "m_scholar": dict(width=0.98, jaw=0.96, chin=0.95, face_len=1.03),
    "m_elder": dict(width=0.98, jaw=0.98, chin=0.96, face_len=1.05, cheek=0.98),
    "m_monk": dict(width=1.0, jaw=1.0, chin=1.0, crown=1.03),
    "m_rogue": dict(width=1.02, jaw=1.06, chin=1.02),
    "f_warrior": dict(scale=0.95, width=0.96, jaw=0.88, chin=0.82, face_len=0.97, cheek=1.0),
    "f_scholar": dict(scale=0.94, width=0.95, jaw=0.86, chin=0.80, face_len=0.97, cheek=1.01),
    "f_elder": dict(scale=0.94, width=0.96, jaw=0.92, chin=0.86, face_len=1.0),
}
BODY = {
    "m_warrior": dict(shoulder=1.08, chest=1.05),
    "m_scholar": dict(shoulder=0.96, slope=1.08),
    "m_elder": dict(shoulder=0.95, slope=1.15),
    "m_monk": dict(shoulder=1.0),
    "m_rogue": dict(shoulder=1.04),
    "f_warrior": dict(shoulder=0.86, chest=0.92, slope=1.12, neck=0.9, neck_len=1.15),
    "f_scholar": dict(shoulder=0.84, chest=0.9, slope=1.18, neck=0.88, neck_len=1.2),
    "f_elder": dict(shoulder=0.86, chest=0.92, slope=1.15, neck=0.92),
}

#: beard types: zone dicts read by face2d.beard (lengths in metres)
BEARDS = {
    "none": None,
    "stubble": dict(moustache=dict(len=0.010, n=60, droop=0.5, w=0.55),
                    chin=dict(len=0.012, n=80, spread=1.0, width=0.02),
                    cheek=dict(len=0.010, n=120, top=-0.030), alpha=0.5, base=0.30),
    "goatee": dict(moustache=dict(len=0.020, n=70, droop=0.55, w=0.8),
                   chin=dict(len=0.050, n=100, spread=0.35, width=0.009, converge=0.4), cheek=None, base=0.5),
    "short_full": dict(moustache=dict(len=0.026, n=110, droop=0.6, w=0.85),
                       chin=dict(len=0.055, n=180, spread=0.8, width=0.022, converge=0.15),
                       cheek=dict(len=0.040, n=240, top=-0.022), base=0.55),
    "five_lock": dict(moustache=dict(len=0.042, n=90, droop=0.85, w=0.85),
                      chin=dict(len=0.150, n=200, spread=0.4, width=0.015, converge=0.35),
                      cheek=dict(len=0.115, n=150, top=-0.034, locks=True), base=0.55),
    "curly": dict(moustache=dict(len=0.028, n=90, droop=0.5, w=0.9),
                  chin=dict(len=0.065, n=180, spread=1.0, width=0.024, converge=0.1),
                  cheek=dict(len=0.045, n=220, top=-0.024), curl=0.35, base=0.65),
}


def face(arch, **over):
    """Canon dict for an archetype with overrides (unknown keys raise)."""
    d = copy.deepcopy(BASE)
    d.update(copy.deepcopy(ARCH.get(arch, {})))
    for k, v in over.items():
        if k not in d:
            raise KeyError("unknown face key %r" % k)
        d[k] = v
    enforce(d)
    return d


def enforce(d):
    """The non-negotiable face rules (applied after every override / random variation)."""
    d["eye_h"] = max(0.30, min(0.50, d["eye_h"]))
    d["iris"] = max(0.36, min(0.50, d["iris"]))
    d["eye_w"] = max(0.026, min(0.032, d["eye_w"]))
    d["lid_w"] = max(1.2, d["lid_w"])
    return d


# ---------------------------------------------------------------------------------------------
# random variation for the 103-portrait cast
# ---------------------------------------------------------------------------------------------
JITTER = dict(eye_w=0.0012, eye_h=0.03, eye_tilt=0.0008, eye_peak=0.04, iris=0.02,
              brow_v=0.0012, brow_len=0.003, brow_rise=0.0015, brow_arch=0.001,
              nose_len=0.002, nose_w=0.0012, nose_h=0.0015, mouth_w=0.0015, mouth_v=0.0015,
              lip_up=0.0006, lip_low=0.0008, mouth_curve=0.0005, rouge=0.03)

HEAD_JITTER = dict(width=0.03, jaw=0.04, chin=0.04, cheek=0.02, face_len=0.03)


def vary(d, rng, amount=1.0):
    for k, s in JITTER.items():
        d[k] = d[k] + rng.uniform(-s, s) * amount
    return enforce(d)


def generate(name):
    """Spec for a generated cast member, e.g. 'm_warrior_07' (see wardrobe.generate)."""
    import wardrobe
    return wardrobe.generate(name)

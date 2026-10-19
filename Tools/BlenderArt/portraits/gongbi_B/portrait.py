"""Portrait composition: a Character spec -> ordered gongbi painting on a Canvas.

Layer order (back to front), as a painter would build the figure:
  cloak behind -> back hair -> neck -> robes (inner to outer) with collars -> armour ->
  face skin + 晕染 -> hair mass -> features (ear, nose, mouth, eyes, brows, contour) ->
  helmet neck guard -> beard -> headgear -> ornaments
"""

import math
from dataclasses import dataclass, field

import numpy as np

import geom2d as g
import palette as pal
from canvas import Canvas
from head import Head
from face import FaceSpec, FaceDrawer
import figure as fig
import hair as hairmod
import headgear as hg
import armour as arm

W, H_ = 384, 480
HEAD = 230.0          # crown-to-chin px (48 % of the frame)
EYE_FRAC = 0.38       # eye line from the top


@dataclass
class Character:
    key: str
    face: FaceSpec
    body: dict = field(default_factory=dict)
    hair: dict = field(default_factory=dict)
    beard: dict = None
    headgear: dict = None
    costume: dict = field(default_factory=dict)
    lead: float = 0.035          # extra room in front of the face (fraction of W)
    seed: int = 0


def place_head(ch):
    F = ch.face
    yaw = F.yaw
    s = HEAD
    crown = EYE_FRAC * H_ - F.eye_y * s
    far = 1 if yaw >= 0 else -1
    cx = W / 2 - 0.40 * s * math.sin(math.radians(yaw)) + far * W * ch.lead
    return Head(cx, crown, s, yaw, F.roll, F.shape)


def draw(ch: Character, cv: Canvas = None):
    cv = cv or Canvas(W, H_, seed=ch.seed)
    F = ch.face
    head = place_head(ch)
    fd = FaceDrawer(cv, head, F)
    fd.face_poly()
    b = ch.body
    T = fig.Torso(head, F.yaw * b.get("yaw_k", 0.85), shoulder=b.get("shoulder", 1.0),
                  neck_r=b.get("neck_r", 0.20), slope=b.get("slope", 1.0))
    co = ch.costume
    rng = np.random.default_rng(ch.seed + 101)
    # --- behind the figure
    if co.get("cloak"):
        arm.cloak(cv, T, **co["cloak"])
    if ch.hair.get("kind") == "lady":
        hairmod.lady_hair_back(cv, fd, T, **ch.hair.get("back", {}))
    # --- neck and robes
    fig.draw_neck(cv, fd, T, F.skin, F.shade, F.shade_k, F.line, adam=b.get("adam", 0.0),
                  lw=F.line_w)
    robes = co.get("robes", [])
    for k, layer in enumerate(robes):
        R = fig.Robe(**{k_: v for k_, v in layer.items() if k_ not in ("pattern",)})
        outer = k == len(robes) - 1
        geo = fig.draw_robe(cv, T, R, fd, folds=outer, seed=ch.seed)
        # contact shade on the layer below: skin (ochre) for the innermost, the garment's own
        # darker tone for the others
        below = robes[k - 1]["color"] if k > 0 else None
        contact = pal.hexs(pal.mix(below, "ink", 0.5)) if below else F.shade
        fig.draw_collar(cv, T, R, geo, pattern_fn=_pattern(layer.get("pattern"), T.s),
                        contact=contact)
    if co.get("kasaya"):
        fig.kasaya(cv, T, **co["kasaya"])
    if co.get("armour"):
        a = co["armour"]
        palette = a.get("palette", "azure_iron")
        arm.cuirass(cv, T, palette=palette, rng=rng, **a.get("cuirass", {}))
        if a.get("mirror"):
            arm.chest_mirror(cv, T, **a["mirror"])
        if a.get("mingguang"):
            arm.mingguang(cv, T, **a["mingguang"])
        far = fd.far
        for side in (far, -far):
            arm.pauldron(cv, T, side, palette=palette, rng=rng, **a.get("pauldron", {}))
        if "scarf" in a:
            sc = dict(a["scarf"])
            sc.setdefault("color", arm.ARMOUR[palette]["scarf"])
            arm.scarf(cv, T, fd, **sc)
    if co.get("shawl"):
        fig.shawl(cv, T, **co["shawl"])
    if co.get("necklace"):
        fig.necklace(cv, T, **co["necklace"])
    if co.get("mala"):
        fig.mala(cv, T, **co["mala"])
    if co.get("extra"):
        co["extra"](cv, T, fd)
    hgd = ch.headgear or {}
    helmet = None
    if hgd.get("kind") == "helmet":
        helmet = hg.Helmet(fd, **{k: v for k, v in hgd.items() if k != "kind"})
        helmet.neck_guard(cv, "back")
    # --- face
    fd.draw_skin_layers()
    hk = ch.hair.get("kind", "male")
    hres = None
    if hk == "male":
        hres = hairmod.male_hair(cv, fd, **{k: v for k, v in ch.hair.items()
                                            if k not in ("kind", "ear")})
    elif hk == "lady":
        fd.ear(top=0.47, bot=0.70)
        hres = hairmod.lady_hair(cv, fd, **{k: v for k, v in ch.hair.items()
                                            if k not in ("kind", "back", "ear", "ornaments")})
    elif hk == "bald":
        hres = hairmod.bald(cv, fd, **{k: v for k, v in ch.hair.items() if k not in ("kind", "ear")})
    fd.draw_features(ear=ch.hair.get("ear", True) and hk != "lady")
    if helmet is not None:
        helmet.neck_guard(cv, "front")
    if ch.beard:
        hairmod.beard(cv, fd, **ch.beard)
    if helmet is not None:
        if helmet.wings:
            helmet.phoenix_wings(cv)
        helmet.bowl(cv)
        helmet.visor(cv)
        helmet.plume(cv)
    elif hgd.get("kind") == "scholar_cap":
        cap = hg.ScholarCap(fd, **{k: v for k, v in hgd.items() if k != "kind"})
        cap.draw(cv)
    elif hgd.get("kind") == "crown" and hres and hres.get("bun") is not None:
        hg.small_crown(cv, fd, hres["bun"], **{k: v for k, v in hgd.items() if k != "kind"})
    elif hgd.get("kind") == "headband":
        hg.headband(cv, fd, **{k: v for k, v in hgd.items() if k != "kind"})
    elif hgd.get("kind") == "fur_hat":
        hg.fur_hat(cv, fd, **{k: v for k, v in hgd.items() if k != "kind"})
    if hk == "lady" and hres is not None:
        orn = dict(ch.hair.get("ornaments", {}))
        if hgd.get("kind") in ("fur_hat", "helmet"):
            # the bun is under the hat: only the earrings and the brow mark remain visible
            orn.update(phoenix=False, flower=None, pins=0, comb=False, crown=False)
        hairmod.lady_ornaments(cv, fd, hres, **orn)
    if co.get("front"):
        co["front"](cv, T, fd)
    return cv, fd, T


def _pattern(kind, s):
    if not kind:
        return None
    if kind == "gold_dots":
        def fn(cv, A_, B_):
            n = int(g.length(A_) / (s * 0.035))
            for k in range(n):
                u = (k + 0.5) / n
                c = (g.at(A_, u) + g.at(B_, u)) / 2
                cv.dot(c, s * 0.008, "gold", 0.95)
        return fn
    if kind == "fur":
        def fn(cv, A_, B_):
            # fur trim on a steppe collar: soft tufts in dark, mid and pale fur tones
            rng = np.random.default_rng(7)
            for k in range(int(g.length(A_) / (s * 0.006))):
                u = rng.uniform(0, 1)
                v = rng.uniform(0, 1)
                p = g.at(A_, u) * (1 - v) + g.at(B_, u) * v
                d = g.at(B_, u) - g.at(A_, u)
                d = d / (np.linalg.norm(d) + 1e-9)
                q = p + (d * rng.normal(0, 0.6) + np.array([-d[1], d[0]]) * rng.choice([-1, 1])) * s * 0.02
                cv.stroke(np.array([p, q]), s * 0.004, rng.choice(["#4a3a30", "#a08a6a", "#d8c8a8"]),
                          rng.uniform(0.5, 0.85), prof="hair")
        return fn
    if kind == "cloud":
        def fn(cv, A_, B_):
            n = int(g.length(A_) / (s * 0.06))
            for k in range(n):
                u = (k + 0.5) / n
                p = g.at(A_, u)
                q = g.at(B_, u)
                c = (p + q) / 2
                r = np.linalg.norm(q - p) * 0.28
                arc = g.ellipse(c, r, r, n=14, a0=0.2, a1=2 * math.pi * 0.85, endpoint=True)
                cv.stroke(arc, s * 0.004, "gold", 0.9, prof="silk")
        return fn
    return None


def draw_unknown(cv=None):
    """unknown.png: the officer not yet met - an ink silhouette (topknot, head, shoulders,
    crossed collar) laid in two flat tones of ink wash on the silk, modelled with soft 分染
    at the edges and brushed contours; no features."""
    from face import FaceSpec
    cv = cv or Canvas(W, H_, seed=7)
    F = FaceSpec(sex="m", yaw=18.0, shape=dict(HEAD_FAM_UNKNOWN))
    ch = Character(key="unknown", face=F)
    head = place_head(ch)
    s = head.s
    fd = FaceDrawer(cv, head, F)
    face_poly = fd.face_poly()
    T = fig.Torso(head, 18 * 0.9, shoulder=1.0, neck_r=0.21)
    body_tone, head_tone = "#8f877c", "#5c554e"
    # body: one flat pale-ink silhouette, darker towards its edges
    ys = np.linspace(1.0, 2.3, 40)
    right = T.P(np.array([T.sil_u(y, 1) for y in ys]), ys)
    left = T.P(np.array([T.sil_u(y, -1) for y in ys]), ys)
    body = np.vstack([right, left[::-1]])
    cv.fill(body, body_tone, 0.92, "paint", grain=1.0)
    for P in (right, left):
        side = 1 if np.dot(g.normals(P)[20], body.mean(0) - P[20]) > 0 else -1
        cv.wash(P, s * 0.25, "ink_m", 0.5, side=side, rows=6)
    R = fig.Robe(body_tone, "ink_m", cross_y=1.42, neck_u=0.62, cw=0.10)
    top_uv, under_uv = fig.collar_edges(T, R, 2.4)
    for uv in (under_uv[:6], top_uv):
        C = g.catmull(T.Puv(uv), 10)
        cv.brush(C, s * 0.013, "#4a443e", style="orchid", alpha=0.75, dry=0.5)
    # neck, head (cranium + face as one mass) and topknot in the darker tone
    neck = np.vstack([head.P([(-0.17, 0.80), (0.17, 0.80)]), T.P(0.62, 1.10)[None], T.P(-0.62, 1.10)[None]])
    cv.fill(neck, head_tone, 0.95, "paint", grain=1.0)
    near, _ = head.silhouette(0.0, 0.70, 50, side=-fd.far, dr=0.024)
    farl, _ = head.silhouette(0.0, 0.62, 50, side=fd.far, dr=0.016)
    cran = np.vstack([farl, near[::-1]])
    cv.fill(cran, head_tone, 1.0, "paint", grain=1.0)
    cv.fill(face_poly, head_tone, 1.0, "paint", grain=1.0)
    bun = hairmod.Shell(head, (0.0, -0.045, -0.05), (0.088, 0.075, 0.088))
    O = bun.outline(0.0, n=40)
    cv.fill(O, head_tone, 1.0, "paint", grain=1.0)
    # soft lit plane on the near cheek and crown (pale ink lifts), darker rim
    cv.blob(head.P([(-fd.far * 0.10, 0.45)])[0], s * 0.16, s * 0.24, "#8a8279", 0.45, mode="paint")
    for P in (near, farl, face_poly[len(face_poly) // 3:]):
        side = 1 if np.dot(g.normals(P)[len(P) // 2], head.P([(0, 0.5)])[0] - P[len(P) // 2]) > 0 else -1
        cv.wash(P, s * 0.06, "ink", 0.35, side=side, rows=4)
    for P in (near, farl, face_poly[int(len(face_poly) * 0.2):]):
        cv.brush(P, s * 0.010, "ink_d", style="orchid", alpha=0.8, dry=0.5)
    cv.brush(np.vstack([O, O[:1]]), s * 0.008, "ink_d", style="iron", alpha=0.8, caps=False)
    for P in (right, left):
        cv.brush(P[:32], s * 0.014, "ink_d", style="reed", alpha=0.8, dry=0.6)
    return cv


HEAD_FAM_UNKNOWN = dict(width=1.0, jaw=1.04, chin=1.02, oval=0.3)

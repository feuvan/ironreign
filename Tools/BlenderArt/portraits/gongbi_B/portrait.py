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
    for layer in co.get("robes", []):
        R = fig.Robe(**{k: v for k, v in layer.items() if k not in ("pattern",)})
        geo = fig.draw_robe(cv, T, R, fd, folds=layer is co["robes"][-1], seed=ch.seed)
        fig.draw_collar(cv, T, R, geo, pattern_fn=_pattern(layer.get("pattern"), T.s))
    if co.get("armour"):
        a = co["armour"]
        arm.cuirass(cv, T, rng=rng, **a.get("cuirass", {}))
        if a.get("mirror"):
            arm.chest_mirror(cv, T, **a["mirror"])
        if a.get("mingguang"):
            arm.mingguang(cv, T, **a["mingguang"])
        far = fd.far
        for side in (far, -far):
            arm.pauldron(cv, T, side, rng=rng, **a.get("pauldron", {}))
    if co.get("shawl"):
        fig.shawl(cv, T, **co["shawl"])
    for k, layer in enumerate(co.get("robes", [])):
        pass
    if co.get("necklace"):
        fig.necklace(cv, T, **co["necklace"])
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
    if hk == "lady" and hres is not None:
        hairmod.lady_ornaments(cv, fd, hres, **ch.hair.get("ornaments", {}))
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

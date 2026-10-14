"""Face canon lab: the three hero heads side by side (skin, hair, features, beard), fast.
render.sh portraits/gongbi_B/lab_faces.py [ss]"""
import os
import numpy as np
from canvas import Canvas
import characters, portrait, hair as hairmod
from face import FaceDrawer
import backend
from ironart import scene as S
OUT = "/tmp/claude-0/-home-user-ironreign/7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/gongbi_B/lab"
a = S.args()
ss = int(a[0]) if a else 3
cv = Canvas(1152, 480, seed=1)
for i, key in enumerate(("hero_warlord", "hero_scholar", "hero_elder")):
    ch = characters.HEROES[key]()
    H = portrait.place_head(ch)
    H.cx += 384 * i
    fd = FaceDrawer(cv, H, ch.face)
    fd.face_poly()
    fd.draw_skin_layers()
    hk = ch.hair.get("kind")
    if hk == "lady":
        fd.ear(top=0.47, bot=0.70)
        hairmod.lady_hair(cv, fd, **{k: v for k, v in ch.hair.items() if k not in ("kind", "ornaments", "back", "ear")})
    else:
        hairmod.male_hair(cv, fd, **{k: v for k, v in ch.hair.items() if k not in ("kind", "ear")})
    fd.draw_features(ear=hk != "lady")
    if ch.beard:
        hairmod.beard(cv, fd, **ch.beard)
backend.render(cv, OUT + "/faces.png", ss=ss, samples=5)
from PIL import Image
im = Image.open(OUT + "/faces.png").convert("RGB")
W = im.size[0] // 3
for i in range(3):
    im.crop((W * i + int(W * 0.22), int(im.size[1] * 0.22), W * i + int(W * 0.80), int(im.size[1] * 0.68))).save(OUT + "/face%d.png" % i)
im.resize((1152, 480), Image.LANCZOS).save(OUT + "/faces_1x.png")
im.resize((288, 120), Image.LANCZOS).save(OUT + "/faces_thumb.png")

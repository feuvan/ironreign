import os, sys
import numpy as np
import geom2d as g
from canvas import Canvas
from head import Head
from face import FaceSpec, FaceDrawer
import figure as fig
import backend
from ironart import scene as S
OUT = "/tmp/claude-0/-home-user-ironreign/7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/gongbi_B/lab"
a = S.args()
yaw = float(a[0]) if a else 20.0
F = FaceSpec(yaw=yaw, eye="phoenix")
cv = Canvas(384, 480, seed=1)
H = Head(192 - 0.12 * 230 * np.sin(np.radians(yaw)) * 1.0, 67, 230, yaw, 0, F.shape)
fd = FaceDrawer(cv, H, F)
fd.face_poly()
T = fig.Torso(H, yaw * 0.9, shoulder=1.0, neck_r=0.20)
inner = fig.Robe("white", "white", cross_y=1.30, neck_u=0.52, cw=0.05)
outer = fig.Robe("ochre_robe", "ink_d", cross_y=1.50, neck_u=0.66, cw=0.09)
fig.draw_neck(cv, fd, T, F.skin)
for R in (inner, outer):
    geo = fig.draw_robe(cv, T, R, fd)
    fig.draw_collar(cv, T, R, geo)
fd.draw_skin_layers()
import hair
kind = a[1] if len(a) > 1 else "full"
grey = float(a[2]) if len(a) > 2 else 0.0
hair.male_hair(cv, fd, grey=grey)
fd.draw_features()
if kind != "none":
    hair.beard(cv, fd, kind=kind, length=0.30 if kind != "long" else 0.6, grey=grey)
backend.render(cv, OUT + "/body.png", ss=3, samples=5)
from PIL import Image
im = Image.open(OUT + "/body.png").convert("RGB")
im.resize((384, 480), Image.LANCZOS).save(OUT + "/body_384.png")

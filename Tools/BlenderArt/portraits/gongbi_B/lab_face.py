"""Face canon lab: renders bare faces (no costume) for review.
render.sh portraits/gongbi_B/lab_face.py <preset> [yaw]"""
import os, sys
import numpy as np
import geom2d as g
from canvas import Canvas
from head import Head
from face import FaceSpec, FaceDrawer
import backend
from ironart import scene as S

OUT = "/tmp/claude-0/-home-user-ironreign/7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/gongbi_B/lab"
os.makedirs(OUT, exist_ok=True)
a = S.args()
name = a[0] if a else "m"
yaw = float(a[1]) if len(a) > 1 else 20.0
PRESETS = {
    "m": FaceSpec(yaw=yaw),
    "f": FaceSpec(sex="f", yaw=yaw, eye="almond", brow="willow", skin="skin_ivory", line_w=0.8,
                  rouge_k=1.0, eye_rouge=0.8, mouth_w=0.14, lip_up=0.018, lip_lo=0.024,
                  nose_tip=0.075, nose_w=0.050, brow_y=0.405, crease=0.8, eye_h=0.36,
                  shape=dict(jaw=0.88, chin=0.85, width=0.96)),
    "w": FaceSpec(yaw=yaw, eye="fierce", brow="sword", skin="skin_warm", shade_k=1.4,
                  brow_th=0.034, brow_knit=1.0, frown=0.8, wrinkles=0.6, mouth_w=0.18,
                  shape=dict(jaw=1.08, chin=1.1, width=1.03)),
}
F = PRESETS[name]
cv = Canvas(384, 480, seed=1)
H = Head(192 - 0.15 * 230 * np.sin(np.radians(yaw)), 67, 230, yaw, 0, F.shape)
fd = FaceDrawer(cv, H, F)
fd.draw_skin_layers()
fd.draw_features()
backend.render(cv, OUT + "/face_%s.png" % name, ss=3, samples=5)
from PIL import Image
im = Image.open(OUT + "/face_%s.png" % name).convert("RGB")
im.resize((384, 480), Image.LANCZOS).save(OUT + "/face_%s_384.png" % name)
im.resize((96, 120), Image.LANCZOS).save(OUT + "/face_%s_96.png" % name)
im.crop((150, 300, 1050, 1000)).save(OUT + "/face_%s_crop.png" % name)

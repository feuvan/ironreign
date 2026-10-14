import sys, os, time
import numpy as np
import geom2d as g
from canvas import Canvas
import backend
OUT = "/tmp/claude-0/-home-user-ironreign/7c9c7cee-d827-5b3c-8cb6-e644913e9b45/scratchpad/portraits/gongbi_B/t"
cv = Canvas()
cv.radial(g.ellipse((192, 200), 90, 120, n=64), (192, 200), "skin_peach", lambda r, u: 1.0 + 0*r, mode="paint")
cv.radial(g.ellipse((192, 200), 90, 120, n=64), (192, 200), "ochre", lambda r, u: 0.5 * g.smoothstep(0.6, 1.0, r), mode="glaze")
cv.blob((150, 230), 25, 18, "rouge", 0.35)
for i, prof in enumerate(["iron", "silk", "orchid", "nail", "tail", "hair"]):
    y = 340 + i * 22
    cv.line([(40, y), (140, y - 8), (240, y + 6), (340, y)], 3.0, "ink", prof=prof)
cv.stroke(g.ellipse((192, 200), 90, 120, n=80, endpoint=True), 1.4, "ink_brown", prof="iron")
cv.edge(g.catmull([(60, 60), (200, 40), (330, 80)]), 30, "azurite", 0.8, side=1)
for k in range(200):
    x0 = 100 + k * 0.9
    cv.line([(x0, 100), (x0 + 10, 160), (x0 - 5, 230)], 0.5, "ink_m", alpha=0.6, prof="hair")
t = backend.render(cv, OUT + "/backend.png", ss=3, samples=5)
from PIL import Image
im = Image.open(OUT + "/backend.png").convert("RGB")
im.resize((384, 480), Image.LANCZOS).save(OUT + "/backend_384.png")
print("TOTAL", t)

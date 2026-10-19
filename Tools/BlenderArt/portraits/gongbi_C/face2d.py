"""2D face of gongbi_C: the canon features drawn as calligraphic strokes on the 3D head.

Every feature is designed in face space (head-local x / z, eye shapes in eye widths), lifted
onto the analytic head surface (``geo.head_loft(...).front``) plus a small virtual relief
(nose, lips), turned with the head pose and projected with the exported camera - so the far
eye foreshortens, the nose line sits on the far flank and the mouth curves round the face
exactly like the 3D contour Blender drew.

Order (see :meth:`Face.paint`): washes (socket, nose shade, rouge, 三白 whites) -> eyes ->
brows -> nose -> mouth -> wrinkles -> ear detail.
"""

import math

import numpy as np

import brush as B
import canon
import geo
import palette as PL

INK = "#1A1512"
IRIS = "#2E2219"
PUPIL = "#0E0A08"
SCLERA = "#F7F2E8"


class Face:
    def __init__(self, cv, pr, spec, masks, seed=0):
        self.cv, self.pr = cv, pr
        self.spec = spec
        self.f = canon.face(spec)
        self.L = geo.head_loft(spec.get("head", {}))
        self.rng = np.random.default_rng(seed + 991)
        self.masks = masks
        Mh = pr.Mh[:3, :3]
        to_cam = -(Mh.T @ pr.look)
        self.to_cam = to_cam / np.linalg.norm(to_cam)
        self.near = 1.0 if self.to_cam[0] >= 0 else -1.0
        self.cam_yaw = math.atan2(self.to_cam[0], -self.to_cam[1])
        self.cam_pitch = math.asin(np.clip(self.to_cam[2], -1, 1))
        self.upx = pr.px_per_unit()            # work px per head unit
        self.ss = cv.ss
        skin = PL.SKIN[spec.get("skin", "warm")]
        self.skin_l, self.skin_d = skin
        self.line_rgb = PL.srgb(self.f.get("line", "skin_line"))
        self.face_m = masks.get("face")

    # ------------------------------------------------------------------------- geometry
    def relief(self, x, z):
        n = self.f["noseP"]
        x = np.asarray(x, np.float64)
        z = np.asarray(z, np.float64)
        top, tip = n["top_z"], n["tip_z"]
        # ridge protrusion along the nose
        t = np.clip((top - z) / max(top - tip, 1e-6), 0, 1)
        prot = n["prot"] * (0.18 + 0.82 * t ** 1.6)
        prot = prot + n.get("hook", 0.0) * 0.012 * np.sin(np.clip(t, 0, 1) * math.pi)
        below = np.clip((tip - z) / 0.05, 0, 1)
        prot = np.where(z < tip, n["prot"] * (1 - below) ** 1.6, prot)
        prot = np.where(z > top + 0.03, 0.0, prot * geo.smoothstep(top + 0.03, top - 0.01, z))
        wid = 0.026 + (n["tip_w"] - 0.026) * t ** 2
        wid = np.where(z < tip, n["tip_w"], wid)
        nose = prot * np.clip(1 - (x / (wid * 1.6)) ** 2, 0, 1) ** 1.2
        # alae (nostril wings)
        az = tip - 0.005
        ala = 0.022 * np.exp(-((np.abs(x) - n["ala_w"] * 0.82) / 0.022) ** 2
                             - ((z - az) / 0.03) ** 2)
        # lips
        m = self.f["mouthP"]
        lips = 0.022 * np.exp(-(x / (m["w"] * 1.1)) ** 4 - ((z - m["z"]) / 0.045) ** 2)
        return nose + ala + lips

    def P(self, x, z, lift=0.004, relief=True):
        """Project face-space points -> work px (n, 3: x, y, depth)."""
        x = np.asarray(x, np.float64)
        z = np.asarray(z, np.float64)
        p = self.L.params(z)
        xc = np.clip(x, -p["W"] * 0.995, p["W"] * 0.995)
        y = self.L.front(xc, z)
        if relief:
            y = y - self.relief(x, z)
        y = y - lift
        return self.pr.head(np.stack([xc, y, z], -1))

    def vis(self, Q, tol=0.03):
        return self.pr.visible(Q, tol=tol, soft=0.02)

    # ---------------------------------------------------------------------------- strokes
    def line(self, x, z, widths, color=None, alpha=0.9, n=None, soft=0.3, mode="paint",
             depth_test=True, lift=0.004, ink=1.0, relief=True, clip=None):
        x = np.asarray(x, np.float64)
        z = np.asarray(z, np.float64)
        if n is not None and len(x) != n:
            xz = B.resample(np.stack([x, z], -1), n)
            x, z = xz[:, 0], xz[:, 1]
        Q = self.P(x, z, lift, relief)
        w = np.asarray(widths, np.float64)
        if w.ndim and len(w) != len(Q):
            w = np.interp(np.linspace(0, 1, len(Q)), np.linspace(0, 1, len(w)), w)
        w = np.broadcast_to(w, (len(Q),))
        a = alpha * (self.vis(Q) if depth_test else 1.0)
        if np.ndim(a) and np.all(a > 0.98 * alpha):
            a = alpha
        self.cv.stroke(Q, w, color or self.line_rgb, a, mode=mode, soft=soft, ink=ink, clip=clip)
        return Q

    def poly_mask(self, x, z, soft=0.3, lift=0.004, relief=True):
        Q = self.P(x, z, lift, relief)
        m = self.cv.raster([Q[:, :2]])
        return B.blur(m, soft * self.ss) if soft > 0 else m

    def wash_at(self, x, z, r, color, alpha, mode="glaze", power=1.6, aspect=1.0, angle=0.0,
                clip=None):
        Q = self.P(np.array([x]), np.array([z]))[0]
        self.cv.radial(Q[:2], r * self.upx, color, alpha, mode=mode, power=power,
                       aspect=aspect, angle=angle, clip=self.face_m if clip is None else clip)

    # ------------------------------------------------------------------------------ paint
    def paint(self):
        self.washes()
        for s in (-1.0, 1.0):
            self.eye(s)
        for s in (-1.0, 1.0):
            self.brow(s)
        self.nose()
        self.mouth()
        self.wrinkles()

    # ----------------------------------------------------------------------------- washes
    def washes(self):
        f = self.f
        e = f["eyeP"]
        deep = self.skin_d
        fm = self.face_m
        # 三白: lead white on forehead, nose bridge, chin (applied first, under everything)
        wk = f.get("whites", 0.2)
        if wk > 0:
            self.wash_at(0.0, 0.20, 0.13, "pearl", wk, mode="paint", power=1.2, aspect=1.4)
            self.wash_at(0.0, -0.07, 0.07, "pearl", wk * 0.9, mode="paint", power=1.2,
                         aspect=0.45)
            self.wash_at(0.0, -0.43, 0.065, "pearl", wk * 0.8, mode="paint", power=1.3,
                         aspect=1.3)
        # 眼窝: socket shade between brow and lid, deeper at the inner corner by the nose
        so = f.get("socket", 0.2)
        if so > 0:
            for s in (-1, 1):
                x = s * (f["eye_x"] - 0.035)
                self.wash_at(x, f["eye_z"] + 0.055, 0.075, deep, so, power=1.5, aspect=1.6)
                self.wash_at(s * 0.055, f["eye_z"] + 0.02, 0.04, deep, so * 0.9, power=1.4)
        # nose: the far flank and under the tip
        n = f["noseP"]
        far = -self.near
        self.wash_at(far * 0.03, (n["top_z"] + n["tip_z"]) * 0.5, 0.11, deep, 0.30,
                     power=1.4, aspect=0.32)
        self.wash_at(0.0, n["tip_z"] - 0.035, 0.05, deep, 0.25, power=1.4, aspect=1.6)
        # philtrum and under the lower lip
        m = f["mouthP"]
        self.wash_at(0.0, m["z"] - m["lower"] - 0.025, 0.06, deep, 0.28, power=1.5, aspect=1.8)
        # rouge on the cheeks (胭脂)
        r = f["rouge"]
        if r.get("alpha", 0) > 0:
            for s in (-1, 1):
                k = 1.0 if s == self.near else 0.75
                self.wash_at(s * r["x"], r["z"], r["r"], r["color"], r["alpha"] * k,
                             power=1.3, aspect=1.25, angle=0.0)
        er = f.get("eye_rouge", 0.0)
        if er > 0:
            for s in (-1, 1):
                self.wash_at(s * (f["eye_x"] + 0.01), f["eye_z"] - 0.02, 0.10, r["color"], er,
                             power=1.2, aspect=1.5)
        # forehead mark (花钿)
        if f.get("mark"):
            self.mark(f["mark"])
        # ordination dots (戒疤) on a monk's crown
        nd = int(f.get("dots", 0) or 0)
        if nd:
            cols = 3
            for i in range(nd):
                x = ((i % cols) - 1) * 0.055
                z = 0.36 + (i // cols) * 0.035
                self.wash_at(x, z, 0.011, "#8A5A48", 0.75, mode="paint", power=0.6, clip=1.0)

    def mark(self, mk):
        z0 = 0.15
        c = mk.get("color", "cinnabar")
        t = np.linspace(0, 2 * math.pi, 24)
        if mk.get("kind", "drop") == "drop":
            x = 0.008 * np.sin(t)
            z = z0 + 0.016 * np.cos(t) * (1 + 0.3 * np.cos(t))
            m = self.poly_mask(x, z, soft=0.2)
            self.cv.apply(m, c, "paint", 0.9)
        else:
            for k in range(3):
                a = (k - 1) * 0.6
                x = 0.006 * np.sin(t) + math.sin(a) * 0.012
                z = z0 + 0.012 * np.cos(t) + math.cos(a) * 0.012 - 0.006
                m = self.poly_mask(x, z, soft=0.2)
                self.cv.apply(m, c, "paint", 0.85)

    # ------------------------------------------------------------------------------- eyes
    def eye_curves(self, e, u):
        s = u + 0.5
        pk = e["peak"] + 0.5
        sp = np.where(s < pk, 0.5 * s / pk, 0.5 + 0.5 * (s - pk) / (1 - pk))
        base = e["tilt"] * s
        up = base + e["open"] * np.sin(math.pi * np.clip(sp, 0, 1)) ** e["round"]
        pl = 0.55
        sl = np.where(s < pl, 0.5 * s / pl, 0.5 + 0.5 * (s - pl) / (1 - pl))
        lo = base - e["lo"] * np.sin(math.pi * np.clip(sl, 0, 1)) ** 1.1
        return up, lo

    def eye(self, s):
        f = self.f
        e = f["eyeP"]
        ex, ez, ew = f["eye_x"], f["eye_z"], e["w"]
        cv = self.cv

        def X(u, v):
            return s * (ex + u * ew), ez + v * ew
        n = 56
        u = np.linspace(-0.5, 0.5, n)
        vu, vl = self.eye_curves(e, u)
        # opening
        xu, zu = X(u, vu)
        xl, zl = X(u[::-1], vl[::-1])
        Qo = self.P(np.r_[xu, xl], np.r_[zu, zl], lift=0.006)
        om = cv.raster([Qo[:, :2]])
        om = B.blur(om, 0.25 * self.ss)
        vis = float(self.vis(Qo).mean())
        if vis < 0.05:
            return
        om *= vis
        cv.apply(om, SCLERA, "paint", 0.95)
        # soft shade on the eyeball under the upper lid and in the corners
        sh_v = vu - 0.16
        xs, zs = X(u, sh_v)
        Qs = self.P(np.r_[xu, xs[::-1]], np.r_[zu, zs[::-1]], lift=0.006)
        sm = B.blur(cv.raster([Qs[:, :2]]), 0.9 * self.ss)
        cv.apply(sm * om, "#B8A096", "glaze", 0.55)
        # iris (round in head units), looking towards the viewer
        g = f.get("gaze", 0.75)
        r_eb = 0.052
        dx = r_eb * math.sin(self.cam_yaw * g) / ew          # head-x shift in eye widths
        uc = s * dx + e.get("iris_u", 0.0) * s
        dz = r_eb * math.sin(self.cam_pitch * g + f.get("gaze_v", 0.0)) / ew
        vu_c, vl_c = self.eye_curves(e, np.array([np.clip(uc, -0.3, 0.3)]))
        r = e["iris"]
        vc = 0.5 * (vu_c[0] + vl_c[0]) + e.get("iris_up", 0.0) + dz
        t = np.linspace(0, 2 * math.pi, 40, endpoint=False)
        xi, zi = X(uc + r * np.cos(t), vc + r * np.sin(t))
        Qi = self.P(xi, zi, lift=0.006)
        im = B.blur(cv.raster([Qi[:, :2]]), 0.25 * self.ss) * om
        cv.apply(im, IRIS, "paint", 0.97)
        ci = Qi[:, :2].mean(0)
        rx = 0.5 * (Qi[:, 0].max() - Qi[:, 0].min())
        ry = 0.5 * (Qi[:, 1].max() - Qi[:, 1].min())
        # lighter warm ring inside the iris, dark pupil, limbal ring
        cv.radial(ci, max(rx, ry) * 0.95, "#6A4A34", 0.35, mode="paint", power=0.6,
                  clip=im, aspect=rx / max(ry, 1e-6))
        xp, zp = X(uc + r * 0.48 * np.cos(t), vc + r * 0.48 * np.sin(t))
        pm = B.blur(cv.raster([self.P(xp, zp, lift=0.006)[:, :2]]), 0.3 * self.ss) * om
        cv.apply(pm, PUPIL, "paint", 0.95)
        inner = B.blur(cv.raster([self.P(*X(uc + r * 0.8 * np.cos(t), vc + r * 0.8 * np.sin(t)),
                                          lift=0.006)[:, :2]]), 0.3 * self.ss)
        ring = (im - inner).clip(0, 1)
        cv.apply(ring, PUPIL, "paint", 0.5)
        # highlight (a tiny 留白 dot, same image-space side for both eyes)
        hx, hy = ci[0] - 0.32 * rx, ci[1] - 0.36 * ry
        hr = max(0.24 * max(rx, ry), 0.55 * self.ss)
        cv.radial((hx, hy), hr, "#FBF8F0", 0.95, mode="paint", power=0.35, clip=om)
        # ---- lines ----
        line_k = e["line"]
        # upper lid + tail
        tail = e.get("tail", 0.08)
        ut = np.linspace(0, 1, 10)[1:]
        slope = (vu[-1] - vu[-4]) / (u[-1] - u[-4])
        u_tail = 0.5 + tail * ut
        v_tail = vu[-1] + slope * 0.25 * tail * ut + e.get("tail_lift", 0.0) * ut ** 1.3
        uu = np.r_[u[1:], u_tail]
        vv = np.r_[vu[1:], v_tail]
        m = len(uu)
        tt = np.linspace(0, 1, m)
        frac_c = (len(u) - 1) / m
        wp = np.interp(tt, [0, 0.12, 0.45, frac_c * 0.92, frac_c, 1.0],
                       [0.30, 0.75, 1.0, 1.05, 0.85, 0.10])
        self.line(*X(uu, vv), wp * line_k, INK, 0.95, lift=0.008)
        # inner corner hook (内眦): a short turn down towards the nose
        hu = np.array([-0.47, -0.505, -0.535, -0.55])
        hv = np.array([0.03, 0.0, -0.035, -0.06])
        self.line(*X(hu, hv), np.array([0.7, 0.8, 0.6, 0.3]) * line_k * 0.55, INK, 0.85,
                  lift=0.008)
        # lid crease (double eyelid), converging towards the outer corner
        if e.get("crease", 0) > 0:
            uc_ = np.linspace(-0.30, 0.47, 24)
            vu_, _ = self.eye_curves(e, uc_)
            vcr = vu_ + e["crease"] * (1 - 0.55 * geo.smoothstep(0.1, 0.5, uc_)) \
                + 0.02 * np.sin((uc_ + 0.3) / 0.77 * math.pi)
            wcr = np.interp(np.linspace(0, 1, 24), [0, 0.3, 0.8, 1], [0.2, 0.75, 0.7, 0.15])
            self.line(*X(uc_, vcr), wcr * 0.85, self.line_col(0.75), e.get("crease_a", 0.45),
                      lift=0.008)
        if e.get("hood", 0) > 0:
            # elder: a soft fold of the upper lid over the outer half
            uh = np.linspace(0.0, 0.62, 18)
            vuh, _ = self.eye_curves(e, np.clip(uh, -0.5, 0.5))
            vh = vuh + e["crease"] * 1.5 - 0.10 * geo.smoothstep(0.25, 0.62, uh)
            self.line(*X(uh, vh), np.interp(np.linspace(0, 1, 18), [0, 0.4, 1], [0.2, 0.7, 0.2]),
                      self.line_col(0.8), 0.45 * e["hood"], lift=0.008)
        # lower lid: light, open at the inner corner
        ul = np.linspace(-0.36, 0.49, 26)
        _, vl_ = self.eye_curves(e, ul)
        wl = np.interp(np.linspace(0, 1, 26), [0, 0.3, 0.75, 1], [0.15, 0.7, 0.8, 0.45])
        self.line(*X(ul, vl_ - 0.01), wl * 0.9, self.line_col(0.7), e.get("lower_a", 0.5),
                  lift=0.008)

    def line_col(self, k=0.8):
        """Skin line colour, ``k`` < 1 deepens towards ink."""
        a = np.array(self.line_rgb)
        b = np.array(PL.srgb(INK))
        return tuple(a * k + b * (1 - k))

    # ------------------------------------------------------------------------------ brows
    def brow_geometry(self, s):
        f = self.f
        b = f["browP"]
        knit = f.get("knit", 0.0)
        x0 = b["x0"] - knit * 0.006
        z0 = b["z0"] - knit * 0.016 + f.get("brow_dz", 0.0)
        x1, z1 = b["x1"], b["z1"] + knit * 0.006 + f.get("brow_dz", 0.0)
        pf, ph = b["peak"]
        pts = [(x0, z0), (x0 + (x1 - x0) * pf * 0.5, z0 + (z1 - z0) * pf * 0.5 + ph * 0.75),
               (x0 + (x1 - x0) * pf, z0 + (z1 - z0) * pf + ph), (x1, z1)]
        if b.get("droop"):
            d = b["droop"]
            pts.append((x1 + 0.025, z1 - d * 0.45))
            pts.append((x1 + 0.035, z1 - d))
        C = B.catmull(np.array(pts), 60)
        t = np.linspace(0, 1, len(C))
        th = b["thick"]
        sh = b["shape"]
        if sh == "silkworm":
            w = th * (0.80 + 0.30 * np.sin(math.pi * np.clip(t * 1.1, 0, 1)))
            w *= np.clip(t / 0.07, 0, 1) ** 0.35 * 0.35 + 0.65
            w *= np.clip((1 - t) / 0.30, 0, 1) ** 0.7 * 0.8 + 0.2
        elif sh == "sword":
            w = th * (1.05 - 0.55 * t)
            w *= np.clip(t / 0.06, 0, 1) ** 0.4 * 0.3 + 0.7
            w *= np.clip((1 - t) / 0.35, 0, 1) ** 0.9 * 0.85 + 0.15
        elif sh == "willow":
            w = th * np.sin(math.pi * np.clip(t, 0, 1) ** 0.8) ** 0.75
            w = np.maximum(w, th * 0.12)
        elif sh == "longevity":
            w = th * (0.75 + 0.35 * np.sin(math.pi * t))
            w *= np.clip((1 - t) / 0.25, 0, 1) ** 0.6 * 0.7 + 0.3
        else:
            w = th * (0.72 + 0.28 * np.sin(math.pi * t))
            w *= np.clip(t / 0.1, 0, 1) ** 0.5 * 0.4 + 0.6
            w *= np.clip((1 - t) / 0.3, 0, 1) ** 0.8 * 0.75 + 0.25
        d = np.gradient(C, axis=0)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        nrm = np.stack([-d[:, 1], d[:, 0]], -1)
        return C, w, d, nrm

    def brow(self, s):
        f = self.f
        b = f["browP"]
        C, w, d, nrm = self.brow_geometry(s)
        col = f.get("brow_color", "ink")
        cols = {"ink": (INK, INK, None), "grey": ("#5E5852", "#2A2622", "#B8B2A8"),
                "white": ("#7E786E", "#F7F4EE", "#5A544A"),
                "grizzled": ("#3E3A36", "#1E1A16", "#C8C2B6")}[col]
        base_c, hair_c, alt_c = cols
        # base wash (lighter at the tail)
        top = C + nrm * (w[:, None] * 0.5)
        bot = C - nrm * (w[:, None] * 0.5)
        poly = np.concatenate([top, bot[::-1]], 0)
        x = poly[:, 0] * s
        z = poly[:, 1]
        Q = self.P(x, z, lift=0.006)
        v = self.vis(Q)
        if v.mean() < 0.05:
            return
        m = B.blur(self.cv.raster([Q[:, :2]]), 0.7 * self.ss)
        # fade the tail
        fade = np.interp(np.linspace(0, 1, len(C)), [0, 0.6, 1], [1.0, 0.85, 0.45])
        Qc = self.P(C[:, 0] * s, C[:, 1], lift=0.006)
        fm = self.cv.strokes_mask([(Qc, w * self.upx / self.ss * 1.6, fade)], soft=1.2)
        self.cv.apply(m * (fm * 1.4).clip(0, 1), base_c, "paint", b["wash"] * float(v.mean()),
                      ink=0.6)
        # hairs
        nh = int(90 * b.get("hairs", 1.0))
        hair_len = b.get("hair_len", 1.0)
        rng = self.rng
        strokes, strokes2 = [], []
        for _ in range(nh):
            t = rng.random() ** 1.15
            i = int(t * (len(C) - 1))
            a = (rng.random() - 0.5) * 0.9
            root = C[i] + nrm[i] * a * w[i]
            # hair direction: steep at the head, along the brow later, converging to the centre
            ang_head = math.radians(65) * (1 - geo.smoothstep(0.0, 0.22, t))
            conv = -a * math.radians(b.get("conv", 38))
            ang = ang_head + conv + rng.normal() * math.radians(6)
            dd = d[i] * math.cos(ang) + nrm[i] * math.sin(ang)
            ln = (0.55 + 0.5 * rng.random()) * max(w[i], 0.012) * 1.6 * hair_len
            if b["shape"] == "longevity" and t > 0.6:
                ln *= 1.8
                dd = dd + np.array([0.0, -0.6 * (t - 0.6)])
                dd /= np.linalg.norm(dd)
            pts = np.array([root, root + dd * ln * 0.5 + nrm[i] * 0.0015 * rng.normal(),
                            root + dd * ln])
            pts = B.catmull(pts, 6)
            Qh = self.P(pts[:, 0] * s, pts[:, 1], lift=0.007)
            wid = np.array([0.55, 0.6, 0.55, 0.45, 0.3, 0.12]) * 0.75
            al = (0.55 + 0.4 * rng.random()) * fade[i]
            if alt_c is not None and rng.random() < (0.45 if col == "white" else 0.3):
                strokes2.append((Qh, wid, al * 0.8))
            else:
                strokes.append((Qh, wid, al))
        vm = float(v.mean())
        light_first = col == "white"
        seq = [(strokes2, alt_c, 0.85), (strokes, hair_c, 0.92)] if light_first else \
            [(strokes, hair_c, 0.9), (strokes2, alt_c, 0.85)]
        for sk, cc, aa in seq:
            if sk:
                mk = self.cv.strokes_mask(sk, soft=0.25)
                self.cv.apply(mk, cc, "paint", aa * vm, ink=0.6)

    # ------------------------------------------------------------------------------- nose
    def nose(self):
        f = self.f
        n = f["noseP"]
        near, far = self.near, -self.near
        lk = n.get("line", 1.0)
        tip, top = n["tip_z"], n["top_z"]
        tw, aw = n["tip_w"], n["ala_w"]
        lc = self.line_col(0.8)
        # bridge line along the far flank, from the brow down towards the tip
        z = np.linspace(top + 0.01, tip + 0.035, 30)
        x = far * (0.006 + 0.010 * geo.smoothstep(top, tip, z))
        wb = np.interp(np.linspace(0, 1, 30), [0, 0.2, 0.7, 1], [0.15, 0.55, 0.7, 0.35])
        self.line(x, z, wb * lk, lc, 0.55, lift=0.004)
        # tip: a short hook from the far flank round the underside of the tip (勾)
        a = np.linspace(0, 1, 16)
        xt = far * (tw * 0.95 - tw * 0.95 * a)
        zt = tip + 0.016 - 0.036 * np.sin(a * math.pi * 0.5)
        wt = np.interp(a, [0, 0.4, 0.85, 1], [0.1, 0.65, 0.5, 0.1])
        self.line(xt, zt, wt * lk, lc, 0.55, lift=0.003)
        # near nostril wing: a separate small curl (the strongest nose line)
        th = np.linspace(0.0, 1.0, 18)
        xa = near * (aw * 0.55 + aw * 0.42 * np.sin(th * math.pi * 0.95))
        za = tip + 0.018 - 0.040 * th
        wa = np.interp(th, [0, 0.3, 0.7, 1], [0.12, 0.85, 0.9, 0.2])
        self.line(xa, za, wa * 1.0 * lk, lc, 0.8, lift=0.003)
        # far ala: barely there
        th2 = np.linspace(0.0, 1.0, 10)
        xf = far * (aw * 0.62 + aw * 0.25 * np.sin(th2 * math.pi))
        zf = tip + 0.006 - 0.024 * th2
        self.line(xf, zf, np.interp(th2, [0, 0.5, 1], [0.1, 0.4, 0.1]) * lk, lc, 0.22, lift=0.002)
        # nostrils: small dark commas under the tip
        for side, k in ((near, 1.0), (far, 0.6)):
            t = np.linspace(0, 2 * math.pi, 16, endpoint=False)
            cx = side * aw * 0.40
            cz = tip - 0.024
            xs = cx + 0.013 * k * np.cos(t)
            zs = cz + 0.006 * np.sin(t)
            m = self.poly_mask(xs, zs, soft=0.5, lift=0.002)
            self.cv.apply(m * (self.face_m if self.face_m is not None else 1), "#4A2A20",
                          "paint", 0.7 * k)

    # ------------------------------------------------------------------------------ mouth
    def mouth(self):
        f = self.f
        m = f["mouthP"]
        mz, mw = m["z"], m["w"]
        cz = m["corner"]
        ul, ll, bow = m["upper"], m["lower"], m["bow"]
        # mouth line (口缝): corners, slight centre dip
        xs = np.array([-1.0, -0.62, -0.25, 0.0, 0.25, 0.62, 1.0]) * mw
        zs = mz + np.array([cz, 0.002, 0.0, -0.004, 0.0, 0.002, cz])
        C = B.catmull(np.stack([xs, zs], -1), 40)
        # upper lip shape
        ux = np.array([-1.0, -0.6, -0.22, 0.0, 0.22, 0.6, 1.0]) * mw
        uz = mz + np.array([cz, ul * 0.65, ul, ul - bow, ul, ul * 0.65, cz])
        U = B.catmull(np.stack([ux, uz], -1), 40)
        # lower lip
        lx = np.array([-1.0, -0.55, 0.0, 0.55, 1.0]) * mw * 0.94
        lz = mz + np.array([cz, -ll * 0.75, -ll, -ll * 0.75, cz])
        Lw = B.catmull(np.stack([lx, lz], -1), 40)
        col = m["color"]
        um = self.poly_mask(np.r_[U[:, 0], C[::-1, 0]], np.r_[U[:, 1], C[::-1, 1]], soft=0.45)
        lm = self.poly_mask(np.r_[C[:, 0], Lw[::-1, 0]], np.r_[C[:, 1], Lw[::-1, 1]], soft=0.6)
        self.cv.apply(um, col, "glaze", m["alpha"])
        self.cv.apply(um, col, "paint", m["alpha"] * 0.35)
        self.cv.apply(lm, PL.mix(col, "pearl", 0.18), "glaze", m["alpha"] * 0.9)
        self.cv.apply(lm, PL.mix(col, "pearl", 0.18), "paint", m["alpha"] * 0.25)
        # lower-lip highlight
        self.wash_at(0.0, mz - ll * 0.5, 0.025, "pearl", 0.35 * m["alpha"], mode="paint",
                     power=1.2, aspect=2.0)
        # the line
        t = np.linspace(0, 1, 40)
        w = 0.55 + 0.5 * np.exp(-((t - 0.5) / 0.12) ** 2) + 0.45 * (np.exp(-(t / 0.08) ** 2)
                                                                   + np.exp(-((1 - t) / 0.08) ** 2))
        w *= np.clip(t / 0.03, 0, 1) * np.clip((1 - t) / 0.03, 0, 1) * 0.6 + 0.4
        self.line(C[:, 0], C[:, 1], w * m.get("line", 1.0), "#5E2420", 0.85, lift=0.004)
        # faint upper-lip contour on the near half (definition, 游丝)
        k = U[:, 0] * self.near > -0.3 * mw
        if k.sum() > 4:
            self.line(U[k, 0], U[k, 1] + 0.002, 0.45, PL.mix(col, "skin_line", 0.5), 0.25,
                      lift=0.004)

    # --------------------------------------------------------------------------- wrinkles
    def wrinkles(self):
        f = self.f
        wr = f.get("wrinkles", {})
        lc = self.line_col(0.85)
        rng = self.rng
        e = f["eyeP"]
        ex, ew = f["eye_x"], e["w"]
        # forehead lines (broken, slightly arched)
        for i in range(int(wr.get("forehead", 0))):
            z0 = 0.175 + i * 0.038
            for seg in ((-0.15, -0.02), (0.01, 0.15)):
                x = np.linspace(seg[0], seg[1], 16) + rng.normal() * 0.006
                z = z0 + 0.012 * np.cos(x / 0.15 * 1.4) + rng.normal() * 0.003
                self.line(x, z, np.interp(np.linspace(0, 1, 16), [0, 0.5, 1], [0.1, 0.6, 0.1]),
                          lc, 0.30, lift=0.003)
        # crow's feet
        for s in (-1, 1):
            for i in range(int(wr.get("crow", 0))):
                a = math.radians(-25 + 25 * i)
                x0 = s * (ex + ew * 0.62)
                z0 = f["eye_z"] + 0.012
                L = 0.035 + 0.01 * i
                x = x0 + s * np.linspace(0, L, 8) * math.cos(a)
                z = z0 + np.linspace(0, L, 8) * math.sin(a)
                self.line(x, z, np.linspace(0.55, 0.1, 8), lc, 0.35, lift=0.003)
        # under-eye bags
        if wr.get("bags", 0) > 0:
            for s in (-1, 1):
                u = np.linspace(-0.25, 0.45, 16)
                _, vl = self.eye_curves(e, u)
                x = s * (ex + u * ew)
                z = f["eye_z"] + (vl - 0.12) * ew
                self.line(x, z, np.interp(np.linspace(0, 1, 16), [0, 0.5, 1], [0.1, 0.6, 0.1]),
                          lc, 0.35 * wr["bags"], lift=0.004)
        # nasolabial folds
        if wr.get("naso", 0) > 0:
            n = f["noseP"]
            m = f["mouthP"]
            for s in (-1, 1):
                x = s * np.array([n["ala_w"] * 1.12, n["ala_w"] * 1.35, m["w"] * 1.25,
                                  m["w"] * 1.32])
                z = np.array([n["tip_z"] + 0.005, n["tip_z"] - 0.04, m["z"] - 0.005,
                              m["z"] - 0.05])
                C = B.catmull(np.stack([x, z], -1), 24)
                k = 1.0 if s == self.near else 0.7
                self.line(C[:, 0], C[:, 1], np.interp(np.linspace(0, 1, 24), [0, 0.3, 1],
                                                      [0.2, 0.75, 0.1]),
                          lc, 0.45 * wr["naso"] * k, lift=0.004)
        # knit lines between the brows (川)
        for i in range(int(wr.get("knit", 0))):
            xk = (i - (wr["knit"] - 1) / 2) * 0.022
            z = np.linspace(0.07, 0.125, 10)
            self.line(xk + 0.004 * np.sin(z * 40), z, np.interp(np.linspace(0, 1, 10),
                                                                [0, 0.5, 1], [0.1, 0.6, 0.1]),
                      lc, 0.4, lift=0.003)
        # mouth-corner lines
        if wr.get("mouth", 0) > 0:
            m = f["mouthP"]
            for s in (-1, 1):
                x = s * np.array([m["w"] * 1.08, m["w"] * 1.14, m["w"] * 1.1])
                z = m["z"] + np.array([0.0, -0.025, -0.05])
                self.line(x, z, np.array([0.2, 0.55, 0.15]), lc, 0.35 * wr["mouth"], n=10,
                          lift=0.004)

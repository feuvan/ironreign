"""2D curve helpers for the gongbi drawing system (pure numpy, no bpy).

All curves are numpy arrays of shape (N, 2) in canvas pixels (x right, y down).
Templates are authored as *through points* (centripetal Catmull-Rom), which is how a painter
thinks of a brush line: "start here, pass there, end here".
"""

import math

import numpy as np


def A(pts):
    return np.asarray(pts, dtype=float).reshape(-1, 2)


def catmull(pts, n=10, closed=False, alpha=0.5):
    """Centripetal Catmull-Rom spline through ``pts`` -> dense polyline."""
    P = A(pts)
    if len(P) < 2:
        return P.copy()
    if len(P) == 2 and not closed:
        t = np.linspace(0, 1, n + 1)[:, None]
        return P[0] * (1 - t) + P[1] * t
    if closed:
        Q = np.vstack([P[-1], P, P[0], P[1]])
    else:
        Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        d01 = max(np.linalg.norm(p1 - p0), 1e-6) ** alpha
        d12 = max(np.linalg.norm(p2 - p1), 1e-6) ** alpha
        d23 = max(np.linalg.norm(p3 - p2), 1e-6) ** alpha
        t0, t1 = 0.0, d01
        t2 = t1 + d12
        t3 = t2 + d23
        ts = np.linspace(t1, t2, n, endpoint=False)[:, None]
        a1 = (t1 - ts) / (t1 - t0) * p0 + (ts - t0) / (t1 - t0) * p1
        a2 = (t2 - ts) / (t2 - t1) * p1 + (ts - t1) / (t2 - t1) * p2
        a3 = (t3 - ts) / (t3 - t2) * p2 + (ts - t2) / (t3 - t2) * p3
        b1 = (t2 - ts) / (t2 - t0) * a1 + (ts - t0) / (t2 - t0) * a2
        b2 = (t3 - ts) / (t3 - t1) * a2 + (ts - t1) / (t3 - t1) * a3
        c = (t2 - ts) / (t2 - t1) * b1 + (ts - t1) / (t2 - t1) * b2
        out.append(c)
    if not closed:
        out.append(P[-1][None])
    return np.vstack(out)


def bezier(p0, p1, p2, p3, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def seglen(P):
    return np.linalg.norm(np.diff(P, axis=0), axis=1)


def length(P):
    return float(seglen(P).sum())


def arclen(P):
    return np.concatenate([[0.0], np.cumsum(seglen(P))])


def resample(P, n=None, step=None, closed=False):
    """Uniform arc-length resampling to ``n`` points (or spacing ``step``)."""
    P = A(P)
    if closed:
        P = np.vstack([P, P[:1]])
    s = arclen(P)
    L = s[-1]
    if L <= 1e-9:
        return np.repeat(P[:1], n or 2, axis=0)
    if n is None:
        n = max(2, int(math.ceil(L / step)) + 1)
    if closed:
        u = np.linspace(0, L, n, endpoint=False)
    else:
        u = np.linspace(0, L, n)
    x = np.interp(u, s, P[:, 0])
    y = np.interp(u, s, P[:, 1])
    return np.stack([x, y], 1)


def tangents(P, closed=False):
    if closed:
        T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
    else:
        T = np.gradient(P, axis=0)
    n = np.linalg.norm(T, axis=1, keepdims=True)
    return T / np.maximum(n, 1e-9)


def normals(P, closed=False):
    """Left-hand normals in screen space (x right, y down): rotate tangent by +90 deg."""
    T = tangents(P, closed)
    return np.stack([-T[:, 1], T[:, 0]], 1)


def offset(P, d, closed=False):
    d = np.asarray(d, float)
    if d.ndim == 0:
        d = np.full(len(P), float(d))
    return P + normals(P, closed) * d[:, None]


def sub(P, t0, t1, n=None):
    """Portion of polyline between arc-length fractions t0..t1."""
    s = arclen(P)
    L = s[-1]
    n = n or max(2, int(len(P) * abs(t1 - t0)) + 2)
    u = np.linspace(t0 * L, t1 * L, n)
    return np.stack([np.interp(u, s, P[:, 0]), np.interp(u, s, P[:, 1])], 1)


def at(P, t):
    """Point at arc-length fraction t."""
    s = arclen(P)
    u = t * s[-1]
    return np.array([np.interp(u, s, P[:, 0]), np.interp(u, s, P[:, 1])])


def lerp(a, b, t):
    return np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0 + 1e-12), 0, 1)
    return t * t * (3 - 2 * t)


def ellipse(c, rx, ry, rot=0.0, n=48, a0=0.0, a1=2 * math.pi, endpoint=False):
    a = np.linspace(a0, a1, n, endpoint=endpoint)
    x = rx * np.cos(a)
    y = ry * np.sin(a)
    cr, sr = math.cos(rot), math.sin(rot)
    return np.stack([c[0] + x * cr - y * sr, c[1] + x * sr + y * cr], 1)


def rot(P, ang, about=(0, 0)):
    P = A(P) - about
    c, s = math.cos(ang), math.sin(ang)
    return np.stack([P[:, 0] * c - P[:, 1] * s, P[:, 0] * s + P[:, 1] * c], 1) + about


def area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def clip_convex(subject, clip):
    """Sutherland-Hodgman: polygon ``subject`` clipped by convex polygon ``clip``."""
    clip = A(clip)
    if area(clip) < 0:
        clip = clip[::-1]
    out = [tuple(p) for p in A(subject)]
    for i in range(len(clip)):
        a = clip[i]
        b = clip[(i + 1) % len(clip)]
        inp = out
        out = []
        if not inp:
            break

        def inside(p):
            return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

        def inter(p, q):
            x1, y1 = p
            x2, y2 = q
            x3, y3 = a
            x4, y4 = b
            den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(den) < 1e-12:
                return q
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
            return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

        s = inp[-1]
        for e in inp:
            if inside(e):
                if not inside(s):
                    out.append(inter(s, e))
                out.append(e)
            elif inside(s):
                out.append(inter(s, e))
            s = e
    return np.array(out, float).reshape(-1, 2)


def smooth_noise(n, seed=0, octaves=3, scale=6.0):
    """Smooth 1D noise in [-1, 1] sampled at n points (sum of random sines)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, n)
    out = np.zeros(n)
    amp = 1.0
    tot = 0.0
    for o in range(octaves):
        f = scale * (2 ** o) * rng.uniform(0.7, 1.3)
        ph = rng.uniform(0, 2 * math.pi)
        out += amp * np.sin(2 * math.pi * f * t + ph)
        tot += amp
        amp *= 0.5
    return out / tot


def poly_contains(poly, pts):
    """Even-odd point in polygon test (vectorised over pts)."""
    poly = A(poly)
    pts = A(pts)
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        inside ^= cond
        j = i
    return inside

"""Illustrated Scenes: art-directed sky dome, aerial perspective and valley mist (Cycles).

Three node groups, built once per scene from one ``sky`` dict:

``IR_SkyBase`` (direction -> colour)
    Elevation gradient (stops in sin(elevation)), sun / moon glows (several lobes each), a warm
    horizon band towards the sun.  No clouds.  Used by the world AND by the aerial perspective
    of every material, so distant mountains always fade into exactly the sky behind them.

``IR_SkyCam`` (direction, base -> colour)
    What the camera sees: perspective-correct cloud decks (a noise field projected on a plane at
    ``height`` m, self-shadowed towards the sun, silver lining, fading into the horizon haze),
    stars, the moon disc, the sun disc and comets.

``IR_Fog`` (shader -> shader)
    Exponential height fog on camera and glossy rays: a thin *haze* layer coloured by the sky along
    the view ray and a dense low *mist* layer (valley mist) with its own colour.  It is inserted
    in front of every material output (:func:`apply_fog`), or by material factories before the
    transparency mix (:func:`fog_wrap`), so cut-out cards never show their rectangle.

The world shows ``IR_SkyCam`` to camera and glossy rays (water reflects the clouds) and a simpler
``IR_SkyBase`` x ``light`` to diffuse rays (ambient light is art-directed separately).

Directions: world +Z up, the cameras of this family look roughly along +Y.  Azimuth ``az`` is in
degrees counter-clockwise from +X (east), so with a camera looking +Y: az 90 = straight ahead,
az 150-170 = ahead-left, az 200 = behind-left.  Colours are sRGB hex (converted to linear).
"""

import math

import bpy
from mathutils import Vector

from . import palette
from .materials import NB, sock


def dir_from(az_deg, el_deg):
    a, e = math.radians(az_deg), math.radians(el_deg)
    return Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))


def lin(c):
    if isinstance(c, str):
        return tuple(palette.lin(c))
    return tuple(c[:3])


def lin4(c):
    return lin(c) + (1.0,)


def scaled(c, k):
    return tuple(x * k for x in lin(c)) + (1.0,)


# ---------------------------------------------------------------------------------------------
# a node-graph helper with vector maths
# ---------------------------------------------------------------------------------------------
class G(NB):
    """NB plus vector maths / constants for building groups."""

    def vmath(self, op, a, b=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.set(n.inputs[0], a)
        if b is not None:
            self.set(n.inputs[1], b)
        if scale is not None:
            self.set(n.inputs[3], scale)
        return n

    def vec(self, v):
        n = self.node("ShaderNodeCombineXYZ")
        for i, k in enumerate("XYZ"):
            n.inputs[k].default_value = float(v[i])
        return n.outputs[0]

    def comb(self, x, y, z):
        n = self.node("ShaderNodeCombineXYZ")
        self.set(n.inputs["X"], x)
        self.set(n.inputs["Y"], y)
        self.set(n.inputs["Z"], z)
        return n.outputs[0]

    def sep(self, v):
        n = self.node("ShaderNodeSeparateXYZ")
        self.set(n.inputs[0], v)
        return n.outputs

    def rgb(self, c):
        n = self.node("ShaderNodeRGB")
        n.outputs[0].default_value = lin4(c) if isinstance(c, str) or len(c) == 3 else tuple(c)
        return n.outputs[0]

    def cmul(self, col, k):
        """colour * scalar socket/value (ShaderNodeMix MULTIPLY with a grey)."""
        if isinstance(k, (int, float)):
            return self.mix(col, (k, k, k, 1.0), 1.0, blend="MULTIPLY", clamp=False)
        g = self.node("ShaderNodeCombineColor")
        for ch in ("Red", "Green", "Blue"):
            self.set(g.inputs[ch], k)
        return self.mix(col, g.outputs[0], 1.0, blend="MULTIPLY", clamp=False)

    def cadd(self, a, b):
        return self.mix(a, b, 1.0, blend="ADD", clamp=False)

    def smooth(self, x, e0, e1, b0=0.0, b1=1.0):
        return self.maprange(x, e0, e1, b0, b1, clamp=True, interp="SMOOTHSTEP")

    def clamp01(self, x):
        n = self.node("ShaderNodeClamp")
        self.set(n.inputs["Value"], x)
        return n.outputs[0]


def new_group(name, inputs, outputs):
    """Shader node group with ``inputs`` / ``outputs`` = [(name, socket_type), ...]."""
    g = bpy.data.node_groups.get(name)
    if g is not None:
        bpy.data.node_groups.remove(g)
    g = bpy.data.node_groups.new(name, "ShaderNodeTree")
    for nm, st in inputs:
        g.interface.new_socket(nm, in_out="INPUT", socket_type=st)
    for nm, st in outputs:
        g.interface.new_socket(nm, in_out="OUTPUT", socket_type=st)
    gb = G(g)
    gi = gb.node("NodeGroupInput")
    go = gb.node("NodeGroupOutput")
    return g, gb, gi, go


# ---------------------------------------------------------------------------------------------
# sky dict defaults
# ---------------------------------------------------------------------------------------------
DEFAULT = dict(
    # gradient stops: (sin(elevation), colour); below the horizon the horizon colour is used
    stops=[(0.0, "#F2D2A2"), (0.06, "#E9C08E"), (0.2, "#A9B8C6"), (0.5, "#6F8DB0"),
           (1.0, "#3E5F8C")],
    strength=1.0,
    # glows: dir (az, el), colour, lobes [(power, amount)], horizon band (amount, width, power)
    glows=[],
    discs=[],               # dict(dir=(az, el), radius_deg, color, strength, texture=0..1)
    clouds=[],              # see _clouds()
    stars=None,             # dict(density, size, strength, color)
    comet=None,             # dict(head=(az, el), tail_az_deg (screen-ish tangent), ...)
    light=dict(strength=1.0, tint="#FFFFFF"),   # ambient (diffuse rays) multiplier / tint
    # aerial perspective & mist
    fog=dict(haze=0.0004, haze_falloff=0.0015, haze_h0=0.0, haze_max=0.92, haze_tint="#FFFFFF",
             haze_zmax=0.18, mist=0.0, mist_falloff=0.08, mist_h0=0.0, mist_max=0.85,
             mist_color="#D8D0C4", mist_strength=1.0),
)


def merged(sky):
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT.items()}
    for k, v in sky.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    return s


# ---------------------------------------------------------------------------------------------
# IR_SkyBase
# ---------------------------------------------------------------------------------------------
def _sky_base(sky):
    g, b, gi, go = new_group("IR_SkyBase", [("Vector", "NodeSocketVector")],
                             [("Color", "NodeSocketColor")])
    D = b.vmath("NORMALIZE", gi.outputs[0]).outputs[0]
    x, y, z = b.sep(D)
    zc = b.math("MAXIMUM", z, 0.0)
    col = b.ramp(zc, [(p, lin4(c)) for p, c in sky["stops"]])
    col = b.cmul(col, sky["strength"])
    # horizontal unit direction (for horizon bands)
    Hd = b.vmath("NORMALIZE", b.comb(x, y, 0.0)).outputs[0]
    for gl in sky["glows"]:
        S = dir_from(*gl["dir"])
        cosA = b.vmath("DOT_PRODUCT", D, b.vec(S)).outputs[1]
        c = b.math("MAXIMUM", cosA, 0.0)
        tot = None
        for pw, amt in gl.get("lobes", []):
            t = b.math("MULTIPLY", b.math("POWER", c, float(pw)), float(amt))
            tot = t if tot is None else b.math("ADD", tot, t)
        hb = gl.get("horizon")
        if hb:
            amt, width, pw = hb
            Sh = Vector((S.x, S.y, 0.0)).normalized()
            ch = b.vmath("DOT_PRODUCT", Hd, b.vec(Sh)).outputs[1]
            ch = b.math("POWER", b.math("ADD", b.math("MULTIPLY", ch, 0.5), 0.5), float(pw))
            band = b.math("EXPONENT", b.math("DIVIDE", b.math("MULTIPLY", zc, -1.0), float(width)))
            t = b.math("MULTIPLY", b.math("MULTIPLY", ch, band), float(amt))
            tot = t if tot is None else b.math("ADD", tot, t)
        if tot is not None:
            col = b.cadd(col, b.cmul(lin4(gl["color"]), tot))
    b.link(col, go.inputs[0])
    return g


# ---------------------------------------------------------------------------------------------
# IR_SkyCam: clouds, stars, discs, comet
# ---------------------------------------------------------------------------------------------
def _clouds(b, D, z, col, base, cl, sun_dir):
    """One perspective cloud deck.  cl keys:
    height (m), scale (m per noise unit), coverage (0..1), softness, detail, roughness,
    stretch (x, y), offset (x, y), lit / shadow / rim colours, rim (amount), shade (gain),
    opacity, fade (z where the deck reaches full opacity), haze (mix towards base far away),
    step (m, self-shadow probe distance), distortion, seed, top (z above which it fades)."""
    zs = b.math("MAXIMUM", z, 0.012)
    x, y, _ = b.sep(D)
    H = float(cl.get("height", 1500.0))
    sx, sy = cl.get("stretch", (1.0, 1.0))
    sc = float(cl.get("scale", 1800.0))
    ox, oy = cl.get("offset", (0.0, 0.0))
    px = b.math("ADD", b.math("MULTIPLY", b.math("DIVIDE", x, zs), H / (sc * sx)), ox)
    py = b.math("ADD", b.math("MULTIPLY", b.math("DIVIDE", y, zs), H / (sc * sy)), oy)
    seed = float(cl.get("seed", 0.0))
    P = b.comb(px, py, seed)

    def noise(vec):
        n = b.node("ShaderNodeTexNoise", noise_dimensions="3D")
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Detail"].default_value = cl.get("detail", 9.0)
        n.inputs["Roughness"].default_value = cl.get("roughness", 0.58)
        n.inputs["Distortion"].default_value = cl.get("distortion", 0.25)
        b.link(vec, n.inputs["Vector"])
        return n.outputs["Fac"]

    n = noise(P)
    cov = float(cl.get("coverage", 0.5))
    soft = float(cl.get("softness", 0.12))
    c0 = 1.0 - cov * 0.6 - 0.2
    dens = b.smooth(n, c0, c0 + soft)
    # self shadow: probe towards the sun on the plane
    sd = Vector((sun_dir.x, sun_dir.y, 0.0))
    if sd.length < 1e-4:
        sd = Vector((0, 1, 0))
    sd.normalize()
    stp = float(cl.get("step", 0.06))
    P2 = b.vmath("ADD", P, b.vec((sd.x * stp / sx, sd.y * stp / sy, 0.0))).outputs[0]
    n2 = noise(P2)
    shade = b.clamp01(b.math("ADD", b.math("MULTIPLY", b.math("SUBTRACT", n, n2),
                                           float(cl.get("shade", 9.0))), 0.55))
    # thick cores are darker underneath (bigger clouds)
    core = b.smooth(n, c0 + soft, c0 + soft + 0.22)
    shade = b.math("SUBTRACT", shade, b.math("MULTIPLY", core, float(cl.get("core_dark", 0.35))))
    shade = b.clamp01(shade)
    ccol = b.mix(lin4(cl.get("shadow", "#6A6E80")), lin4(cl.get("lit", "#F4E2C8")), shade)
    # silver lining near the sun on thin parts
    cosA = b.vmath("DOT_PRODUCT", D, b.vec(sun_dir)).outputs[1]
    near = b.math("POWER", b.math("MAXIMUM", cosA, 0.0), float(cl.get("rim_power", 10.0)))
    thin = b.math("SUBTRACT", 1.0, core)
    rim = b.math("MULTIPLY", b.math("MULTIPLY", near, thin), float(cl.get("rim", 2.0)))
    ccol = b.cadd(ccol, b.cmul(lin4(cl.get("rim_color", "#FFE0A8")), rim))
    # far clouds dissolve into the haze
    fade = b.smooth(z, 0.0, float(cl.get("fade", 0.10)))
    hz = float(cl.get("haze", 0.55))
    ccol = b.mix(base, ccol, b.math("ADD", 1.0 - hz, b.math("MULTIPLY", fade, hz)))
    a = b.math("MULTIPLY", dens, float(cl.get("opacity", 0.9)))
    a = b.math("MULTIPLY", a, b.smooth(z, 0.0, float(cl.get("fade", 0.10)) * 0.6))
    top = cl.get("top")
    if top:
        a = b.math("MULTIPLY", a, b.maprange(z, top, top + 0.2, 1.0, 0.0, clamp=True,
                                             interp="SMOOTHSTEP"))
    band = cl.get("band")
    if band:
        # restrict the deck to a band of azimuths/elevations via a mask noise (clouds in patches)
        m = noise(b.vmath("MULTIPLY", P, b.vec((0.25, 0.25, 1.0))).outputs[0])
        a = b.math("MULTIPLY", a, b.smooth(m, band[0], band[1]))
    return b.mix(col, ccol, a)


def _sky_cam(sky, base_group):
    g, b, gi, go = new_group("IR_SkyCam", [("Vector", "NodeSocketVector"),
                                           ("Base", "NodeSocketColor")],
                             [("Color", "NodeSocketColor")])
    D = b.vmath("NORMALIZE", gi.outputs[0]).outputs[0]
    x, y, z = b.sep(D)
    base = gi.outputs[1]
    col = base
    sun = sky["glows"][0]["dir"] if sky["glows"] else (90.0, 30.0)
    sun_dir = dir_from(*sun)
    # stars (behind clouds)
    st = sky.get("stars")
    if st:
        v = b.node("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="F1")
        v.inputs["Scale"].default_value = st.get("density", 260.0)
        b.link(D, v.inputs["Vector"])
        dist = v.outputs["Distance"]
        rnd = b.sep(v.outputs["Color"])[0]
        bright = b.math("POWER", rnd, float(st.get("power", 6.0)))
        dot = b.maprange(dist, 0.0, st.get("size", 0.06), 1.0, 0.0, interp="SMOOTHSTEP")
        s = b.math("MULTIPLY", b.math("MULTIPLY", dot, bright), st.get("strength", 6.0))
        s = b.math("MULTIPLY", s, b.smooth(z, 0.04, 0.3))
        col = b.cadd(col, b.cmul(lin4(st.get("color", "#DDE6FF")), s))
        # milky band (soft noise)
        mw = st.get("milky", 0.0)
        if mw:
            n = b.node("ShaderNodeTexNoise")
            n.inputs["Scale"].default_value = 3.0
            n.inputs["Detail"].default_value = 6.0
            b.link(D, n.inputs["Vector"])
            col = b.cadd(col, b.cmul(lin4(st.get("color", "#DDE6FF")),
                                     b.math("MULTIPLY", b.smooth(n.outputs["Fac"], 0.5, 0.75), mw)))
    # discs (sun / moon) behind the clouds
    for dsc in sky["discs"]:
        M = dir_from(*dsc["dir"])
        r = math.radians(dsc.get("radius_deg", 0.5))
        cosM = b.vmath("DOT_PRODUCT", D, b.vec(M)).outputs[1]
        edge = dsc.get("edge", 0.08)
        disc = b.smooth(cosM, math.cos(r * (1 + edge)), math.cos(r * (1 - edge)))
        dcol = lin4(dsc.get("color", "#FFF4E0"))
        tex = dsc.get("texture", 0.0)
        if tex:
            n = b.node("ShaderNodeTexNoise")
            n.inputs["Scale"].default_value = 2.2
            n.inputs["Detail"].default_value = 5.0
            n.inputs["Roughness"].default_value = 0.65
            b.link(b.vmath("SCALE", b.vmath("SUBTRACT", D, b.vec(M)).outputs[0], scale=1.0 / max(r, 1e-4)).outputs[0],
                   n.inputs["Vector"])
            maria = b.smooth(n.outputs["Fac"], 0.42, 0.62)
            # limb darkening
            limb = b.smooth(cosM, math.cos(r), math.cos(r * 0.2))
            k = b.math("MULTIPLY", b.math("SUBTRACT", 1.0, b.math("MULTIPLY", maria, tex)),
                       b.math("ADD", 0.75, b.math("MULTIPLY", limb, 0.25)))
            dcol = b.cmul(dcol, k)
        col = b.mix(col, b.cmul(dcol, dsc.get("strength", 20.0)), disc)
    # comet
    cm = sky.get("comet")
    if cm:
        C = dir_from(*cm["head"])
        # tail tangent: rotate 'up' around the view to the given screen angle
        up = Vector((0, 0, 1))
        right = up.cross(C).normalized() * -1.0
        upv = C.cross(right).normalized() * -1.0
        a = math.radians(cm.get("tail_angle", 200.0))
        T = (right * math.cos(a) + upv * math.sin(a)).normalized()
        B = C.cross(T).normalized()
        dc = b.vmath("DOT_PRODUCT", D, b.vec(C)).outputs[1]
        Dp = b.vmath("SUBTRACT", D, b.vmath("SCALE", b.vec(C), scale=dc).outputs[0]).outputs[0]
        u = b.vmath("DOT_PRODUCT", Dp, b.vec(T)).outputs[1]
        v = b.vmath("DOT_PRODUCT", Dp, b.vec(B)).outputs[1]
        L = math.radians(cm.get("length_deg", 25.0))
        w0 = math.radians(cm.get("width_deg", 0.4))
        fan = cm.get("fan", 0.18)
        tot = None
        for k, (curv, amt, wmul) in enumerate(cm.get("tails", [(0.0, 1.0, 1.0), (0.08, 0.6, 1.8)])):
            # curved dust tail: v offset grows with u^2
            vv = b.math("SUBTRACT", v, b.math("MULTIPLY", b.math("MULTIPLY", u, u), curv / max(L, 1e-3)))
            w = b.math("ADD", w0 * wmul, b.math("MULTIPLY", b.math("MAXIMUM", u, 0.0), fan * wmul))
            q = b.math("DIVIDE", vv, w)
            across = b.math("EXPONENT", b.math("MULTIPLY", b.math("MULTIPLY", q, q), -1.0))
            along = b.math("EXPONENT", b.math("DIVIDE", b.math("MAXIMUM", u, 0.0), -L))
            front = b.smooth(u, -w0 * 0.5, w0 * 1.5)
            t = b.math("MULTIPLY", b.math("MULTIPLY", across, along), b.math("MULTIPLY", front, amt))
            tot = t if tot is None else b.math("ADD", tot, t)
        # streaks along the tail
        n = b.node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Detail"].default_value = 3.0
        b.link(b.comb(b.math("MULTIPLY", v, 400.0), b.math("MULTIPLY", u, 6.0), 0.0), n.inputs["Vector"])
        streak = b.math("ADD", 0.55, b.math("MULTIPLY", n.outputs["Fac"], 0.9))
        tot = b.math("MULTIPLY", tot, streak)
        col = b.cadd(col, b.cmul(lin4(cm.get("tail_color", "#FF5A2A")),
                                 b.math("MULTIPLY", tot, cm.get("tail_strength", 3.0))))
        ang = b.math("ARCCOSINE", b.math("MINIMUM", dc, 1.0))
        hr = math.radians(cm.get("head_deg", 0.35))
        head = b.math("EXPONENT", b.math("MULTIPLY", b.math("POWER", b.math("DIVIDE", ang, hr), 2.0), -1.0))
        col = b.cadd(col, b.cmul(lin4(cm.get("head_color", "#FFE8D0")),
                                 b.math("MULTIPLY", head, cm.get("head_strength", 30.0))))
        coma = b.math("EXPONENT", b.math("MULTIPLY", b.math("DIVIDE", ang, hr * 6), -1.0))
        col = b.cadd(col, b.cmul(lin4(cm.get("tail_color", "#FF5A2A")),
                                 b.math("MULTIPLY", coma, cm.get("coma_strength", 1.5))))
    # clouds over everything above
    for cl in sky["clouds"]:
        col = _clouds(b, D, z, col, base, cl, sun_dir)
    b.link(col, go.inputs[0])
    return g


# ---------------------------------------------------------------------------------------------
# world
# ---------------------------------------------------------------------------------------------
def build(sky):
    """Build the world from a ``sky`` dict (see :data:`DEFAULT`).  Returns the merged dict."""
    sky = merged(sky)
    base_g = _sky_base(sky)
    cam_g = _sky_cam(sky, base_g)
    w = bpy.data.worlds.get("IR_World") or bpy.data.worlds.new("IR_World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    b = G(nt)
    tc = b.node("ShaderNodeTexCoord")
    gb = b.node("ShaderNodeGroup")
    gb.node_tree = base_g
    b.link(tc.outputs["Generated"], gb.inputs[0])
    gc = b.node("ShaderNodeGroup")
    gc.node_tree = cam_g
    b.link(tc.outputs["Generated"], gc.inputs[0])
    b.link(gb.outputs[0], gc.inputs[1])
    lt = sky["light"]
    light = b.cmul(gb.outputs[0], lt.get("strength", 1.0))
    light = b.mix(light, lin4(lt.get("tint", "#FFFFFF")), 1.0, blend="MULTIPLY", clamp=False)
    lp = b.node("ShaderNodeLightPath")
    seen = b.math("MAXIMUM", lp.outputs["Is Camera Ray"], lp.outputs["Is Glossy Ray"])
    col = b.mix(light, gc.outputs[0], seen)
    bg = b.node("ShaderNodeBackground")
    b.link(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    out = b.node("ShaderNodeOutputWorld")
    b.link(bg.outputs[0], out.inputs["Surface"])
    # importance-sample the world for the bright sun/glow (less noise in ambient)
    try:
        w.cycles.sampling_method = "MANUAL"
        w.cycles.sample_map_resolution = 1024
    except AttributeError:
        pass
    _fog_group(sky, base_g)
    return sky


# ---------------------------------------------------------------------------------------------
# IR_Fog
# ---------------------------------------------------------------------------------------------
def _height_tau(b, dens, falloff, h0, dist, pz, oz):
    """Optical depth of exponential height fog density(h) = dens * exp(-falloff * (h - h0))
    along a segment of length ``dist`` from height ``oz`` (eye) to ``pz`` (surface)."""
    if dens <= 0:
        return None
    base = b.math("EXPONENT", b.math("MULTIPLY", b.math("SUBTRACT", oz, h0), -falloff))
    k = b.math("MULTIPLY", b.math("SUBTRACT", pz, oz), falloff)
    k = b.math("MINIMUM", b.math("MAXIMUM", k, -30.0), 30.0)
    small = b.math("LESS_THAN", b.math("ABSOLUTE", k), 1e-3)
    ks = b.math("ADD", b.math("MULTIPLY", k, b.math("SUBTRACT", 1.0, small)), b.math("MULTIPLY", small, 1e-3))
    gk = b.math("DIVIDE", b.math("SUBTRACT", 1.0, b.math("EXPONENT", b.math("MULTIPLY", ks, -1.0))), ks)
    return b.math("MULTIPLY", b.math("MULTIPLY", b.math("MULTIPLY", base, gk), dist), dens)


def _fog_group(sky, base_g):
    f = sky["fog"]
    g, b, gi, go = new_group("IR_Fog", [("Shader", "NodeSocketShader")],
                             [("Shader", "NodeSocketShader")])
    geo = b.node("ShaderNodeNewGeometry")
    cd = b.node("ShaderNodeCameraData")
    lp = b.node("ShaderNodeLightPath")
    cam = lp.outputs["Is Camera Ray"]
    dist = b.math("ADD", b.math("MULTIPLY", cd.outputs["View Distance"], cam),
                  b.math("MULTIPLY", lp.outputs["Ray Length"], b.math("SUBTRACT", 1.0, cam)))
    P = geo.outputs["Position"]
    I = geo.outputs["Incoming"]
    pz = b.sep(P)[2]
    ix, iy, iz = b.sep(I)
    oz = b.math("ADD", pz, b.math("MULTIPLY", iz, dist))
    # camera rays only: fog on glossy rays turns rough reflections into fireflies
    flag = cam
    cur = gi.outputs[0]
    # haze: sky colour along the (horizon-clamped) view ray
    th = _height_tau(b, f["haze"], f["haze_falloff"], f["haze_h0"], dist, pz, oz)
    if th is not None:
        dz = b.math("MINIMUM", b.math("MAXIMUM", b.math("MULTIPLY", iz, -1.0), 0.0), f["haze_zmax"])
        Dv = b.comb(b.math("MULTIPLY", ix, -1.0), b.math("MULTIPLY", iy, -1.0), dz)
        sg = b.node("ShaderNodeGroup")
        sg.node_tree = base_g
        b.link(Dv, sg.inputs[0])
        hc = b.mix(sg.outputs[0], lin4(f["haze_tint"]), 1.0, blend="MULTIPLY", clamp=False)
        fh = b.math("MINIMUM", b.math("SUBTRACT", 1.0, b.math("EXPONENT", b.math("MULTIPLY", th, -1.0))),
                    f["haze_max"])
        em = b.node("ShaderNodeEmission")
        b.link(hc, em.inputs["Color"])
        em.inputs["Strength"].default_value = 1.0
        mx = b.node("ShaderNodeMixShader")
        b.link(b.math("MULTIPLY", fh, flag), mx.inputs[0])
        b.link(cur, mx.inputs[1])
        b.link(em.outputs[0], mx.inputs[2])
        cur = mx.outputs[0]
    tm = _height_tau(b, f["mist"], f["mist_falloff"], f["mist_h0"], dist, pz, oz)
    if tm is not None:
        fm = b.math("MINIMUM", b.math("SUBTRACT", 1.0, b.math("EXPONENT", b.math("MULTIPLY", tm, -1.0))),
                    f["mist_max"])
        em = b.node("ShaderNodeEmission")
        em.inputs["Color"].default_value = lin4(f["mist_color"])
        em.inputs["Strength"].default_value = f.get("mist_strength", 1.0)
        mx = b.node("ShaderNodeMixShader")
        b.link(b.math("MULTIPLY", fm, flag), mx.inputs[0])
        b.link(cur, mx.inputs[1])
        b.link(em.outputs[0], mx.inputs[2])
        cur = mx.outputs[0]
    b.link(cur, go.inputs[0])
    return g


def fog_node(nb, shader_socket):
    """Insert ``IR_Fog`` after ``shader_socket`` in the material tree of ``nb``; returns the
    fogged shader output (use it before any transparency mix)."""
    g = bpy.data.node_groups.get("IR_Fog")
    if g is None:
        return shader_socket
    n = nb.node("ShaderNodeGroup")
    n.node_tree = g
    nb.link(shader_socket, n.inputs[0])
    return n.outputs[0]


def apply_fog(materials=None, skip=("IR_NoFog",)):
    """Wrap the Surface output of every (or the given) opaque material with ``IR_Fog``.
    Materials already fogged (``mat['ir_fog']``) or named with a ``skip`` prefix are left alone."""
    g = bpy.data.node_groups.get("IR_Fog")
    if g is None:
        return 0
    n_done = 0
    for m in (materials or list(bpy.data.materials)):
        if not m.use_nodes or m.get("ir_fog") or m.name.startswith(tuple(skip)):
            continue
        nt = m.node_tree
        out = None
        for n in nt.nodes:
            if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output:
                out = n
        if out is None:
            for n in nt.nodes:
                if n.bl_idname == "ShaderNodeOutputMaterial":
                    out = n
        if out is None or not out.inputs["Surface"].is_linked:
            continue
        src = out.inputs["Surface"].links[0].from_socket
        fn = nt.nodes.new("ShaderNodeGroup")
        fn.node_tree = g
        nt.links.new(src, fn.inputs[0])
        nt.links.new(fn.outputs[0], out.inputs["Surface"])
        m["ir_fog"] = 1
        n_done += 1
    return n_done


# ---------------------------------------------------------------------------------------------
# lights
# ---------------------------------------------------------------------------------------------
def sun(az, el, energy=4.0, color="#FFE6C8", angle_deg=1.0, name="Sun", shadow=True):
    """Sun lamp shining from azimuth/elevation (degrees, same convention as the sky glows)."""
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = energy
    ld.color = lin(color)
    ld.angle = math.radians(angle_deg)
    ld.cycles.cast_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    d = dir_from(az, el)
    ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    return ob


def point(loc, power=100.0, color="#FFB060", radius=0.1, name="Point", shadow=True):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = power
    ld.color = lin(color)
    ld.shadow_soft_size = radius
    ld.cycles.cast_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


def spot(loc, target, power=1000.0, color="#FFE0B0", angle_deg=30.0, blend=0.3, radius=0.2,
         name="Spot"):
    ld = bpy.data.lights.new(name, "SPOT")
    ld.energy = power
    ld.color = lin(color)
    ld.spot_size = math.radians(angle_deg)
    ld.spot_blend = blend
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def area(loc, target, power=500.0, size=2.0, color="#FFFFFF", name="Area", shadow=True):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.color = lin(color)
    ld.size = size
    ld.cycles.cast_shadow = shadow
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob

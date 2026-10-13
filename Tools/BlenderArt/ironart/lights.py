"""The studio "Koei key light" rigs - ONE sun for every family.

Every asset family is lit from the **top-left of the screen** so icons, sprites, tiles, portraits
and the map agree when they sit together on screen.  Directions are in *screen space* of the
active camera:

    screen angle  degrees counter-clockwise from screen +X (right):  135 = from the top-left
    elevation     degrees above the image plane towards the viewer: 90 = from the camera

so the same numbers work for the top-down map camera and the 3/4 sprite camera.  The single
table (:data:`SUN`, STYLE.md section 4) - every rig default below equals it:

    family     key angle / elev   key                    fill / bounce            rim     ambient
    map, hex   135 / 50           sun 3.4, 16 deg soft    -                        -       sky #AEB4B8 x0.55
    sprites    155 / 52 (world    sun 4.6, 6 deg soft     sun 0.25 -30/35 cool,    1.2     sky x0.18
               elev 40 from WSW: the oblique camera needs it to split tops / west / south)
                                                          zenith 0.45 shadowless
    portraits  135 / 35           area 0.5 m, 40 W        14 W cool, bounce 4 W    26 W    #3A3530 x0.04
    UI         135 / 50           sun solved: flat = 1.0 x albedo, white key, white ambient

Shadows therefore fall towards screen 315 deg (bottom-right) everywhere; on the map and hex tiles
they are ~0.84 x the object height long (tan 50), and the composited sprite contact shadow
(``post.drop_shadow``) uses the matching (2.2, 2.2) px offset.
"""

import math

import bpy
from mathutils import Vector

from . import palette

#: the studio sun (screen space) - map/hex use it directly, the other rigs derive from it
SUN = {"angle": 135.0, "elevation": 50.0, "color": "#FFF7EC"}

KEY_COLOR = SUN["color"]          # near-neutral warm white: keeps sage greens sage
FILL_COLOR = "#B8C8E0"
RIM_COLOR = "#E8EEF8"
SKY_COLOR = "#AEB4B8"             # warm-neutral grey sky: shadow sides grey, never navy
PORTRAIT_KEY_COLOR = "#FFEBD2"    # a touch warmer for skin
BOUNCE_COLOR = "#C89060"          # warm floor/armour bounce under the chin


def screen_dir(cam, angle_deg=135.0, elevation_deg=40.0):
    """World direction *towards* the light for a screen-space angle/elevation of ``cam``."""
    m = cam.matrix_world.to_3x3()
    right = m @ Vector((1, 0, 0))
    up = m @ Vector((0, 1, 0))
    toward = m @ Vector((0, 0, 1))
    a, e = math.radians(angle_deg), math.radians(elevation_deg)
    d = (right * math.cos(a) + up * math.sin(a)) * math.cos(e) + toward * math.sin(e)
    return d.normalized()


def world_dir(azimuth_deg=135.0, elevation_deg=45.0):
    """World direction towards the light from map azimuth (CCW from +X/east) and elevation."""
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    return Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))


def _light(name, kind, color, energy, shadow=True):
    ld = bpy.data.lights.new(name, kind)
    ld.color = palette.lin(color) if isinstance(color, str) else color
    ld.energy = energy
    ld.cycles.cast_shadow = shadow
    try:
        ld.use_shadow = shadow
    except AttributeError:
        pass
    ob = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def sun(name, direction, strength=3.0, color=KEY_COLOR, angle_deg=4.0, shadow=True):
    """Sun lamp shining *from* ``direction`` (world vector towards the light)."""
    ob = _light(name, "SUN", color, strength, shadow)
    ob.data.angle = math.radians(angle_deg)
    d = Vector(direction).normalized()
    ob.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    ob.location = d * 20.0
    return ob


def area(name, location, target, power=100.0, size=1.0, size_y=None, color=KEY_COLOR,
         shadow=True, spread_deg=180.0):
    """Area lamp at ``location`` aimed at ``target``; ``power`` in Watts."""
    ob = _light(name, "AREA", color, power, shadow)
    ld = ob.data
    if size_y is None:
        ld.shape = "SQUARE"
        ld.size = size
    else:
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size, size_y
    ld.spread = math.radians(spread_deg)
    ob.location = location
    d = Vector(target) - Vector(location)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def world(color=SKY_COLOR, strength=0.35, horizon=None):
    """World background/ambient. Optional ``horizon`` colour makes a vertical gradient sky."""
    w = bpy.data.worlds.get("IronWorld") or bpy.data.worlds.new("IronWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    if horizon is None:
        bg.inputs["Color"].default_value = palette.lin4(color)
    else:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.0
        ramp.color_ramp.elements[0].color = palette.lin4(horizon)
        ramp.color_ramp.elements[1].position = 0.6
        ramp.color_ramp.elements[1].color = palette.lin4(color)
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return w


# ---------------------------------------------------------------------------------------------
# rigs
# ---------------------------------------------------------------------------------------------
def rig_sprite(cam, key=4.6, fill=0.25, rim=1.2, sky=0.18, key_angle=155.0, key_elev=52.0,
               softness_deg=6.0, top_fill=0.45, shadow_lift=0.2, neutral=False):
    """Cities, units, banners, icons: top-left sun + weak cool fill + cool rim + low sky ambient.

    With the standard sprite camera (elevation 35, azimuth -20) the key (screen 155 / 52) lands at
    world elevation 40 from the west-south-west, so the visible planes separate (measured on the
    city style frame, 8-bit luma): wall tops ~195, west faces ~148, south faces ~104, painted roof
    lit / shadow slopes ~105 / ~65.  Low fill and sky keep the planes apart; ``top_fill`` (a
    shadowless zenith light) and ``shadow_lift`` (that fraction of the key cast without shadows)
    keep cast shadows readable (>= 60) instead of black holes.

    ``neutral=True`` makes every light and the sky pure white/grey: use it for assets with
    tintable white cloth (Banner, Flag, Unit_*), so the whites stay R = G = B (STYLE.md section 8).
    """
    kc, fc, rc, sk = (KEY_COLOR, FILL_COLOR, RIM_COLOR, SKY_COLOR) if not neutral else \
        ("#FFFFFF", "#FFFFFF", "#FFFFFF", "#A0A0A0")
    kd = screen_dir(cam, key_angle, key_elev)
    rig = {
        "key": sun("Key", kd, key * (1.0 - shadow_lift), kc, softness_deg),
        "fill": sun("Fill", screen_dir(cam, -30.0, 35.0), fill, fc, 20.0, shadow=False),
    }
    if shadow_lift > 0:
        # the same sun without shadows: cast shadows keep (shadow_lift x) the key's modelling, so
        # a keep's shadow on a lit wall reads as a darker plane, not a black hole
        rig["key_lift"] = sun("KeyLift", kd, key * shadow_lift, kc, softness_deg, shadow=False)
    if rim > 0:
        rig["rim"] = sun("Rim", screen_dir(cam, 60.0, -35.0), rim, rc, 10.0, shadow=False)
    if top_fill > 0:
        # shadowless light from the zenith: lifts cast shadows on courtyards/ground (which face
        # up) out of black without flattening the vertical wall planes
        rig["top_fill"] = sun("TopFill", Vector((0, 0, 1)), top_fill, sk, 30.0, shadow=False)
    rig["world"] = world(sk, sky)
    return rig


def rig_map(cam=None, key=3.4, sky=0.55, azimuth_deg=SUN["angle"], elevation_deg=SUN["elevation"],
            softness_deg=16.0, fill=0.0, sky_color=SKY_COLOR, shadow_lift=0.0):
    """Top-down relief (world map, hex tiles): the studio sun from the top-left at 50 deg - cast
    shadows ~0.84 x height, soft (16 deg) - plus a neutral grey sky that lifts the shadow sides to
    ~#5E6670 on rock (painted, never navy)."""
    d = screen_dir(cam, azimuth_deg, elevation_deg) if cam else world_dir(azimuth_deg, elevation_deg)
    rig = {"key": sun("Sun", d, key * (1.0 - shadow_lift), KEY_COLOR, softness_deg)}
    if shadow_lift > 0:
        # part of the sun without shadows: dense canopies keep readable gaps (hex forest)
        rig["key_lift"] = sun("SunLift", d, key * shadow_lift, KEY_COLOR, softness_deg, shadow=False)
    if fill > 0:
        rig["fill"] = sun("Fill", world_dir(azimuth_deg + 180, 60), fill, FILL_COLOR, 30, False)
    rig["world"] = world(sky_color, sky)
    return rig


def rig_portrait(cam, target, key=40.0, fill=14.0, bounce=4.0, rim=26.0, sky=0.04,
                 key_angle=SUN["angle"], key_elev=35.0, distance=1.6, key_size=0.5):
    """Painted bust lighting: soft warm key from the upper left at 35 deg (Rembrandt triangle on
    the shadow cheek), broad cool fill from the right, warm low bounce from below-front (lifts the
    jaw, beard and armour out of black), cool rim from behind/top-right that cuts the helmet and
    beard out of the ground.

    Energies are Watts for area lights at ``distance`` metres from ``target`` (head ~0.23 m).
    Calibrated on the warrior style frame (Filmic Medium Contrast): lit cheek ~#C08660, shadow
    cheek >= 35 % of it, armour midtones 55-95, frame mean luma 65-80.
    """
    t = Vector(target)
    kd = screen_dir(cam, key_angle, key_elev)
    fd = screen_dir(cam, -15.0, 25.0)
    bd = screen_dir(cam, -90.0, -20.0)
    rd = screen_dir(cam, 40.0, -45.0)
    rig = {
        "key": area("Key", t + kd * distance, t, key, size=key_size, color=PORTRAIT_KEY_COLOR),
        "fill": area("Fill", t + fd * distance * 1.2, t, fill, size=1.6, color=FILL_COLOR,
                     shadow=False),
        "rim": area("Rim", t + rd * distance, t, rim, size=0.5, size_y=1.2, color=RIM_COLOR),
        "world": world("#3A3530", sky),
    }
    if bounce > 0:
        # from below the frame (screen -90) and slightly behind the image plane: under-chin warmth
        bpos = t + Vector(bd) * distance * 0.9 + Vector((0, 0, -0.25))
        rig["bounce"] = area("Bounce", bpos, t + Vector((0, 0, -0.12)), bounce, size=0.8,
                             color=BOUNCE_COLOR, shadow=False)
    return rig


def rig_ui(cam, flat_gain=1.0, ambient=0.2, key_angle=SUN["angle"], key_elev=SUN["elevation"],
           softness_deg=3.0, warm=False):
    """Calibrated UI light: a flat face-up surface renders at ``flat_gain`` x its albedo
    (Standard view), so palette colours (Paper, Lacquer, Gold...) land on their tokens.

    Cycles: sun strength S on albedo A at elevation e gives A * S * sin(e) / pi; a uniform world of
    strength w adds A * w.  We solve S for ``flat_gain - ambient``.  Bevels facing the top-left get
    up to ~1.3x, those facing bottom-right fall to the ambient level -> embossed look.

    ``warm=False`` (default): white key and white ambient, so a token lands within 3 levels per
    channel (measured: Paper field (231, 219, 191) vs (233, 220, 192)).  ``warm=True`` tints the
    key #FFF7EC with a luminance-only compensation - it shifts hue (paper goes yellow) and is only
    for painted illustrations, never for 9-slice pieces or tint plates.
    """
    e = math.radians(key_elev)
    S = (flat_gain - ambient) * math.pi / math.sin(e)
    rig = {"key": sun("Key", screen_dir(cam, key_angle, key_elev), S,
                      KEY_COLOR if warm else "#FFFFFF", softness_deg)}
    w = bpy.data.worlds.get("IronWorld") or bpy.data.worlds.new("IronWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    amb = nt.nodes.new("ShaderNodeBackground")          # diffuse ambient: uniform, calibrated
    amb.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    amb.inputs["Strength"].default_value = ambient
    # glossy rays see a "studio ring": bright towards the horizon, dark at the zenith - so flat
    # face-up lacquer/paper (which mirror the zenith into the top-down camera) keep their
    # palette colour, while bevels and metal mouldings pick up rich reflections.
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.85
    mr.inputs["From Max"].default_value = 0.35
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    ref = nt.nodes.new("ShaderNodeBackground")
    ref.inputs["Color"].default_value = palette.lin4("#FFF4E0")
    nt.links.new(mr.outputs[0], ref.inputs["Strength"])
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Glossy Ray"], mix.inputs[0])
    nt.links.new(amb.outputs[0], mix.inputs[1])
    nt.links.new(ref.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    rig["world"] = w
    if warm:
        kc = palette.lin(KEY_COLOR)
        lum = 0.2126 * kc[0] + 0.7152 * kc[1] + 0.0722 * kc[2]
        rig["key"].data.energy = S / lum
    return rig

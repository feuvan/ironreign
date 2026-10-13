"""The studio "Koei key light" rigs.

Every asset family is lit from the **top-left of the screen** so icons, sprites, tiles, portraits
and the map all agree.  Directions are expressed in *screen space* of the active camera:

    screen angle  degrees counter-clockwise from screen +X (right):  135 = from the top-left
    elevation     degrees above the image plane towards the viewer: 90 = from the camera

so the same numbers work for the top-down map camera and the 3/4 sprite camera.  Defaults (see
STYLE.md "Light"):

    key   angle 135, elevation 40, warm  #FFF1DC   (sprites: 145 / 62 so fronts are lit)
    fill  angle -30 (bottom-right), elevation 35, cool #B8C8E0, no shadows, ~18 % of key
    rim   angle 60 (top-right), elevation -35 (from behind), cool-white, portraits/sprites only
    world cool sky #8C9AB0 (ambient, also fills transparent-film sprites)
"""

import math

import bpy
from mathutils import Vector

from . import palette

KEY_COLOR = "#FFF1DC"
FILL_COLOR = "#B8C8E0"
RIM_COLOR = "#E8EEF8"
SKY_COLOR = "#8C9AB0"


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
def rig_sprite(cam, key=3.2, fill=0.55, rim=1.2, sky=0.45, key_angle=145.0, key_elev=62.0,
               softness_deg=6.0):
    """Cities, units, banners, icons: warm top-left sun + cool fill + cool rim + sky ambient.

    With the standard sprite camera (elevation 35, azimuth -20) the key (screen 145 deg / 62 deg)
    lands at world elevation ~47 deg from the south-west, so faces read in three values:
    roofs/tops brightest (N.L 0.73), west faces (0.56), front/south faces (0.40); east and
    north faces only get fill + sky.
    """
    rig = {
        "key": sun("Key", screen_dir(cam, key_angle, key_elev), key, KEY_COLOR, softness_deg),
        "fill": sun("Fill", screen_dir(cam, -30.0, 35.0), fill, FILL_COLOR, 20.0, shadow=False),
    }
    if rim > 0:
        rig["rim"] = sun("Rim", screen_dir(cam, 60.0, -35.0), rim, RIM_COLOR, 10.0, shadow=False)
    rig["world"] = world(SKY_COLOR, sky)
    return rig


def rig_map(cam=None, key=3.0, sky=0.55, azimuth_deg=135.0, elevation_deg=38.0, softness_deg=8.0,
            fill=0.0):
    """Top-down relief: a single warm sun from the north-west (top-left) at a low-ish elevation
    for readable hill-shading, plus a bluish sky that tints the shadow side (soft, painted)."""
    d = screen_dir(cam, azimuth_deg, elevation_deg) if cam else world_dir(azimuth_deg, elevation_deg)
    rig = {"key": sun("Sun", d, key, KEY_COLOR, softness_deg)}
    if fill > 0:
        rig["fill"] = sun("Fill", world_dir(azimuth_deg + 180, 60), fill, FILL_COLOR, 30, False)
    rig["world"] = world("#9FB2C8", sky)
    return rig


def rig_portrait(cam, target, key=150.0, fill=8.0, rim=90.0, sky=0.04, key_angle=152.0,
                 key_elev=20.0, distance=1.6, key_size=0.5):
    """Dramatic bust lighting: big warm soft-box from the upper left (front), weak cool fill from
    the right, strong cool rim from behind/top-right to cut the silhouette out of the dark ground.

    Energies are Watts for area lights at ``distance`` metres from ``target`` (head ~0.25 m).
    """
    t = Vector(target)
    kd = screen_dir(cam, key_angle, key_elev)
    fd = screen_dir(cam, -15.0, 25.0)
    rd = screen_dir(cam, 40.0, -45.0)
    rig = {
        "key": area("Key", t + kd * distance, t, key, size=key_size, color=KEY_COLOR),
        "fill": area("Fill", t + fd * distance * 1.2, t, fill, size=1.6, color=FILL_COLOR,
                     shadow=False),
        "rim": area("Rim", t + rd * distance, t, rim, size=0.5, size_y=1.2, color=RIM_COLOR),
        "world": world("#3A3530", sky),
    }
    return rig


def rig_ui(cam, flat_gain=1.0, ambient=0.18, key_angle=135.0, key_elev=50.0, softness_deg=3.0,
           warm=True):
    """Calibrated UI light: a flat face-up surface renders at exactly ``flat_gain`` x its albedo
    (Standard view), so palette colours (Paper, Lacquer, Gold...) land where DESIGN.md says.

    Cycles: sun strength S on albedo A at elevation e gives A * S * sin(e) / pi; a uniform world of
    strength w adds A * w.  We solve S for ``flat_gain - ambient``.  Bevels facing the top-left get
    up to ~1.3x, those facing bottom-right fall to the ambient level -> embossed look.
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
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = ambient
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    rig["world"] = w
    if warm:
        # KEY_COLOR is not pure white: compensate its luminance so the gain stays calibrated
        kc = palette.lin(KEY_COLOR)
        lum = 0.2126 * kc[0] + 0.7152 * kc[1] + 0.0722 * kc[2]
        rig["key"].data.energy = S / lum
    return rig

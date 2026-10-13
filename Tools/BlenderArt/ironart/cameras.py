"""Cameras and exact pixel framing.

Conventions (shared by every asset family - keep them so light & perspective stay coherent):

* World: +Z up, +Y "north / away from the viewer", +X east. Ground at z = 0.
* **Top-down** (world map, hex tiles, UI slabs): orthographic, looking down -Z, screen-up = +Y.
* **Sprite 3/4** (cities, units, banners, icons): orthographic, elevation 35 deg, azimuth -20 deg
  (camera sits front-left of the subject so the lit left faces and the front read; see STYLE.md).
* **Portrait**: perspective 85 mm on a 36 mm *vertical* sensor (full-frame portrait orientation),
  eyes placed at 38 % from the top as DESIGN.md requires.

Fitting helpers project the *evaluated vertices* (modifiers included) into the camera, so a sprite
can be framed to an exact pixel box and anchored (e.g. bottom-centre at (48, 92) in a 96x96 icon).
"""

import math

import bpy
from mathutils import Matrix, Vector

from . import scene as _scene


def _new_camera(name, ortho):
    cd = bpy.data.cameras.new(name)
    cd.type = "ORTHO" if ortho else "PERSP"
    cd.clip_start = 0.01
    cd.clip_end = 1000.0
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def look_at(obj, target, up_axis="Y"):
    """Rotate ``obj`` so its -Z axis points at ``target`` (world)."""
    d = Vector(target) - obj.location
    obj.rotation_mode = "XYZ"
    obj.rotation_euler = d.to_track_quat("-Z", up_axis).to_euler()
    bpy.context.view_layer.update()
    return obj


def _orient(cam, direction):
    """Point the camera along ``direction`` (world vector) with world +Z as screen-up."""
    q = Vector(direction).normalized().to_track_quat("-Z", "Y")
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = q.to_euler()
    bpy.context.view_layer.update()


def ortho_top_down(center=(0.0, 0.0), width=2.0, height=None, z=50.0, name="CamTop"):
    """Orthographic camera looking straight down at ``center`` covering ``width`` x ``height``.

    Set the render resolution *before* calling so the aspect is known. ``ortho_scale`` covers the
    larger render dimension (Blender sensor-fit AUTO), so with ``height`` given and the right
    aspect, the frame maps exactly onto the rectangle.
    """
    cam = _new_camera(name, ortho=True)
    cam.location = (center[0], center[1], z)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    sc = bpy.context.scene
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    if height is None:
        height = width * ry / rx
    if rx >= ry:
        cam.data.ortho_scale = width
    else:
        cam.data.ortho_scale = height
    bpy.context.view_layer.update()
    return cam


def sprite_camera(target=(0.0, 0.0, 0.0), elevation_deg=35.0, azimuth_deg=-20.0, distance=60.0,
                  ortho_scale=10.0, name="CamSprite"):
    """3/4 orthographic sprite camera.

    azimuth 0 = camera in front (-Y) looking north; negative azimuth swings it to the west so the
    viewer sees the front and the (lit) west face.  Use :func:`fit_ortho` afterwards.
    """
    cam = _new_camera(name, ortho=True)
    el, az = math.radians(elevation_deg), math.radians(azimuth_deg)
    offs = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = Vector(target) + offs * distance
    cam.data.ortho_scale = ortho_scale
    _orient(cam, -offs)
    return cam


def portrait_camera(eye_point, head_height=0.26, yaw_deg=-18.0, pitch_deg=-3.0, focal_mm=85.0,
                    eye_line=0.38, head_frac=0.47, name="CamPortrait"):
    """Perspective bust camera.

    eye_point    world point between the eyes
    head_height  chin-to-crown height of the model (m) - used to set the distance
    yaw_deg      camera swing around the head (negative = camera to the subject's left, i.e.
                 viewer's left, giving the standard Koei 3/4 view with the face turned to the
                 viewer's left of camera... see STYLE.md)
    pitch_deg    camera tilt (negative looks slightly up at the subject = heroic)
    eye_line     fraction from the top of the frame where the eyes land (DESIGN.md: 0.38)
    head_frac    fraction of the frame height the head occupies
    """
    cam = _new_camera(name, ortho=False)
    cd = cam.data
    cd.lens = focal_mm
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 36.0
    cd.sensor_width = 36.0
    half = math.atan(18.0 / focal_mm)
    dist = head_height / (head_frac * 2.0 * math.tan(half))
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    offs = Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch),
                   -math.sin(pitch)))
    cam.location = Vector(eye_point) + offs * dist
    _orient(cam, -offs)
    # vertical shift so the eye point lands at eye_line from the top
    # (shift is a fraction of the larger sensor dimension = frame height for portrait aspect)
    sc = bpy.context.scene
    aspect = sc.render.resolution_x / sc.render.resolution_y
    frac_of_larger = 1.0 if aspect <= 1.0 else 1.0 / aspect
    # eye_line < 0.5 means eyes above centre -> the frame moves DOWN relative to the eyes
    cd.shift_y = -(0.5 - eye_line) * frac_of_larger
    cam["ironart_eye_point"] = tuple(eye_point)
    bpy.context.view_layer.update()
    return cam


# ---------------------------------------------------------------------------------------------
# projection helpers
# ---------------------------------------------------------------------------------------------
def _eval_points(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type not in {"MESH", "CURVE", "SURFACE", "FONT", "META"}:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        pts.extend(mw @ v.co for v in me.vertices)
        ev.to_mesh_clear()
    return pts


def world_to_pixel(cam, co, scene=None):
    """World point -> (x, y) render pixels with origin at the *top-left* (PIL convention)."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = scene or bpy.context.scene
    v = world_to_camera_view(sc, cam, Vector(co))
    return v.x * sc.render.resolution_x, (1.0 - v.y) * sc.render.resolution_y


def pixel_bounds(cam, objs, scene=None):
    """(xmin, ymin, xmax, ymax) render-pixel bounds (top-left origin) of the objects' vertices."""
    sc = scene or bpy.context.scene
    from bpy_extras.object_utils import world_to_camera_view
    xs, ys = [], []
    W, H = sc.render.resolution_x, sc.render.resolution_y
    for p in _eval_points(objs):
        v = world_to_camera_view(sc, cam, p)
        xs.append(v.x * W)
        ys.append((1.0 - v.y) * H)
    return min(xs), min(ys), max(xs), max(ys)


def fit_ortho(cam, objs, margin_px=2.0, anchor="center", anchor_world=None, anchor_px=None,
              units_per_px=None, scene=None):
    """Frame ``objs`` exactly in an orthographic camera. Works in *target* pixels.

    margin_px     free border in target pixels (scaled by the scene supersample factor)
    anchor        'center' - content bbox centred;
                  'bottom_center' - bbox centred horizontally, bottom edge on the bottom margin
    anchor_world  optional world point (e.g. the ground centre of a city) that must land on
                  ``anchor_px`` (target pixels, top-left origin, e.g. (48, 92)); the scale is the
                  largest that still keeps every vertex inside the margins around that anchor.
    units_per_px  force a scale (world units per *target* pixel) so a family of sprites shares
                  one scale; the anchor logic still applies.
    Returns the world units per target pixel used (store it to reuse for sibling sprites).
    """
    sc = scene or bpy.context.scene
    ss = _scene.supersample_factor(sc)
    W, H = sc.render.resolution_x, sc.render.resolution_y
    m = margin_px * ss
    inv = cam.matrix_world.inverted()
    local = [inv @ p for p in _eval_points(objs)]
    if not local:
        raise ValueError("fit_ortho: no geometry")
    xmin = min(p.x for p in local); xmax = max(p.x for p in local)
    ymin = min(p.y for p in local); ymax = max(p.y for p in local)

    if anchor_world is not None:
        a = inv @ Vector(anchor_world)
        ax, ay = a.x, a.y
        px, py = (anchor_px[0] * ss, anchor_px[1] * ss) if anchor_px else (W / 2.0, H - m)
    elif anchor == "bottom_center":
        ax, ay = (xmin + xmax) / 2.0, ymin
        px, py = (anchor_px[0] * ss, anchor_px[1] * ss) if anchor_px else (W / 2.0, H - m)
    else:
        ax, ay = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
        px, py = (anchor_px[0] * ss, anchor_px[1] * ss) if anchor_px else (W / 2.0, H / 2.0)

    if units_per_px is not None:
        u = units_per_px / ss
    else:
        cands = []
        for ext, avail in ((ax - xmin, px - m), (xmax - ax, W - m - px),
                           (ymax - ay, py - m), (ay - ymin, H - m - py)):
            if ext > 1e-9:
                cands.append(ext / max(avail, 1e-6))
        u = max(cands) if cands else 0.01
    view_w, view_h = u * W, u * H
    cam.data.ortho_scale = max(view_w, view_h)
    cam.data.shift_x = cam.data.shift_y = 0.0
    cx = ax - (px / W - 0.5) * view_w
    cy = ay - (0.5 - py / H) * view_h
    rot = cam.matrix_world.to_3x3()
    cam.location = cam.location + rot @ Vector((cx, cy, 0.0))
    bpy.context.view_layer.update()
    return u * ss


def ortho_units_per_px(cam, scene=None):
    """World units per *target* pixel of an orthographic camera."""
    sc = scene or bpy.context.scene
    W, H = sc.render.resolution_x, sc.render.resolution_y
    return cam.data.ortho_scale / max(W, H) * _scene.supersample_factor(sc)

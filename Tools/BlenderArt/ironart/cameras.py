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
from mathutils import Vector

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


def portrait_camera(eye_point, head_height=0.232, yaw_deg=20.0, pitch_deg=-4.0, focal_mm=85.0,
                    eye_line=0.38, head_frac=0.6, name="CamPortrait"):
    """Perspective bust camera (studio standard = the defaults).

    eye_point    world point between the eyes
    head_height  chin-to-crown height of the model (m) - used to set the distance
    yaw_deg      camera swing around the head; +20 puts the camera on the subject's left so the
                 face turns towards screen-left, into the top-left key ("short" lighting)
    pitch_deg    camera tilt (negative looks slightly up at the subject = heroic)
    eye_line     fraction from the top of the frame where the eyes land (DESIGN.md: 0.38)
    head_frac    fraction of the frame height the head occupies (0.6 = Koei bust, helmet crest
                 may be cropped)
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


def world_to_target_px(cam, co, scene=None):
    """World point -> (x, y) in **target** pixels (render pixels / supersample), top-left origin.
    Use this for anything written into the game (glyph areas, anchors)."""
    sc = scene or bpy.context.scene
    x, y = world_to_pixel(cam, co, sc)
    ss = _scene.supersample_factor(sc)
    return x / ss, y / ss


def target_rect(cam, corners, scene=None):
    """Axis-aligned bbox (x, y, w, h) in integer target pixels of projected world ``corners``
    (e.g. the 4 cloth corners :func:`ironart.geometry.banner` returns).  Rounds outward."""
    import math as _m
    pts = [world_to_target_px(cam, c, scene) for c in corners]
    x0 = _m.floor(min(p[0] for p in pts)); y0 = _m.floor(min(p[1] for p in pts))
    x1 = _m.ceil(max(p[0] for p in pts)); y1 = _m.ceil(max(p[1] for p in pts))
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


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

    margin_px     free border in target pixels (scaled by the scene supersample factor): one
                  number, or ``(left, top, right, bottom)`` - sprites need more room on the right
                  and bottom for the ink half-width and the contact shadow (recipes: (2, 2, 5, 4))
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
    if isinstance(margin_px, (int, float)):
        margin_px = (margin_px,) * 4
    ml, mt, mr, mb = (v * ss for v in margin_px)
    inv = cam.matrix_world.inverted()
    local = [inv @ p for p in _eval_points(objs)]
    if not local:
        raise ValueError("fit_ortho: no geometry")
    xmin = min(p.x for p in local); xmax = max(p.x for p in local)
    ymin = min(p.y for p in local); ymax = max(p.y for p in local)

    cxm = (ml + W - mr) / 2.0                     # centre of the free area
    cym = (mt + H - mb) / 2.0
    if anchor_world is not None:
        a = inv @ Vector(anchor_world)
        ax, ay = a.x, a.y
        px, py = (anchor_px[0] * ss, anchor_px[1] * ss) if anchor_px else (cxm, H - mb)
    elif anchor == "bottom_center":
        ax, ay = (xmin + xmax) / 2.0, ymin
        px, py = (anchor_px[0] * ss, anchor_px[1] * ss) if anchor_px else (cxm, H - mb)
    else:
        ax, ay = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
        px, py = (anchor_px[0] * ss, anchor_px[1] * ss) if anchor_px else (cxm, cym)

    if units_per_px is not None:
        u = units_per_px / ss
    else:
        cands = []
        for ext, avail in ((ax - xmin, px - ml), (xmax - ax, W - mr - px),
                           (ymax - ay, py - mt), (ay - ymin, H - mb - py)):
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


def center_on(cam, objs, x_frac=0.5, scene=None):
    """Shift a (perspective or ortho) camera horizontally so the pixel bbox of ``objs`` is centred
    at ``x_frac`` of the frame width (portraits: centre head+helmet whatever the yaw)."""
    sc = scene or bpy.context.scene
    x0, y0, x1, y1 = pixel_bounds(cam, objs, sc)
    W, H = sc.render.resolution_x, sc.render.resolution_y
    dx = ((x0 + x1) / 2.0 - x_frac * W) / max(W, H)
    cam.data.shift_x += dx
    bpy.context.view_layer.update()
    return dx


def surface_samples(cam, width=None, height=None, scene=None):
    """Ray-cast one ray per *target* pixel centre of an orthographic camera.

    Returns ``{"hit": HxW bool, "normal": HxWx3 world face normals, "mat": HxW material names
    ('' = miss), "obj": HxW object names}`` - used by QA to measure plane values (wall tops vs west
    / south / east faces, lit vs shadow roof slopes) in the finished sprite.
    """
    import numpy as np
    sc = scene or bpy.context.scene
    tw, th = sc.get("ironart_target", (sc.render.resolution_x, sc.render.resolution_y))
    W, H = int(width or tw), int(height or th)
    dg = bpy.context.evaluated_depsgraph_get()
    m = cam.matrix_world
    right = m.to_3x3() @ Vector((1, 0, 0))
    up = m.to_3x3() @ Vector((0, 1, 0))
    fwd = (m.to_3x3() @ Vector((0, 0, -1))).normalized()
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    scale = cam.data.ortho_scale
    vw, vh = (scale, scale * ry / rx) if rx >= ry else (scale * rx / ry, scale)
    centre = m.translation + right * (cam.data.shift_x * scale) + up * (cam.data.shift_y * scale)
    hit = np.zeros((H, W), bool)
    nrm = np.zeros((H, W, 3), np.float32)
    mats = np.full((H, W), "", dtype=object)
    objs = np.full((H, W), "", dtype=object)
    for j in range(H):
        for i in range(W):
            o = centre + right * ((i + 0.5) / W - 0.5) * vw + up * (0.5 - (j + 0.5) / H) * vh
            ok, loc, n, idx, ob, _mx = sc.ray_cast(dg, o, fwd)
            if not ok:
                continue
            hit[j, i] = True
            nrm[j, i] = tuple(n)
            objs[j, i] = ob.name
            try:
                ev = ob.evaluated_get(dg)
                mi = ev.data.polygons[idx].material_index
                mats[j, i] = ev.data.materials[mi].name if ev.data.materials[mi] else ""
            except (AttributeError, IndexError):
                pass
    return {"hit": hit, "normal": nrm, "mat": mats, "obj": objs}

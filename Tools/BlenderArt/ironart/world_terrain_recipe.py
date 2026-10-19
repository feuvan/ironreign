"""World Terrain family recipe: legacy look numbers of the Blender scene helpers.

The 2D map is now a gongbi blue-green painting: its numbers live with the code that uses them -
:mod:`ironart.world_terrain_glyphs` (``ELEV_DEG``, ``GLYPH``, ``CITY_CLEAR_PX``, ``TREE_GLYPH``:
the pictorial mountains, hills and trees) and :mod:`ironart.world_terrain_gongbi` (``GP``: the
silk and mineral palette, glazes, ink weights).  The 3D albedo palette is
:data:`ironart.world_terrain_paint.PAL`.

What is left here is used only by :mod:`ironart.world_terrain_render` (the scratch 3/4 previews):
``WORLDMAP`` (the retired realistic top-down render; ``light_top`` default only), ``PREVIEW3D``
(``light_persp`` default) and ``TREES`` (the stand-in tree prototypes, used when the World Models
glbs are missing).
"""

WORLDMAP = dict(
    size=(2400, 1500), ss=2, spp=40, adaptive=0.02,
    sun=dict(screen_angle=135.0, elevation=50.0, strength=3.9, color="#FFF4E6", softness=12.0),
    sky=dict(color="#B5BCC2", strength=0.5),
    # finishing (target px)
    kuwahara=dict(size=1.6, sharpness=0.5, eccentricity=1.4, amount=0.42),
    grade=dict(saturation=0.98, contrast=1.06, warmth=0.006, gamma=1.0),
    unsharp=(0.8, 0.28),
    vignette=0.0,
    sea=dict(shallow="#5FA3A0", mid="#2F7484", deep="#1E4B63", abyss="#173A54", foam="#E9F0EE"),
)

PREVIEW3D = dict(
    size=(1600, 900), spp=48, focal_fov=40.0, tilt=55.0,
    sun=dict(azimuth_from_north=225.0, elevation=32.0, strength=4.2, color="#FFF1DE", softness=1.0),
    focus=[(1240, 640, 1150.0), (720, 420, 900.0), (1250, 1180, 1000.0)],
)

TREES = dict(
    # stand-ins for SM_Tree_* in the 2D map: same size and silhouette family as the World Models
    # trees (Broad 23 m tall / ~19 m crown, Pine 27 m with layered pads, Bamboo 18.5 m / ~11 m)
    broad=dict(height=22.0, crown=18.5, color="#557F3B", color2="#6A9246", dark="#3F5F2C"),
    pine=dict(height=26.0, crown=16.0, color="#3F5E3A", color2="#4B6C43", dark="#2E4529"),
    bamboo=dict(height=18.5, crown=11.0, color="#6E8F45", color2="#80A050", dark="#55723A"),
)

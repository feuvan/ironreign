"""ironart - the Iron Reign Blender art pipeline.

Shared library every asset script uses to build, light, render and post-process game art with
Blender (Cycles, CPU) in the studio "Koei" look (painterly NPR on top of 3D, light from the top-left).

Usage from an asset script (always run through ``Tools/BlenderArt/render.sh``)::

    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))   # -> Tools/BlenderArt
    from ironart import scene, cameras, lights, materials, geometry, ink, post, palette

Modules
    palette    colour tokens (DESIGN.md section 8) in sRGB hex / linear floats + material colours
    scene      factory reset, Cycles CPU settings, resolution/supersampling, render helpers, seeds
    cameras    top-down ortho, 3/4 sprite, portrait cameras; fit object bounds into a pixel frame
    lights     "Koei key" light rigs (top-left key, cool fill, rim) and world colour
    materials  node-built procedural materials + the NPR "paint" shading option
    geometry   MeshBuilder + procedural builders (roofs, walls, gate towers, trees, hexes, frames...)
    ink        Freestyle brush-ink outlines (with the empty-scene line-style fix)
    post       compositor graphs (Kuwahara painterly...) and numpy/Pillow post-processing helpers
    terrain    relief-map heightfields, biome albedo painting, terrain build, forest scatter
    figure     portrait kit: sculpted head, lids/eyes, hair-curve beards/brows/plumes, helmet,
               armour, scarf, cape
    run        the single headless entry point (timing, logging, error exit codes)

``post``, ``palette`` and the numpy half of ``terrain`` import without ``bpy`` so they can also be
used from the system python3.
See ``Tools/BlenderArt/STYLE.md`` for the numbers (angles, energies, samples, radii, naming).
"""

import os as _os

__version__ = "1.0.0"

#: Tools/BlenderArt
TOOLS_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
#: repository root
REPO_DIR = _os.path.dirname(_os.path.dirname(TOOLS_DIR))
#: Content/Data/Art (final committed assets; see DESIGN.md section 8 manifest)
ART_DIR = _os.path.join(REPO_DIR, "Content", "Data", "Art")


def out_dir(*parts, create=True):
    """Scratch output directory for previews/intermediates.

    Uses ``$IRONART_OUT`` when set (render.sh sets it), else ``/tmp/ironart``. Final assets must be
    written to :data:`ART_DIR` paths explicitly by the asset script, never here.
    """
    base = _os.environ.get("IRONART_OUT") or "/tmp/ironart"
    path = _os.path.join(base, *parts)
    if create:
        _os.makedirs(path, exist_ok=True)
    return path

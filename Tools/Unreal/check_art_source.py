#!/usr/bin/env python3
"""Check ArtSource/ and Content/Data/Art3D/ against the 3D contract of docs/DESIGN.md section 12, without Unreal.

    python3 Tools/Unreal/check_art_source.py [--art-source DIR] [--art3d DIR]

Runs in CI (data job) and before Tools/Unreal/build_assets.sh. It catches what would otherwise only show up as an
ugly or broken import: unreadable or Draco-compressed .glb files, missing models, models in the wrong units or not
standing on their origin, missing "Tint" slots, untextured (flat colour) exports, wrong terrain texture sizes and a
heightmap that does not match Terrain.json. Exit status 1 when there are errors (warnings do not fail).
Nothing is checked (exit 0) when ArtSource/ does not exist yet.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

import ironreign_gltf as gltf  # noqa: E402  (shared with the Unreal import script)
import ironreign_terrain as terrain_chunks  # noqa: E402  (the import's terrain chunks; check_art3d's "terrain" is Terrain.json)

TERRAINS = ("Plain", "Forest", "Hill", "Mountain", "Water", "Ford", "Bridge", "Road", "Wall", "Gate", "Town",
            "Castle", "Rubble")
EXPECTED_MODELS = (["City_1", "City_2", "City_3", "Sect", "Banner", "Flag", "Tree_Pine", "Tree_Broad", "Tree_Bamboo",
                    "Unit_Infantry", "Unit_Cavalry", "Unit_Archer", "Unit_Base"]
                   + ["Hex_" + t for t in TERRAINS])
NEEDS_TINT = ("Banner", "Flag", "Unit_Infantry", "Unit_Cavalry", "Unit_Archer", "Unit_Base")
TRIANGLE_BUDGET = 150000
# (measure, low, high) in metres; measure: footprint = max horizontal extent, height = vertical extent.
SIZE_RANGES = {
    "City_1": ("footprint", 25.0, 80.0),
    "City_2": ("footprint", 40.0, 130.0),
    "City_3": ("footprint", 70.0, 200.0),
    "Sect": ("largest", 18.0, 70.0),
    "Banner": ("height", 12.0, 35.0),
    "Flag": ("height", 5.0, 18.0),
    "Tree_Pine": ("height", 12.0, 45.0),
    "Tree_Broad": ("height", 12.0, 45.0),
    "Tree_Bamboo": ("height", 12.0, 45.0),
    "Unit_Infantry": ("footprint", 1.0, 7.5),
    "Unit_Cavalry": ("footprint", 1.0, 7.5),
    "Unit_Archer": ("footprint", 1.0, 7.5),
    "Unit_Base": ("footprint", 4.0, 8.0),
}
TERRAIN_SIZE = (4800, 3000)
TREE_TYPES = ("pine", "broad", "bamboo")


class Report(object):
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def error(self, where, message):
        self.errors += 1
        print("ERROR %s: %s" % (where, message))

    def warn(self, where, message):
        self.warnings += 1
        print("WARN  %s: %s" % (where, message))

    @staticmethod
    def info(where, message):
        print("ok    %s: %s" % (where, message))

    @staticmethod
    def note(where, message):
        print("note  %s: %s" % (where, message))


def rel(path):
    try:
        return os.path.relpath(path, REPO)
    except ValueError:
        return path


def check_manifest(art, report):
    path = os.path.join(art, "manifest.json")
    if not os.path.isfile(path):
        report.error(rel(path), "missing (the import needs {\"version\": N})")
        return
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        report.error(rel(path), "unreadable: %s" % exc)
        return
    version = data.get("version") if isinstance(data, dict) else None
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        report.error(rel(path), "\"version\" must be a positive integer (bump it whenever ArtSource changes)")
        return
    convention = data.get("normalMapConvention", "opengl")
    if convention not in ("opengl", "directx"):
        report.warn(rel(path), "normalMapConvention should be \"opengl\" (Blender, glTF) or \"directx\"")
    report.info(rel(path), "version %d" % version)


def check_terrain(art, report):
    sizes = {}
    for name, wanted in (("Albedo.png", ("rgb", "rgba")), ("Masks.png", ("rgba",))):
        path = os.path.join(art, "Terrain", name)
        if not os.path.isfile(path):
            report.error(rel(path), "missing (M_IronTerrain needs it)")
            continue
        info = gltf.png_info(path)
        if info is None:
            report.error(rel(path), "not a PNG")
            continue
        width, height, depth, color = info
        sizes[name] = (width, height)
        if (width, height) != TERRAIN_SIZE:
            report.warn(rel(path), "%dx%d, DESIGN.md 12.2 specifies %dx%d (2 px per metre)" % (
                width, height, TERRAIN_SIZE[0], TERRAIN_SIZE[1]))
        if depth != 8:
            report.warn(rel(path), "%d-bit channels; 8-bit expected" % depth)
        if color not in wanted:
            report.warn(rel(path), "colour type %s, expected %s%s" % (
                color, " or ".join(wanted), " (A = road mask)" if name == "Masks.png" else ""))
        if (width, height) == TERRAIN_SIZE and depth == 8 and color in wanted:
            report.info(rel(path), "%dx%d %s" % (width, height, color))
    if len(sizes) == 2 and sizes["Albedo.png"] != sizes["Masks.png"]:
        report.error(rel(os.path.join(art, "Terrain")), "Albedo.png and Masks.png must have the same size")


def check_textures(art, report):
    folder = os.path.join(art, "Textures")
    normal = os.path.join(folder, "Water_Normal.png")
    if not os.path.isfile(normal):
        report.warn(rel(normal), "missing: M_IronWater falls back to a flat (mirror-like) surface")
    if not os.path.isdir(folder):
        return
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not name.lower().endswith(".png"):
            continue
        info = gltf.png_info(path)
        if info is None:
            report.error(rel(path), "not a readable PNG")
            continue
        if not (gltf.is_power_of_two(info[0]) and gltf.is_power_of_two(info[1])):
            report.warn(rel(path), "%dx%d is not a power of two (tiling textures need mips)" % (info[0], info[1]))
        else:
            report.info(rel(path), "%dx%d %s" % (info[0], info[1], info[3]))


def _measure(bounds):
    (x0, y0, z0), (x1, y1, z1) = bounds
    footprint = max(x1 - x0, z1 - z0)
    height = y1 - y0
    return {"footprint": footprint, "height": height, "largest": max(footprint, height)}


def check_model(path, report):
    name = os.path.splitext(os.path.basename(path))[0]
    where = rel(path)
    try:
        asset = gltf.GltfAsset(path)
    except gltf.GltfError as exc:
        report.error(where, str(exc))
        return
    unsupported = asset.unsupported_extensions()
    if unsupported:
        report.error(where, "requires %s, which Unreal's glTF import cannot decode" % ", ".join(unsupported))
    if asset.mesh_node_count() == 0:
        report.error(where, "contains no mesh")
        return
    if asset.mesh_node_count() > 1:
        report.warn(where, "%d mesh objects: join them into one object so the import yields a single static mesh"
                    % asset.mesh_node_count())
    triangles = asset.triangle_count()
    if triangles > TRIANGLE_BUDGET:
        report.warn(where, "%d triangles (budget %d)" % (triangles, TRIANGLE_BUDGET))
    for image in range(asset.image_count()):
        if not asset.image_is_embedded(image):
            report.warn(where, "image '%s' is an external file; export .glb with embedded images"
                        % asset.image_name(image))
    names = [m.name for m in asset.materials]
    has_tint = any(n.lower().startswith("tint") for n in names)
    if name in NEEDS_TINT and not has_tint:
        report.warn(where, "no material named 'Tint' (the faction colour is applied to Tint slots)")
    textured = [m for m in asset.materials if not m.name.lower().startswith("tint") and m.base_color_texture is not None]
    untinted = [m for m in asset.materials if not m.name.lower().startswith("tint")]
    if untinted and not textured:
        report.warn(where, "no material has a base colour texture: bake the procedural Blender materials to "
                    "images, otherwise the model imports as flat colours")
    for material in asset.materials:
        if material.uses_secondary_uv:
            report.warn(where, "material '%s' samples a second UV set (only UV0 is used)" % material.name)
        if material.alpha_mode == "BLEND":
            report.warn(where, "material '%s' uses alpha BLEND; it is imported alpha-tested (MASK)" % material.name)
    bounds = asset.bounds()
    if bounds is None:
        report.error(where, "no POSITION bounds (accessor min/max missing)")
        return
    sizes = _measure(bounds)
    (x0, y0, z0), (x1, y1, z1) = bounds
    if name.startswith("Hex_"):
        if not (7.4 <= x1 - x0 <= 8.6 and 6.4 <= z1 - z0 <= 7.5):
            report.warn(where, "hex is %.2f x %.2f m; a flat-top hex of corner radius 4 m is 8.00 x 6.93 m "
                        "(corners along Blender X)" % (x1 - x0, z1 - z0))
        if not -1.6 <= y0 <= -0.4:
            report.warn(where, "lowest point at %.2f m; the skirt should reach about -1 m below the top (Z = 0)" % y0)
    else:
        if not -3.0 <= y0 <= 0.5:
            report.warn(where, "lowest point at %.2f m: the origin should be at the model's base on the ground" % y0)
        measure = SIZE_RANGES.get(name)
        if measure is not None:
            kind, low, high = measure
            value = sizes[kind]
            if not low <= value <= high:
                hint = " (exported in centimetres?)" if value > high * 50 else ""
                report.warn(where, "%s %.1f m outside the expected %.0f-%.0f m%s" % (kind, value, low, high, hint))
    center_x = (x0 + x1) * 0.5
    center_z = (z0 + z1) * 0.5
    off_centre = abs(center_x) > 0.25 * sizes["footprint"] + 1.0 or abs(center_z) > 0.25 * sizes["footprint"] + 1.0
    if off_centre and name not in ("Banner", "Flag"):  # cloth hangs to one side of the pole
        report.warn(where, "bounds centre (%.1f, %.1f) m (Blender X, Y) is far from the origin: centre the model "
                    "on its base" % (center_x, -center_z))
    double_sided = [m.name for m in asset.materials if m.double_sided and m.alpha_mode == "OPAQUE"]
    if double_sided:
        report.note(where, "double-sided opaque material(s) %s import two-sided (Blender: Backface Culling off); "
                    "enable Backface Culling on closed meshes" % ", ".join(double_sided))
    report.info(where, "%d triangles, %d material(s), %d image(s), footprint %.1f m, height %.1f m" % (
        triangles, len(asset.materials), asset.image_count(), sizes["footprint"], sizes["height"]))


def check_models(art, report):
    folder = os.path.join(art, "Models")
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".glb", ".gltf"))) \
        if os.path.isdir(folder) else []
    if not files:
        report.error(rel(folder), "no .glb models")
        return
    present = set(os.path.splitext(f)[0] for f in files)
    missing = [m for m in EXPECTED_MODELS if m not in present]
    if missing:
        report.warn(rel(folder), "missing models (the game uses fallbacks for them): %s" % ", ".join(missing))
    for file_name in files:
        check_model(os.path.join(folder, file_name), report)


def _load_json(path, report):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        report.error(rel(path), "unreadable JSON: %s" % exc)
        return None


def check_art3d(art3d, report):
    """Runtime data written by the Blender pipeline next to ArtSource (DESIGN.md 12.2 / 12.3)."""
    if not os.path.isdir(art3d):
        report.warn(rel(art3d), "missing (terrain heightmap, trees and model parameters for the 3D map)")
        return
    terrain_path = os.path.join(art3d, "Terrain", "Terrain.json")
    terrain = _load_json(terrain_path, report) if os.path.isfile(terrain_path) else None
    if terrain is None:
        if not os.path.isfile(terrain_path):
            report.error(rel(terrain_path), "missing")
    else:
        keys = ("width", "height", "gridStep", "minHeight", "maxHeight", "seaLevel")
        absent = [k for k in keys if not isinstance(terrain.get(k), (int, float)) or isinstance(terrain.get(k), bool)]
        if absent:
            report.error(rel(terrain_path), "missing numeric field(s): %s" % ", ".join(absent))
        else:
            step = terrain["gridStep"]
            expected = (int(round(terrain["width"] / step)) + 1, int(round(terrain["height"] / step)) + 1) \
                if step > 0 else None
            height_path = os.path.join(art3d, "Terrain", "Height.png")
            info = gltf.png_info(height_path)
            if info is None:
                report.error(rel(height_path), "missing or not a PNG")
            else:
                if expected and (info[0], info[1]) != expected:
                    report.error(rel(height_path), "%dx%d, Terrain.json implies %dx%d" % (
                        info[0], info[1], expected[0], expected[1]))
                if info[2] != 16 or info[3] != "grey":
                    report.error(rel(height_path), "%d-bit %s; a 16-bit greyscale PNG is required" % (info[2], info[3]))
                if expected and (info[0], info[1]) == expected and info[2] == 16 and info[3] == "grey":
                    report.info(rel(height_path), "%dx%d 16-bit" % (info[0], info[1]))
                # The import cuts the static terrain chunks (Lumen scene) from it with a pure-Python decoder.
                try:
                    with open(height_path, "rb") as handle:
                        terrain_chunks.decode_grey_png(handle.read())
                except (OSError, terrain_chunks.TerrainError) as exc:
                    report.warn(rel(height_path), "the import cannot cut SM_Terrain_* chunks from it (%s); the game then "
                                "builds the terrain at runtime, outside the Lumen scene" % exc)
    models_path = os.path.join(art3d, "Models.json")
    if os.path.isfile(models_path):
        models = _load_json(models_path, report)
        if models is not None:
            front = models.get("frontYaw") if isinstance(models, dict) else None
            if isinstance(front, bool) or not isinstance(front, (int, float)):
                report.error(rel(models_path), "\"frontYaw\" must be a number (degrees)")
    else:
        report.warn(rel(models_path), "missing (frontYaw defaults to 90)")
    trees_path = os.path.join(art3d, "Terrain", "Trees.json")
    if os.path.isfile(trees_path):
        trees = _load_json(trees_path, report)
        if trees is not None:
            if not isinstance(trees, list):
                report.error(rel(trees_path), "must be a JSON array")
            else:
                bad = [t for t in trees if not isinstance(t, dict) or t.get("t") not in TREE_TYPES
                       or not all(isinstance(t.get(k), (int, float)) for k in ("x", "y"))]
                if bad:
                    report.error(rel(trees_path), "%d malformed entries (need t in %s, numeric x/y)"
                                 % (len(bad), "/".join(TREE_TYPES)))
                if len(trees) > 25000:
                    report.warn(rel(trees_path), "%d trees (DESIGN.md budget ~25k)" % len(trees))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--art-source", default=os.path.join(REPO, "ArtSource"))
    parser.add_argument("--art3d", default=os.path.join(REPO, "Content", "Data", "Art3D"))
    args = parser.parse_args()
    art = os.path.abspath(args.art_source)
    if not os.path.isdir(art):
        print("ArtSource not found at %s: nothing to check (the game uses its 2D presentation)." % rel(art))
        return 0
    report = Report()
    check_manifest(art, report)
    check_terrain(art, report)
    check_textures(art, report)
    check_models(art, report)
    check_art3d(os.path.abspath(args.art3d), report)
    print("%d error(s), %d warning(s)" % (report.errors, report.warnings))
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())

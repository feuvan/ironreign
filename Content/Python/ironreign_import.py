"""Iron Reign editor asset pipeline: ArtSource/ -> /Game/IronReign (docs/DESIGN.md section 12).

Runs inside the Unreal Editor's Python (UE adds Content/Python to sys.path):

    import ironreign_import
    ironreign_import.build_all()            # only when ArtSource/manifest.json "version" changed
    ironreign_import.build_all(force=True)  # rebuild everything

It is started automatically by Content/Python/init_unreal.py on editor start when the assets are out of date, and
explicitly by Tools/Unreal/build_assets.sh / .bat (commandlet ``-run=pythonscript``).

What it builds (every path is a build product, regenerated deterministically; nothing here is committed):

    /Game/IronReign/Textures/   T_Terrain_Albedo (sRGB), T_Terrain_Masks (linear masks), T_<Name> for
                                ArtSource/Textures/<Name>.png (T_Water_Normal...), T_IronWhite, T_IronWhiteLinear,
                                T_IronFlatNormal (generated defaults)
    /Game/IronReign/Materials/  MPC_IronSeason, M_IronTerrain + MI_IronTerrain, M_IronWater + MI_IronWater,
                                M_IronTint + MI_IronTintInstanced, M_IronHighlight + MI_IronHighlightHex, M_IronInk,
                                M_IronModel / M_IronModelTwoSided / M_IronModelMasked (glTF PBR masters),
                                MI_IronClouds (wraps the engine volumetric cloud material so it is cooked)
    /Game/IronReign/Models/     SM_<Name> for ArtSource/Models/<Name>.glb (Nanite, no collision), SM_IronPlane
                                (copy of the engine 1 m plane); <Name>/MI_<Name>_<Material>, <Name>/T_<Name>_<Image>
    /Game/IronReign/IronReignAssetVersion   UIronAssetManifest, written last (= the import is complete)
    Saved/IronReign/asset_version.txt        JSON build record (versions, errors, warnings, assets)
    Saved/IronReign/asset_build_result.txt   OK / FAILED / SKIPPED (read by the build scripts)

The importer never raises out of build_all(): problems are logged with unreal.log_warning / log_error, recorded in
the build record and reported through the return value.
"""

import datetime
import json
import os
import re
import shutil
import struct
import time
import traceback
import zlib

import unreal

import ironreign_gltf as gltf

# Bump when this script changes what it produces: editors then rebuild on their next start.
PIPELINE_VERSION = 1

ROOT_DIR = "/Game/IronReign"
MODELS_DIR = ROOT_DIR + "/Models"
TEXTURES_DIR = ROOT_DIR + "/Textures"
MATERIALS_DIR = ROOT_DIR + "/Materials"
# Interchange imports land here first; the static mesh is then moved to MODELS_DIR and the rest deleted.
STAGING_DIR = ROOT_DIR + "/Import"
MARKER_NAME = "IronReignAssetVersion"
MARKER_PATH = ROOT_DIR + "/" + MARKER_NAME
MARKER_CLASS_NAME = "IronAssetManifest"  # C++ UIronAssetManifest (Source/IronReign/World/IronAssetManifest.h)

MPC_NAME = "MPC_IronSeason"
PLANE_PATH = MODELS_DIR + "/SM_IronPlane"
ENGINE_PLANE_PATH = "/Engine/BasicShapes/Plane"
CLOUD_PARENT_CANDIDATES = (
    "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst",
    "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud",
)

# World space (DESIGN.md 12.2): the map rectangle in centimetres.
MAP_WIDTH_CM = 240000.0
MAP_HEIGHT_CM = 150000.0

# Model meshes are presentation only: picking is done in map space, so no collision is cooked.
STRIP_MODEL_COLLISION = True
# "single_layer_water" (depth-tinted water through Single Layer Water shading) or "default_lit".
WATER_SHADING = "single_layer_water"

# Look constants (linear colours). The runtime can override every one of them through material parameters.
SNOW_COLOR = (0.80, 0.84, 0.90, 1.0)
AUTUMN_TINT = (2.1, 1.15, 0.38, 1.0)
LUMA = (0.30, 0.59, 0.11)
WATER_COLOR = (0.006, 0.045, 0.05, 1.0)
WATER_SCATTERING = (0.002, 0.03, 0.035, 1.0)
WATER_ABSORPTION = (0.40, 0.075, 0.07, 1.0)
INK_TONE = (0.12, 0.09, 0.07, 1.0)
HIGHLIGHT_COLOR = (0.25, 0.6, 1.0, 1.0)

EXPECTED_MATERIALS = ("M_IronTerrain", "MI_IronTerrain", "M_IronWater", "MI_IronWater", "M_IronTint",
                      "MI_IronTintInstanced", "M_IronHighlight", "MI_IronHighlightHex", "M_IronInk", "M_IronModel",
                      "M_IronModelTwoSided", "M_IronModelMasked", MPC_NAME)
DEFAULT_TEXTURES = (
    # (asset name, RGBA bytes, kind)
    ("T_IronWhite", (255, 255, 255, 255), gltf.KIND_COLOR),
    ("T_IronWhiteLinear", (255, 255, 255, 255), gltf.KIND_MASKS),
    ("T_IronFlatNormal", (128, 128, 255, 255), gltf.KIND_NORMAL),
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tga")

LOG_PREFIX = "[IronReign] "


class _BuildError(Exception):
    """A step that cannot continue (logged as an error, the build goes on with the next step)."""


class _Report(object):
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.assets = []
        self.models = []
        self.notes = {}


_report = _Report()


# ----- logging --------------------------------------------------------------------------------------------------

def _log(message):
    unreal.log(LOG_PREFIX + message)


def _warn(message):
    _report.warnings.append(message)
    unreal.log_warning(LOG_PREFIX + message)


def _error(message):
    _report.errors.append(message)
    unreal.log_error(LOG_PREFIX + message)


# ----- small utilities ------------------------------------------------------------------------------------------

def _enum(enum_name, *members):
    """unreal.<enum_name>.<first existing member>, or None (enum names move between engine versions)."""
    enum_type = getattr(unreal, enum_name, None)
    if enum_type is None:
        return None
    for member in members:
        value = getattr(enum_type, member, None)
        if value is not None:
            return value
    return None


def _try_set(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True, ""
    except Exception as exc:  # property renamed/removed in this engine version, or wrong type
        return False, str(exc)


def _set(obj, name, value, context=""):
    """set_editor_property with a warning instead of an exception."""
    if value is None:
        _warn("%s: no value for '%s' in this engine version" % (context or _name_of(obj), name))
        return False
    ok, detail = _try_set(obj, name, value)
    if not ok:
        _warn("%s: cannot set '%s' (%s)" % (context or _name_of(obj), name, detail))
    return ok


def _name_of(obj):
    try:
        return obj.get_name()
    except Exception:
        return str(obj)


def _safe_name(text, fallback="Asset"):
    name = re.sub(r"[^A-Za-z0-9_]+", "_", text or "").strip("_")
    return name or fallback


def _norm(text):
    return re.sub(r"[^0-9a-z]+", "", (text or "").lower())


def _unique(name, used):
    candidate = name
    index = 2
    while candidate.lower() in used:
        candidate = "%s_%d" % (name, index)
        index += 1
    used.add(candidate.lower())
    return candidate


def _package_of(path):
    return str(path).split(".", 1)[0]


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----- paths and ArtSource --------------------------------------------------------------------------------------

def _project_dir():
    override = os.environ.get("IRONREIGN_PROJECT_DIR")
    if override:
        return os.path.abspath(override)
    try:
        return os.path.abspath(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
    except Exception:
        # Content/Python/ironreign_import.py -> project root
        return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def paths():
    """Filesystem locations used by the pipeline (ArtSource can be moved with IRONREIGN_ART_SOURCE)."""
    project = _project_dir()
    saved = os.path.join(project, "Saved", "IronReign")
    return {
        "project": project,
        "art": os.path.abspath(os.environ.get("IRONREIGN_ART_SOURCE") or os.path.join(project, "ArtSource")),
        "saved": saved,
        "staging": os.path.join(saved, "Staging"),
        "status": os.path.join(saved, "asset_version.txt"),
        "result": os.path.join(saved, "asset_build_result.txt"),
    }


def read_manifest(art_dir, quiet=False):
    """ArtSource/manifest.json as a dict with an int "version", or None."""
    path = os.path.join(art_dir, "manifest.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        if not quiet:
            _error("cannot read %s: %s" % (path, exc))
        return None
    version = data.get("version") if isinstance(data, dict) else None
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        if not quiet:
            _error("%s: \"version\" must be a positive integer" % path)
        return None
    return data


def _list_files(directory, extensions):
    if not os.path.isdir(directory):
        return []
    return sorted(os.path.join(directory, name) for name in os.listdir(directory)
                  if name.lower().endswith(extensions) and not name.startswith("."))


def _write_png(path, width, height, rgba):
    """A solid-colour 8-bit RGBA PNG (default textures; no PIL in the editor's Python)."""
    row = b"\x00" + bytes(rgba) * width
    raw = row * height

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    data = (gltf.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


# ----- asset helpers --------------------------------------------------------------------------------------------

def _exists(path):
    try:
        return bool(unreal.EditorAssetLibrary.does_asset_exist(path))
    except Exception:
        return False


def _load(path):
    if not _exists(path):
        return None
    try:
        return unreal.EditorAssetLibrary.load_asset(path)
    except Exception as exc:
        _warn("cannot load %s: %s" % (path, exc))
        return None


def _save(asset):
    try:
        if not unreal.EditorAssetLibrary.save_loaded_asset(asset, False):
            _warn("could not save %s" % _name_of(asset))
    except Exception as exc:
        _warn("could not save %s: %s" % (_name_of(asset), exc))


def _record(path):
    if path not in _report.assets:
        _report.assets.append(path)


def _referencers(path):
    try:
        return [str(p) for p in (unreal.EditorAssetLibrary.find_package_referencers_for_asset(path, False) or [])]
    except Exception:
        return []


def _delete_asset(path):
    """Deletes an asset nothing else references. True when it is gone."""
    if not _exists(path):
        return True
    references = [r for r in _referencers(path) if r != _package_of(path)]
    if references:
        _error("cannot replace %s: it is referenced by %s (remove those references, or delete it by hand)"
               % (path, ", ".join(sorted(references)[:5])))
        return False
    try:
        if unreal.EditorAssetLibrary.delete_asset(path):
            return True
    except Exception as exc:
        _warn("deleting %s failed: %s" % (path, exc))
    return not _exists(path)


def _cleanup_folder(folder, keep=()):
    """Deletes every unreferenced asset in a folder (dependents first), then the folder when it is empty."""
    library = unreal.EditorAssetLibrary
    try:
        if not library.does_directory_exist(folder):
            return
        unreal.SystemLibrary.collect_garbage()
        keep_packages = set(_package_of(k) for k in keep)
        for _ in range(4):
            progress = False
            for path in library.list_assets(folder, True, False) or []:
                if _package_of(path) in keep_packages or _referencers(path):
                    continue
                if library.delete_asset(path):
                    progress = True
            if not progress:
                break
        leftovers = [p for p in (library.list_assets(folder, True, False) or [])
                     if _package_of(p) not in keep_packages]
        if not library.list_assets(folder, True, False):
            library.delete_directory(folder)
        elif leftovers:
            _log("kept %d referenced asset(s) in %s" % (len(leftovers), folder))
    except Exception as exc:
        _warn("cleanup of %s failed: %s" % (folder, exc))


def _create_or_load(name, directory, asset_class, make_factory):
    """Loads directory/name when it already has the right class (references stay valid), else creates it."""
    path = directory + "/" + name
    existing = _load(path)
    if existing is not None:
        if isinstance(existing, asset_class):
            return existing
        _warn("replacing %s (it is a %s, expected %s)" % (path, existing.get_class().get_name(), asset_class.__name__))
        if not _delete_asset(path):
            return None
    try:
        asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, directory, asset_class, make_factory())
    except Exception as exc:
        _error("cannot create %s: %s" % (path, exc))
        return None
    if asset is None:
        _error("cannot create %s" % path)
    return asset


def _import_file(filename, destination_path, destination_name=None):
    """AssetImportTask (automated, replace existing, saved); returns the imported objects."""
    task = unreal.AssetImportTask()
    context = "import " + os.path.basename(filename)
    _set(task, "filename", filename, context)
    _set(task, "destination_path", destination_path, context)
    if destination_name:
        _set(task, "destination_name", destination_name, context)
    _set(task, "automated", True, context)
    _set(task, "replace_existing", True, context)
    _set(task, "save", True, context)
    _try_set(task, "replace_existing_settings", True)
    try:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    except Exception as exc:
        _error("importing %s failed: %s" % (filename, exc))
        return []
    objects = []
    try:
        imported = list(task.get_editor_property("imported_object_paths") or [])
    except Exception:
        imported = []
    for object_path in imported:
        try:
            loaded = unreal.load_asset(str(object_path))
        except Exception:
            loaded = None
        if loaded is not None:
            objects.append(loaded)
    if not objects:
        try:
            objects = [o for o in (task.get_objects() or []) if o is not None]
        except Exception:
            pass
    return objects


def _static_mesh_subsystem():
    try:
        return unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    except Exception:
        return None


# ----- textures -------------------------------------------------------------------------------------------------

def _texture_kind_for_name(name):
    """Water_Normal / Rock_N -> normal map, Foam_Mask / Rock_ORM / Sand_Roughness -> linear masks, else colour."""
    lowered = name.lower()
    if re.search(r"(^|_)(normal|nrm|n)$", lowered) or "normal" in lowered.split("_"):
        return gltf.KIND_NORMAL
    if re.search(r"(^|_)(mask|masks|orm|roughness|height|ao)$", lowered):
        return gltf.KIND_MASKS
    return gltf.KIND_COLOR


def _configure_texture(texture, kind, flip_green, clamp, source_size):
    properties = {}
    if kind == gltf.KIND_NORMAL:
        properties["srgb"] = False
        properties["compression_settings"] = _enum("TextureCompressionSettings", "TC_NORMALMAP")
        properties["lod_group"] = _enum("TextureGroup", "TEXTUREGROUP_WORLD_NORMAL_MAP")
        properties["flip_green_channel"] = bool(flip_green)
    elif kind == gltf.KIND_MASKS:
        properties["srgb"] = False
        properties["compression_settings"] = _enum("TextureCompressionSettings", "TC_MASKS")
        properties["lod_group"] = _enum("TextureGroup", "TEXTUREGROUP_WORLD")
    else:
        properties["srgb"] = True
        properties["compression_settings"] = _enum("TextureCompressionSettings", "TC_DEFAULT")
        properties["lod_group"] = _enum("TextureGroup", "TEXTUREGROUP_WORLD")
    properties["mip_gen_settings"] = _enum("TextureMipGenSettings", "TMGS_FROM_TEXTURE_GROUP")
    address = _enum("TextureAddress", "TA_CLAMP" if clamp else "TA_WRAP")
    properties["address_x"] = address
    properties["address_y"] = address
    if source_size and not (gltf.is_power_of_two(source_size[0]) and gltf.is_power_of_two(source_size[1])):
        # Non power-of-two sources (the 4800x3000 terrain maps) would get no mips: stretch them on build.
        stretch = _enum("TexturePowerOfTwoSetting", "STRETCH_TO_POWER_OF_TWO")
        if stretch is not None:
            properties["power_of_two_mode"] = stretch
        else:
            _warn("%s is %dx%d (not a power of two) and this engine has no stretch mode: it will have no mips"
                  % (_name_of(texture), source_size[0], source_size[1]))
    properties = dict((k, v) for k, v in properties.items() if v is not None)
    try:
        texture.set_editor_properties(properties)
    except Exception:
        for key, value in properties.items():
            _set(texture, key, value)


def _import_texture(source, directory, asset_name, kind, flip_green=False, clamp=False, staging_dir=None):
    """Imports an image as directory/asset_name and configures colour space, compression and mips."""
    staged = source
    if staging_dir:
        # The staged copy carries the asset name, so the import lands on it whatever naming the importer uses.
        staged = os.path.join(staging_dir, asset_name + os.path.splitext(source)[1].lower())
        os.makedirs(staging_dir, exist_ok=True)
        shutil.copyfile(source, staged)
    objects = _import_file(staged, directory, asset_name)
    texture = next((o for o in objects if isinstance(o, unreal.Texture2D)), None)
    expected = directory + "/" + asset_name
    if texture is None:
        loaded = _load(expected)
        texture = loaded if isinstance(loaded, unreal.Texture2D) else None
    if texture is None:
        _error("importing %s produced no texture" % source)
        return None
    actual = _package_of(texture.get_path_name())
    if actual != expected:
        _warn("%s was imported as %s (expected %s)" % (os.path.basename(source), actual, expected))
    info = gltf.png_info(staged)
    _configure_texture(texture, kind, flip_green, clamp, (info[0], info[1]) if info else None)
    _save(texture)
    _record(actual)
    return texture


class _Context(object):
    """State shared by the build steps."""

    def __init__(self, folders, manifest):
        self.paths = folders
        self.manifest = manifest
        convention = str(manifest.get("normalMapConvention", "opengl")).lower()
        # Blender and glTF write OpenGL (+Y) normal maps; Unreal expects DirectX (-Y): flip green on import.
        self.flip_green = convention != "directx"
        self.textures = {}
        self.materials = {}
        self.mpc = None
        self.water_shading = ""

    def texture(self, key, fallback="T_IronWhite"):
        found = self.textures.get(key) or self.textures.get(fallback)
        return found


def _build_default_textures(ctx):
    generated = os.path.join(ctx.paths["staging"], "Generated")
    for asset_name, rgba, kind in DEFAULT_TEXTURES:
        path = os.path.join(generated, asset_name + ".png")
        _write_png(path, 8, 8, rgba)
        texture = _import_texture(path, TEXTURES_DIR, asset_name, kind)
        if texture is not None:
            ctx.textures[asset_name] = texture


def _build_art_textures(ctx):
    art = ctx.paths["art"]
    staging = os.path.join(ctx.paths["staging"], "Textures")
    for file_name, asset_name, kind in (("Albedo.png", "T_Terrain_Albedo", gltf.KIND_COLOR),
                                        ("Masks.png", "T_Terrain_Masks", gltf.KIND_MASKS)):
        source = os.path.join(art, "Terrain", file_name)
        if not os.path.isfile(source):
            _error("missing %s: M_IronTerrain falls back to a white ground" % source)
            continue
        info = gltf.png_info(source)
        if info and (info[0], info[1]) != (4800, 3000):
            _warn("%s is %dx%d (DESIGN.md 12.2 expects 4800x3000; it is stretched over the map anyway)"
                  % (source, info[0], info[1]))
        texture = _import_texture(source, TEXTURES_DIR, asset_name, kind, clamp=True, staging_dir=staging)
        if texture is not None:
            ctx.textures[asset_name] = texture
    for source in _list_files(os.path.join(art, "Textures"), IMAGE_EXTENSIONS):
        base = _safe_name(os.path.splitext(os.path.basename(source))[0])
        kind = _texture_kind_for_name(base)
        texture = _import_texture(source, TEXTURES_DIR, "T_" + base, kind, flip_green=ctx.flip_green,
                                  staging_dir=staging)
        if texture is not None:
            ctx.textures["T_" + base] = texture
    if "T_Water_Normal" not in ctx.textures:
        _warn("no ArtSource/Textures/Water_Normal.png: M_IronWater uses a flat normal")


# ----- material graphs ------------------------------------------------------------------------------------------

class _Graph(object):
    """Thin layer over MaterialEditingLibrary: creates and wires expressions and counts wiring failures."""

    def __init__(self, material):
        self.material = material
        self.name = material.get_name()
        self.failures = 0
        self._count = 0
        self._constants = {}
        self._collections = {}

    def fail(self, message, optional=False):
        if optional:
            _log("%s: %s (optional)" % (self.name, message))
        else:
            self.failures += 1
            _warn("%s: %s" % (self.name, message))

    def node(self, class_name, **properties):
        expression_class = getattr(unreal, class_name, None)
        if expression_class is None:
            raise _BuildError("%s: unreal.%s does not exist in this engine version" % (self.name, class_name))
        column = self._count % 10
        row = self._count // 10
        self._count += 1
        expression = unreal.MaterialEditingLibrary.create_material_expression(
            self.material, expression_class, -320 - 260 * column, -600 + 160 * row)
        if expression is None:
            raise _BuildError("%s: could not create %s" % (self.name, class_name))
        for key, value in properties.items():
            ok, detail = _try_set(expression, key, value)
            if not ok:
                self.fail("cannot set %s.%s (%s)" % (class_name, key, detail))
        return expression

    # -- operands: an expression, (expression, "OutputName"), a number or a tuple of 2-4 numbers --

    def source(self, value):
        if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], str):
            return value
        if isinstance(value, bool):
            raise _BuildError("%s: boolean operand" % self.name)
        if isinstance(value, (int, float)):
            return self.constant(value), ""
        if isinstance(value, (tuple, list)):
            return self.constant_vector(value), ""
        return value, ""

    def constant(self, value):
        key = ("s", float(value))
        if key not in self._constants:
            self._constants[key] = self.node("MaterialExpressionConstant", r=float(value))
        return self._constants[key]

    def constant_vector(self, values):
        values = tuple(float(v) for v in values)
        key = ("v",) + values
        if key not in self._constants:
            if len(values) == 2:
                node = self.node("MaterialExpressionConstant2Vector", r=values[0], g=values[1])
            elif len(values) == 3:
                node = self.node("MaterialExpressionConstant3Vector",
                                 constant=unreal.LinearColor(values[0], values[1], values[2], 1.0))
            elif len(values) == 4:
                node = self.node("MaterialExpressionConstant4Vector", constant=unreal.LinearColor(*values))
            else:
                raise _BuildError("%s: vector constant of size %d" % (self.name, len(values)))
            self._constants[key] = node
        return self._constants[key]

    def link(self, value, target, inputs, optional=False):
        expression, output = self.source(value)
        names = [inputs] if isinstance(inputs, str) else list(inputs)
        for name in names:
            try:
                if unreal.MaterialEditingLibrary.connect_material_expressions(expression, output, target, name):
                    return True
            except Exception:
                pass
        self.fail("cannot connect %s[%s] -> %s.%s" % (_name_of(expression.get_class()), output or "0",
                                                      _name_of(target.get_class()), "/".join(names) or "<first>"),
                  optional)
        return False

    def output(self, value, property_name):
        expression, output = self.source(value)
        material_property = _enum("MaterialProperty", property_name)
        ok = False
        if material_property is not None:
            try:
                ok = unreal.MaterialEditingLibrary.connect_material_property(expression, output, material_property)
            except Exception:
                ok = False
        if not ok:
            self.fail("cannot connect %s to the material output %s" % (_name_of(expression.get_class()),
                                                                       property_name))

    # -- math --

    def binary(self, class_name, a, b, names=("A", "B")):
        node = self.node(class_name)
        self.link(a, node, names[0])
        self.link(b, node, names[1])
        return node

    def unary(self, class_name, value, **properties):
        node = self.node(class_name, **properties)
        self.link(value, node, "")
        return node

    def mul(self, a, b):
        return self.binary("MaterialExpressionMultiply", a, b)

    def add(self, a, b):
        return self.binary("MaterialExpressionAdd", a, b)

    def sub(self, a, b):
        return self.binary("MaterialExpressionSubtract", a, b)

    def div(self, a, b):
        return self.binary("MaterialExpressionDivide", a, b)

    def max(self, a, b):
        return self.binary("MaterialExpressionMax", a, b)

    def dot(self, a, b):
        return self.binary("MaterialExpressionDotProduct", a, b)

    def append(self, a, b):
        return self.binary("MaterialExpressionAppendVector", a, b)

    def lerp(self, a, b, alpha):
        node = self.node("MaterialExpressionLinearInterpolate")
        self.link(a, node, "A")
        self.link(b, node, "B")
        self.link(alpha, node, "Alpha")
        return node

    def sat(self, value):
        return self.unary("MaterialExpressionSaturate", value)

    def one_minus(self, value):
        return self.unary("MaterialExpressionOneMinus", value)

    def abs(self, value):
        return self.unary("MaterialExpressionAbs", value)

    def sqrt(self, value):
        return self.unary("MaterialExpressionSquareRoot", value)

    def sine(self, value, period=1.0):
        return self.unary("MaterialExpressionSine", value, period=float(period))

    def mask(self, value, channels):
        return self.unary("MaterialExpressionComponentMask", value,
                          r="r" in channels, g="g" in channels, b="b" in channels, a="a" in channels)

    # -- parameters --

    def _named(self, class_name, name, group, **properties):
        node = self.node(class_name, parameter_name=name, group=group, **properties)
        try:
            actual = str(node.get_editor_property("parameter_name"))
        except Exception:
            actual = name
        if actual != name:
            self.fail("parameter '%s' was renamed to '%s' by the editor" % (name, actual))
        return node

    def scalar(self, name, default, group="Look"):
        return self._named("MaterialExpressionScalarParameter", name, group, default_value=float(default))

    def vector(self, name, rgba, group="Look"):
        return self._named("MaterialExpressionVectorParameter", name, group,
                           default_value=unreal.LinearColor(*[float(c) for c in rgba]))

    def texture(self, name, texture, uv=None, group="Textures"):
        node = self._named("MaterialExpressionTextureSampleParameter2D", name, group)
        if texture is None:
            self.fail("no texture for parameter %s" % name)
        else:
            # Setting the texture also picks the matching sampler type (colour / linear / masks / normal).
            ok, detail = _try_set(node, "texture", texture)
            if not ok:
                self.fail("cannot set texture of %s (%s)" % (name, detail))
        if uv is not None:
            self.link(uv, node, ("UVs", "Coordinates"))
        return node

    def collection(self, mpc, name, fallback):
        """A MPC_IronSeason parameter (falls back to a constant when the collection could not be built)."""
        if mpc is None:
            return self.source(fallback)[0]
        if name not in self._collections:
            self._collections[name] = self.node("MaterialExpressionCollectionParameter", collection=mpc,
                                                parameter_name=name)
        return self._collections[name]


def _begin_material(name, properties):
    material = _create_or_load(name, MATERIALS_DIR, unreal.Material, unreal.MaterialFactoryNew)
    if material is None:
        raise _BuildError("cannot create %s/%s" % (MATERIALS_DIR, name))
    unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
    for key, value in properties.items():
        _set(material, key, value, name)
    return material, _Graph(material)


def _end_material(graph):
    material = graph.material
    try:
        unreal.MaterialEditingLibrary.layout_material_expressions(material)
    except Exception:
        pass
    unreal.MaterialEditingLibrary.recompile_material(material)
    _save(material)
    _record(_package_of(material.get_path_name()))
    if graph.failures:
        _error("%s: %d graph problem(s), see the warnings above; it may render incorrectly"
               % (graph.name, graph.failures))
    else:
        _log("built %s (%d expressions)" % (graph.name, graph._count))
    return material


def _surface_properties(blend="BLEND_OPAQUE", shading="MSM_DEFAULT_LIT", two_sided=False, nanite=False,
                        instanced=False):
    properties = {
        "material_domain": _enum("MaterialDomain", "MD_SURFACE"),
        "blend_mode": _enum("BlendMode", blend),
        "shading_model": _enum("MaterialShadingModel", shading),
        "two_sided": two_sided,
    }
    if nanite:
        properties["used_with_nanite"] = True
    if instanced:
        # Usage flags cannot be added in a cooked game: without them the mesh renders with the default material.
        properties["used_with_instanced_static_meshes"] = True
    return properties


def _material_instance(name, directory, parent, scalars=None, vectors=None, textures=None):
    """Creates or refreshes a MaterialInstanceConstant with exactly the given parameter overrides."""
    if parent is None:
        _error("%s/%s: no parent material" % (directory, name))
        return None

    def factory():
        made = unreal.MaterialInstanceConstantFactoryNew()
        _try_set(made, "initial_parent", parent)
        return made

    instance = _create_or_load(name, directory, unreal.MaterialInstanceConstant, factory)
    if instance is None:
        return None
    library = unreal.MaterialEditingLibrary
    library.set_material_instance_parent(instance, parent)
    library.clear_all_material_instance_parameters(instance)
    for key, value in (scalars or {}).items():
        if not library.set_material_instance_scalar_parameter_value(instance, key, float(value)):
            _warn("%s: no scalar parameter %s" % (name, key))
    for key, value in (vectors or {}).items():
        rgba = list(value) + [1.0] * (4 - len(value))
        if not library.set_material_instance_vector_parameter_value(instance, key, unreal.LinearColor(*rgba)):
            _warn("%s: no vector parameter %s" % (name, key))
    for key, value in (textures or {}).items():
        if value is not None and not library.set_material_instance_texture_parameter_value(instance, key, value):
            _warn("%s: no texture parameter %s" % (name, key))
    library.update_material_instance(instance)
    _save(instance)
    _record(directory + "/" + name)
    return instance


def _build_season_collection(ctx):
    """MPC_IronSeason: Snow / Autumn / Wetness (0..1) and the shared snow and autumn colours.

    Model materials read it (roofs whiten in winter, trees turn golden in autumn); M_IronTerrain uses
    max(its own scalar, the collection) so the runtime can drive either.
    """
    mpc = _create_or_load(MPC_NAME, MATERIALS_DIR, unreal.MaterialParameterCollection,
                          unreal.MaterialParameterCollectionFactoryNew)
    if mpc is None:
        return None
    try:
        scalars = list(mpc.get_editor_property("scalar_parameters"))
        by_name = dict((str(p.get_editor_property("parameter_name")), p) for p in scalars)
        for name in ("Snow", "Autumn", "Wetness"):
            parameter = by_name.get(name)
            if parameter is None:
                parameter = unreal.CollectionScalarParameter()
                parameter.set_editor_property("parameter_name", name)
                scalars.append(parameter)
            parameter.set_editor_property("default_value", 0.0)
        mpc.set_editor_property("scalar_parameters", scalars)
        vectors = list(mpc.get_editor_property("vector_parameters"))
        by_name = dict((str(p.get_editor_property("parameter_name")), p) for p in vectors)
        for name, value in (("SnowColor", SNOW_COLOR), ("AutumnTint", AUTUMN_TINT)):
            parameter = by_name.get(name)
            if parameter is None:
                parameter = unreal.CollectionVectorParameter()
                parameter.set_editor_property("parameter_name", name)
                vectors.append(parameter)
            parameter.set_editor_property("default_value", unreal.LinearColor(*value))
        mpc.set_editor_property("vector_parameters", vectors)
    except Exception as exc:
        _error("%s: cannot set its parameters (%s); season effects on models are disabled" % (MPC_NAME, exc))
        return None
    _save(mpc)
    _record(MATERIALS_DIR + "/" + MPC_NAME)
    return mpc


def _build_terrain_material(ctx):
    material, g = _begin_material("M_IronTerrain", _surface_properties())
    world = g.node("MaterialExpressionWorldPosition")
    # Map UV from world position (DESIGN.md 12.2: UV = map x / 2400 m, map y / 1500 m), independent of mesh UVs.
    origin = g.mask(g.vector("MapOrigin", (0.0, 0.0, 0.0, 0.0), "Map"), "rg")
    size = g.mask(g.vector("MapSize", (MAP_WIDTH_CM, MAP_HEIGHT_CM, 0.0, 0.0), "Map"), "rg")
    uv = g.div(g.sub(g.mask(world, "rg"), origin), size)
    albedo_node = g.texture("Albedo", ctx.texture("T_Terrain_Albedo"), uv)
    masks_node = g.texture("Masks", ctx.texture("T_Terrain_Masks", "T_IronWhiteLinear"), uv)
    water = (masks_node, "R")
    forest = (masks_node, "G")
    rock = (masks_node, "B")
    road = (masks_node, "A")
    land = g.one_minus(water)
    snow = g.max(g.scalar("Snow", 0.0, "Season"), g.collection(ctx.mpc, "Snow", 0.0))
    autumn = g.max(g.scalar("Autumn", 0.0, "Season"), g.collection(ctx.mpc, "Autumn", 0.0))
    wet = g.max(g.scalar("Wetness", 0.0, "Season"), g.collection(ctx.mpc, "Wetness", 0.0))

    # Micro variation: world-space noise breaks up the 2 px/m texel grid when the camera is close.
    noise = g.node("MaterialExpressionNoise", scale=0.002, levels=2, output_min=-1.0, output_max=1.0,
                   turbulence=False)
    g.link(world, noise, "Position")
    base = g.mul((albedo_node, "RGB"), g.add(1.0, g.mul(noise, g.scalar("DetailStrength", 0.06))))

    # Autumn: green-dominant ground and forest floor turn golden (not roads, rock or water).
    green = g.mask(base, "g")
    greenness = g.sat(g.mul(g.div(g.sub(green, g.max(g.mask(base, "r"), g.mask(base, "b"))), g.add(green, 0.02)),
                            2.5))
    vegetation = g.mul(g.sat(g.add(greenness, g.mul(forest, 0.6))),
                       g.mul(g.mul(land, g.one_minus(road)), g.one_minus(g.mul(rock, 0.8))))
    autumn_color = g.mul(g.dot(base, LUMA), g.mask(g.collection(ctx.mpc, "AutumnTint", AUTUMN_TINT), "rgb"))
    base = g.lerp(base, autumn_color, g.sat(g.mul(g.mul(autumn, vegetation), 0.9)))

    # Wetness darkens the ground (roads most) and makes it glossier.
    wet_ground = g.mul(g.mul(wet, land), g.add(0.7, g.mul(road, 0.3)))
    base = g.mul(base, g.one_minus(g.mul(wet_ground, 0.35)))

    # Rivers and lakes painted in the albedo read a little deeper.
    base = g.lerp(base, g.mul(base, g.scalar("WaterDarken", 0.8, "Water")), water)

    # Snow settles on flat ground, more on high rock, less under forest; never on water.
    up = g.sat(g.mul(g.sub(g.mask(g.node("MaterialExpressionVertexNormalWS"), "b"), 0.55), 4.0))
    cover = g.sat(g.sub(g.mul(g.mul(snow, g.add(0.6, g.mul(rock, 0.8))), g.mul(up, 1.4)), g.mul(forest, 0.2)))
    snow_mask = g.mul(cover, land)
    base = g.lerp(base, g.mask(g.collection(ctx.mpc, "SnowColor", SNOW_COLOR), "rgb"), snow_mask)

    rough = g.lerp(g.scalar("Roughness", 0.85), g.scalar("RockRoughness", 0.75), rock)
    rough = g.lerp(rough, g.scalar("WetRoughness", 0.45, "Season"), wet_ground)
    rough = g.lerp(rough, g.scalar("SnowRoughness", 0.6, "Season"), snow_mask)
    rough = g.lerp(rough, g.scalar("WaterRoughness", 0.08, "Water"), water)
    specular = g.lerp(0.5, g.scalar("WaterSpecular", 0.6, "Water"), water)

    g.output(base, "MP_BASE_COLOR")
    g.output(rough, "MP_ROUGHNESS")
    g.output(specular, "MP_SPECULAR")
    return _end_material(g)


def _build_water_material(ctx):
    single_layer = (WATER_SHADING == "single_layer_water"
                    and _enum("MaterialShadingModel", "MSM_SINGLE_LAYER_WATER") is not None
                    and hasattr(unreal, "MaterialExpressionSingleLayerWaterMaterialOutput"))
    if WATER_SHADING == "single_layer_water" and not single_layer:
        _warn("M_IronWater: Single Layer Water is not available; using default lit opaque water")
    material, g = _begin_material("M_IronWater", _surface_properties(
        shading="MSM_SINGLE_LAYER_WATER" if single_layer else "MSM_DEFAULT_LIT"))
    normal_texture = ctx.texture("T_Water_Normal", "T_IronFlatNormal")
    xy = g.mask(g.node("MaterialExpressionWorldPosition"), "rg")
    # Two panning scales of the same normal map break up tiling on the large plane.
    pan_a = g.node("MaterialExpressionPanner", speed_x=0.012, speed_y=0.007)
    g.link(g.div(xy, g.scalar("NormalScaleA", 3200.0, "Waves")), pan_a, "Coordinate")
    pan_b = g.node("MaterialExpressionPanner", speed_x=-0.009, speed_y=0.013)
    g.link(g.div(xy, g.scalar("NormalScaleB", 1100.0, "Waves")), pan_b, "Coordinate")
    normal_a = (g.texture("NormalA", normal_texture, pan_a), "RGB")
    normal_b = (g.texture("NormalB", normal_texture, pan_b), "RGB")
    combined = g.append(g.add(g.mask(normal_a, "rg"), g.mask(normal_b, "rg")),
                        g.mul(g.mask(normal_a, "b"), g.mask(normal_b, "b")))
    # Waves flatten with distance so the far sea does not shimmer.
    fade = g.sat(g.div(g.node("MaterialExpressionPixelDepth"), g.scalar("NormalFadeDistance", 250000.0, "Waves")))
    strength = g.mul(g.scalar("NormalStrength", 0.4, "Waves"), g.one_minus(g.mul(fade, 0.7)))
    g.output(g.lerp((0.0, 0.0, 1.0), combined, strength), "MP_NORMAL")
    g.output(g.mask(g.vector("WaterColor", WATER_COLOR), "rgb"), "MP_BASE_COLOR")
    g.output(g.scalar("Roughness", 0.05), "MP_ROUGHNESS")
    g.output(g.scalar("Specular", 0.6), "MP_SPECULAR")
    g.output(0.0, "MP_METALLIC")
    if single_layer:
        # Opacity = coverage of a surface layer (foam) over the water volume: 0 shows the depth-tinted water.
        g.output(g.scalar("SurfaceCoverage", 0.0), "MP_OPACITY")
        water_out = g.node("MaterialExpressionSingleLayerWaterMaterialOutput")
        g.link(g.mask(g.vector("Scattering", WATER_SCATTERING, "Depth"), "rgb"), water_out,
               ("ScatteringCoefficients", "Scattering Coefficients"))
        # DepthFade scales the absorption: 0 = clear water, 1 = default, higher = murkier, darker deep sea.
        g.link(g.mul(g.mask(g.vector("Absorption", WATER_ABSORPTION, "Depth"), "rgb"),
                     g.scalar("DepthFade", 1.0, "Depth")), water_out,
               ("AbsorptionCoefficients", "Absorption Coefficients"))
        g.link(g.scalar("PhaseG", 0.1, "Depth"), water_out, ("PhaseG", "Phase G"))
        g.link(g.scalar("ColorScaleBehindWater", 0.9, "Depth"), water_out,
               ("ColorScaleBehindWater", "Color Scale Behind Water"))
    ctx.water_shading = "single_layer_water" if single_layer else "default_lit"
    return _end_material(g)


def _instance_color(g):
    """Per-instance RGB custom data 0..2 (ISM/HISM armies) as one float3."""
    if hasattr(unreal, "MaterialExpressionPerInstanceCustomData3Vector"):
        return g.node("MaterialExpressionPerInstanceCustomData3Vector", data_index=0)
    channels = [g.node("MaterialExpressionPerInstanceCustomData", data_index=i) for i in range(3)]
    return g.append(g.append(channels[0], channels[1]), channels[2])


def _build_tint_material(ctx):
    material, g = _begin_material("M_IronTint", _surface_properties(two_sided=True, nanite=True, instanced=True))
    tint = g.mask(g.vector("Tint", (1.0, 1.0, 1.0, 1.0), "Tint"), "rgb")
    color = g.lerp(tint, _instance_color(g), g.scalar("UseInstanceColor", 0.0, "Tint"))
    base = g.texture("BaseTex", ctx.texture("T_IronWhite"))
    g.output(g.mul((base, "RGB"), color), "MP_BASE_COLOR")
    g.output(g.scalar("Roughness", 0.6), "MP_ROUGHNESS")
    g.output(g.scalar("Metallic", 0.0), "MP_METALLIC")
    return _end_material(g)


def _build_highlight_material(ctx):
    properties = _surface_properties(blend="BLEND_TRANSLUCENT", shading="MSM_UNLIT", two_sided=True, instanced=True)
    material, g = _begin_material("M_IronHighlight", properties)
    color_node = g.vector("Color", HIGHLIGHT_COLOR, "Highlight")
    hex_shape = g.scalar("HexShape", 0.0, "Shape")
    # p in [-1, 1]; for hexes the quad spans the hex bounding box (8 m x 6.93 m), so y is scaled by sqrt(3)/2.
    p = g.mul(g.sub(g.node("MaterialExpressionTextureCoordinate", coordinate_index=0), (0.5, 0.5)), 2.0)
    px = g.abs(g.mask(p, "r"))
    py = g.mul(g.abs(g.mask(p, "g")), g.lerp(1.0, 0.8660254, hex_shape))
    circle = g.sqrt(g.add(g.mul(px, px), g.mul(py, py)))
    hexagon = g.max(g.mul(py, 1.1547005), g.add(px, g.mul(py, 0.5773503)))
    distance = g.lerp(circle, hexagon, hex_shape)
    ring = g.sat(g.sub(1.0, g.div(g.abs(g.sub(distance, g.scalar("RingRadius", 0.82, "Shape"))),
                                  g.scalar("RingWidth", 0.1, "Shape"))))
    inside = g.sat(g.mul(g.sub(1.0, distance), 25.0))
    pulse_min = g.scalar("PulseMin", 0.65, "Pulse")
    wave = g.mul(g.add(g.sine(g.mul(g.node("MaterialExpressionTime"), g.scalar("PulseSpeed", 1.2, "Pulse"))), 1.0),
                 0.5)
    pulse = g.add(pulse_min, g.mul(g.one_minus(pulse_min), wave))
    coverage = g.mul(g.add(ring, g.mul(inside, g.scalar("FillOpacity", 0.18, "Shape"))), pulse)
    g.output(g.mul(g.mul(g.mask(color_node, "rgb"), g.scalar("Intensity", 4.0, "Highlight")), coverage),
             "MP_EMISSIVE_COLOR")
    g.output(g.sat(g.mul(coverage, (color_node, "A"))), "MP_OPACITY")
    return _end_material(g)


def _build_ink_material(ctx):
    location = _enum("BlendableLocation", "BL_SCENE_COLOR_BEFORE_DOF", "BL_BEFORE_TRANSLUCENCY",
                     "BL_BEFORE_TONEMAPPING")
    material, g = _begin_material("M_IronInk", {
        "material_domain": _enum("MaterialDomain", "MD_POST_PROCESS"),
        # Before DOF: the tilt-shift blur softens far lines and TSR anti-aliases them.
        "blendable_location": location,
    })
    ids = {
        "depth": _enum("SceneTextureId", "PPI_SCENE_DEPTH"),
        "normal": _enum("SceneTextureId", "PPI_WORLD_NORMAL"),
        "color": _enum("SceneTextureId", "PPI_POST_PROCESS_INPUT0"),
    }
    uv = (g.node("MaterialExpressionScreenPosition"), "ViewportUV")
    view = g.node("MaterialExpressionViewSize")
    pixels = g.mul(g.scalar("Thickness", 1.0, "Lines"), g.max(1.0, g.div(g.mask(view, "g"), 1080.0)))
    texel = g.div(pixels, view)

    def sample(texture_id, offset):
        node = g.node("MaterialExpressionSceneTexture", scene_texture_id=texture_id, filtered=False)
        if offset is not None:
            g.link(g.add(uv, g.mul(texel, offset)), node, ("UVs", "Coordinates"))
        return (node, "Color")

    offsets = ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0))
    depth_center = g.mask(sample(ids["depth"], None), "r")
    depths = [g.mask(sample(ids["depth"], o), "r") for o in offsets]
    twice = g.mul(depth_center, 2.0)
    laplacian = g.add(g.abs(g.sub(g.add(depths[0], depths[1]), twice)),
                      g.abs(g.sub(g.add(depths[2], depths[3]), twice)))
    depth_edge = g.mul(g.div(laplacian, g.max(depth_center, 1.0)), g.scalar("DepthSensitivity", 80.0, "Lines"))
    normal_center = g.mask(sample(ids["normal"], None), "rgb")
    agreement = None
    for offset in offsets:
        term = g.dot(normal_center, g.mask(sample(ids["normal"], offset), "rgb"))
        agreement = term if agreement is None else g.add(agreement, term)
    normal_edge = g.mul(g.sub(4.0, agreement), g.scalar("NormalSensitivity", 1.2, "Lines"))
    edge = g.sat(g.mul(g.sub(g.max(depth_edge, normal_edge), g.scalar("Threshold", 0.18, "Lines")),
                       g.scalar("Sharpness", 2.5, "Lines")))
    # Lines fade out with distance (and vanish on the sky).
    distance_fade = g.one_minus(g.sat(g.div(g.sub(depth_center, g.scalar("FadeStart", 300000.0, "Lines")),
                                            g.scalar("FadeRange", 900000.0, "Lines"))))
    ink = g.mul(g.mul(edge, distance_fade), g.scalar("Strength", 0.6, "Lines"))
    scene = g.mask(sample(ids["color"], None), "rgb")
    inked = g.mul(scene, g.lerp((1.0, 1.0, 1.0), g.mask(g.vector("InkTone", INK_TONE, "Lines"), "rgb"), ink))
    # Paper grain: static screen-space noise, about two pixels per grain.
    grain_noise = g.node("MaterialExpressionNoise", scale=1.0, levels=1, output_min=-1.0, output_max=1.0,
                         turbulence=False)
    g.link(g.append(g.div(g.mul(uv, view), g.scalar("GrainSize", 2.0, "Paper")), 0.0), grain_noise, "Position")
    grain = g.add(1.0, g.mul(grain_noise, g.scalar("GrainStrength", 0.035, "Paper")))
    g.output(g.mul(inked, grain), "MP_EMISSIVE_COLOR")
    return _end_material(g)


def _build_model_master(ctx, name, masked, two_sided):
    """glTF metallic-roughness master for imported models (+ MPC_IronSeason snow/autumn/wetness)."""
    properties = _surface_properties(blend="BLEND_MASKED" if masked else "BLEND_OPAQUE", two_sided=two_sided,
                                     nanite=True, instanced=True)
    if masked:
        properties["opacity_mask_clip_value"] = 0.5
    material, g = _begin_material(name, properties)
    base_node = g.texture("BaseColorTex", ctx.texture("T_IronWhite"))
    base_factor = g.vector("BaseColorFactor", (1.0, 1.0, 1.0, 1.0), "Factors")
    metal_rough = g.texture("MetalRoughTex", ctx.texture("T_IronWhiteLinear"))
    occlusion = g.texture("OcclusionTex", ctx.texture("T_IronWhiteLinear"))
    normal = g.texture("NormalTex", ctx.texture("T_IronFlatNormal"))
    emissive = g.texture("EmissiveTex", ctx.texture("T_IronWhite"))

    albedo = g.mul((base_node, "RGB"), g.mask(base_factor, "rgb"))
    rough = g.max(g.mul((metal_rough, "G"), g.scalar("RoughnessFactor", 1.0, "Factors")), 0.04)
    metallic = g.mul((metal_rough, "B"), g.scalar("MetallicFactor", 1.0, "Factors"))
    ambient = g.lerp(1.0, (occlusion, "R"), g.scalar("OcclusionStrength", 1.0, "Factors"))
    bumped = g.lerp((0.0, 0.0, 1.0), (normal, "RGB"), g.scalar("NormalStrength", 1.0, "Factors"))
    glow = g.mul((emissive, "RGB"), g.mask(g.vector("EmissiveFactor", (0.0, 0.0, 0.0, 1.0), "Factors"), "rgb"))

    # Seasons from MPC_IronSeason, scaled per model (trees and hexes take autumn, units little snow...).
    green = g.mask(albedo, "g")
    greenness = g.sat(g.mul(g.div(g.sub(green, g.max(g.mask(albedo, "r"), g.mask(albedo, "b"))),
                                  g.add(green, 0.02)), 3.0))
    autumn = g.mul(g.collection(ctx.mpc, "Autumn", 0.0), g.scalar("AutumnAffect", 1.0, "Season"))
    autumn_color = g.mul(g.dot(albedo, LUMA), g.mask(g.collection(ctx.mpc, "AutumnTint", AUTUMN_TINT), "rgb"))
    albedo = g.lerp(albedo, autumn_color, g.sat(g.mul(autumn, greenness)))
    wet = g.mul(g.collection(ctx.mpc, "Wetness", 0.0), g.scalar("WetAffect", 1.0, "Season"))
    albedo = g.mul(albedo, g.one_minus(g.mul(wet, 0.3)))
    rough = g.lerp(rough, g.mul(rough, 0.5), wet)
    up = g.sat(g.mul(g.sub(g.mask(g.node("MaterialExpressionVertexNormalWS"), "b"), 0.45), 3.0))
    snow = g.mul(g.collection(ctx.mpc, "Snow", 0.0), g.scalar("SnowAffect", 1.0, "Season"))
    snow_mask = g.sat(g.mul(g.sub(g.mul(up, g.mul(snow, 1.4)), 0.25), 2.5))
    albedo = g.lerp(albedo, g.mask(g.collection(ctx.mpc, "SnowColor", SNOW_COLOR), "rgb"), snow_mask)
    rough = g.lerp(rough, 0.65, snow_mask)

    g.output(albedo, "MP_BASE_COLOR")
    g.output(metallic, "MP_METALLIC")
    g.output(rough, "MP_ROUGHNESS")
    g.output(ambient, "MP_AMBIENT_OCCLUSION")
    g.output(bumped, "MP_NORMAL")
    g.output(glow, "MP_EMISSIVE_COLOR")
    if masked:
        # glTF alphaCutoff per instance: clip at 0.5 of (alpha - AlphaCutoff + 0.5).
        alpha = g.mul((base_node, "A"), (base_factor, "A"))
        g.output(g.add(g.sub(alpha, g.scalar("AlphaCutoff", 0.5, "Factors")), 0.5), "MP_OPACITY_MASK")
    return _end_material(g)


def _build_materials(ctx):
    ctx.mpc = _build_season_collection(ctx)
    builders = (
        ("terrain", _build_terrain_material),
        ("water", _build_water_material),
        ("tint", _build_tint_material),
        ("highlight", _build_highlight_material),
        ("ink", _build_ink_material),
        ("model", lambda c: _build_model_master(c, "M_IronModel", False, False)),
        ("model_two_sided", lambda c: _build_model_master(c, "M_IronModelTwoSided", False, True)),
        ("model_masked", lambda c: _build_model_master(c, "M_IronModelMasked", True, True)),
    )
    for key, builder in builders:
        try:
            ctx.materials[key] = builder(ctx)
        except _BuildError as exc:
            _error(str(exc))
        except Exception as exc:
            _error("building the %s material failed: %s\n%s" % (key, exc, traceback.format_exc()))
    _material_instance("MI_IronTerrain", MATERIALS_DIR, ctx.materials.get("terrain"),
                       textures={"Albedo": ctx.textures.get("T_Terrain_Albedo"),
                                 "Masks": ctx.textures.get("T_Terrain_Masks")})
    water_normal = ctx.textures.get("T_Water_Normal")
    _material_instance("MI_IronWater", MATERIALS_DIR, ctx.materials.get("water"),
                       textures={"NormalA": water_normal, "NormalB": water_normal})
    _material_instance("MI_IronTintInstanced", MATERIALS_DIR, ctx.materials.get("tint"),
                       scalars={"UseInstanceColor": 1.0})
    _material_instance("MI_IronHighlightHex", MATERIALS_DIR, ctx.materials.get("highlight"),
                       scalars={"HexShape": 1.0})


# ----- models ---------------------------------------------------------------------------------------------------

def _model_profile(name):
    """Per-model season response (MPC_IronSeason) of the model materials."""
    if name.startswith("Tree_") or name.startswith("Hex_"):
        return {"AutumnAffect": 1.0, "SnowAffect": 1.0, "WetAffect": 1.0}
    if name.startswith("Unit_"):
        return {"AutumnAffect": 0.0, "SnowAffect": 0.35, "WetAffect": 0.5}
    return {"AutumnAffect": 0.0, "SnowAffect": 1.0, "WetAffect": 1.0}


def _model_textures(name, asset, data_dir, ctx):
    """Extracts the images of a .glb and imports them per use: {(image index, kind): Texture2D}."""
    result = {}
    staging = os.path.join(ctx.paths["staging"], "Models", name)
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    used = set()
    kinds_by_image = asset.texture_kinds_by_image()
    for image in sorted(kinds_by_image):
        try:
            data, extension = asset.image_bytes(image)
        except gltf.GltfError as exc:
            _warn("%s.glb: %s" % (name, exc))
            continue
        base = _safe_name(asset.image_name(image), "Image%d" % image)
        if base.lower().startswith(name.lower() + "_") and len(base) > len(name) + 1:
            base = base[len(name) + 1:]
        kinds = sorted(kinds_by_image[image])
        for kind in kinds:
            suffix = "" if len(kinds) == 1 else "_" + kind.capitalize()
            asset_name = _unique("T_%s_%s%s" % (name, base, suffix), used)
            path = os.path.join(staging, asset_name + extension)
            with open(path, "wb") as handle:
                handle.write(data)
            texture = _import_texture(path, data_dir, asset_name, kind, flip_green=ctx.flip_green)
            if texture is not None:
                result[(image, kind)] = texture
    return result


def _model_materials(name, asset, textures, data_dir, ctx):
    """Material instances of a model: ({normalized glTF material name: material}, [created package paths])."""
    result = {}
    produced = []
    used = set()
    profile = _model_profile(name)

    def texture_for(texture_index, kind):
        if texture_index is None:
            return None
        return textures.get((asset.texture_image(texture_index), kind))

    for info in asset.materials:
        key = _norm(info.name)
        instance_name = _unique("MI_%s_%s" % (name, _safe_name(info.name, "Material%d" % info.index)), used)
        if key.startswith("tint"):
            base = texture_for(info.base_color_texture, gltf.KIND_COLOR)
            tint = ctx.materials.get("tint")
            if base is None or tint is None:
                result[key] = tint
                continue
            instance = _material_instance(instance_name, data_dir, tint, textures={"BaseTex": base})
            result[key] = instance or tint
            if instance is not None:
                produced.append(data_dir + "/" + instance_name)
            continue
        if info.alpha_mode in ("MASK", "BLEND"):
            if info.alpha_mode == "BLEND":
                _warn("%s.glb material '%s' uses alpha BLEND; imported as alpha-tested (Nanite has no translucency)"
                      % (name, info.name))
            parent = ctx.materials.get("model_masked")
        elif info.double_sided:
            parent = ctx.materials.get("model_two_sided")
        else:
            parent = ctx.materials.get("model")
        if parent is None:
            continue
        scalars = dict(profile)
        scalars.update({
            "RoughnessFactor": info.roughness_factor,
            "MetallicFactor": info.metallic_factor,
            "NormalStrength": info.normal_scale if info.normal_texture is not None else 1.0,
            "OcclusionStrength": info.occlusion_strength if info.occlusion_texture is not None else 0.0,
        })
        if info.alpha_mode in ("MASK", "BLEND"):
            scalars["AlphaCutoff"] = info.alpha_cutoff
        vectors = {"BaseColorFactor": info.base_color_factor, "EmissiveFactor": info.emissive_factor}
        texture_values = {
            "BaseColorTex": texture_for(info.base_color_texture, gltf.KIND_COLOR),
            "MetalRoughTex": texture_for(info.metal_rough_texture, gltf.KIND_MASKS),
            "OcclusionTex": texture_for(info.occlusion_texture, gltf.KIND_MASKS),
            "NormalTex": texture_for(info.normal_texture, gltf.KIND_NORMAL),
            "EmissiveTex": texture_for(info.emissive_texture, gltf.KIND_COLOR),
        }
        texture_values = dict((k, v) for k, v in texture_values.items() if v is not None)
        instance = _material_instance(instance_name, data_dir, parent, scalars, vectors, texture_values)
        if instance is not None:
            result[key] = instance
            produced.append(data_dir + "/" + instance_name)
    return result, produced


def _assign_slots(name, mesh, slot_map, ctx):
    try:
        slots = list(mesh.get_editor_property("static_materials"))
    except Exception as exc:
        _error("SM_%s: cannot read material slots (%s)" % (name, exc))
        return
    assigned = 0
    for index, slot in enumerate(slots):
        names = []
        for prop in ("material_slot_name", "imported_material_slot_name"):
            try:
                names.append(str(slot.get_editor_property(prop)))
            except Exception:
                pass
        try:
            current = slot.get_editor_property("material_interface")
        except Exception:
            current = None
        if current is not None:
            names.append(re.sub(r"^(MI|M|MAT)_", "", current.get_name()))
        keys = [_norm(n) for n in names if n and n != "None"]
        target = next((slot_map[k] for k in keys if slot_map.get(k) is not None), None)
        if target is None and any(k.startswith("tint") for k in keys):
            target = ctx.materials.get("tint")
        if target is None:
            _warn("SM_%s: material slot '%s' matches no glTF material; it keeps the imported material, which may "
                  "lack the Nanite/instancing usage flags in a cooked game" % (name, names[0] if names else index))
            continue
        try:
            mesh.set_material(index, target)
            assigned += 1
        except Exception as exc:
            _error("SM_%s: cannot assign %s to slot %d (%s)" % (name, target.get_name(), index, exc))
    _log("SM_%s: %d of %d material slot(s) assigned" % (name, assigned, len(slots)))


def _verify_scale(name, mesh, asset):
    """glTF is in metres and Unreal in centimetres: expect a 100x ratio, fix a 1x import with BuildScale3D."""
    bounds = asset.bounds()
    if bounds is None:
        return
    source_extent = max(bounds[1][axis] - bounds[0][axis] for axis in range(3))
    try:
        box = mesh.get_bounding_box()
        imported_extent = max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z)
    except Exception:
        return
    if source_extent <= 1e-6 or imported_extent <= 1e-6:
        return
    ratio = imported_extent / source_extent
    if 60.0 <= ratio <= 160.0:
        return
    if 0.6 <= ratio <= 1.6:
        subsystem = _static_mesh_subsystem()
        try:
            settings = subsystem.get_lod_build_settings(mesh, 0)
            settings.set_editor_property("build_scale3d", unreal.Vector(100.0, 100.0, 100.0))
            subsystem.set_lod_build_settings(mesh, 0, settings)
            _warn("SM_%s was imported in metres (ratio %.2f); applied a build scale of 100" % (name, ratio))
            return
        except Exception as exc:
            _error("SM_%s was imported in metres (ratio %.2f) and could not be rescaled: %s" % (name, ratio, exc))
            return
    _warn("SM_%s: imported size is %.1fx the glTF size (expected 100x: metres to centimetres)" % (name, ratio))


def _configure_mesh(name, mesh):
    subsystem = _static_mesh_subsystem()
    if STRIP_MODEL_COLLISION:
        try:
            if subsystem is not None:
                subsystem.remove_collisions(mesh)
        except Exception as exc:
            _log("SM_%s: remove_collisions failed (%s)" % (name, exc))
        try:
            body = mesh.get_editor_property("body_setup")
            flag = _enum("CollisionTraceFlag", "CTF_USE_SIMPLE_AS_COMPLEX")
            if body is not None and flag is not None:
                body.set_editor_property("collision_trace_flag", flag)
        except Exception as exc:
            _log("SM_%s: could not disable complex collision (%s)" % (name, exc))
    try:
        settings = mesh.get_editor_property("nanite_settings")
        settings.set_editor_property("enabled", True)
        if name.startswith("Tree_"):
            # Foliage keeps its silhouette area when Nanite simplifies it (property name differs by version).
            if not _try_set(settings, "preserve_area", True)[0]:
                _try_set(settings, "shape_preservation", _enum("NaniteShapePreservation", "PRESERVE_AREA"))
        applied = False
        if subsystem is not None and hasattr(subsystem, "set_nanite_settings"):
            try:
                subsystem.set_nanite_settings(mesh, settings, True)
                applied = True
            except Exception:
                applied = False
        if not applied:
            mesh.set_editor_property("nanite_settings", settings)
        if not mesh.get_editor_property("nanite_settings").get_editor_property("enabled"):
            _error("SM_%s: Nanite could not be enabled" % name)
    except Exception as exc:
        _error("SM_%s: cannot enable Nanite (%s)" % (name, exc))


def _largest_mesh(meshes):
    subsystem = _static_mesh_subsystem()

    def vertices(mesh):
        try:
            return subsystem.get_number_verts(mesh, 0)
        except Exception:
            return 0

    return max(meshes, key=vertices)


def _import_model(name, glb_path, ctx):
    final_path = MODELS_DIR + "/SM_" + name
    staging = STAGING_DIR + "/" + name
    data_dir = MODELS_DIR + "/" + name
    label = os.path.basename(glb_path)
    try:
        asset = gltf.GltfAsset(glb_path)
    except gltf.GltfError as exc:
        _error("%s: %s" % (label, exc))
        return False
    unsupported = asset.unsupported_extensions()
    if unsupported:
        _error("%s requires %s, which the Unreal glTF import cannot decode; export without compression"
               % (label, ", ".join(unsupported)))
        return False
    if asset.mesh_node_count() > 1:
        _warn("%s has %d mesh objects: join them into one object in Blender (only the largest imported mesh is used)"
              % (label, asset.mesh_node_count()))
    if any(m.uses_secondary_uv for m in asset.materials):
        _warn("%s: some textures use a second UV set; the model materials sample UV0 only" % label)

    if not _delete_asset(final_path):
        return False
    _cleanup_folder(staging)
    objects = _import_file(glb_path, staging)
    meshes = [o for o in objects if isinstance(o, unreal.StaticMesh)]
    if not meshes and unreal.EditorAssetLibrary.does_directory_exist(staging):
        for path in unreal.EditorAssetLibrary.list_assets(staging, True, False) or []:
            loaded = _load(_package_of(path))
            if isinstance(loaded, unreal.StaticMesh):
                meshes.append(loaded)
    if not meshes:
        _error("%s: the import produced no static mesh (is the glTF importer / Interchange enabled?)" % label)
        _cleanup_folder(staging)
        return False
    mesh = _largest_mesh(meshes) if len(meshes) > 1 else meshes[0]
    if not unreal.EditorAssetLibrary.rename_asset(_package_of(mesh.get_path_name()), final_path):
        _error("%s: could not move the imported mesh to %s" % (label, final_path))
        return False
    mesh = _load(final_path)
    if not isinstance(mesh, unreal.StaticMesh):
        _error("%s: %s is missing after the move" % (label, final_path))
        return False

    textures = _model_textures(name, asset, data_dir, ctx)
    slot_map, produced = _model_materials(name, asset, textures, data_dir, ctx)
    _assign_slots(name, mesh, slot_map, ctx)
    _verify_scale(name, mesh, asset)
    _configure_mesh(name, mesh)
    _save(mesh)
    _record(final_path)
    _cleanup_folder(staging)
    keep = list(produced) + [_package_of(t.get_path_name()) for t in textures.values()]
    _cleanup_folder(data_dir, keep=keep)
    triangles = asset.triangle_count()
    if triangles > 150000:
        _warn("%s has %d triangles (DESIGN.md 12.3 budget: 150k)" % (label, triangles))
    _log("imported %s -> %s (%d triangles, %d material(s), %d texture(s))"
         % (label, final_path, triangles, len(asset.materials), len(textures)))
    return True


# ----- engine content wrappers ----------------------------------------------------------------------------------

def _find_cloud_material():
    for path in CLOUD_PARENT_CANDIDATES:
        loaded = _load(path)
        if isinstance(loaded, unreal.MaterialInterface):
            return loaded
    try:
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        for data in registry.get_assets_by_path("/Engine/EngineSky", True) or []:
            if "volumetriccloud" in str(data.asset_name).lower():
                loaded = data.get_asset()
                if isinstance(loaded, unreal.MaterialInterface):
                    return loaded
    except Exception as exc:
        _log("asset registry search for a cloud material failed: %s" % exc)
    return None


def _build_engine_wrappers(ctx):
    """Game-side references to engine content the runtime uses, so cooking /Game/IronReign cooks it too."""
    parent = _find_cloud_material()
    if parent is None:
        _warn("no engine volumetric cloud material under /Engine/EngineSky: MI_IronClouds not created")
    else:
        _material_instance("MI_IronClouds", MATERIALS_DIR, parent)
        try:
            names = [str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(parent)]
            _report.notes["cloudParent"] = parent.get_path_name()
            _report.notes["cloudScalarParameters"] = names
            _log("MI_IronClouds parent %s, scalar parameters: %s" % (parent.get_path_name(), ", ".join(names)))
        except Exception:
            pass
    if not _exists(PLANE_PATH):
        try:
            if not unreal.EditorAssetLibrary.duplicate_asset(ENGINE_PLANE_PATH, PLANE_PATH):
                _warn("could not copy %s to %s" % (ENGINE_PLANE_PATH, PLANE_PATH))
        except Exception as exc:
            _warn("could not copy %s to %s: %s" % (ENGINE_PLANE_PATH, PLANE_PATH, exc))
    if _exists(PLANE_PATH):
        _record(PLANE_PATH)


# ----- version marker and build record --------------------------------------------------------------------------

def _marker_class():
    return getattr(unreal, MARKER_CLASS_NAME, None)


def _read_marker():
    """{"art_version", "pipeline_version"} from the content marker, or None."""
    marker_class = _marker_class()
    if marker_class is None or not _exists(MARKER_PATH):
        return None
    marker = _load(MARKER_PATH)
    if not isinstance(marker, marker_class):
        return None
    try:
        return {"art_version": int(marker.get_editor_property("art_version")),
                "pipeline_version": int(marker.get_editor_property("pipeline_version"))}
    except Exception:
        return None


def _write_marker(art_version):
    marker_class = _marker_class()
    if marker_class is None:
        _warn("C++ class UIronAssetManifest is not loaded (build the IronReign editor module): %s not written; "
              "the version is only kept in Saved/IronReign/asset_version.txt" % MARKER_PATH)
        return

    def factory():
        made = unreal.DataAssetFactory()
        if not _try_set(made, "data_asset_class", marker_class)[0]:
            try:
                _try_set(made, "data_asset_class", marker_class.static_class())
            except Exception:
                pass
        return made

    marker = _create_or_load(MARKER_NAME, ROOT_DIR, marker_class, factory)
    if marker is None:
        return
    _set(marker, "art_version", int(art_version))
    _set(marker, "pipeline_version", PIPELINE_VERSION)
    _set(marker, "built_at_utc", _utc_now())
    try:
        _set(marker, "engine_version", str(unreal.SystemLibrary.get_engine_version()))
    except Exception:
        pass
    _set(marker, "models", list(_report.models))
    _save(marker)
    _record(MARKER_PATH)


def _read_status(folders):
    try:
        with open(folders["status"], "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_status(folders, art_version, result, started):
    record = {
        "result": result,
        "ok": result == "OK",
        "artVersion": art_version,
        "pipelineVersion": PIPELINE_VERSION,
        "builtAtUtc": _utc_now(),
        "durationSeconds": round(time.time() - started, 1),
        "artSource": folders["art"],
        "errors": _report.errors,
        "warnings": _report.warnings,
        "models": _report.models,
        "assets": sorted(_report.assets),
        "notes": _report.notes,
    }
    try:
        record["engineVersion"] = str(unreal.SystemLibrary.get_engine_version())
    except Exception:
        pass
    try:
        os.makedirs(folders["saved"], exist_ok=True)
        with open(folders["status"], "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        _write_result(folders, result)
    except OSError as exc:
        unreal.log_warning(LOG_PREFIX + "cannot write %s: %s" % (folders["status"], exc))


def _write_result(folders, result):
    try:
        os.makedirs(folders["saved"], exist_ok=True)
        with open(folders["result"], "w", encoding="utf-8") as handle:
            handle.write(result + "\n")
    except OSError as exc:
        unreal.log_warning(LOG_PREFIX + "cannot write %s: %s" % (folders["result"], exc))


def expected_assets(folders=None):
    """Package paths a complete build must contain (used by the up-to-date check)."""
    folders = folders or paths()
    expected = [TEXTURES_DIR + "/" + name for name, _, _ in DEFAULT_TEXTURES]
    expected += [MATERIALS_DIR + "/" + name for name in EXPECTED_MATERIALS]
    art = folders["art"]
    for file_name, asset_name in (("Albedo.png", "T_Terrain_Albedo"), ("Masks.png", "T_Terrain_Masks")):
        if os.path.isfile(os.path.join(art, "Terrain", file_name)):
            expected.append(TEXTURES_DIR + "/" + asset_name)
    for source in _list_files(os.path.join(art, "Textures"), IMAGE_EXTENSIONS):
        expected.append(TEXTURES_DIR + "/T_" + _safe_name(os.path.splitext(os.path.basename(source))[0]))
    for source in _list_files(os.path.join(art, "Models"), (".glb", ".gltf")):
        expected.append(MODELS_DIR + "/SM_" + _safe_name(os.path.splitext(os.path.basename(source))[0]))
    return expected


def _check_up_to_date(folders, art_version):
    marker = _read_marker()
    if marker is None and _marker_class() is None:
        status = _read_status(folders)
        if status and status.get("ok"):
            marker = {"art_version": status.get("artVersion"), "pipeline_version": status.get("pipelineVersion")}
    if marker is None:
        return False, "no complete build recorded (%s)" % MARKER_PATH
    if marker["art_version"] != art_version:
        return False, "ArtSource version %s, assets built from version %s" % (art_version, marker["art_version"])
    if marker["pipeline_version"] != PIPELINE_VERSION:
        return False, "import pipeline version %s, assets built by version %s" % (PIPELINE_VERSION,
                                                                                  marker["pipeline_version"])
    missing = [p for p in expected_assets(folders) if not _exists(p)]
    if missing:
        return False, "%d asset(s) missing, e.g. %s" % (len(missing), missing[0])
    return True, "assets are up to date (ArtSource version %s)" % art_version


def needs_build():
    """(bool, reason): True when ArtSource exists and /Game/IronReign is missing or stale."""
    folders = paths()
    manifest = read_manifest(folders["art"], quiet=True)
    if manifest is None:
        return False, "no valid ArtSource/manifest.json at %s" % folders["art"]
    fresh, reason = _check_up_to_date(folders, manifest["version"])
    return (not fresh), reason


def should_auto_build():
    """needs_build(), except that a build which already failed for these inputs is not retried on every start."""
    needed, reason = needs_build()
    if not needed:
        return False, reason
    folders = paths()
    manifest = read_manifest(folders["art"], quiet=True) or {}
    last = _read_status(folders)
    if (last and not last.get("ok") and last.get("artVersion") == manifest.get("version")
            and last.get("pipelineVersion") == PIPELINE_VERSION):
        return False, ("the last import of ArtSource version %s failed (see %s); fix it and run "
                       "ironreign_import.build_all(force=True) or Tools/Unreal/build_assets.sh"
                       % (manifest.get("version"), folders["status"]))
    return True, reason


# ----- entry point ----------------------------------------------------------------------------------------------

def _run_steps(ctx, art_version):
    models = _list_files(os.path.join(ctx.paths["art"], "Models"), (".glb", ".gltf"))
    if not models:
        _warn("no models in %s" % os.path.join(ctx.paths["art"], "Models"))
    steps = 6 + len(models)
    with unreal.ScopedSlowTask(steps, "Building Iron Reign 3D assets") as progress:
        progress.make_dialog(True)

        def step(label):
            if progress.should_cancel():
                raise _BuildError("cancelled by the user")
            progress.enter_progress_frame(1, label)
            _log(label)

        step("Removing the old version marker")
        # Without a marker a half-finished build never looks complete (to the editor or to the game).
        if _exists(MARKER_PATH) and not _delete_asset(MARKER_PATH):
            _warn("could not remove the old marker %s" % MARKER_PATH)
        step("Importing textures")
        _build_default_textures(ctx)
        _build_art_textures(ctx)
        step("Building materials")
        _build_materials(ctx)
        for glb_path in models:
            name = _safe_name(os.path.splitext(os.path.basename(glb_path))[0])
            step("Importing model %s" % name)
            try:
                if _import_model(name, glb_path, ctx):
                    _report.models.append(name)
            except Exception as exc:
                _error("importing %s failed: %s\n%s" % (os.path.basename(glb_path), exc, traceback.format_exc()))
        step("Wrapping engine content")
        _build_engine_wrappers(ctx)
        step("Saving")
        _cleanup_folder(STAGING_DIR)
        try:
            unreal.EditorAssetLibrary.save_directory(ROOT_DIR, True, True)
        except Exception as exc:
            _warn("save_directory failed: %s" % exc)
        step("Writing the version marker")
        _report.notes["waterShading"] = ctx.water_shading
        if _report.errors:
            _warn("%d error(s): the version marker is not written, the next editor start will not retry this "
                  "version automatically" % len(_report.errors))
        else:
            _write_marker(art_version)


def build_all(force=False):
    """Builds /Game/IronReign from ArtSource. Returns True on success (or when already up to date)."""
    global _report
    _report = _Report()
    started = time.time()
    folders = paths()
    if not os.path.isdir(folders["art"]) or not os.path.isfile(os.path.join(folders["art"], "manifest.json")):
        _warn("no ArtSource at %s (ArtSource/manifest.json missing): 3D assets not built; the game keeps its 2D "
              "presentation" % folders["art"])
        _write_status(folders, None, "SKIPPED", started)
        return False
    manifest = read_manifest(folders["art"])
    if manifest is None:
        _write_status(folders, None, "FAILED", started)
        return False
    art_version = manifest["version"]
    if not force:
        fresh, reason = _check_up_to_date(folders, art_version)
        if fresh:
            _log(reason)
            _write_result(folders, "OK")
            return True
        _log("rebuilding: %s" % reason)
    _log("building /Game/IronReign from %s (version %d, pipeline %d%s)"
         % (folders["art"], art_version, PIPELINE_VERSION, ", forced" if force else ""))
    ctx = _Context(folders, manifest)
    try:
        _run_steps(ctx, art_version)
    except _BuildError as exc:
        _error(str(exc))
    except Exception as exc:
        _error("unexpected failure: %s\n%s" % (exc, traceback.format_exc()))
    result = "FAILED" if _report.errors else "OK"
    _write_status(folders, art_version, result, started)
    summary = "%s in %.0f s: %d model(s), %d asset(s), %d warning(s), %d error(s); record: %s" % (
        result, time.time() - started, len(_report.models), len(_report.assets), len(_report.warnings),
        len(_report.errors), folders["status"])
    if _report.errors:
        unreal.log_error(LOG_PREFIX + summary)
    else:
        _log(summary)
    return not _report.errors

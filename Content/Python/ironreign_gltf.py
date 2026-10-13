"""Minimal glTF 2.0 reader for the Iron Reign asset pipeline (DESIGN.md section 12).

Pure Python (standard library only, no ``unreal``) so it is shared by

* ``Content/Python/ironreign_import.py`` inside the Unreal editor (material and texture data of each model), and
* ``Tools/Unreal/check_art_source.py`` with the system ``python3`` (CI validation of ``ArtSource/``).

It reads ``.glb`` (and ``.gltf`` with external or data-URI buffers): materials, embedded images, mesh/triangle
counts and the world-space bounds of every mesh node. glTF axes are kept (metres, +Y up, front = +Z for a model
exported from Blender with "+Y up", whose front faces Blender -Y).
"""

import base64
import json
import math
import os
import struct

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
MODE_TRIANGLES = 4
MODE_TRIANGLE_STRIP = 5
MODE_TRIANGLE_FAN = 6

# Texture usage kinds: how the importer configures the Unreal texture.
KIND_COLOR = "color"     # sRGB, default compression (base colour, emissive)
KIND_MASKS = "masks"     # linear, TC_Masks (metallic/roughness, occlusion)
KIND_NORMAL = "normal"   # TC_Normalmap (green flipped for glTF/OpenGL convention)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_COLOR_TYPES = {0: "grey", 2: "rgb", 3: "palette", 4: "grey+alpha", 6: "rgba"}

# Extensions Unreal's glTF import cannot decode (geometry would be missing).
UNSUPPORTED_REQUIRED_EXTENSIONS = ("KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu",
                                   "EXT_texture_webp")


class GltfError(Exception):
    """Malformed or unsupported glTF data."""


def _number(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float(default)
    if math.isnan(value) or math.isinf(value):
        return float(default)
    return float(value)


def _vector(value, size, default):
    if not isinstance(value, list) or len(value) != size:
        return tuple(float(v) for v in default)
    return tuple(_number(v, d) for v, d in zip(value, default))


def _texture_ref(info):
    """(texture index, texCoord) of a glTF textureInfo, or (None, 0)."""
    if not isinstance(info, dict):
        return None, 0
    index = info.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        return None, 0
    tex_coord = info.get("texCoord", 0)
    if isinstance(tex_coord, bool) or not isinstance(tex_coord, int):
        tex_coord = 0
    return index, tex_coord


class MaterialInfo(object):
    """The PBR metallic-roughness parameters of one glTF material (spec defaults applied)."""

    def __init__(self, index, data):
        if not isinstance(data, dict):
            data = {}
        pbr = data.get("pbrMetallicRoughness")
        if not isinstance(pbr, dict):
            pbr = {}
        self.index = index
        name = data.get("name")
        self.name = name if isinstance(name, str) and name.strip() else "Material_%d" % index
        alpha_mode = data.get("alphaMode")
        self.alpha_mode = alpha_mode.upper() if isinstance(alpha_mode, str) else "OPAQUE"
        self.alpha_cutoff = _number(data.get("alphaCutoff"), 0.5)
        self.double_sided = data.get("doubleSided") is True
        self.base_color_factor = _vector(pbr.get("baseColorFactor"), 4, (1.0, 1.0, 1.0, 1.0))
        self.metallic_factor = _number(pbr.get("metallicFactor"), 1.0)
        self.roughness_factor = _number(pbr.get("roughnessFactor"), 1.0)
        self.base_color_texture, uv_base = _texture_ref(pbr.get("baseColorTexture"))
        self.metal_rough_texture, uv_mr = _texture_ref(pbr.get("metallicRoughnessTexture"))
        normal = data.get("normalTexture")
        self.normal_texture, uv_normal = _texture_ref(normal)
        self.normal_scale = _number(normal.get("scale"), 1.0) if isinstance(normal, dict) else 1.0
        occlusion = data.get("occlusionTexture")
        self.occlusion_texture, uv_occ = _texture_ref(occlusion)
        self.occlusion_strength = _number(occlusion.get("strength"), 1.0) if isinstance(occlusion, dict) else 1.0
        self.emissive_texture, uv_em = _texture_ref(data.get("emissiveTexture"))
        emissive = _vector(data.get("emissiveFactor"), 3, (0.0, 0.0, 0.0))
        extensions = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}
        strength_ext = extensions.get("KHR_materials_emissive_strength")
        strength = _number(strength_ext.get("emissiveStrength"), 1.0) if isinstance(strength_ext, dict) else 1.0
        self.emissive_factor = tuple(c * strength for c in emissive)
        self.extensions = sorted(extensions.keys())
        self.uses_secondary_uv = any(uv != 0 for uv in (uv_base, uv_mr, uv_normal, uv_occ, uv_em))

    def texture_uses(self):
        """[(texture index, kind, role)] for every texture this material samples."""
        uses = []
        for index, kind, role in ((self.base_color_texture, KIND_COLOR, "baseColor"),
                                  (self.metal_rough_texture, KIND_MASKS, "metallicRoughness"),
                                  (self.occlusion_texture, KIND_MASKS, "occlusion"),
                                  (self.normal_texture, KIND_NORMAL, "normal"),
                                  (self.emissive_texture, KIND_COLOR, "emissive")):
            if index is not None:
                uses.append((index, kind, role))
        return uses


def _parse_glb(data):
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise GltfError("not a binary glTF (.glb) file")
    version, length = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise GltfError("glTF container version %d (expected 2)" % version)
    if length > len(data):
        raise GltfError("truncated file (%d of %d bytes)" % (len(data), length))
    offset = 12
    document = None
    binary = None
    while offset + 8 <= length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        if offset + chunk_length > length:
            raise GltfError("truncated chunk")
        chunk = data[offset:offset + chunk_length]
        offset += chunk_length
        if chunk_type == CHUNK_JSON and document is None:
            try:
                document = json.loads(chunk.decode("utf-8").rstrip(" \t\r\n\x00"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise GltfError("invalid JSON chunk: %s" % exc)
        elif chunk_type == CHUNK_BIN and binary is None:
            binary = chunk
    if document is None:
        raise GltfError("no JSON chunk")
    return document, binary


def _identity():
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _multiply(a, b):
    """Column-major 4x4 product a * b."""
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
    return out


def _node_matrix(node):
    matrix = node.get("matrix")
    if isinstance(matrix, list) and len(matrix) == 16:
        return [_number(v, 0.0) for v in matrix]
    tx, ty, tz = _vector(node.get("translation"), 3, (0.0, 0.0, 0.0))
    qx, qy, qz, qw = _vector(node.get("rotation"), 4, (0.0, 0.0, 0.0, 1.0))
    sx, sy, sz = _vector(node.get("scale"), 3, (1.0, 1.0, 1.0))
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    rotation = [1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy),
                2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx),
                2 * (xz + wy), 2 * (yz - wx), 1 - 2 * (xx + yy)]
    return [rotation[0] * sx, rotation[1] * sx, rotation[2] * sx, 0.0,
            rotation[3] * sy, rotation[4] * sy, rotation[5] * sy, 0.0,
            rotation[6] * sz, rotation[7] * sz, rotation[8] * sz, 0.0,
            tx, ty, tz, 1.0]


def _transform_point(matrix, point):
    x, y, z = point
    return (matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
            matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
            matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14])


class GltfAsset(object):
    """A parsed .glb/.gltf file."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            raise GltfError("cannot read %s: %s" % (path, exc))
        if path.lower().endswith(".gltf"):
            try:
                self.json = json.loads(data.decode("utf-8-sig"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise GltfError("invalid JSON: %s" % exc)
            self.bin = None
        else:
            self.json, self.bin = _parse_glb(data)
        if not isinstance(self.json, dict):
            raise GltfError("top-level JSON is not an object")
        asset = self.json.get("asset")
        version = str(asset.get("version", "")) if isinstance(asset, dict) else ""
        if not version.startswith("2"):
            raise GltfError("asset.version is '%s' (expected 2.x)" % version)
        self.generator = str(asset.get("generator", "")) if isinstance(asset, dict) else ""
        self.materials = [MaterialInfo(i, m) for i, m in enumerate(self._list("materials"))]
        self._buffer_cache = {}

    # ----- generic access -------------------------------------------------------------------------------------

    def _list(self, key):
        value = self.json.get(key)
        return value if isinstance(value, list) else []

    def _item(self, key, index):
        items = self._list(key)
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
            return None
        item = items[index]
        return item if isinstance(item, dict) else None

    def required_extensions(self):
        return [e for e in self._list("extensionsRequired") if isinstance(e, str)]

    def unsupported_extensions(self):
        return [e for e in self.required_extensions() if e in UNSUPPORTED_REQUIRED_EXTENSIONS]

    def _buffer(self, index):
        if index in self._buffer_cache:
            return self._buffer_cache[index]
        buffer = self._item("buffers", index)
        if buffer is None:
            raise GltfError("buffer %s does not exist" % index)
        uri = buffer.get("uri")
        if uri is None:
            if index != 0 or self.bin is None:
                raise GltfError("buffer %d has no uri and no GLB binary chunk" % index)
            data = self.bin
        else:
            data = self._read_uri(uri)
        self._buffer_cache[index] = data
        return data

    def _read_uri(self, uri):
        if not isinstance(uri, str):
            raise GltfError("invalid uri")
        if uri.startswith("data:"):
            comma = uri.find(",")
            if comma < 0 or ";base64" not in uri[:comma]:
                raise GltfError("unsupported data uri")
            try:
                return base64.b64decode(uri[comma + 1:])
            except (ValueError, TypeError) as exc:
                raise GltfError("bad base64 data uri: %s" % exc)
        path = os.path.join(os.path.dirname(os.path.abspath(self.path)), uri.replace("%20", " "))
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError as exc:
            raise GltfError("cannot read external resource %s: %s" % (uri, exc))

    def _buffer_view_bytes(self, index):
        view = self._item("bufferViews", index)
        if view is None:
            raise GltfError("bufferView %s does not exist" % index)
        data = self._buffer(view.get("buffer", 0))
        start = view.get("byteOffset", 0)
        length = view.get("byteLength", 0)
        if not isinstance(start, int) or not isinstance(length, int) or start < 0 or start + length > len(data):
            raise GltfError("bufferView %d is out of range" % index)
        return data[start:start + length]

    # ----- textures and images --------------------------------------------------------------------------------

    def texture_image(self, texture_index):
        """Image index used by a texture, or None (e.g. only an unsupported extension source)."""
        texture = self._item("textures", texture_index)
        if texture is None:
            return None
        source = texture.get("source")
        if isinstance(source, bool) or not isinstance(source, int) or self._item("images", source) is None:
            return None
        return source

    def image_count(self):
        return len(self._list("images"))

    def image_name(self, image_index):
        image = self._item("images", image_index) or {}
        name = image.get("name")
        if isinstance(name, str) and name.strip():
            return name
        uri = image.get("uri")
        if isinstance(uri, str) and not uri.startswith("data:"):
            return os.path.splitext(os.path.basename(uri))[0]
        return "Image%d" % image_index

    def image_is_embedded(self, image_index):
        image = self._item("images", image_index) or {}
        uri = image.get("uri")
        return "bufferView" in image or (isinstance(uri, str) and uri.startswith("data:"))

    def image_bytes(self, image_index):
        """(bytes, extension) of an image; extension is '.png' or '.jpg'."""
        image = self._item("images", image_index)
        if image is None:
            raise GltfError("image %s does not exist" % image_index)
        if "bufferView" in image:
            data = self._buffer_view_bytes(image["bufferView"])
        elif "uri" in image:
            data = self._read_uri(image["uri"])
        else:
            raise GltfError("image %d has neither bufferView nor uri" % image_index)
        if data[:8] == PNG_SIGNATURE:
            return data, ".png"
        if data[:3] == b"\xff\xd8\xff":
            return data, ".jpg"
        raise GltfError("image %d is neither PNG nor JPEG (mimeType %s)" % (image_index, image.get("mimeType")))

    # ----- geometry -------------------------------------------------------------------------------------------

    def mesh_count(self):
        return len(self._list("meshes"))

    def mesh_node_count(self):
        return sum(1 for node in self._list("nodes") if isinstance(node, dict) and "mesh" in node)

    def _accessor_count(self, index):
        accessor = self._item("accessors", index)
        if accessor is None:
            return 0
        count = accessor.get("count", 0)
        return count if isinstance(count, int) and count > 0 else 0

    def _mesh_triangles(self, mesh_index):
        mesh = self._item("meshes", mesh_index)
        if mesh is None:
            return 0
        total = 0
        for primitive in mesh.get("primitives", []):
            if not isinstance(primitive, dict):
                continue
            mode = primitive.get("mode", MODE_TRIANGLES)
            if "indices" in primitive:
                count = self._accessor_count(primitive["indices"])
            else:
                attributes = primitive.get("attributes") if isinstance(primitive.get("attributes"), dict) else {}
                count = self._accessor_count(attributes.get("POSITION"))
            if mode == MODE_TRIANGLES:
                total += count // 3
            elif mode in (MODE_TRIANGLE_STRIP, MODE_TRIANGLE_FAN):
                total += max(0, count - 2)
        return total

    def _mesh_local_box(self, mesh_index):
        mesh = self._item("meshes", mesh_index)
        if mesh is None:
            return None
        box = None
        for primitive in mesh.get("primitives", []):
            if not isinstance(primitive, dict) or not isinstance(primitive.get("attributes"), dict):
                continue
            accessor = self._item("accessors", primitive["attributes"].get("POSITION"))
            if accessor is None:
                continue
            lo = accessor.get("min")
            hi = accessor.get("max")
            if not (isinstance(lo, list) and isinstance(hi, list) and len(lo) == 3 and len(hi) == 3):
                continue
            lo = tuple(_number(v, 0.0) for v in lo)
            hi = tuple(_number(v, 0.0) for v in hi)
            if box is None:
                box = [list(lo), list(hi)]
            else:
                for axis in range(3):
                    box[0][axis] = min(box[0][axis], lo[axis])
                    box[1][axis] = max(box[1][axis], hi[axis])
        return box

    def _walk_mesh_nodes(self):
        """[(mesh index, world matrix)] for every node of the default scene (all roots when there is no scene)."""
        nodes = self._list("nodes")
        roots = None
        scene_index = self.json.get("scene", 0)
        scene = self._item("scenes", scene_index if isinstance(scene_index, int) else 0)
        if scene is not None and isinstance(scene.get("nodes"), list):
            roots = [n for n in scene["nodes"] if isinstance(n, int)]
        if roots is None:
            children = set()
            for node in nodes:
                if isinstance(node, dict):
                    children.update(c for c in node.get("children", []) if isinstance(c, int))
            roots = [i for i in range(len(nodes)) if i not in children]
        result = []
        stack = [(index, _identity(), 0) for index in roots]
        while stack:
            index, parent, depth = stack.pop()
            node = self._item("nodes", index)
            if node is None or depth > 64:
                continue
            world = _multiply(parent, _node_matrix(node))
            if isinstance(node.get("mesh"), int):
                result.append((node["mesh"], world))
            for child in node.get("children", []):
                if isinstance(child, int):
                    stack.append((child, world, depth + 1))
        return result

    def triangle_count(self):
        """Triangles of the scene (meshes counted once per node that instances them)."""
        instances = self._walk_mesh_nodes()
        if not instances:
            return sum(self._mesh_triangles(i) for i in range(self.mesh_count()))
        return sum(self._mesh_triangles(mesh) for mesh, _ in instances)

    def bounds(self):
        """((minx, miny, minz), (maxx, maxy, maxz)) in glTF metres (+Y up), or None without geometry."""
        lo = [float("inf")] * 3
        hi = [float("-inf")] * 3
        found = False
        for mesh, matrix in self._walk_mesh_nodes():
            box = self._mesh_local_box(mesh)
            if box is None:
                continue
            for cx in (box[0][0], box[1][0]):
                for cy in (box[0][1], box[1][1]):
                    for cz in (box[0][2], box[1][2]):
                        point = _transform_point(matrix, (cx, cy, cz))
                        for axis in range(3):
                            lo[axis] = min(lo[axis], point[axis])
                            hi[axis] = max(hi[axis], point[axis])
                        found = True
        if not found:
            return None
        return tuple(lo), tuple(hi)

    def texture_kinds_by_image(self):
        """{image index: set(kinds)} over all materials; textures without a usable image are skipped."""
        result = {}
        for material in self.materials:
            for texture_index, kind, _role in material.texture_uses():
                image = self.texture_image(texture_index)
                if image is not None:
                    result.setdefault(image, set()).add(kind)
        return result


def png_info(source):
    """(width, height, bit depth, colour type name) from PNG bytes or a file path; None if not a PNG."""
    if isinstance(source, (bytes, bytearray)):
        header = bytes(source[:33])
    else:
        try:
            with open(source, "rb") as handle:
                header = handle.read(33)
        except OSError:
            return None
    if len(header) < 33 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        return None
    width, height, depth, color_type = struct.unpack(">IIBB", header[16:26])
    return width, height, depth, PNG_COLOR_TYPES.get(color_type, "unknown")


def is_power_of_two(value):
    return value > 0 and (value & (value - 1)) == 0

"""Static terrain chunks for the Iron Reign asset import (docs/DESIGN.md section 12.2).

Pure Python (standard library only, no ``unreal``) so it is shared by

* ``Content/Python/ironreign_import.py`` inside the Unreal editor, which turns the chunks into the static meshes
  ``/Game/IronReign/Models/SM_Terrain_<cx>_<cy>`` (Nanite, mesh distance fields, Lumen cards), and
* ``Tools/Unreal/check_art_source.py`` with the system ``python3`` (CI: the heightmap must decode here too).

The game (``AIronTerrain``, Source/IronReign/World/IronTerrain.cpp) draws the campaign ground from
``Content/Data/Art3D/Terrain/Height.png`` + ``Terrain.json``. A runtime procedural mesh is invisible to software Lumen
(only static meshes, instanced meshes and landscapes have distance fields and cards), so the importer cuts the very
same mesh into static meshes. Everything here mirrors the C++ exactly: the decoded heights (float32), the mesh vertex
grid (every ``stride``-th heightmap pixel plus the last one), the 8 x 5 chunk split with shared edges, the two
triangles per cell (A D B and B D C: diagonal from the top-right to the bottom-left corner, as
``FIronHeightField::Sample`` interpolates), central-difference normals and the UVs. ``source_hash`` identifies the
heightmap; the import records it and the game only uses chunks cut from the Height.png it loads.

Positions are written in Unreal world space (centimetres, map x -> X, map y -> Y, height -> Z) through an axis map
measured on the running engine's glTF import (``write_probe_glb`` + ``solve_axis_map``), so no assumption about the
importer's glTF-to-Unreal axis conversion is needed.
"""

import array
import json
import os
import struct
import sys
import zlib

CHUNKS_X = 8
CHUNKS_Y = 5
# UV1 tiling (IronTerrainDetail::DetailTileM).
DETAIL_TILE_M = 50.0
CM_PER_METRE = 100.0

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Terrain.json defaults (FIronTerrainInfo).
DEFAULT_INFO = {"width": 2400.0, "height": 1500.0, "gridStep": 2.0, "minHeight": -40.0, "maxHeight": 180.0,
                "seaLevel": 0.0}

# The probe: a tetrahedron from the origin along glTF +X (1 m), +Y (2 m) and +Z (3 m).
PROBE_LENGTHS = (1.0, 2.0, 3.0)

_GLB_MAGIC = b"glTF"
_CHUNK_JSON = 0x4E4F534A
_CHUNK_BIN = 0x004E4942
_FLOAT = 5126
_UNSIGNED_INT = 5125
_ARRAY_BUFFER = 34962
_ELEMENT_ARRAY_BUFFER = 34963


class TerrainError(Exception):
    """Missing, unreadable or unsupported terrain data, or an axis map that cannot be measured."""


def chunk_name(chunk_x, chunk_y):
    """Model name of a chunk ("Terrain_3_1" -> /Game/IronReign/Models/SM_Terrain_3_1), as IronTerrainDetail."""
    return "Terrain_%d_%d" % (chunk_x, chunk_y)


def chunk_names():
    return [chunk_name(x, y) for y in range(CHUNKS_Y) for x in range(CHUNKS_X)]


def source_hash(data):
    """FIronHeightField::SourceHash of Height.png's bytes: standard CRC-32 in hex and the byte count."""
    return "%08x-%d" % (zlib.crc32(bytes(data)) & 0xFFFFFFFF, len(data))


def file_source_hash(path):
    """source_hash of a file, or "" when it cannot be read."""
    try:
        with open(path, "rb") as handle:
            return source_hash(handle.read())
    except OSError:
        return ""


# ----- Terrain.json and Height.png ------------------------------------------------------------------------------

def _number(value, default):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float(default)
    return float(value)


def read_info(path):
    """Terrain.json with the C++ defaults applied (IronTerrainDetail::ParseInfo)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise TerrainError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise TerrainError("%s is not a JSON object" % path)
    info = dict((key, _number(data.get(key), default)) for key, default in DEFAULT_INFO.items())
    if not (info["width"] > 0.0 and info["height"] > 0.0 and info["gridStep"] > 0.0
            and info["maxHeight"] > info["minHeight"]):
        raise TerrainError("%s has invalid sizes" % path)
    return info


def _paeth(left, up, up_left):
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def _unfilter(filter_type, line, previous, step):
    """Reverses one PNG scanline filter in place (step = bytes per pixel)."""
    count = len(line)
    if filter_type == 0:
        return
    if filter_type == 1:
        for index in range(step, count):
            line[index] = (line[index] + line[index - step]) & 0xFF
    elif filter_type == 2:
        for index in range(count):
            line[index] = (line[index] + previous[index]) & 0xFF
    elif filter_type == 3:
        for index in range(count):
            left = line[index - step] if index >= step else 0
            line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
    elif filter_type == 4:
        for index in range(count):
            if index >= step:
                line[index] = (line[index] + _paeth(line[index - step], previous[index], previous[index - step])) & 0xFF
            else:
                line[index] = (line[index] + previous[index]) & 0xFF
    else:
        raise TerrainError("unknown PNG filter type %d" % filter_type)


def decode_grey_png(data):
    """(width, height, bit depth, samples) of a non-interlaced 8- or 16-bit greyscale PNG; samples row-major ints.

    Only greyscale is accepted: the game's decoder may convert colour images differently, and DESIGN.md 12.2 requires
    16-bit greyscale anyway.
    """
    data = bytes(data)
    if data[:8] != PNG_SIGNATURE:
        raise TerrainError("not a PNG file")
    header = None
    compressed = []
    position = 8
    while position + 8 <= len(data):
        length, tag = struct.unpack(">I4s", data[position:position + 8])
        position += 8
        payload = data[position:position + length]
        position += length + 4
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload[:13])
        elif tag == b"IDAT":
            compressed.append(payload)
        elif tag == b"IEND":
            break
    if header is None:
        raise TerrainError("PNG without IHDR")
    width, height, depth, color_type, _compression, _filter_method, interlace = header
    if color_type != 0:
        raise TerrainError("colour type %d; a greyscale PNG is required" % color_type)
    if depth not in (8, 16):
        raise TerrainError("%d-bit greyscale; 8 or 16 bits are required" % depth)
    if interlace != 0:
        raise TerrainError("interlaced PNG (save it without Adam7 interlacing)")
    if width < 2 or height < 2:
        raise TerrainError("too small (%dx%d)" % (width, height))
    try:
        raw = zlib.decompress(b"".join(compressed))
    except zlib.error as exc:
        raise TerrainError("corrupt image data: %s" % exc)
    step = depth // 8
    stride = width * step
    if len(raw) < height * (stride + 1):
        raise TerrainError("truncated image data")
    samples = array.array("I")
    previous = bytearray(stride)
    row_format = ">%dH" % width
    for row in range(height):
        start = row * (stride + 1)
        line = bytearray(raw[start + 1:start + 1 + stride])
        _unfilter(raw[start], line, previous, step)
        if depth == 16:
            samples.extend(struct.unpack(row_format, bytes(line)))
        else:
            samples.extend(line)
        previous = line
    return width, height, depth, samples


class HeightField(object):
    """The decoded heightmap and the mesh vertex grid, as FIronHeightField."""

    def __init__(self, info, samples_x, samples_y, heights, hash_text=""):
        self.info = info
        self.samples_x = samples_x
        self.samples_y = samples_y
        self.heights = heights
        self.source_hash = hash_text
        self.columns = []
        self.rows = []
        self.stride = 1
        self.build_mesh_grid(1)

    @classmethod
    def load(cls, terrain_dir):
        """Terrain.json + Height.png from a Content/Data/Art3D/Terrain folder (FIronHeightField::Load)."""
        info = read_info(os.path.join(terrain_dir, "Terrain.json"))
        height_path = os.path.join(terrain_dir, "Height.png")
        try:
            with open(height_path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            raise TerrainError("cannot read %s: %s" % (height_path, exc))
        try:
            width, height, depth, samples = decode_grey_png(data)
        except TerrainError as exc:
            raise TerrainError("%s: %s" % (height_path, exc))
        expected_width = info["width"] / info["gridStep"] + 1.0
        if abs(expected_width - width) > 0.5:
            # As the game: the map extent stays authoritative, the pixel spacing follows the image.
            info["gridStep"] = info["width"] / float(width - 1)
        lowest = info["minHeight"]
        span = info["maxHeight"] - info["minHeight"]
        top = 65535.0 if depth == 16 else 255.0
        # Same double arithmetic as the C++, then float32 storage like TArray<float>.
        heights = array.array("f", [lowest + (value / top) * span for value in samples])
        return cls(info, width, height, heights, source_hash(data))

    def at(self, pixel_x, pixel_y):
        return self.heights[pixel_y * self.samples_x + pixel_x]

    def build_mesh_grid(self, stride):
        self.stride = max(1, int(stride))
        self.columns = list(range(0, self.samples_x - 1, self.stride)) + [self.samples_x - 1]
        self.rows = list(range(0, self.samples_y - 1, self.stride)) + [self.samples_y - 1]

    def chunk_ranges(self):
        """[(chunk x, chunk y, first column, last column, first row, last row)] in mesh-vertex indices, row-major."""
        cells_x = len(self.columns) - 1
        cells_y = len(self.rows) - 1
        count_x = max(1, min(CHUNKS_X, cells_x))
        count_y = max(1, min(CHUNKS_Y, cells_y))
        ranges = []
        for chunk_y in range(count_y):
            for chunk_x in range(count_x):
                ranges.append((chunk_x, chunk_y, cells_x * chunk_x // count_x, cells_x * (chunk_x + 1) // count_x,
                               cells_y * chunk_y // count_y, cells_y * (chunk_y + 1) // count_y))
        return ranges

    def normal_at(self, vertex_x, vertex_y):
        """IronTerrainDetail::NormalAt: central differences on the mesh grid (map axes = Unreal axes)."""
        columns = self.columns
        rows = self.rows
        pixel_x = columns[vertex_x]
        pixel_y = rows[vertex_y]
        west = columns[max(vertex_x - 1, 0)]
        east = columns[min(vertex_x + 1, len(columns) - 1)]
        north = rows[max(vertex_y - 1, 0)]
        south = rows[min(vertex_y + 1, len(rows) - 1)]
        step = self.info["gridStep"]
        span_x = max(1, east - west) * step
        span_y = max(1, south - north) * step
        slope_x = (self.at(east, pixel_y) - self.at(west, pixel_y)) / span_x
        slope_y = (self.at(pixel_x, south) - self.at(pixel_x, north)) / span_y
        length = (slope_x * slope_x + slope_y * slope_y + 1.0) ** 0.5
        return (-slope_x / length, -slope_y / length, 1.0 / length)

    def build_chunk(self, first_x, last_x, first_y, last_y):
        """IronTerrainDetail::BuildChunk for the inclusive vertex range: a dict of flat lists.

        positions: Unreal world cm (x, y, z) per vertex; normals: unit vectors in Unreal axes; uv0 / uv1: (u, v);
        triangles: vertex index triples A D B, B D C (front faces up in Unreal).
        """
        step = self.info["gridStep"]
        width_m = self.info["width"]
        height_m = self.info["height"]
        positions = []
        normals = []
        uv0 = []
        uv1 = []
        for vertex_y in range(first_y, last_y + 1):
            pixel_y = self.rows[vertex_y]
            y_m = pixel_y * step
            for vertex_x in range(first_x, last_x + 1):
                pixel_x = self.columns[vertex_x]
                x_m = pixel_x * step
                positions.extend((x_m * CM_PER_METRE, y_m * CM_PER_METRE, self.at(pixel_x, pixel_y) * CM_PER_METRE))
                normals.extend(self.normal_at(vertex_x, vertex_y))
                uv0.extend((x_m / width_m, y_m / height_m))
                uv1.extend((x_m / DETAIL_TILE_M, y_m / DETAIL_TILE_M))
        per_row = last_x - first_x + 1
        rows = last_y - first_y + 1
        triangles = []
        for row in range(rows - 1):
            for column in range(per_row - 1):
                a = row * per_row + column
                b = a + 1
                d = a + per_row
                c = d + 1
                triangles.extend((a, d, b, b, d, c))
        return {"positions": positions, "normals": normals, "uv0": uv0, "uv1": uv1, "triangles": triangles,
                "vertex_count": per_row * rows}


# ----- glTF axis map --------------------------------------------------------------------------------------------

def solve_axis_map(bounds_min, bounds_max):
    """The importer's glTF -> Unreal mapping from the imported probe's bounding box (Unreal cm).

    Returns {"axes": (j0, j1, j2), "signs": (s0, s1, s2), "scale": s}: Unreal axis k = signs[k] * scale * glTF axis
    axes[k]. Raises TerrainError when the box is not the probe under a signed axis permutation and a uniform scale
    (for example when the importer moved the pivot).
    """
    extents = [float(bounds_max[k]) - float(bounds_min[k]) for k in range(3)]
    total = sum(extents)
    if total <= 1e-6 or min(extents) <= 1e-6:
        raise TerrainError("degenerate probe bounds %s .. %s" % (tuple(bounds_min), tuple(bounds_max)))
    scale = total / sum(PROBE_LENGTHS)
    axes = []
    signs = []
    for k in range(3):
        lengths = [abs(extents[k] - scale * length) for length in PROBE_LENGTHS]
        axis = lengths.index(min(lengths))
        if lengths[axis] > 0.02 * scale:
            raise TerrainError("probe extent %.3f on axis %d matches no glTF axis (scale %.3f)" % (extents[k], k, scale))
        low = float(bounds_min[k])
        high = float(bounds_max[k])
        tolerance = 0.02 * scale
        if abs(low) <= tolerance and high > tolerance:
            signs.append(1)
        elif abs(high) <= tolerance and low < -tolerance:
            signs.append(-1)
        else:
            raise TerrainError("the glTF import moved the probe's origin (axis %d spans %.3f .. %.3f)" % (k, low, high))
        axes.append(axis)
    if sorted(axes) != [0, 1, 2]:
        raise TerrainError("probe axes %s are not a permutation" % (axes,))
    return {"axes": tuple(axes), "signs": tuple(signs), "scale": scale}


def describe_axis_map(mapping):
    if not mapping:
        return "unknown"
    names = "XYZ"
    return ", ".join("UE %s = %s%.4g * glTF %s" % (names[k], "-" if mapping["signs"][k] < 0 else "", mapping["scale"],
                                                  names[mapping["axes"][k]]) for k in range(3))


def _to_gltf_vector(mapping, vector):
    """A direction in Unreal axes as a glTF direction (no scale)."""
    out = [0.0, 0.0, 0.0]
    for k in range(3):
        out[mapping["axes"][k]] = mapping["signs"][k] * vector[k]
    return out


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def keeps_winding(mapping):
    """True when the Unreal triangle order A D B is counter-clockwise (glTF front face) seen from Unreal +Z."""
    corner_d = _to_gltf_vector(mapping, (0.0, 1.0, 0.0))
    corner_b = _to_gltf_vector(mapping, (1.0, 0.0, 0.0))
    up = _to_gltf_vector(mapping, (0.0, 0.0, 1.0))
    normal = _cross(corner_d, corner_b)
    return sum(normal[k] * up[k] for k in range(3)) > 0.0


# ----- glb writing ----------------------------------------------------------------------------------------------

def _pack(type_code, values):
    packed = array.array(type_code, values)
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def _write_glb(path, name, attributes, triangles):
    """attributes: [(glTF attribute, components, flat float list)]; one mesh, one node, no material."""
    blobs = []
    views = []
    accessors = []
    offset = 0
    primitive_attributes = {}
    for attribute, components, values in attributes:
        blob = _pack("f", values)
        count = len(values) // components
        accessor = {"bufferView": len(views), "componentType": _FLOAT, "count": count,
                    "type": "VEC%d" % components}
        if attribute == "POSITION":
            accessor["min"] = [min(values[i::components]) for i in range(components)]
            accessor["max"] = [max(values[i::components]) for i in range(components)]
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(blob), "target": _ARRAY_BUFFER})
        primitive_attributes[attribute] = len(accessors)
        accessors.append(accessor)
        blobs.append(blob)
        offset += len(blob)
    index_blob = _pack("I", triangles)
    views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(index_blob), "target": _ELEMENT_ARRAY_BUFFER})
    accessors.append({"bufferView": len(views) - 1, "componentType": _UNSIGNED_INT, "count": len(triangles),
                      "type": "SCALAR"})
    blobs.append(index_blob)
    binary = b"".join(blobs)
    document = {
        "asset": {"version": "2.0", "generator": "Iron Reign ironreign_terrain.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{"name": name, "primitives": [{"attributes": primitive_attributes,
                                                  "indices": len(accessors) - 1, "mode": 4}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    json_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((4 - len(json_bytes) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    data = (struct.pack("<4sII", _GLB_MAGIC, 2, total) + struct.pack("<II", len(json_bytes), _CHUNK_JSON) + json_bytes
            + struct.pack("<II", len(binary), _CHUNK_BIN) + binary)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def write_probe_glb(path):
    """The axis probe: origin plus points 1 m along glTF X, 2 m along Y and 3 m along Z (a closed tetrahedron)."""
    length_x, length_y, length_z = PROBE_LENGTHS
    positions = [0.0, 0.0, 0.0, length_x, 0.0, 0.0, 0.0, length_y, 0.0, 0.0, 0.0, length_z]
    # Counter-clockwise seen from outside.
    triangles = [0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3]
    _write_glb(path, "IronAxisProbe", [("POSITION", 3, positions)], triangles)


def write_chunk_glb(path, name, chunk, mapping):
    """Writes a build_chunk() result as a .glb that the measured importer turns into the chunk's Unreal geometry."""
    axes = mapping["axes"]
    signs = mapping["signs"]
    scale = float(mapping["scale"])
    source = chunk["positions"]
    positions = [0.0] * len(source)
    normals = [0.0] * len(source)
    source_normals = chunk["normals"]
    for k in range(3):
        target = axes[k]
        factor = 1.0 / (signs[k] * scale)
        sign = float(signs[k])
        positions[target::3] = [value * factor for value in source[k::3]]
        normals[target::3] = [value * sign for value in source_normals[k::3]]
    triangles = chunk["triangles"]
    if not keeps_winding(mapping):
        reordered = list(triangles)
        reordered[1::3] = triangles[2::3]
        reordered[2::3] = triangles[1::3]
        triangles = reordered
    _write_glb(path, name, [("POSITION", 3, positions), ("NORMAL", 3, normals), ("TEXCOORD_0", 2, chunk["uv0"]),
                            ("TEXCOORD_1", 2, chunk["uv1"])], triangles)


def main(argv):
    """python3 ironreign_terrain.py [Content/Data/Art3D/Terrain]: decodes the heightmap and lists the chunks."""
    here = os.path.dirname(os.path.abspath(__file__))
    folder = argv[1] if len(argv) > 1 else os.path.join(here, "..", "Data", "Art3D", "Terrain")
    try:
        field = HeightField.load(folder)
    except TerrainError as exc:
        print("error: %s" % exc)
        return 1
    print("%dx%d px, %.3f m grid, %.1f .. %.1f m, %s" % (field.samples_x, field.samples_y, field.info["gridStep"],
                                                        min(field.heights), max(field.heights), field.source_hash))
    for chunk_x, chunk_y, first_x, last_x, first_y, last_y in field.chunk_ranges():
        print("%s: columns %d..%d, rows %d..%d" % (chunk_name(chunk_x, chunk_y), first_x, last_x, first_y, last_y))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

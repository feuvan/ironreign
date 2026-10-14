#!/usr/bin/env python3
"""Self-test of Content/Python/ironreign_terrain.py (the import's SM_Terrain_* chunks), without Unreal.

    python3 Tools/Unreal/test_terrain_chunks.py

The chunks only work if they are exactly the surface the game samples, so this checks the module against an
independent port of FIronHeightField::Sample (Source/IronReign/World/IronTerrain.cpp): PNG decoding through every
scanline filter, the 8 x 5 split with shared edges, triangles that reproduce the sampler at random points, and a
.glb that lands on Unreal world positions under several importer axis conventions. Standard library only.
"""

import json
import math
import os
import random
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "Content", "Python"))

import ironreign_terrain as terrain  # noqa: E402

FAILURES = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)
        print("FAIL: " + message)


def write_grey_png(path, width, height, values, depth):
    """Greyscale PNG whose rows cycle through all five scanline filters."""
    step = depth // 8
    rows = []
    previous = bytearray(width * step)
    for row in range(height):
        chunk = values[row * width:(row + 1) * width]
        line = bytearray(struct.pack(">%dH" % width, *chunk) if depth == 16 else bytes(chunk))
        kind = row % 5
        encoded = bytearray(len(line))
        for index in range(len(line)):
            left = line[index - step] if index >= step else 0
            up = previous[index]
            up_left = previous[index - step] if index >= step else 0
            predictor = (0, left, up, (left + up) >> 1, terrain._paeth(left, up, up_left))[kind]
            encoded[index] = (line[index] - predictor) & 0xFF
        rows.append(bytes([kind]) + bytes(encoded))
        previous = line

    def png_chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    data = (terrain.PNG_SIGNATURE + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, 0, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"".join(rows))) + png_chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(data)


def sample_like_cpp(field, x_m, y_m):
    """FIronHeightField::Sample."""
    step = field.info["gridStep"]
    pixel_x = min(max(x_m / step, 0.0), field.samples_x - 1.0)
    pixel_y = min(max(y_m / step, 0.0), field.samples_y - 1.0)
    cell_x = min(max(int(math.floor(pixel_x / field.stride)), 0), len(field.columns) - 2)
    cell_y = min(max(int(math.floor(pixel_y / field.stride)), 0), len(field.rows) - 2)
    x0, x1 = field.columns[cell_x], field.columns[cell_x + 1]
    y0, y1 = field.rows[cell_y], field.rows[cell_y + 1]
    fx = min(max((pixel_x - x0) / max(1, x1 - x0), 0.0), 1.0)
    fy = min(max((pixel_y - y0) / max(1, y1 - y0), 0.0), 1.0)
    a, b, c, d = field.at(x0, y0), field.at(x1, y0), field.at(x1, y1), field.at(x0, y1)
    if fx + fy <= 1.0:
        return a + fx * (b - a) + fy * (d - a)
    return c + (1.0 - fx) * (d - c) + (1.0 - fy) * (b - c)


def triangle_height(p0, p1, p2, x, y):
    determinant = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(determinant) < 1e-12:
        return None
    l0 = ((p1[1] - p2[1]) * (x - p2[0]) + (p2[0] - p1[0]) * (y - p2[1])) / determinant
    l1 = ((p2[1] - p0[1]) * (x - p2[0]) + (p0[0] - p2[0]) * (y - p2[1])) / determinant
    l2 = 1.0 - l0 - l1
    if min(l0, l1, l2) < -1e-9:
        return None
    return l0 * p0[2] + l1 * p1[2] + l2 * p2[2]


def chunk_height(field, chunks, x_m, y_m):
    for (first_x, last_x, first_y, last_y), chunk in chunks:
        step = field.info["gridStep"]
        if not (field.columns[first_x] * step <= x_m <= field.columns[last_x] * step
                and field.rows[first_y] * step <= y_m <= field.rows[last_y] * step):
            continue
        positions = chunk["positions"]
        triangles = chunk["triangles"]
        per_row = last_x - first_x + 1
        # The cell under the point, then its two triangles.
        column = min(max(int((x_m / step - field.columns[first_x]) // field.stride), 0), per_row - 2)
        row = min(max(int((y_m / step - field.rows[first_y]) // field.stride), 0), last_y - first_y - 1)
        cell = (row * (per_row - 1) + column) * 6
        for start in (cell, cell + 3):
            points = [tuple(positions[3 * v + k] / 100.0 for k in range(3)) for v in triangles[start:start + 3]]
            height = triangle_height(points[0], points[1], points[2], x_m, y_m)
            if height is not None:
                return height
    return None


def read_glb(path):
    with open(path, "rb") as handle:
        data = handle.read()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length].decode("utf-8"))
    binary = data[20 + json_length + 8:]
    primitive = document["meshes"][0]["primitives"][0]

    def accessor(index):
        item = document["accessors"][index]
        view = document["bufferViews"][item["bufferView"]]
        size = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[item["type"]] * item["count"]
        code = "f" if item["componentType"] == 5126 else "I"
        return list(struct.unpack_from("<%d%s" % (size, code), binary, view["byteOffset"]))

    return dict((name, accessor(index)) for name, index in primitive["attributes"].items()), accessor(primitive["indices"])


def main():
    rng = random.Random(11)
    folder = tempfile.mkdtemp(prefix="ironreign_terrain_")
    width_m, height_m, step = 96.0, 60.0, 2.0
    samples_x, samples_y = int(width_m / step) + 1, int(height_m / step) + 1
    values = []
    for y in range(samples_y):
        for x in range(samples_x):
            wave = 0.5 + 0.25 * math.sin(x * 0.21) * math.cos(y * 0.37) + 0.2 * math.sin(x * 0.6 + y * 0.45)
            values.append(max(0, min(65535, int((wave + rng.random() * 0.05) * 65535))))
    write_grey_png(os.path.join(folder, "Height.png"), samples_x, samples_y, values, 16)
    with open(os.path.join(folder, "Terrain.json"), "w") as handle:
        json.dump({"width": width_m, "height": height_m, "gridStep": step, "minHeight": -40, "maxHeight": 180,
                   "seaLevel": 0}, handle)

    with open(os.path.join(folder, "Height.png"), "rb") as handle:
        png = handle.read()
    decoded = terrain.decode_grey_png(png)
    check(decoded[:3] == (samples_x, samples_y, 16) and list(decoded[3]) == values, "16-bit decode")
    check(terrain.source_hash(b"123456789") == "cbf43926-9", "source hash = zlib CRC-32 and size")
    eight = [v >> 8 for v in values]
    write_grey_png(os.path.join(folder, "Grey8.png"), samples_x, samples_y, eight, 8)
    with open(os.path.join(folder, "Grey8.png"), "rb") as handle:
        check(list(terrain.decode_grey_png(handle.read())[3]) == eight, "8-bit decode")

    field = terrain.HeightField.load(folder)
    check(field.at(3, 2) == struct.unpack("<f", struct.pack("<f", -40.0 + values[2 * samples_x + 3] / 65535.0 * 220.0))[0],
          "heights stored as float32 like the C++")
    for stride in (1, 2, 3):
        field.build_mesh_grid(stride)
        ranges = field.chunk_ranges()
        check(len(ranges) == terrain.CHUNKS_X * terrain.CHUNKS_Y, "8 x 5 chunks at stride %d" % stride)
        by_index = dict(((r[0], r[1]), r) for r in ranges)
        for (chunk_x, chunk_y), (_, _, first_x, _, first_y, _) in by_index.items():
            if chunk_x > 0:
                check(by_index[(chunk_x - 1, chunk_y)][3] == first_x, "shared column edge")
            if chunk_y > 0:
                check(by_index[(chunk_x, chunk_y - 1)][5] == first_y, "shared row edge")
        chunks = [((r[2], r[3], r[4], r[5]), field.build_chunk(r[2], r[3], r[4], r[5])) for r in ranges]
        worst = 0.0
        for _ in range(2000):
            x_m, y_m = rng.uniform(0.0, width_m), rng.uniform(0.0, height_m)
            found = chunk_height(field, chunks, x_m, y_m)
            worst = max(worst, 1e9 if found is None else abs(found - sample_like_cpp(field, x_m, y_m)))
        check(worst < 1e-4, "stride %d: chunk triangles = FIronHeightField::Sample (worst %.3g m)" % (stride, worst))

    # A .glb written for a measured importer convention imports onto the intended Unreal positions, front faces up.
    field.build_mesh_grid(1)
    first = field.chunk_ranges()[9]
    chunk = field.build_chunk(first[2], first[3], first[4], first[5])
    conventions = ({"axes": (0, 2, 1), "signs": (1, 1, 1), "scale": 100.0},
                   {"axes": (0, 2, 1), "signs": (1, -1, 1), "scale": 100.0},
                   {"axes": (2, 0, 1), "signs": (-1, 1, 1), "scale": 100.0},
                   {"axes": (0, 1, 2), "signs": (1, 1, 1), "scale": 1.0})
    probe = os.path.join(folder, "Probe.glb")
    terrain.write_probe_glb(probe)
    probe_points = read_glb(probe)[0]["POSITION"]
    for truth in conventions:
        def to_unreal(values_g, index):
            return [truth["signs"][k] * truth["scale"] * values_g[index + truth["axes"][k]] for k in range(3)]

        corners = [to_unreal(probe_points, i) for i in range(0, len(probe_points), 3)]
        solved = terrain.solve_axis_map([min(c[k] for c in corners) for k in range(3)],
                                        [max(c[k] for c in corners) for k in range(3)])
        check(solved["axes"] == truth["axes"] and solved["signs"] == truth["signs"]
              and abs(solved["scale"] - truth["scale"]) < 1e-9, "axis map %s" % (truth,))
        path = os.path.join(folder, "Chunk.glb")
        terrain.write_chunk_glb(path, "Terrain_1_1", chunk, solved)
        attributes, indices = read_glb(path)
        gltf_positions = attributes["POSITION"]
        error = max(abs(to_unreal(gltf_positions, 3 * v)[k] - chunk["positions"][3 * v + k])
                    for v in range(chunk["vertex_count"]) for k in range(3))
        check(error < 0.05, "positions land on the game grid (%.4f cm) for %s" % (error, truth))
        a, b, c = indices[:3]
        edge_1 = [gltf_positions[3 * b + k] - gltf_positions[3 * a + k] for k in range(3)]
        edge_2 = [gltf_positions[3 * c + k] - gltf_positions[3 * a + k] for k in range(3)]
        normal = terrain._cross(edge_1, edge_2)
        check(normal[truth["axes"][2]] * truth["signs"][2] > 0, "glTF front faces Unreal +Z for %s" % (truth,))
    for low, high in (([-50, -100, -150], [50, 100, 150]), ([0, 0, 0], [100, 100, 100])):
        try:
            terrain.solve_axis_map(low, high)
            check(False, "a moved or distorted probe must be rejected")
        except terrain.TerrainError:
            pass

    print("%d failure(s)" % len(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())

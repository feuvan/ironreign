"""Review sheets of the 2D battle art (system python3 or Blender's): every asset at 1x and 3x
on silk and on Night, plus a mock 2D board laid out as SIronHexView draws it (tiles 128x111 at
odd-q offsets, units at 0.86 x the hex height over the tinted base)."""

import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ART = os.path.join(REPO, "Content", "Data", "Art", "Battle")
LEGEND = {"P": "Plain", "F": "Forest", "H": "Hill", "M": "Mountain", "W": "Water", "O": "Ford", "B": "Bridge",
          "R": "Road", "L": "Wall", "G": "Gate", "T": "Town", "C": "Castle", "X": "Rubble"}


def load(name):
    p = os.path.join(ART, name + ".png")
    return Image.open(p).convert("RGBA") if os.path.isfile(p) else None


def tint(im, rgb):
    a = np.asarray(im, np.float32) / 255.0
    a[..., :3] *= np.array(rgb, np.float32)
    return Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGBA")


def board(rows, units, out, scale=1.0, bg=None):
    W, Hh = 128, 111
    ncol = max(len(r) for r in rows)
    w = int((ncol * 96 + 64) * scale) + 40
    h = int((len(rows) * 110.85 + 56) * scale) + 40
    if bg is None:
        bgim = load("Background")
        canvas = bgim.resize((w, h), Image.LANCZOS) if bgim else Image.new("RGBA", (w, h), (27, 23, 18, 255))
    else:
        canvas = Image.new("RGBA", (w, h), bg)
    tiles = {}
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            n = LEGEND[ch]
            if n not in tiles:
                tiles[n] = load("Hex_" + n)
            t = tiles[n]
            if t is None:
                continue
            cx = 20 + (64 + 96 * c) * scale
            cy = 20 + (55.4 + 110.85 * (r + 0.5 * (c & 1))) * scale
            tt = t.resize((int(round(W * scale)), int(round(Hh * scale))), Image.LANCZOS) if scale != 1 else t
            canvas.alpha_composite(tt, (int(round(cx - tt.width / 2)), int(round(cy - tt.height / 2))))
    base = load("Unit_Base")
    cols = {0: (0.70, 0.16, 0.18), 1: (0.18, 0.43, 0.71)}
    for (c, r, kind, side) in units:
        cx = 20 + (64 + 96 * c) * scale
        cy = 20 + (55.4 + 110.85 * (r + 0.5 * (c & 1))) * scale
        us = int(round(111 * 0.86 * scale))
        if base:
            b = tint(base, cols[side]).resize((us, us), Image.LANCZOS)
            canvas.alpha_composite(b, (int(cx - us / 2), int(cy + us * 0.05 - us / 2)))
        f = load("Unit_" + kind)
        if f:
            f = f.resize((us, us), Image.LANCZOS)
            canvas.alpha_composite(f, (int(cx - us / 2), int(cy - us * 0.04 - us / 2)))
    canvas.convert("RGB").save(out)
    return out


def sheet(out):
    names = ["Hex_" + n for n in ("Plain", "Forest", "Hill", "Mountain", "Water", "Ford", "Bridge", "Road", "Wall",
                                  "Gate", "Town", "Castle", "Rubble", "Fill", "Outline")] + \
        ["Unit_Infantry", "Unit_Cavalry", "Unit_Archer", "Unit_Base", "Fx_Fire", "Fx_Confuse", "Fx_Rally", "Fx_Hit"]
    cell = (3 * 128 + 20, 3 * 111 + 40)
    cols = 5
    rows = (len(names) + cols - 1) // cols
    canvas = Image.new("RGBA", (cell[0] * cols, cell[1] * rows * 2), (230, 214, 176, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    for i, n in enumerate(names):
        im = load(n)
        if im is None:
            continue
        x = (i % cols) * cell[0]
        y = (i // cols) * cell[1] * 2
        big = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
        canvas.alpha_composite(big, (x + 10, y + 20))
        dark = Image.new("RGBA", (cell[0], cell[1]), (27, 23, 18, 255))
        canvas.paste(dark, (x, y + cell[1]))
        canvas.alpha_composite(big, (x + 10, y + cell[1] + 20))
        canvas.alpha_composite(im, (x + cell[0] - im.width - 6, y + 4))
        d.text((x + 6, y + 4), n, fill=(30, 26, 22, 255))
    canvas.convert("RGB").save(out)
    return out


def main(out):
    os.makedirs(out, exist_ok=True)
    print(sheet(os.path.join(out, "Battle2D_sheet.png")))
    print(board(["PFFPHHMP", "PFPWPHMM", "RRROBRRP", "PPPWPPFP", "FPPWFFPP", "FFPOPPHP"],
                [(1, 2, "Infantry", 0), (2, 3, "Cavalry", 0), (1, 1, "Archer", 0), (5, 2, "Infantry", 1),
                 (6, 3, "Archer", 1), (4, 4, "Cavalry", 1)], os.path.join(out, "Battle2D_field.png")))
    print(board(["PPPLTTT", "RRRGTCT", "PPPLTTT", "PFPXTTT", "FFPLTTP"],
                [(1, 1, "Infantry", 0), (2, 3, "Cavalry", 0), (5, 1, "Archer", 1)],
                os.path.join(out, "Battle2D_siege.png")))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp")

"""Colour tokens for the Iron Reign art pipeline (no bpy dependency).

All tokens are authored as sRGB hex (what an artist picks in a colour picker / what DESIGN.md
section 8 lists). Blender shader and light inputs expect *scene linear* values, so always go
through :func:`lin` / :func:`lin4` when feeding a node socket, and :func:`srgb8` when drawing with
Pillow.

Three groups:

* ``UI``        - the DESIGN.md section 8 palette (hard contract with the UI code).
* ``FACTION``   - faction colours (used by the runtime tint; art must stay neutral or pure white
                  where tint is applied, see STYLE.md "Tinting").
* ``MAT``       - studio material base colours (stone, roof tile, lacquer, terrain biomes ...).
                  Muted, slightly warm, never neon.  These are *albedo* values: what the surface
                  looks like under the neutral key light before painterly post.
"""

UI = {
    "Paper": "#E9DCC0",
    "PaperDark": "#CDB990",
    "Ink": "#2A2119",
    "InkSoft": "#5A4A3A",
    "Lacquer": "#7E1F17",
    "LacquerDark": "#4A120D",
    "Gold": "#C9A24A",
    "Jade": "#3F6E5A",
    "Indigo": "#2E3F5C",
    "Night": "#1B1712",
}

FACTION = {
    "IronBanner": "#B3282D",
    "WolfRiders": "#B07A2A",
    "AzureCourt": "#2F6DB5",
    "SeaLeague": "#1F8F8A",
    "SouthernLotus": "#4C9A3C",
    "BlackMountain": "#4A4A55",
    "Independent": "#8C8577",
}

MAT = {
    # architecture
    "stone": "#8E8B82",          # grey wall stone (slightly warm)
    "stone_dark": "#5E5C57",
    "mortar": "#B5AE9E",
    "roof_tile": "#3D4A4E",       # dark grey-teal glazed tile
    "roof_tile_light": "#5E6E70",
    "roof_ridge": "#2C3436",
    "pillar_red": "#8C2A1C",      # red-lacquer pillars / beams
    "plaster": "#D9CCB0",         # warm white plaster walls
    "timber": "#5A3B26",
    "dark_wood": "#3A2619",
    "lacquer": UI["Lacquer"],
    "lacquer_dark": UI["LacquerDark"],
    "gold": UI["Gold"],
    "bronze": "#8A6A3A",
    "iron": "#5C6066",
    "iron_dark": "#3A3D42",
    "leather": "#5A3E2A",
    "lacing_red": "#9A2E22",
    "cloth_white": "#FFFFFF",     # pure white tintable cloth (exactly white albedo!)
    "silk_blue": "#2F4A6A",
    "silk_red": "#8A2A20",
    "paper": UI["Paper"],
    "paper_dark": UI["PaperDark"],
    "ink": UI["Ink"],
    # people
    "skin": "#C68F6A",
    "skin_shadow": "#8A5440",
    "lips": "#A0584A",
    "hair_black": "#1C1714",
    "hair_grey": "#8A8580",
    "hair_white": "#DAD5CC",
    "eye_white": "#D8D0C4",
    "iris": "#3A2416",
    # terrain / map (RTK IX relief map look)
    "plain": "#94A26E",           # sage lowland (renders ~#97A26E, hue 75-85)
    "grass": "#7E9A5C",           # sage green
    "meadow": "#93A867",
    "steppe": "#B5A06E",          # sandy steppe (renders ~#C7AC76 under the map sun)
    "desert": "#BFA776",
    "hill": "#949A6A",
    "rock": "#8A8578",
    "mountain": "#7C838C",        # blue-grey mountain
    "mountain_dark": "#5A6068",
    "snow": "#ECEBE6",
    "forest": "#3E5E3A",
    "forest_dark": "#2C4430",
    "forest_light": "#5E7A44",
    "bamboo": "#6E8A4A",
    "trunk": "#4A3626",
    "sea_deep": "#1D3A52",        # deep teal-indigo
    "sea": "#2A5068",
    "sea_shallow": "#5E9A9A",     # bright coastal shallows
    "beach": "#CDBB8E",
    "river": "#4F86A8",           # clear blue ribbon
    "river_bank": "#3A6A88",      # 1 px darker bank line
    "lake": "#3F7290",
    "dirt": "#8E7552",
    "road": "#A8916A",
}


def hex_to_srgb(h):
    """'#RRGGBB' -> (r, g, b) floats in 0..1 (sRGB encoded)."""
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c):
    """sRGB-encoded component(s) -> linear. Accepts a float or a sequence."""
    if isinstance(c, (tuple, list)):
        return tuple(srgb_to_linear(x) for x in c)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    if isinstance(c, (tuple, list)):
        return tuple(linear_to_srgb(x) for x in c)
    c = max(0.0, c)
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _resolve(name_or_hex):
    if isinstance(name_or_hex, (tuple, list)):
        return tuple(name_or_hex[:3])
    s = str(name_or_hex)
    if not s.startswith("#"):
        for table in (MAT, UI, FACTION):
            if s in table:
                s = table[s]
                break
        else:
            raise KeyError("unknown colour token %r" % name_or_hex)
    return hex_to_srgb(s)


def srgb(name_or_hex):
    """Token name ('stone', 'Paper', 'IronBanner') or '#hex' or sRGB tuple -> sRGB float triple."""
    return _resolve(name_or_hex)


def lin(name_or_hex, scale=1.0):
    """Token/hex/sRGB tuple -> *linear* (r, g, b), optionally multiplied by ``scale``."""
    return tuple(srgb_to_linear(x) * scale for x in _resolve(name_or_hex))


def lin4(name_or_hex, alpha=1.0, scale=1.0):
    """Like :func:`lin` but returns RGBA (what Blender colour sockets expect)."""
    return lin(name_or_hex, scale) + (alpha,)


def srgb8(name_or_hex, alpha=None):
    """Token -> (R, G, B[, A]) bytes for Pillow."""
    rgb = tuple(int(round(x * 255)) for x in _resolve(name_or_hex))
    return rgb if alpha is None else rgb + (int(alpha),)


def mix(a, b, t):
    """Mix two tokens in *linear* space; returns a linear triple."""
    la, lb = lin(a), lin(b)
    return tuple(x + (y - x) * t for x, y in zip(la, lb))


def table_markdown():
    """Markdown table of every token in sRGB hex and linear floats (used to build STYLE.md)."""
    rows = ["| Group | Token | sRGB | Linear |", "|---|---|---|---|"]
    for gname, table in (("UI", UI), ("Faction", FACTION), ("Material", MAT)):
        for k, v in table.items():
            l3 = lin(v)
            rows.append("| %s | %s | `%s` | %.3f, %.3f, %.3f |" % (gname, k, v.upper(), *l3))
    return "\n".join(rows)

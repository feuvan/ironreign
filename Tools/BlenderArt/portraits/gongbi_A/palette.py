"""Gongbi mineral / plant pigments (sRGB hex) and helpers.

Mineral colours (石色) are opaque and slightly chalky; plant colours (水色) are transparent glazes.
The names follow the traditional pigment names so a spec reads like a painter's palette.
"""

P = {
    # grounds
    "silk": "#DCCAA4",          # aged warm silk
    "silk_dark": "#C9AE7E",
    "silk_light": "#ECDDBB",
    # inks
    "ink": "#1C1916",            # 焦墨 scorched ink
    "ink_dense": "#2A2520",      # 浓墨
    "ink_mid": "#55504A",        # 中墨
    "ink_light": "#8A847A",      # 淡墨
    "ink_ochre": "#4E2F22",      # 赭墨 ochre-ink: face lines
    "ink_rouge": "#7A2E2A",      # 胭脂墨: lip lines
    # skin (washes)
    "skin_ivory": "#F3E1CC",     # ladies, youths
    "skin_peach": "#EED3B8",     # scholars
    "skin_warm": "#E6C3A0",      # officers
    "skin_bronze": "#D9B08A",    # weathered warriors (warm ochre, never orange)
    "skin_old": "#E8CDB2",
    "rouge": "#D9776E",          # 胭脂 cheek rouge (diluted)
    "rouge_lip": "#B8332F",      # 朱/胭脂 lips
    "rouge_lip_m": "#A9524A",    # men's lips: muted
    "ochre": "#A0643E",          # 赭石
    "ochre_light": "#C89A6C",
    # minerals
    "cinnabar": "#B8371F",       # 朱砂
    "vermilion": "#D0533A",      # 朱膘
    "carmine": "#9A2433",        # 胭脂 deep
    "azurite": "#2C4F8C",        # 头青
    "azurite2": "#4F78AD",       # 二青
    "azurite3": "#8DAAC8",       # 三青
    "malachite": "#2F7457",      # 头绿
    "malachite2": "#4E9576",     # 二绿
    "malachite3": "#97C3A6",     # 三绿
    "indigo": "#34485A",         # 花青
    "gamboge": "#D9AE45",        # 藤黄
    "ochre_gold": "#B8893C",
    "gold": "#C9A040",           # 泥金
    "gold_light": "#E6C978",
    "lead_white": "#F2EDE1",     # 蛤粉
    "pearl": "#E4DED0",
    "iron": "#5A6068",           # armour iron (ink + azurite grey)
    "iron_light": "#8E959C",
    "bronze": "#8C6A3C",
    "leather": "#6E4630",
    "purple": "#6A4A78",         # 紫 (ochre + indigo + rouge)
    "plum": "#7A3550",
    "teal": "#2F6A6E",
    "hair": "#1E1C1B",
    "hair_grey": "#8C8780",
    "hair_white": "#E9E6DE",
    "eye_white": "#F4EFE4",
    "iris": "#2A1F1A",
}


def hex_rgb(h):
    h = P.get(h, h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def lin(c):
    """sRGB (hex/name/tuple 0..1) -> scene linear RGBA."""
    if isinstance(c, str):
        c = hex_rgb(c)

    def f(x):
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return (f(c[0]), f(c[1]), f(c[2]), 1.0)


def mix(a, b, t):
    a = hex_rgb(a) if isinstance(a, str) else a
    b = hex_rgb(b) if isinstance(b, str) else b
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def scale(a, k):
    a = hex_rgb(a) if isinstance(a, str) else a
    return tuple(min(1.0, x * k) for x in a)

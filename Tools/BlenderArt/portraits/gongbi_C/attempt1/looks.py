"""Palette for the gongbi_C portraits (pure python: usable in Blender and in system python3).

Mineral pigments from DESIGN.md section 8 plus the mixed tones a gongbi painter makes from them.
Colours are sRGB hex *as painted on the reference silk* (#E6D6B0).
"""

PAL = {
    # ground and ink
    "silk": "#E6D6B0", "silk_edge": "#D8C39A", "ink": "#1E1A16", "ink_warm": "#3A2A20",
    "ink_brown": "#4E3426", "ink_grey": "#6E665C", "ink_wash": "#4A443C",
    # minerals (DESIGN.md)
    "malachite": "#3E8E6E", "malachite_l": "#8CBFA0", "azurite": "#2B5C8A", "azurite_l": "#7FA6C8",
    "cinnabar": "#B5382A", "vermilion": "#D0643C", "ochre": "#A0643A", "rouge": "#9E3B4A",
    "gold": "#C9A24B", "white": "#F0E8D8",
    # mixed tones
    "gold_l": "#E0C47E", "gold_d": "#9A7A34", "cinnabar_d": "#7E2418", "rouge_l": "#C77D84",
    "malachite_d": "#2A6A52", "azurite_d": "#1E4468", "indigo": "#2E3F5C", "indigo_d": "#1E2838",
    "teal": "#2F6A6A", "ochre_l": "#C9A274", "ochre_d": "#7A4A2A", "umber": "#5A4030",
    "iron": "#5E6670", "iron_l": "#8E98A0", "iron_d": "#363C44", "steel_blue": "#4E6478",
    "jade": "#7FB09A", "pearl": "#F4EEE2", "lacquer": "#7E1F17", "plum": "#6E3A52",
    "lotus": "#E7B9B0", "pine": "#3A5A48", "sand": "#CDB88E", "brown": "#6E4A32",
    "hair": "#24201C", "hair_l": "#4A4440", "hair_grey": "#8A857E", "hair_white": "#ECE6DA",
}

#: skin washes (light, deep) - warm ivory / peach; deeper warm ochre for weathered men.  Never
#: yellow, grey or orange: every tone keeps a little rouge in it.
SKIN = {
    "ivory": ("#F3E3CF", "#E2BFA2"),      # court ladies
    "peach": ("#F0DAC2", "#DDB394"),      # young men, scholars
    "warm": ("#EACDB0", "#D2A584"),       # officers
    "weathered": ("#E2BE9C", "#C08D6C"),  # warriors, outdoorsmen
    "elder": ("#ECD6BE", "#D1AE92"),      # old men (paler, thinner wash)
    "bronze": ("#DDB592", "#B88262"),     # steppe riders, sailors
}


def _hex(c):
    c = PAL.get(c, c)
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb(c):
    """token / '#hex' / sRGB tuple -> sRGB float triple"""
    if isinstance(c, str):
        return _hex(c)
    return tuple(float(x) for x in c[:3])


def _to_lin(x):
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def lin(c):
    """token / '#hex' / sRGB tuple -> linear RGB tuple (for emission sockets)"""
    return tuple(_to_lin(v) for v in srgb(c))


def mix(a, b, t):
    a, b = srgb(a), srgb(b)
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def deepen(c, k):
    """k < 1 darkens towards a warm ink, k > 1 lightens towards lead white"""
    c = srgb(c)
    if k <= 1.0:
        ink = srgb(PAL["ink_warm"])
        t = 1.0 - k
        return tuple(x + (y - x) * t for x, y in zip(c, ink))
    w = srgb(PAL["white"])
    t = min(1.0, k - 1.0)
    return tuple(x + (y - x) * t for x, y in zip(c, w))

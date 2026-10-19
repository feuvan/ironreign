"""gongbi_C palette: mineral pigments, ink tones, skin washes (sRGB hex, as painted on silk).

Pure python (used by Blender and by the 2D stage).  Pigment names follow the studio palette of
``ironart.scenes_gongbi.PAL`` with the extra tones a figure painter needs.
"""

PAL = {
    # ground and ink
    "silk": "#E6D6B0", "silk_l": "#EEE2C4", "ink": "#1E1A16", "ink_d": "#141110",
    "ink_grey": "#6E665C", "ink_grey_l": "#A79E8E", "ink_wash": "#4A443C",
    "skin_line": "#6A4434", "lip_line": "#7A2E2A",
    # mineral colours (石色) and dyes (水色)
    "cinnabar": "#B5382A", "cinnabar_d": "#8A2A20", "cinnabar_l": "#D27A62",
    "vermilion": "#D0643C", "rouge": "#C0505A", "rouge_d": "#9E3B4A", "peach": "#E8A090",
    "malachite": "#3E8E6E", "malachite_l": "#8CBFA0", "malachite_d": "#2A6A52",
    "azurite": "#2B5C8A", "azurite_l": "#7FA6C8", "azurite_d": "#1E4468",
    "indigo": "#2E3F5C", "indigo_d": "#1E2838", "teal": "#2F6A6A", "teal_l": "#7AA8A0",
    "ochre": "#A0643A", "ochre_l": "#C9A274", "ochre_d": "#7A4A2A",
    "gold": "#C9A24B", "gold_l": "#E2C67E", "gold_d": "#94742E",
    "white": "#F2ECDE", "pearl": "#F6F1E6", "lead_white": "#EDE6D6",
    "plum": "#7A3A52", "plum_l": "#B07890", "lotus": "#D88A92", "lotus_l": "#EDBFBF",
    "steel": "#5F6C78", "steel_l": "#8E9AA4", "steel_d": "#3A444E", "iron": "#4A4E52",
    "bronze": "#8A6A3A", "leather": "#7A4E30", "leather_d": "#553420",
    "jade": "#6FA38A", "moon": "#C8D2D2", "straw": "#C8AA6E", "umber": "#5A4030",
    "hair": "#24201C", "hair_l": "#4A4440", "grey_hair": "#8E8A84", "white_hair": "#E8E4DA",
}

#: skin washes (light facing the viewer, deep towards the contour) - warm ivory / peach /
#: weathered ochre; never yellow, grey or orange
SKIN = {
    "ivory":     ("#F5E6D6", "#E6C4AE"),   # court ladies
    "fair":      ("#F2E0CC", "#DDBA9E"),   # young men, scholars
    "warm":      ("#EED8C0", "#D6AE8C"),   # most men
    "weathered": ("#E8CDB0", "#C99B78"),   # field warriors
    "bronzed":   ("#E2C3A2", "#BE8E6C"),   # steppe riders, sailors
    "elder":     ("#F0DDCA", "#D8B49A"),   # old men and women
}


def _hex(c):
    c = PAL.get(c, c)
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def hexof(c):
    c = PAL.get(c, c)
    return c if c.startswith("#") else "#" + c


def srgb(c):
    if isinstance(c, (tuple, list)):
        return tuple(float(v) for v in c[:3])
    return _hex(c)


def _to_lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def lin(c):
    return tuple(_to_lin(v) for v in srgb(c))


def lin4(c, a=1.0):
    return lin(c) + (a,)


def mix(a, b, t):
    A, B = srgb(a), srgb(b)
    return tuple(A[i] * (1 - t) + B[i] * t for i in range(3))


def deepen(c, k=0.7, warm=0.03):
    """Deeper tone of a colour (multiplied, a touch warmer) - the 分染 shade of a wash."""
    r, g, b = srgb(c)
    return (r * k * (1 + warm), g * k, b * k * (1 - warm))


def lighten(c, t=0.5):
    return mix(c, "pearl", t)


def to_hex(c):
    r, g, b = srgb(c)
    return "#%02X%02X%02X" % tuple(int(round(max(0, min(1, v)) * 255)) for v in (r, g, b))

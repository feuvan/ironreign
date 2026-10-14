"""Gongbi mineral / vegetable pigment palette (sRGB hex, as mixed on aged silk).

Names follow the painter's box: 墨 ink, 赭石 ochre, 朱砂/朱膘 cinnabar, 胭脂 rouge, 石青 azurite,
石绿 malachite, 花青 indigo, 蛤粉 shell white, 泥金 gold.  Skin tones are 粉 + 赭 + 胭脂 mixes:
warm ivory / peach, never yellow, grey or orange.
"""

import numpy as np

P = {
    # inks
    "ink": "#1d1814",          # 焦墨 burnt ink, the line colour
    "ink_d": "#2a231d",        # 浓墨
    "ink_m": "#4e463f",        # 重墨 (greyed)
    "ink_l": "#857c72",        # 淡墨
    "ink_brown": "#5a3326",    # 赭墨 face line ink (ochre + ink)
    "ink_rouge": "#6e2a26",    # 胭脂墨 lip line
    # silk
    "silk": "#d9c6a0",
    "silk_d": "#b9a074",
    # skin (粉 / 赭 / 胭脂)
    "skin_ivory": "#f5e4d3",
    "skin_peach": "#f0d6c0",
    "skin_warm": "#e7c3a5",
    "skin_bronze": "#d8ab8a",
    "skin_elder": "#ecd3bd",
    "ochre": "#a4643f",        # 赭石 shading wash
    "ochre_l": "#c98b62",
    "rouge": "#c0505a",        # 胭脂
    "rouge_d": "#93303c",
    "lip": "#bd3f45",
    "lip_l": "#d77a76",
    "white": "#f6f1e6",        # 蛤粉 shell white
    "eye_white": "#f4efe6",
    "iris": "#2b1d16",
    # minerals
    "cinnabar": "#b5372a",     # 朱砂
    "cinnabar_l": "#d0684e",   # 朱膘
    "vermilion": "#c4442c",
    "carmine": "#8f2430",      # 胭脂红 deep
    "azurite": "#2f5a8c",      # 石青 (头青)
    "azurite_l": "#5f88b4",    # 二青
    "azurite_p": "#9db8cf",    # 三青
    "malachite": "#2f7a62",    # 石绿 (头绿)
    "malachite_l": "#5c9f83",  # 二绿
    "malachite_p": "#9cc4ab",  # 三绿
    "indigo": "#2c3e55",       # 花青
    "indigo_l": "#5b6f86",
    "gold": "#c79b45",         # 泥金
    "gold_l": "#e6c77a",
    "gold_d": "#8a6326",
    "ochre_robe": "#b98546",
    "cream": "#efe3c8",
    "tea": "#8a6a45",
    "purple": "#5d3a5e",       # 紫 (cinnabar + indigo)
    "purple_l": "#8c6a8e",
    "iron": "#5a6470",         # armour iron (花青+墨)
    "iron_l": "#8d99a6",
    "iron_d": "#363d46",
    "leather": "#6d4630",
    "hair": "#211c19",
    "hair_grey": "#8d8781",
    "hair_white": "#eeeae2",
}


def srgb(c):
    if isinstance(c, str):
        h = P.get(c, c).lstrip("#")
        return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return np.asarray(c, float)[:3]


def _to_lin(x):
    x = np.asarray(x, float)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin(c):
    return _to_lin(srgb(c))


def lin_arr(a):
    return _to_lin(np.clip(np.asarray(a, float), 0, 1))


def mix(a, b, t):
    return srgb(a) * (1 - t) + srgb(b) * t


def hexs(rgb):
    r = np.clip(np.asarray(rgb, float), 0, 1)
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in r)
